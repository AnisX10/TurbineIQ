"""Injected faults for the simulated plant: degradation, sensor faults and a slow fuel valve.

This is the fault-injection layer of roadmap WP3. It creates the ground truth that the
estimation work of WP4 is tested against, so everything here is deterministic given the
session seed and the event log.

Three kinds of fault:

* **Gas-path degradation** changes the plant physics through the health deltas of
  :class:`~turbineiq.simulation.maps.Health`. *Compressor fouling* of severity ``s``
  percent removes ``s`` percent of compressor flow capacity and ``s / 2`` points of
  compressor polytropic efficiency (a 2:1 flow-to-efficiency ratio, a common assumption in
  gas-path analysis studies and labelled here as an assumption). *Turbine erosion* of
  severity ``s`` removes ``s`` points of turbine polytropic efficiency; the flow-capacity
  increase that erosion also causes is not modelled because the cycle model does not treat
  the turbine as choked. Both can grow at a set rate while air flows through the machine.
* **Sensor faults** change what an instrument reports, not the plant: ``bias`` (constant
  offset), ``drift`` (offset growing linearly in time), ``stuck`` (frozen at the reading
  when the fault started) and ``noise`` (extra Gaussian noise). The exhaust thermocouple
  reading is also what the temperature control and the over-temperature protection use,
  so a fault there acts on the plant through the controller, as it would on a real unit.
  The other channels are monitoring channels only: the governor and the overspeed
  protection in this model use the true speed (real units vote redundant pickups).
* **Fuel valve lag**: a slower valve positioner (a sticky or degraded valve).

All magnitudes and ranges are illustrative choices for a simulator, not OEM data.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from .maps import CLEAN, Health

#: Share of the fouling severity (flow-capacity loss, percent) lost as compressor
#: polytropic efficiency points. Assumed 2:1 flow-to-efficiency, see the module docstring.
FOULING_EFFICIENCY_RATIO = 0.5

DEGRADATIONS: dict[str, float] = {
    "compressor_fouling": 10.0,  # maximum severity, percent of flow capacity
    "turbine_erosion": 5.0,  # maximum severity, points of turbine polytropic efficiency
}
MAX_DEGRADATION_RATE_PCT_PER_H = 10.0


@dataclass(frozen=True)
class Channel:
    unit: str
    limit: float  # largest allowed |bias|, |drift per hour| or noise sigma
    noise_abs: float  # baseline measurement noise (absolute part)
    noise_rel: float  # baseline measurement noise (relative part)


#: Instrument channels in a fixed order (the order of noise draws depends on it).
CHANNELS: dict[str, Channel] = {
    "electrical_power": Channel("MW", 10.0, 0.0, 0.002),
    "exhaust_temperature": Channel("K", 100.0, 0.5, 0.0),
    "speed": Channel("pu", 0.05, 0.0005, 0.0),
    "compressor_discharge_temperature": Channel("K", 50.0, 0.5, 0.0),
    "compressor_discharge_pressure": Channel("kPa", 100.0, 0.0, 0.002),
    "fuel_flow": Channel("kg/s", 0.5, 0.0, 0.005),
}
SENSOR_MODES = ("bias", "drift", "stuck", "noise")
FUEL_VALVE_LAG_RANGE_S = (0.05, 5.0)
CLEAR_TARGETS = ("all", *DEGRADATIONS, "fuel_valve", *CHANNELS)


class FaultError(ValueError):
    """A fault command with an invalid or inapplicable argument."""


@dataclass
class SensorFault:
    mode: str
    magnitude: float | None
    start_s: float
    stuck_value: float | None = None

    def read(self, true_value: float, t_s: float, rng: random.Random) -> float:
        if self.mode == "bias":
            return true_value + float(self.magnitude or 0.0)
        if self.mode == "drift":
            return true_value + float(self.magnitude or 0.0) * (t_s - self.start_s) / 3600.0
        if self.mode == "stuck":
            return float(self.stuck_value if self.stuck_value is not None else true_value)
        return true_value + float(self.magnitude or 0.0) * rng.gauss(0.0, 1.0)

    def to_dict(self, channel: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "mode": self.mode,
            "magnitude": self.magnitude,
            "unit": CHANNELS[channel].unit + ("/h" if self.mode == "drift" else ""),
            "since_s": round(self.start_s, 6),
        }
        if self.mode == "stuck":
            out["stuck_value"] = self.stuck_value
        return out


@dataclass
class Degradation:
    severity_pct: float = 0.0
    rate_pct_per_h: float = 0.0
    maximum_pct: float = 0.0

    @property
    def active(self) -> bool:
        return self.severity_pct > 0.0 or self.rate_pct_per_h > 0.0

    def grow(self, dt_s: float) -> bool:
        if self.rate_pct_per_h <= 0.0 or self.severity_pct >= self.maximum_pct:
            return False
        self.severity_pct = min(
            self.maximum_pct, self.severity_pct + self.rate_pct_per_h * dt_s / 3600.0
        )
        return True


class FaultState:
    """Active faults and their ground truth. Noise faults draw from their own seeded RNG."""

    def __init__(self, seed: int = 0) -> None:
        self.degradation = {
            name: Degradation(maximum_pct=limit) for name, limit in DEGRADATIONS.items()
        }
        self.sensors: dict[str, SensorFault] = {}
        self.fuel_valve_lag_s: float | None = None
        # A separate stream so that runs without noise faults are unaffected by it.
        self.rng = random.Random(seed * 2 + 1)
        self.health = CLEAN

    # ------------------------------------------------------------------ physics
    def _update_health(self) -> None:
        fouling = self.degradation["compressor_fouling"].severity_pct / 100.0
        erosion = self.degradation["turbine_erosion"].severity_pct / 100.0
        self.health = Health(
            compressor_flow=-fouling,
            compressor_efficiency=-FOULING_EFFICIENCY_RATIO * fouling,
            turbine_efficiency=-erosion,
        )

    def advance(self, dt_s: float, air_flowing: bool) -> None:
        if not air_flowing:
            return
        changed = False
        for item in self.degradation.values():
            changed |= item.grow(dt_s)
        if changed:
            self._update_health()

    # ------------------------------------------------------------------ commands
    def inject_degradation(self, kind: str, severity_pct: float, rate_pct_per_h: float) -> None:
        if kind not in DEGRADATIONS:
            raise FaultError(f"kind must be one of {', '.join(DEGRADATIONS)}")
        limit = DEGRADATIONS[kind]
        if not 0.0 <= severity_pct <= limit:
            raise FaultError(f"{kind} severity must be between 0 and {limit:g} percent")
        if not 0.0 <= rate_pct_per_h <= MAX_DEGRADATION_RATE_PCT_PER_H:
            raise FaultError(
                f"rate must be between 0 and {MAX_DEGRADATION_RATE_PCT_PER_H:g} percent per hour"
            )
        if severity_pct == 0.0 and rate_pct_per_h == 0.0:
            raise FaultError("give a severity or a growth rate above zero (use clear_fault)")
        item = self.degradation[kind]
        item.severity_pct = severity_pct
        item.rate_pct_per_h = rate_pct_per_h
        self._update_health()

    def inject_sensor_fault(
        self, channel: str, mode: str, magnitude: float | None, t_s: float, current: float
    ) -> None:
        if channel not in CHANNELS:
            raise FaultError(f"channel must be one of {', '.join(CHANNELS)}")
        if mode not in SENSOR_MODES:
            raise FaultError(f"mode must be one of {', '.join(SENSOR_MODES)}")
        spec = CHANNELS[channel]
        if mode == "stuck":
            if magnitude is not None:
                raise FaultError("a stuck sensor takes no magnitude; it freezes at its reading")
            self.sensors[channel] = SensorFault("stuck", None, t_s, stuck_value=current)
            return
        if magnitude is None or not math.isfinite(magnitude):
            raise FaultError(f"a {mode} fault needs a magnitude in {spec.unit}")
        if mode == "noise" and not 0.0 < magnitude <= spec.limit:
            raise FaultError(f"noise sigma must be above 0 and at most {spec.limit:g} {spec.unit}")
        if mode != "noise" and not (0.0 < abs(magnitude) <= spec.limit):
            raise FaultError(
                f"{mode} magnitude must be non-zero and within +/-{spec.limit:g} {spec.unit}"
            )
        self.sensors[channel] = SensorFault(mode, float(magnitude), t_s)

    def set_fuel_valve_lag(self, tau_s: float) -> None:
        lo, hi = FUEL_VALVE_LAG_RANGE_S
        if not lo <= tau_s <= hi:
            raise FaultError(f"fuel valve lag must be between {lo:g} and {hi:g} s")
        self.fuel_valve_lag_s = tau_s

    def clear(self, target: str) -> None:
        if target not in CLEAR_TARGETS:
            raise FaultError(f"target must be one of {', '.join(CLEAR_TARGETS)}")
        if target == "all":
            if not self.any_active():
                raise FaultError("no fault is active")
            for item in self.degradation.values():
                item.severity_pct = item.rate_pct_per_h = 0.0
            self.sensors.clear()
            self.fuel_valve_lag_s = None
        elif target in DEGRADATIONS:
            item = self.degradation[target]
            if not item.active:
                raise FaultError(f"{target} is not active")
            item.severity_pct = item.rate_pct_per_h = 0.0
        elif target == "fuel_valve":
            if self.fuel_valve_lag_s is None:
                raise FaultError("the fuel valve has no injected lag")
            self.fuel_valve_lag_s = None
        else:
            if target not in self.sensors:
                raise FaultError(f"no fault on the {target} sensor")
            del self.sensors[target]
        self._update_health()

    def wash_compressor(self) -> None:
        item = self.degradation["compressor_fouling"]
        if item.severity_pct <= 0.0:
            raise FaultError("the compressor has no fouling to wash off")
        item.severity_pct = 0.0  # the growth rate (the dirty-air condition) stays
        self._update_health()

    # ------------------------------------------------------------------ readings
    def read(self, channel: str, true_value: float, t_s: float) -> float:
        fault = self.sensors.get(channel)
        if fault is None:
            return true_value
        return fault.read(true_value, t_s, self.rng)

    def any_active(self) -> bool:
        return (
            any(item.active for item in self.degradation.values())
            or bool(self.sensors)
            or self.fuel_valve_lag_s is not None
        )

    def to_dict(self) -> dict[str, Any]:
        """Ground truth of the injected faults (an estimator must not read this)."""

        h = self.health
        return {
            "degradation": {
                name: {
                    "severity_pct": item.severity_pct,
                    "rate_pct_per_h": item.rate_pct_per_h,
                }
                for name, item in self.degradation.items()
                if item.active
            },
            "health": {
                "compressor_flow_capacity_delta": h.compressor_flow,
                "compressor_efficiency_delta": h.compressor_efficiency,
                "turbine_efficiency_delta": h.turbine_efficiency,
            },
            "sensors": {
                channel: fault.to_dict(channel)
                for channel in CHANNELS
                if (fault := self.sensors.get(channel)) is not None
            },
            "fuel_valve_lag_s": self.fuel_valve_lag_s,
        }
