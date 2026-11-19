"""Seeded, event-logged simulation sessions with bit-for-bit replay.

A session wraps one :class:`~turbineiq.simulation.plant.GasTurbinePlant`. Operator
commands, including injected faults, are validated, applied between fixed steps and
written to an event log keyed by the step index. The only randomness is measurement noise
and noise-type sensor faults, drawn from generators seeded by the session seed in a fixed
order, so the same configuration and event log reproduce the same trajectory exactly (same
machine and Python build). :func:`replay` checks that.
"""

from __future__ import annotations

import hashlib
import math
import random
import struct
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from .faults import CHANNELS
from .maps import operating_maps
from .plant import CommandError, GasTurbinePlant, PlantParameters, UnitState

MODEL_NOTE = (
    "Simulated plant. Rowen-type dynamics (fuel system, rotor, exhaust thermocouple, "
    "governor/temperature/acceleration control) on static maps generated from the "
    "calibrated variable-property cycle model. Time constants, start-up timings and "
    "protection thresholds are illustrative; nothing here is validated against real "
    "6B.03 transients, and nothing is connected to a real machine."
)

COMMANDS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "start": {},
    "stop": {},
    "trip": {},
    "reset": {},
    "set_load": {"mw": (int, float), "ramp_mw_per_min": (int, float, type(None))},
    "set_igv": {"mode": str, "position": (int, float, type(None))},
    "set_ambient": {"temperature_c": (int, float)},
    "open_breaker": {},
    "close_breaker": {},
    "set_grid_frequency": {"hz": (int, float)},
    "set_island_load": {"mw": (int, float)},
    "inject_degradation": {
        "kind": str,
        "severity_pct": (int, float),
        "rate_pct_per_h": (int, float, type(None)),
    },
    "inject_sensor_fault": {
        "channel": str,
        "mode": str,
        "magnitude": (int, float, type(None)),
    },
    "set_fuel_valve_lag": {"tau_s": (int, float)},
    "clear_fault": {"target": str},
    "wash_compressor": {},
}

#: Fault commands are accepted in every unit state (a fault does not wait for the operator).
FAULT_COMMANDS = ("inject_degradation", "inject_sensor_fault", "set_fuel_valve_lag", "clear_fault")
#: Version of the per-step record hashed into the trace digest. Format 2 adds the extra
#: instrument channels, the controller's thermocouple reading and the injected health, so
#: logs recorded before fault injection existed do not replay to the same digest.
TRACE_FORMAT = 2

_STATE_CODES = {state: i for i, state in enumerate(UnitState)}
_ALLOWED: dict[UnitState, tuple[str, ...]] = {
    UnitState.STANDSTILL: (
        "start",
        "set_load",
        "set_igv",
        "set_ambient",
        "set_island_load",
        "wash_compressor",
        *FAULT_COMMANDS,
    ),
    UnitState.TRIPPED: ("reset", "set_load", "set_igv", "set_ambient", *FAULT_COMMANDS),
    UnitState.COASTDOWN: ("trip", "set_load", "set_igv", "set_ambient", *FAULT_COMMANDS),
}
_RUNNING = (
    "stop",
    "trip",
    "set_load",
    "set_igv",
    "set_ambient",
    "open_breaker",
    "close_breaker",
    "set_grid_frequency",
    "set_island_load",
    *FAULT_COMMANDS,
)


