"""Rowen-type dynamic model of a single-shaft gas turbine on the calibrated cycle maps.

Structure follows Rowen (1983): a speed/load governor, an exhaust-temperature control
loop and an acceleration control loop feed a minimum-value select that sets the fuel
stroke reference (FSR); the fuel valve and fuel system are first-order lags; a
combustor lag and the rotor inertia follow; the exhaust gas passes through a
thermocouple lag. Rowen's closed-form torque and exhaust-temperature functions are
replaced by the maps of :mod:`turbineiq.simulation.maps`.

Everything in :class:`PlantParameters` is an illustrative, Rowen-order-of-magnitude
value. None of it is identified for a real GE 6B.03, and the trip and limit thresholds
are labelled assumptions, not OEM limits. Per-unit bases: speed on rated speed, fuel
flow on the calibrated rated fuel flow, shaft power on the calibrated rated shaft power.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .faults import CHANNELS, FaultState
from .maps import HealthMaps, OperatingMaps, health_maps, igv_air_factor


class UnitState(str, Enum):
    STANDSTILL = "standstill"
    CRANK = "crank"
    PURGE = "purge"
    IGNITION = "ignition"
    WARMUP = "warmup"
    ACCELERATE = "accelerate"
    FSNL = "full_speed_no_load"
    LOADED = "loaded"
    UNLOADING = "unloading"
    COOLDOWN = "cooldown"
    COASTDOWN = "coastdown"
    TRIPPED = "tripped"


#: States in which the speed is held by the starter and so is not integrated.
_PINNED_STATES = (UnitState.PURGE, UnitState.IGNITION, UnitState.WARMUP)
#: States in which the fuel controller (governor, temperature, acceleration) is active.
_CONTROLLED_STATES = (
    UnitState.ACCELERATE,
    UnitState.FSNL,
    UnitState.LOADED,
    UnitState.UNLOADING,
    UnitState.COOLDOWN,
)
_PROTECTED_STATES = _CONTROLLED_STATES + (UnitState.IGNITION, UnitState.WARMUP)


class CommandError(ValueError):
    """A command that is not allowed in the present state or has invalid arguments."""


@dataclass(frozen=True)
class PlantParameters:
    """Illustrative dynamic parameters. Times in seconds, speeds and fuel in per unit."""

    dt_s: float = 0.05
    two_h_s: float = 8.0  # rotor inertia constant, Rowen quotes roughly 3.5 to 10 s
    valve_lag_s: float = 0.05
    fuel_lag_s: float = 0.4
    combustor_lag_s: float = 0.2
    exhaust_lag_s: float = 0.05
    thermocouple_lag_s: float = 2.5
    igv_lag_s: float = 3.0
    droop: float = 0.04
    load_damping: float = 1.0  # island load change per unit frequency change
    temperature_limit_margin_k: float = 10.0  # control limit above the calibrated rated exhaust T
    trip_temperature_margin_k: float = 50.0  # over-temperature trip above the same reference
    temperature_ki: float = 4.0e-4  # FSR per second per kelvin
    temperature_kp: float = 1.0e-3  # FSR per kelvin
    tracking_margin: float = 0.05  # active limiters follow the selected FSR within this margin
    temperature_band_k: float = 40.0  # temperature control stays inactive further below the limit
    acceleration_band: float = 0.5  # acceleration control stays inactive below this fraction
    acceleration_limit_pu_s: float = 0.01
    acceleration_ki: float = 2.4
    speed_kp: float = 20.0
    speed_ki: float = 4.0
    trim_ki: float = 0.05
    trim_limit: float = 0.25
    fsr_min: float = 0.10
    fsr_max: float = 1.5
    fsr_ignition: float = 0.04
    overspeed_trip_pu: float = 1.10
    underspeed_trip_pu: float = 0.90
    starter_torque_pu: float = 0.15
    starter_cutout_pu: float = 0.60
    hold_speed_pu: float = 0.20
    purge_s: float = 30.0
    ignition_s: float = 5.0
    warmup_s: float = 20.0
    acceleration_ramp_pu_s: float = 0.005
    sync_dwell_s: float = 10.0
    cooldown_s: float = 60.0
    min_load_mw: float = 3.0
    default_ramp_mw_per_min: float = 10.0
    standstill_speed_pu: float = 0.03


def _lag(x: float, target: float, tau: float) -> float:
    return (target - x) / tau


class GasTurbinePlant:
    """Continuous states, controllers and the unit state machine, advanced at a fixed step."""

    def __init__(
        self,
        maps: OperatingMaps,
        *,
        params: PlantParameters | None = None,
        grid: str = "infinite_bus",
        grid_frequency_hz: float = 50.0,
        island_load_mw: float = 20.0,
        fault_seed: int = 0,
    ) -> None:
        if grid not in ("infinite_bus", "island"):
            raise ValueError("grid must be 'infinite_bus' or 'island'")
        self.p = params or PlantParameters()
        self.maps = maps
        self.grid = grid
        self.grid_frequency_hz = grid_frequency_hz
        self.island_load_mw = island_load_mw
        self.rated_frequency_hz = 50.0

        self.state = UnitState.STANDSTILL
        self.state_time_s = 0.0
        self.breaker_closed = False
        self.flame = False
        self.trip_cause: str | None = None
        self.alarms: list[tuple[float, str]] = []
        self.time_s = 0.0

        ambient_k = maps.ambient_temperature_c + 273.15
        # Continuous states.
        self.n = 0.0
        self.v = 0.0
        self.wf = 0.0
        self.wfc = 0.0
        self.tx = ambient_k
        self.tm = ambient_k
        self.igv = 0.0

        # Controller states and commands.
        self.x_temp = self.p.fsr_max
        self.x_acc = self.p.fsr_max
        self.x_speed = 0.0
        self.trim = 0.0
        self.n_ref = 0.0
        self.load_target_mw = self.p.min_load_mw
        self.load_ref_mw = 0.0
        self.ramp_mw_per_min = self.p.default_ramp_mw_per_min
        self.igv_mode = "auto"
        self.igv_manual = 1.0
        self.fsr = 0.0
        self.limiter = "none"
        self.dn_dt = 0.0

        self._fsnl_fuel = maps.fuel_for_power(0.0)
        self._rated_fuel = maps.fuel_for_power(1.0)
        self.droop_gain = (self._rated_fuel - self._fsnl_fuel) / self.p.droop
        self.temperature_limit_k = maps.rated_exhaust_k + self.p.temperature_limit_margin_k
        self.trip_temperature_k = maps.rated_exhaust_k + self.p.trip_temperature_margin_k

        # Injected faults. The controllers and protections see ``readings`` (sensor values
        # after any sensor fault, before measurement noise); the physics sees the health.
        self.faults = FaultState(fault_seed)
        self._health_maps: HealthMaps | None = None
        self.readings: dict[str, float] = {}
        self._update_readings()

    # ------------------------------------------------------------------ helpers
    @property
    def grid_speed_pu(self) -> float:
        return self.grid_frequency_hz / self.rated_frequency_hz

    def _air_factor(self) -> float:
        return igv_air_factor(self.igv)

    def _enter(self, state: UnitState) -> None:
        self.state = state
        self.state_time_s = 0.0

    def _mw_to_pu(self, mw: float) -> float:
        return mw / self.maps.rated_electrical_power_mw

    def _schedule_fuel(self, load_ref_pu: float) -> float:
        """Fuel flow that gives ``load_ref_pu`` at rated speed and fully open IGV."""

        return self.maps.fuel_for_power(max(load_ref_pu, 0.0))

    def _island_load_pu(self, n: float) -> float:
        base = self._mw_to_pu(self.island_load_mw)
        return base * (1.0 + self.p.load_damping * (n - 1.0))

    def _lookup(self, n: float, air_factor: float, fuel_pu: float) -> tuple[float, float]:
        """Plant physics: the maps at the present component health."""

        health = self.faults.health
        if health.is_clean():
            return self.maps.lookup(n, air_factor, fuel_pu)
        if self._health_maps is None:
            self._health_maps = health_maps(self.maps.ambient_temperature_c)
        return self._health_maps.lookup(health, n, air_factor, fuel_pu)

    def compressor_discharge(self) -> tuple[float, float]:
        """True compressor discharge temperature (K) and pressure (kPa)."""

        health = self.faults.health
        if health.is_clean():
            return self.maps.compressor_discharge(self.n, self._air_factor())
        if self._health_maps is None:
            self._health_maps = health_maps(self.maps.ambient_temperature_c)
        return self._health_maps.compressor_discharge(health, self.n, self._air_factor())

    @property
    def valve_lag_s(self) -> float:
        lag = self.faults.fuel_valve_lag_s
        return self.p.valve_lag_s if lag is None else lag

    def shaft_power_pu(self) -> float:
        return self._lookup(self.n, self._air_factor(), self.wfc)[0]

    def electrical_power_mw(self) -> float:
        if not self.breaker_closed:
            return 0.0
        if self.grid == "island":
            return self.maps.rated_electrical_power_mw * self._island_load_pu(self.n)
        return self.maps.electrical_mw(self.shaft_power_pu())

    # ------------------------------------------------------------------ dynamics
    def _starter_torque(self, n: float) -> float:
        p = self.p
        if self.state == UnitState.CRANK:
            return p.starter_torque_pu
        if self.state == UnitState.ACCELERATE and n < p.starter_cutout_pu:
            return p.starter_torque_pu * (1.0 - n / p.starter_cutout_pu)
        return 0.0

    def _derivs(
        self, x: tuple[float, ...], fsr: float, igv_cmd: float, pinned_n: bool
    ) -> tuple[float, ...]:
        n, v, wf, wfc, tx, tm, igv = x
        p = self.p
        g = igv_air_factor(igv)
        power_pu, t_exh = self._lookup(n, g, wfc)
        if pinned_n:
            dn = 0.0
        else:
            if self.breaker_closed and self.grid == "island":
                load = self._island_load_pu(n)
            else:
                load = 0.0
            torque = (power_pu - load) / max(n, 0.05) + self._starter_torque(n)
            dn = torque / p.two_h_s
        return (
            dn,
            _lag(v, fsr, self.valve_lag_s),
            _lag(wf, v, p.fuel_lag_s),
            _lag(wfc, wf, p.combustor_lag_s),
            _lag(tx, t_exh, p.exhaust_lag_s),
            _lag(tm, tx, p.thermocouple_lag_s),
            _lag(igv, igv_cmd, p.igv_lag_s),
        )

    def _igv_command(self) -> float:
        if self.igv_mode == "manual":
            return self.igv_manual
        # Auto schedule: closed through start, fully open from 95 percent speed.
        return min(1.0, max(0.0, (self.n - 0.85) / 0.10))

    # ------------------------------------------------------------------ controllers
    def _governor_demand(self, dt: float) -> float:
        p = self.p
        if self.state == UnitState.ACCELERATE:
            err = self.n_ref - self.n
            return self.x_speed + p.speed_kp * err
        # Droop governor with a load schedule (FSNL, loaded, unloading, cooldown).
        load_ref_pu = self._mw_to_pu(self.load_ref_mw) if self.breaker_closed else 0.0
        fuel = self._schedule_fuel(load_ref_pu)
        return fuel + self.droop_gain * (1.0 - self.n) + self.trim

    def _update_controllers(self, dt: float) -> float:
        p = self.p
        state = self.state
        if state in (UnitState.IGNITION, UnitState.WARMUP):
            self.limiter = "ignition_schedule"
            return p.fsr_ignition
        if state not in _CONTROLLED_STATES:
            self.limiter = "fuel_off"
            return 0.0

        # Load reference ramp.
        if self.breaker_closed:
            target = 0.0 if state == UnitState.UNLOADING else self.load_target_mw
            step = self.ramp_mw_per_min / 60.0 * dt
            delta = target - self.load_ref_mw
            self.load_ref_mw += max(-step, min(step, delta))

        # Speed reference (start ramp, otherwise rated).
        if state == UnitState.ACCELERATE:
            self.n_ref = min(1.0, self.n_ref + p.acceleration_ramp_pu_s * dt)
            self.x_speed = min(self.x_speed + p.speed_ki * (self.n_ref - self.n) * dt, p.fsr_max)
        else:
            self.n_ref = 1.0

        # Load trim: removes the schedule mismatch (off-ISO ambient, manual IGV) when the unit
        # is on an infinite bus. It tracks the droop-corrected load target.
        if (
            state in (UnitState.LOADED, UnitState.UNLOADING)
            and self.grid == "infinite_bus"
            and self.limiter == "governor"  # no windup while a limiter holds the fuel down
        ):
            target_pu = self._mw_to_pu(self.load_ref_mw) + (self.n_ref - self.n) / p.droop
            # Steady-state power of the demanded fuel, so fuel-system lag is not mistaken for error.
            # It stands in for measured power, so it uses the plant (degraded) maps.
            meas_pu = self._lookup(self.n, self._air_factor(), self.fsr)[0]
            self.trim += p.trim_ki * (target_pu - meas_pu) * dt
            self.trim = max(-p.trim_limit, min(p.trim_limit, self.trim))
        elif state != UnitState.ACCELERATE:
            self.trim = 0.0

        # Temperature and acceleration integrators (wind up to fsr_max when inactive).
        # Temperature control acts on the exhaust thermocouple reading, faults included.
        tc = self.readings["exhaust_temperature"]
        self.x_temp += p.temperature_ki * (self.temperature_limit_k - tc) * dt
        self.x_temp = max(0.0, min(p.fsr_max, self.x_temp))
        self.x_acc += p.acceleration_ki * (p.acceleration_limit_pu_s - self.dn_dt) * dt
        self.x_acc = max(0.0, min(p.fsr_max, self.x_acc))

        gov = self._governor_demand(dt)
        temp_demand = self.x_temp + p.temperature_kp * (self.temperature_limit_k - tc)
        demands = (("governor", gov), ("temperature", temp_demand), ("acceleration", self.x_acc))
        name, fsr = min(demands, key=lambda item: item[1])
        floor = p.fsr_ignition if state == UnitState.ACCELERATE else p.fsr_min
        fsr = max(floor, min(p.fsr_max, fsr))
        self.limiter = name
        # A limiter that is far from its limit stays out of the way (wound up to fsr_max);
        # near its limit it tracks the selected FSR so it can take over without delay.
        ceiling = max(fsr + p.tracking_margin, 0.0)
        if tc < self.temperature_limit_k - p.temperature_band_k:
            self.x_temp = p.fsr_max
        else:
            self.x_temp = min(self.x_temp, ceiling)
        if self.dn_dt < p.acceleration_band * p.acceleration_limit_pu_s:
            self.x_acc = p.fsr_max
        else:
            self.x_acc = min(self.x_acc, ceiling)
        if state == UnitState.ACCELERATE and name != "governor":
            # Conditional tracking keeps the speed integrator from winding up behind a limit.
            self.x_speed = fsr - p.speed_kp * (self.n_ref - self.n)
        return fsr

    # ------------------------------------------------------------------ protection
    def _check_protection(self) -> None:
        p = self.p
        if self.state not in _PROTECTED_STATES:
            return
        if self.n > p.overspeed_trip_pu:
            self._trip("overspeed")
        elif self.readings["exhaust_temperature"] > self.trip_temperature_k:
            self._trip("exhaust_over_temperature")
        elif self.state in (UnitState.LOADED, UnitState.UNLOADING) and (
            self.n < p.underspeed_trip_pu
        ):
            self._trip("underspeed")

    def _trip(self, cause: str) -> None:
        self.trip_cause = cause
        self.alarms.append((self.time_s, f"trip: {cause}"))
        self.breaker_closed = False
        self.flame = False
        self.v = 0.0  # the fuel stop valve closes at once; the fuel system still drains
        self._enter(UnitState.TRIPPED)

    # ------------------------------------------------------------------ state machine
    def _advance_state_machine(self) -> None:
        p = self.p
        s = self.state
        if s == UnitState.CRANK and self.n >= p.hold_speed_pu:
            self.n = p.hold_speed_pu
            self._enter(UnitState.PURGE)
        elif s == UnitState.PURGE and self.state_time_s >= p.purge_s:
            self.flame = True
            self._enter(UnitState.IGNITION)
        elif s == UnitState.IGNITION and self.state_time_s >= p.ignition_s:
            self._enter(UnitState.WARMUP)
        elif s == UnitState.WARMUP and self.state_time_s >= p.warmup_s:
            self.n_ref = self.n
            self.x_speed = p.fsr_ignition - p.speed_kp * 0.0
            self.x_temp = p.fsr_max
            self.x_acc = p.fsr_max
            self._enter(UnitState.ACCELERATE)
        elif s == UnitState.ACCELERATE and self.n >= 0.995 and self.n_ref >= 1.0:
            self.trim = 0.0
            self._enter(UnitState.FSNL)
        elif s == UnitState.FSNL and not self.breaker_closed:
            ready = abs(self.n - self.grid_speed_pu) <= 0.005 or self.grid == "island"
            if self.state_time_s >= p.sync_dwell_s and self.auto_sync and ready:
                self.close_breaker()
        elif s == UnitState.COOLDOWN and self.state_time_s >= p.cooldown_s:
            self.flame = False
            self._enter(UnitState.COASTDOWN)
        elif s == UnitState.UNLOADING and self.load_ref_mw <= p.min_load_mw + 1e-9:
            self.open_breaker()
            self._enter(UnitState.COOLDOWN)
        elif s in (UnitState.COASTDOWN, UnitState.TRIPPED) and self.n < p.standstill_speed_pu:
            self.n = 0.0
            if s == UnitState.COASTDOWN:
                self._enter(UnitState.STANDSTILL)

    auto_sync = True

    # ------------------------------------------------------------------ commands
    def close_breaker(self) -> None:
        if self.breaker_closed:
            raise CommandError("breaker is already closed")
        if self.state not in (UnitState.FSNL, UnitState.LOADED):
            raise CommandError("the breaker can only be closed at full speed no load")
        if abs(self.n - self.grid_speed_pu) > 0.005 and self.grid == "infinite_bus":
            raise CommandError("speed is not within 0.5 percent of grid frequency")
        self.breaker_closed = True
        if self.grid == "island":
            self.load_target_mw = self.island_load_mw
            self.load_ref_mw = self.island_load_mw
        else:
            self.load_ref_mw = 0.0
            # Bumpless handover: the trim carries the fuel demand across the breaker.
            self.trim = 0.0
        self._enter(UnitState.LOADED)

    def open_breaker(self) -> None:
        if not self.breaker_closed:
            raise CommandError("breaker is already open")
        self.breaker_closed = False
        self.load_ref_mw = 0.0
        self.trim = 0.0
        if self.state in (UnitState.LOADED, UnitState.UNLOADING):
            self._enter(UnitState.FSNL)
            self.auto_sync = False

    def command_start(self) -> None:
        if self.state != UnitState.STANDSTILL:
            raise CommandError(f"cannot start from state {self.state.value}")
        self.trip_cause = None
        self.auto_sync = True
        self.n_ref = 0.0
        self.load_ref_mw = 0.0
        self.trim = 0.0
        self._enter(UnitState.CRANK)

    def command_stop(self) -> None:
        s = self.state
        if s in (UnitState.CRANK, UnitState.PURGE, UnitState.IGNITION, UnitState.WARMUP):
            self.flame = False
            self._enter(UnitState.COASTDOWN)
        elif s == UnitState.ACCELERATE:
            self.flame = False
            self._enter(UnitState.COASTDOWN)
        elif s == UnitState.FSNL:
            self._enter(UnitState.COOLDOWN)
        elif s == UnitState.LOADED:
            if self.grid == "island" and self.island_load_mw > self.p.min_load_mw:
                raise CommandError("reduce the island load to the minimum load before stopping")
            self._enter(UnitState.UNLOADING)
        else:
            raise CommandError(f"cannot stop from state {s.value}")

    def command_trip(self) -> None:
        if self.state in (UnitState.STANDSTILL, UnitState.TRIPPED):
            raise CommandError(f"cannot trip from state {self.state.value}")
        self._trip("manual_emergency_trip")

    def command_reset(self) -> None:
        if self.state != UnitState.TRIPPED:
            raise CommandError("reset is only possible after a trip")
        if self.n >= self.p.standstill_speed_pu:
            raise CommandError("the rotor is still turning; wait for standstill")
        self.trip_cause = None
        self._enter(UnitState.STANDSTILL)

    def command_set_load(self, mw: float, ramp_mw_per_min: float | None) -> None:
        cap = 1.05 * self.maps.rated_electrical_power_mw
        if not 0.0 <= mw <= cap:
            raise CommandError(f"load setpoint must be between 0 and {cap:.1f} MW")
        self.load_target_mw = max(mw, self.p.min_load_mw) if mw > 0 else 0.0
        if ramp_mw_per_min is not None:
            if not 0.1 <= ramp_mw_per_min <= 120.0:
                raise CommandError("ramp must be between 0.1 and 120 MW/min")
            self.ramp_mw_per_min = ramp_mw_per_min

    def command_set_igv(self, mode: str, position: float | None) -> None:
        if mode not in ("auto", "manual"):
            raise CommandError("IGV mode must be 'auto' or 'manual'")
        if mode == "manual":
            if position is None or not 0.0 <= position <= 1.0:
                raise CommandError("manual IGV needs a position between 0 and 1")
            self.igv_manual = position
        self.igv_mode = mode

    def command_set_island_load(self, mw: float) -> None:
        if self.grid != "island":
            raise CommandError("island load only applies to an island grid")
        if not 0.0 <= mw <= 1.05 * self.maps.rated_electrical_power_mw:
            raise CommandError("island load out of range")
        self.island_load_mw = mw

    def command_set_grid_frequency(self, hz: float) -> None:
        if self.grid != "infinite_bus":
            raise CommandError("grid frequency only applies to an infinite bus")
        if not 47.5 <= hz <= 52.5:
            raise CommandError("grid frequency must be between 47.5 and 52.5 Hz")
        self.grid_frequency_hz = hz

    # ------------------------------------------------------------------ fault commands
    def command_inject_degradation(
        self, kind: str, severity_pct: float, rate_pct_per_h: float | None
    ) -> None:
        self.faults.inject_degradation(kind, severity_pct, rate_pct_per_h or 0.0)
        self._update_readings()

    def command_inject_sensor_fault(self, channel: str, mode: str, magnitude: float | None) -> None:
        current = self.readings.get(channel, 0.0)
        self.faults.inject_sensor_fault(channel, mode, magnitude, self.time_s, current)
        self._update_readings()

    def command_set_fuel_valve_lag(self, tau_s: float) -> None:
        self.faults.set_fuel_valve_lag(tau_s)

    def command_clear_fault(self, target: str) -> None:
        self.faults.clear(target)
        self._update_readings()

    def command_wash_compressor(self) -> None:
        if self.state != UnitState.STANDSTILL:
            raise CommandError("an offline compressor wash needs the unit at standstill")
        self.faults.wash_compressor()
        self._update_readings()

    def set_maps(self, maps: OperatingMaps) -> None:
        self.maps = maps
        self._fsnl_fuel = maps.fuel_for_power(0.0)
        self._rated_fuel = maps.fuel_for_power(1.0)
        self.droop_gain = (self._rated_fuel - self._fsnl_fuel) / self.p.droop
        self.temperature_limit_k = maps.rated_exhaust_k + self.p.temperature_limit_margin_k
        self.trip_temperature_k = maps.rated_exhaust_k + self.p.trip_temperature_margin_k
        self._health_maps = None  # rebuilt for the new ambient when health is not clean

    # ------------------------------------------------------------------ sensors
    def true_measurands(self) -> dict[str, float]:
        """True values of the instrumented quantities, in :data:`CHANNELS` order."""

        cdt, cdp = self.compressor_discharge()
        return {
            "electrical_power": self.electrical_power_mw(),
            "exhaust_temperature": self.tm,
            "speed": self.n,
            "compressor_discharge_temperature": cdt,
            "compressor_discharge_pressure": cdp,
            "fuel_flow": self.wfc * self.maps.rated_fuel_kg_s,
        }

    def _update_readings(self) -> None:
        values = self.true_measurands()
        faults = self.faults
        self.readings = {
            channel: faults.read(channel, values[channel], self.time_s) for channel in CHANNELS
        }

    # ------------------------------------------------------------------ one fixed step
    def step(self) -> None:
        dt = self.p.dt_s
        self.state_time_s += dt
        self.time_s += dt

        self._check_protection()
        fsr = self._update_controllers(dt)
        self.fsr = fsr
        igv_cmd = self._igv_command()

        grid_pinned = self.breaker_closed and self.grid == "infinite_bus"
        pinned = grid_pinned or self.state in _PINNED_STATES
        if grid_pinned:
            self.n = self.grid_speed_pu

        x = (self.n, self.v, self.wf, self.wfc, self.tx, self.tm, self.igv)
        k1 = self._derivs(x, fsr, igv_cmd, pinned)
        self.dn_dt = k1[0]
        x2 = tuple(a + 0.5 * dt * b for a, b in zip(x, k1, strict=True))
        k2 = self._derivs(x2, fsr, igv_cmd, pinned)
        x3 = tuple(a + 0.5 * dt * b for a, b in zip(x, k2, strict=True))
        k3 = self._derivs(x3, fsr, igv_cmd, pinned)
        x4 = tuple(a + dt * b for a, b in zip(x, k3, strict=True))
        k4 = self._derivs(x4, fsr, igv_cmd, pinned)
        new = tuple(
            a + dt * (b + 2 * c + 2 * d + e) / 6.0
            for a, b, c, d, e in zip(x, k1, k2, k3, k4, strict=True)
        )
        self.n, self.v, self.wf, self.wfc, self.tx, self.tm, self.igv = new
        if self.n < 0.0:
            self.n = 0.0
        if grid_pinned:
            self.n = self.grid_speed_pu
        self.faults.advance(dt, air_flowing=self.n > 0.5)
        self._advance_state_machine()
        self._update_readings()
