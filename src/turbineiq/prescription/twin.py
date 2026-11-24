"""The predictive twin used for what-if runs: the plant's dynamics on the twin's own engine.

A forward run must not read the plant's hidden truth. :func:`predictive_twin` therefore
builds a :class:`TwinPlant` from three sources, and only these:

* **Control-system state** copied from the plant: unit state and timers, breaker, setpoints,
  ramp rate, IGV mode and position, governor/temperature/acceleration controller states,
  limits. A real control system knows all of these.
* **The twin's engine model**: maps of a perturbed copy of the calibrated engine (by default
  the WP4 ``combined`` mismatch), at the twin's estimated health, not the plant's.
* **Measurements**: fuel flow and speed; the exhaust temperature is the twin's own steady
  value at that fuel flow, so a failed thermocouple cannot poison the forward run.

Injected faults (degradation, sensor faults, a slow fuel valve) are not copied: the twin
knows only what its health estimate says. The twin is then settled for a short time so its
controllers re-balance on its own engine before a candidate is applied.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from turbineiq.engineering import RealGasInputs
from turbineiq.simulation.faults import FaultState
from turbineiq.simulation.maps import Health, HealthMaps, engine_health_maps, igv_air_factor
from turbineiq.simulation.plant import CommandError, GasTurbinePlant, UnitState

SETTLE_S = 30.0


class TwinPlant(GasTurbinePlant):
    """A :class:`GasTurbinePlant` whose physics are the twin's engine at a given health."""

    twin_maps: HealthMaps
    twin_health: Health

    def _lookup(self, n: float, air_factor: float, fuel_pu: float) -> tuple[float, float]:
        return self.twin_maps.lookup(self.twin_health, n, air_factor, fuel_pu)

    def compressor_discharge(self) -> tuple[float, float]:
        return self.twin_maps.compressor_discharge(self.twin_health, self.n, self._air_factor())


def predictive_twin(
    plant: GasTurbinePlant,
    engine: RealGasInputs,
    health: Health,
    *,
    fuel_kg_s: float,
    speed_pu: float,
    settle_s: float = SETTLE_S,
) -> TwinPlant:
    """A twin of ``plant`` initialised from control state and measurements (see module doc)."""

    state = {k: v for k, v in plant.__dict__.items() if k not in ("faults", "maps", "_health_maps")}
    twin = TwinPlant.__new__(TwinPlant)
    twin.__dict__.update(copy.deepcopy(state))
    twin.faults = FaultState(0)
    twin._health_maps = None
    twin.twin_health = Health(*(float(h) for h in health))
    twin.twin_maps = engine_health_maps(engine, plant.maps.ambient_temperature_c)
    clean = twin.twin_maps.clean
    twin.maps = clean
    twin._fsnl_fuel = clean.fuel_for_power(0.0)
    twin._rated_fuel = clean.fuel_for_power(1.0)
    twin.droop_gain = (twin._rated_fuel - twin._fsnl_fuel) / twin.p.droop
    # Limits are control-system settings: keep the plant's, not the twin engine's rating.
    twin.temperature_limit_k = plant.temperature_limit_k
    twin.trip_temperature_k = plant.trip_temperature_k
    twin.exhaust_feedback_source = "thermocouple"
    twin.exhaust_substitute_k = None
    # Physical states from measurements; exhaust from the twin itself at that fuel flow.
    fuel_pu = max(0.0, fuel_kg_s / clean.rated_fuel_kg_s)
    twin.n = speed_pu
    twin.v = twin.wf = twin.wfc = fuel_pu
    _, exhaust_k = twin._lookup(twin.n, igv_air_factor(twin.igv), fuel_pu)
    twin.tx = twin.tm = exhaust_k
    twin._update_readings()
    _run(twin, settle_s)
    return twin


def _run(plant: GasTurbinePlant, seconds: float) -> None:
    for _ in range(round(seconds / plant.p.dt_s)):
        plant.step()


@dataclass(frozen=True)
class ForwardResult:
    """Summary of a forward run of the twin (true twin values, no sensor noise)."""

    horizon_s: float
    tripped: bool
    trip_cause: str | None
    end_state: str
    max_exhaust_k: float
    end_exhaust_k: float
    end_power_mw: float
    end_fuel_kg_s: float
    end_heat_rate_kj_per_kwh: float | None
    min_speed_pu: float
    max_speed_pu: float
    end_limiter: str
    temperature_limit_k: float
    trip_temperature_k: float

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def apply_to_twin(twin: GasTurbinePlant, command: str, params: dict[str, Any]) -> None:
    """Apply a supervisory command to a twin. Only the commands the layer itself sends."""

    if command == "set_load":
        twin.command_set_load(float(params["mw"]), params.get("ramp_mw_per_min"))
    elif command == "set_igv":
        position = params.get("position")
        twin.command_set_igv(str(params["mode"]), None if position is None else float(position))
    elif command == "set_exhaust_feedback":
        # The twin has a healthy thermocouple of its own; a substitute changes nothing in it.
        return
    else:
        raise CommandError(f"the twin cannot run {command!r} forward")


def forward_run(
    twin: GasTurbinePlant, actions: list[dict[str, Any]], horizon_s: float
) -> ForwardResult:
    """Apply ``actions`` to a copy of ``twin`` and simulate ``horizon_s`` seconds."""

    sim = copy.deepcopy(twin)
    for action in actions:
        apply_to_twin(sim, action["command"], dict(action.get("params", {})))
    dt = sim.p.dt_s
    max_exhaust = sim.tm
    min_speed = max_speed = sim.n
    for _ in range(round(horizon_s / dt)):
        sim.step()
        max_exhaust = max(max_exhaust, sim.tm)
        min_speed = min(min_speed, sim.n)
        max_speed = max(max_speed, sim.n)
    maps = sim.maps
    power = sim.electrical_power_mw()
    fuel = sim.wfc * maps.rated_fuel_kg_s
    heat_rate = None
    if power > 0.05 * maps.rated_electrical_power_mw:
        heat_rate = fuel * maps.fuel_lhv_kj_kg * 3600.0 / (power * 1000.0)
    return ForwardResult(
        horizon_s=horizon_s,
        tripped=sim.state == UnitState.TRIPPED,
        trip_cause=sim.trip_cause,
        end_state=sim.state.value,
        max_exhaust_k=max_exhaust,
        end_exhaust_k=sim.tm,
        end_power_mw=power,
        end_fuel_kg_s=fuel,
        end_heat_rate_kj_per_kwh=heat_rate,
        min_speed_pu=min_speed,
        max_speed_pu=max_speed,
        end_limiter=sim.limiter,
        temperature_limit_k=sim.temperature_limit_k,
        trip_temperature_k=sim.trip_temperature_k,
    )