@dataclass(frozen=True)
class SessionConfig:
    seed: int = 0
    ambient_temperature_c: float = 15.0
    grid: str = "infinite_bus"
    grid_frequency_hz: float = 50.0
    island_load_mw: float = 20.0
    measurement_noise: bool = True
    record_interval_s: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.seed, int) or not 0 <= self.seed <= 2_147_483_647:
            raise ValueError("seed must be an integer between 0 and 2147483647")
        for name in ("ambient_temperature_c", "grid_frequency_hz", "island_load_mw"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be a finite number")
        if self.grid not in ("infinite_bus", "island"):
            raise ValueError("grid must be 'infinite_bus' or 'island'")
        if not 47.5 <= self.grid_frequency_hz <= 52.5:
            raise ValueError("grid_frequency_hz must be between 47.5 and 52.5")
        if not 0.0 <= self.island_load_mw <= 60.0:
            raise ValueError("island_load_mw must be between 0 and 60")
        if not 0.1 <= self.record_interval_s <= 60.0:
            raise ValueError("record_interval_s must be between 0.1 and 60")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionConfig:
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown config fields: {sorted(unknown)}")
        return cls(**data)


@dataclass(frozen=True)
class SimEvent:
    step: int
    command: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"step": self.step, "command": self.command, "params": dict(self.params)}


class InvalidCommand(CommandError):
    """A command whose name or parameters are malformed (as opposed to refused by state)."""


def _validate_params(command: str, params: dict[str, Any]) -> dict[str, Any]:
    if command not in COMMANDS:
        raise InvalidCommand(f"unknown command {command!r}; choose one of {', '.join(COMMANDS)}")
    spec = COMMANDS[command]
    unknown = set(params) - set(spec)
    if unknown:
        raise InvalidCommand(f"unknown parameters for {command}: {sorted(unknown)}")
    clean: dict[str, Any] = {}
    for name, types in spec.items():
        optional = type(None) in (types if isinstance(types, tuple) else (types,))
        if name not in params:
            if optional:
                clean[name] = None
                continue
            raise InvalidCommand(f"{command} needs parameter {name!r}")
        value = params[name]
        if isinstance(value, bool) or not isinstance(value, types):
            raise InvalidCommand(f"parameter {name!r} of {command} has the wrong type")
        if isinstance(value, float) and not math.isfinite(value):
            raise InvalidCommand(f"parameter {name!r} of {command} must be finite")
        clean[name] = value
    return clean


