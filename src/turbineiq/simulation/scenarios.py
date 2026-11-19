"""A seeded bank of operating scenarios with known injected faults (ground truth).

The bank is the test set for the estimation and detection work of roadmap WP4 and the
prescription work of WP5: each scenario is a session configuration plus a timed command
script, so it can be regenerated bit-for-bit (same machine and Python build) and every
fault's type, size and onset time is known exactly. Clean scenarios are included so false
alarms can be counted, and some faults are chosen to look alike (a compressor discharge
temperature sensor bias that mimics fouling, a power transducer bias that mimics an
output loss) so that a detector has to separate sensor faults from component faults.

Degradation rates are accelerated (percent per hour rather than per month) so that a
scenario fits in about two simulated hours. That is a stated simplification: it tests
whether an estimator can follow a trend, not whether it can follow one at a realistic
rate through months of noise and ambient change.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .plant import PlantParameters
from .session import Session, SessionConfig, _validate_params

GROUND_TRUTH_COMMANDS = frozenset(
    {
        "inject_degradation",
        "inject_sensor_fault",
        "set_fuel_valve_lag",
        "clear_fault",
        "wash_compressor",
    }
)
_DEFAULT_VALVE_LAG_S = PlantParameters().valve_lag_s
ONSET_S = 1800.0  # faults start after 30 minutes of healthy operation
LOAD_AT_S = 300.0  # the unit synchronises at about 236 s after a start


@dataclass(frozen=True)
class ScriptStep:
    t_s: float
    command: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"t_s": self.t_s, "command": self.command, "params": dict(self.params)}


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str  # baseline, degradation, sensor, actuator or maintenance
    description: str
    seed: int
    duration_s: float
    script: tuple[ScriptStep, ...]
    ambient_temperature_c: float = 15.0
    record_interval_s: float = 1.0

    def config(self) -> SessionConfig:
        return SessionConfig(
            seed=self.seed,
            ambient_temperature_c=self.ambient_temperature_c,
            record_interval_s=self.record_interval_s,
        )

    def fault_events(self) -> list[dict[str, Any]]:
        """The ground-truth fault timeline: every fault command with its time."""

        return [step.to_dict() for step in self.script if step.command in GROUND_TRUTH_COMMANDS]


def _start(load_mw: float, ramp: float = 60.0) -> list[ScriptStep]:
    return [
        ScriptStep(0.0, "start"),
        ScriptStep(LOAD_AT_S, "set_load", {"mw": load_mw, "ramp_mw_per_min": ramp}),
    ]


def _load(t_s: float, mw: float, ramp: float = 60.0) -> ScriptStep:
    return ScriptStep(t_s, "set_load", {"mw": mw, "ramp_mw_per_min": ramp})


def _degrade(t_s: float, kind: str, severity: float, rate: float | None = None) -> ScriptStep:
    return ScriptStep(
        t_s,
        "inject_degradation",
        {"kind": kind, "severity_pct": severity, "rate_pct_per_h": rate},
    )


def _sensor(t_s: float, channel: str, mode: str, magnitude: float | None) -> ScriptStep:
    return ScriptStep(
        t_s, "inject_sensor_fault", {"channel": channel, "mode": mode, "magnitude": magnitude}
    )


def _ambient(t_s: float, temperature_c: float) -> ScriptStep:
    return ScriptStep(t_s, "set_ambient", {"temperature_c": temperature_c})


_AMBIENT_SWING = (_ambient(2400.0, 20.0), _ambient(3600.0, 25.0), _ambient(4800.0, 18.0),
                  _ambient(6000.0, 10.0))  # fmt: skip
_FAST_STEPS = (_load(2400.0, 40.0, 120.0), _load(3600.0, 30.0, 120.0),
               _load(4800.0, 42.0, 120.0))  # fmt: skip
_TWO_HOURS = 7200.0

SCENARIOS: tuple[Scenario, ...] = (
    # ------------------------------------------------------------- healthy references
    Scenario(
        "clean_part_load",
        "baseline",
        "Healthy unit held at 35 MW for two hours. Reference for false alarms.",
        101,
        _TWO_HOURS,
        tuple(_start(35.0)),
    ),
    Scenario(
        "clean_base_load",
        "baseline",
        "Healthy unit asked for 47 MW, so it runs on the exhaust temperature limit.",
        102,
        _TWO_HOURS,
        tuple(_start(47.0)),
    ),
    Scenario(
        "clean_load_cycling",
        "baseline",
        "Healthy unit stepping between 25 and 45 MW every 20 minutes.",
        103,
        _TWO_HOURS,
        (
            *_start(30.0),
            _load(1500.0, 40.0),
            _load(2700.0, 25.0),
            _load(3900.0, 45.0),
            _load(5100.0, 35.0),
        ),
    ),
    Scenario(
        "clean_ambient_swing",
        "baseline",
        "Healthy unit at 35 MW while the ambient steps 15, 20, 25, 18, 10 C (a confounder).",
        104,
        _TWO_HOURS,
        (*_start(35.0), *_AMBIENT_SWING),
    ),
    Scenario(
        "clean_fast_load_steps",
        "baseline",
        "Healthy unit with fast (120 MW/min) load steps; the reference for the slow valve.",
        105,
        _TWO_HOURS,
        (*_start(30.0), *_FAST_STEPS),
    ),
    # ------------------------------------------------------------- component degradation
    Scenario(
        "fouling_step_part_load",
        "degradation",
        "3 percent compressor fouling appears at 30 minutes; load held at 35 MW.",
        201,
        _TWO_HOURS,
        (*_start(35.0), _degrade(ONSET_S, "compressor_fouling", 3.0)),
    ),
    Scenario(
        "fouling_progressive_base_load",
        "degradation",
        "Compressor fouling grows at 3 percent per hour (accelerated) from 30 minutes, "
        "on the temperature limit, so output falls.",
        202,
        _TWO_HOURS,
        (*_start(47.0), _degrade(ONSET_S, "compressor_fouling", 0.0, 3.0)),
    ),
    Scenario(
        "fouling_progressive_ambient_swing",
        "degradation",
        "Fouling growing at 2 percent per hour while the ambient steps; the trend must be "
        "separated from the ambient effect.",
        203,
        _TWO_HOURS,
        (*_start(35.0), _degrade(ONSET_S, "compressor_fouling", 0.0, 2.0), *_AMBIENT_SWING),
    ),
    Scenario(
        "erosion_step_part_load",
        "degradation",
        "Turbine erosion of 1.5 efficiency points appears at 30 minutes; load held at 35 MW.",
        204,
        _TWO_HOURS,
        (*_start(35.0), _degrade(ONSET_S, "turbine_erosion", 1.5)),
    ),
    Scenario(
        "fouling_then_erosion",
        "degradation",
        "2 percent fouling at 30 minutes, then 1 point of turbine erosion at 60 minutes.",
        205,
        _TWO_HOURS,
        (
            *_start(35.0),
            _degrade(ONSET_S, "compressor_fouling", 2.0),
            _degrade(3600.0, "turbine_erosion", 1.0),
        ),
    ),
    # ------------------------------------------------------------- maintenance
    Scenario(
        "fouled_unit_offline_wash",
        "maintenance",
        "A unit with 3 percent fouling runs at 40 MW, is stopped at 30 minutes, washed at "
        "standstill and restarted to 40 MW.",
        301,
        9000.0,
        (
            _degrade(0.0, "compressor_fouling", 3.0),
            *_start(40.0),
            ScriptStep(ONSET_S, "stop"),
            ScriptStep(3600.0, "wash_compressor"),
            ScriptStep(3660.0, "start"),
            _load(3960.0, 40.0),
        ),
    ),
    # ------------------------------------------------------------- sensor faults
    Scenario(
        "exhaust_tc_drift_base_load",
        "sensor",
        "Exhaust thermocouple drifts down 10 K per hour from 30 minutes on the temperature "
        "limit, so the control overfires the true exhaust.",
        401,
        _TWO_HOURS,
        (*_start(47.0), _sensor(ONSET_S, "exhaust_temperature", "drift", -10.0)),
    ),
    Scenario(
        "exhaust_tc_stuck_load_increase",
        "sensor",
        "Exhaust thermocouple sticks at 35 MW; load is raised to 47 MW 10 minutes later and "
        "the temperature control cannot see the limit.",
        402,
        _TWO_HOURS,
        (
            *_start(35.0),
            _sensor(ONSET_S, "exhaust_temperature", "stuck", None),
            _load(2400.0, 47.0),
        ),
    ),
    Scenario(
        "exhaust_tc_noise",
        "sensor",
        "Exhaust thermocouple noise of 3 K (sigma) from 30 minutes at 35 MW.",
        403,
        _TWO_HOURS,
        (*_start(35.0), _sensor(ONSET_S, "exhaust_temperature", "noise", 3.0)),
    ),
    Scenario(
        "power_transducer_bias",
        "sensor",
        "The power transducer reads 1 MW high from 30 minutes; the plant itself is healthy.",
        404,
        _TWO_HOURS,
        (*_start(35.0), _sensor(ONSET_S, "electrical_power", "bias", 1.0)),
    ),
    Scenario(
        "fuel_meter_drift",
        "sensor",
        "The fuel flow meter drifts up 0.06 kg/s per hour (about 3 percent per hour) from "
        "30 minutes; the plant is healthy.",
        405,
        _TWO_HOURS,
        (*_start(35.0), _sensor(ONSET_S, "fuel_flow", "drift", 0.06)),
    ),
    Scenario(
        "cdt_sensor_bias",
        "sensor",
        "Compressor discharge temperature reads 9 K high from 30 minutes, about what 3 "
        "percent fouling does to the true value; the plant is healthy.",
        406,
        _TWO_HOURS,
        (*_start(35.0), _sensor(ONSET_S, "compressor_discharge_temperature", "bias", 9.0)),
    ),
    # ------------------------------------------------------------- actuator
    Scenario(
        "slow_fuel_valve_load_steps",
        "actuator",
        "Fuel valve lag rises from 0.05 to 2.5 s at 30 minutes; same fast load steps as "
        "clean_fast_load_steps.",
        501,
        _TWO_HOURS,
        (
            *_start(30.0),
            ScriptStep(ONSET_S, "set_fuel_valve_lag", {"tau_s": 2.5}),
            *_FAST_STEPS,
        ),
    ),
)


def scenario(scenario_id: str) -> Scenario:
    for item in SCENARIOS:
        if item.id == scenario_id:
            return item
    raise KeyError(scenario_id)


def check_script(item: Scenario) -> None:
    """Static checks: commands and parameters are well formed and times are in order."""

    last = -1.0
    for step in item.script:
        _validate_params(step.command, dict(step.params))
        if step.t_s < last or not 0.0 <= step.t_s < item.duration_s:
            raise ValueError(f"{item.id}: script times must be ordered and within the run")
        last = step.t_s


def run_scenario(item: Scenario, until_s: float | None = None) -> Session:
    """Run a scenario (optionally only up to ``until_s``) and return the session.

    A command the plant refuses raises, because a scenario whose script does not apply
    would silently lose its ground truth.
    """

    check_script(item)
    end_s = item.duration_s if until_s is None else min(until_s, item.duration_s)
    session = Session(item.config())
    for step in item.script:
        if step.t_s > end_s:
            break
        session.advance(round(step.t_s / session.dt) - session.step_count)
        session.apply(step.command, dict(step.params))
    session.advance(round(end_s / session.dt) - session.step_count)
    return session


def trace_rows(session: Session) -> Iterable[dict[str, Any]]:
    """Flatten the recorded history into rows: measured values, then ground truth."""

    for snap in session.history:
        measured = snap["measured"]
        truth = snap["injected_faults"]
        health = truth["health"]
        yield {
            "t_s": snap["t_s"],
            "state": snap["state"],
            "breaker_closed": snap["breaker_closed"],
            "load_setpoint_mw": snap["load_setpoint_mw"],
            "ambient_temperature_c": snap["ambient_temperature_c"],
            "igv_position": snap["igv_position"],
            "meas_electrical_power_mw": measured["electrical_power_mw"],
            "meas_exhaust_temperature_k": measured["exhaust_temperature_k"],
            "meas_speed_pu": measured["speed_pu"],
            "meas_compressor_discharge_temperature_k": measured[
                "compressor_discharge_temperature_k"
            ],
            "meas_compressor_discharge_pressure_kpa": measured["compressor_discharge_pressure_kpa"],
            "meas_fuel_flow_kg_s": measured["fuel_flow_kg_s"],
            "true_electrical_power_mw": snap["electrical_power_mw"],
            "true_exhaust_temperature_k": snap["exhaust_temperature_k"],
            "true_fuel_flow_kg_s": snap["fuel_flow_kg_s"],
            "true_compressor_discharge_temperature_k": snap["compressor_discharge_temperature_k"],
            "true_compressor_flow_capacity_delta": health["compressor_flow_capacity_delta"],
            "true_compressor_efficiency_delta": health["compressor_efficiency_delta"],
            "true_turbine_efficiency_delta": health["turbine_efficiency_delta"],
            "true_sensor_faults": ";".join(
                f"{channel}:{fault['mode']}" for channel, fault in truth["sensors"].items()
            ),
            "true_fuel_valve_lag_s": truth["fuel_valve_lag_s"] or _DEFAULT_VALVE_LAG_S,
            "limiter": snap["limiter"],
            "trip_cause": snap["trip_cause"] or "",
        }