class Session:
    """One simulated unit with an event log, noisy measurements and a trace digest."""

    max_steps = 4_000_000  # about 55 hours of simulated time at the default step

    def __init__(self, config: SessionConfig | None = None, params: PlantParameters | None = None):
        self.config = config or SessionConfig()
        self.plant = GasTurbinePlant(
            operating_maps(self.config.ambient_temperature_c),
            params=params,
            grid=self.config.grid,
            grid_frequency_hz=self.config.grid_frequency_hz,
            island_load_mw=self.config.island_load_mw,
            fault_seed=self.config.seed,
        )
        self.dt = self.plant.p.dt_s
        self.step_count = 0
        self.events: list[SimEvent] = []
        self._rng = random.Random(self.config.seed)
        # Noise for the channels added with fault injection; a separate stream keeps the
        # power and exhaust-temperature noise sequence of earlier versions unchanged.
        self._rng_extra = random.Random(self.config.seed * 2 + 2)
        self._hash = hashlib.sha256()
        self._record_every = max(1, round(self.config.record_interval_s / self.dt))
        self.history: deque[dict[str, Any]] = deque(maxlen=20_000)
        self.measured: dict[str, float] = {}
        self._sample()

    # ------------------------------------------------------------------ commands
    def apply(self, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate and apply a command now; accepted commands are logged at this step."""

        clean = _validate_params(command, dict(params or {}))
        plant = self.plant
        try:
            if command == "start":
                plant.command_start()
            elif command == "stop":
                plant.command_stop()
            elif command == "trip":
                plant.command_trip()
            elif command == "reset":
                plant.command_reset()
            elif command == "set_load":
                plant.command_set_load(float(clean["mw"]), clean["ramp_mw_per_min"])
            elif command == "set_igv":
                position = clean["position"]
                plant.command_set_igv(clean["mode"], None if position is None else float(position))
            elif command == "set_ambient":
                try:
                    maps = operating_maps(float(clean["temperature_c"]))
                except ValueError as exc:
                    raise CommandError(str(exc)) from exc
                plant.set_maps(maps)
            elif command == "open_breaker":
                plant.open_breaker()
            elif command == "close_breaker":
                plant.close_breaker()
            elif command == "set_grid_frequency":
                plant.command_set_grid_frequency(float(clean["hz"]))
            elif command == "set_island_load":
                plant.command_set_island_load(float(clean["mw"]))
            elif command == "inject_degradation":
                rate = clean["rate_pct_per_h"]
                plant.command_inject_degradation(
                    clean["kind"],
                    float(clean["severity_pct"]),
                    None if rate is None else float(rate),
                )
            elif command == "inject_sensor_fault":
                magnitude = clean["magnitude"]
                plant.command_inject_sensor_fault(
                    clean["channel"], clean["mode"], None if magnitude is None else float(magnitude)
                )
            elif command == "set_fuel_valve_lag":
                plant.command_set_fuel_valve_lag(float(clean["tau_s"]))
            elif command == "clear_fault":
                plant.command_clear_fault(clean["target"])
            elif command == "wash_compressor":
                plant.command_wash_compressor()
        except ValueError as exc:
            if isinstance(exc, CommandError):
                raise
            raise CommandError(str(exc)) from exc
        event = SimEvent(self.step_count, command, clean)
        self.events.append(event)
        return event.to_dict()

    def allowed_commands(self) -> list[str]:
        plant = self.plant
        fixed = _ALLOWED.get(plant.state)
        if fixed is not None:
            return list(fixed)
        commands = list(_RUNNING)
        # Only offer commands that can act on the present state.
        if plant.breaker_closed:
            commands.remove("close_breaker")
        else:
            commands.remove("open_breaker")
        if plant.state not in (UnitState.FSNL, UnitState.LOADED) and "close_breaker" in commands:
            commands.remove("close_breaker")
        commands.remove("set_island_load" if plant.grid == "infinite_bus" else "set_grid_frequency")
        return commands

    # ------------------------------------------------------------------ stepping
    def advance(self, steps: int) -> None:
        if steps < 0:
            raise ValueError("steps must be non-negative")
        if self.step_count + steps > self.max_steps:
            raise CommandError("session step limit reached; create a new session")
        for _ in range(steps):
            self._one_step()

    def advance_seconds(self, seconds: float) -> None:
        self.advance(round(seconds / self.dt))

    def _one_step(self) -> None:
        self.plant.step()
        self.step_count += 1
        self._sample()

    def _sample(self) -> None:
        plant = self.plant
        readings = plant.readings
        measured: dict[str, float] = {}
        for channel, spec in CHANNELS.items():
            value = readings[channel]
            if self.config.measurement_noise:
                # Power and exhaust temperature draw from the original stream, in its order.
                rng = (
                    self._rng
                    if channel in ("electrical_power", "exhaust_temperature")
                    else (self._rng_extra)
                )
                g = rng.gauss(0.0, 1.0)
                value = (
                    value * (1.0 + spec.noise_rel * g)
                    if spec.noise_rel
                    else (value + spec.noise_abs * g)
                )
            measured[channel] = value
        self.measured = measured
        power = plant.electrical_power_mw()
        health = plant.faults.health
        self._hash.update(
            struct.pack(
                "<9d",
                plant.n,
                plant.wfc,
                plant.tm,
                plant.tx,
                plant.igv,
                plant.fsr,
                power,
                measured["electrical_power"],
                float(_STATE_CODES[plant.state]),
            )
        )
        self._hash.update(
            struct.pack(
                "<10d",
                measured["exhaust_temperature"],
                measured["speed"],
                measured["compressor_discharge_temperature"],
                measured["compressor_discharge_pressure"],
                measured["fuel_flow"],
                readings["exhaust_temperature"],
                health.compressor_flow,
                health.compressor_efficiency,
                health.turbine_efficiency,
                plant.valve_lag_s,
            )
        )
        if self.step_count % self._record_every == 0:
            self.history.append(self.snapshot())

    # ------------------------------------------------------------------ outputs
    def trace_digest(self) -> str:
        return self._hash.copy().hexdigest()

    def snapshot(self) -> dict[str, Any]:
        plant = self.plant
        maps = plant.maps
        power = plant.electrical_power_mw()
        fuel_kg_s = plant.wfc * maps.rated_fuel_kg_s
        cdt, cdp = plant.compressor_discharge()
        m = self.measured
        heat_rate = None
        if power > 0.05 * maps.rated_electrical_power_mw and fuel_kg_s > 0:
            heat_rate = fuel_kg_s * maps.fuel_lhv_kj_kg * 3600.0 / (power * 1000.0)
        return {
            "t_s": round(self.step_count * self.dt, 6),
            "step": self.step_count,
            "state": plant.state.value,
            "breaker_closed": plant.breaker_closed,
            "flame": plant.flame,
            "trip_cause": plant.trip_cause,
            "grid": plant.grid,
            "speed_pu": plant.n,
            "speed_hz_equivalent": plant.n * plant.rated_frequency_hz,
            "grid_frequency_hz": plant.grid_frequency_hz if plant.grid == "infinite_bus" else None,
            "fsr": plant.fsr,
            "limiter": plant.limiter,
            "fuel_flow_kg_s": fuel_kg_s,
            "electrical_power_mw": power,
            "shaft_power_mw": plant.shaft_power_pu() * maps.rated_shaft_power_mw,
            "load_setpoint_mw": plant.load_target_mw,
            "load_reference_mw": plant.load_ref_mw,
            "ramp_mw_per_min": plant.ramp_mw_per_min,
            "exhaust_temperature_k": plant.tm,
            "exhaust_temperature_c": plant.tm - 273.15,
            "temperature_limit_k": plant.temperature_limit_k,
            "trip_temperature_k": plant.trip_temperature_k,
            "igv_position": plant.igv,
            "igv_mode": plant.igv_mode,
            "ambient_temperature_c": maps.ambient_temperature_c,
            "heat_rate_kj_per_kwh": heat_rate,
            "compressor_discharge_temperature_k": cdt,
            "compressor_discharge_pressure_kpa": cdp,
            # What the instruments report: sensor faults applied, then measurement noise.
            # Speed in per unit, the rest in the units of the matching true value.
            "measured": {
                "electrical_power_mw": m["electrical_power"],
                "exhaust_temperature_k": m["exhaust_temperature"],
                "speed_pu": m["speed"],
                "compressor_discharge_temperature_k": m["compressor_discharge_temperature"],
                "compressor_discharge_pressure_kpa": m["compressor_discharge_pressure"],
                "fuel_flow_kg_s": m["fuel_flow"],
            },
            # Ground truth of injected faults, for the console and for scoring estimators.
            # An estimator under test must use only "measured" (and the commands it sent).
            "injected_faults": plant.faults.to_dict(),
            "alarms": [{"t_s": t, "message": m} for t, m in plant.alarms[-5:]],
            "available_commands": self.allowed_commands(),
            "synthetic_simulation": True,
        }

    def log(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "steps": self.step_count,
            "dt_s": self.dt,
            "trace_digest": self.trace_digest(),
            "trace_format": TRACE_FORMAT,
            "model_note": MODEL_NOTE,
        }


def replay(log: dict[str, Any]) -> Session:
    """Re-run a session from its log (config, events, step count) and return it."""

    config = SessionConfig.from_dict(dict(log["config"]))
    events = [SimEvent(int(e["step"]), str(e["command"]), dict(e["params"])) for e in log["events"]]
    total = int(log["steps"])
    if any(e.step < 0 or e.step > total for e in events) or events != sorted(
        events, key=lambda e: e.step
    ):
        raise ValueError("events must be ordered by step and lie within the run")
    session = Session(config)
    index = 0
    while True:
        while index < len(events) and events[index].step == session.step_count:
            session.apply(events[index].command, events[index].params)
            index += 1
        if session.step_count >= total:
            break
        next_stop = events[index].step if index < len(events) else total
        session.advance(max(1, min(next_stop, total) - session.step_count))
    return session
