"""Off-design static maps generated from the calibrated cycle model.

The dynamic plant needs shaft power and exhaust temperature as functions of shaft speed,
inlet-guide-vane (IGV) position and fuel flow. Rowen (1983) uses generic closed-form
functions for these. Here they are tabulated from :mod:`turbineiq.engineering.real_gas`,
so the dynamic model inherits the calibrated thermodynamics (docs/CALIBRATION.md).

Off-design assumptions (all illustrative, none validated against 6B.03 data):

* air mass flow scales with shaft speed and with an IGV factor, and with inlet density
  (``m ~ 1/T``) at fixed inlet volume flow;
* the pressure ratio follows from compressor specific work ``~ N^2``, using a fixed
  effective exponent, rather than from a compressor map;
* component polytropic efficiencies, cooling fraction and pressure losses stay at their
  calibrated values at every speed and load;
* a change in compressor flow capacity (fouling) scales the pressure rise ``PR - 1`` in
  proportion. Near design that is close to the proportional drop in pressure ratio of a
  choked first-stage turbine nozzle at fixed firing temperature, and the effect fades as
  the pressure ratio approaches 1, where the nozzle unchokes. This is applied to the
  health change only: IGV position and firing temperature do not change the pressure
  ratio, so the clean engine behaves exactly as calibrated;
* nothing below 20 percent speed is tabulated.

Maps are keyed by ambient temperature and component health, and cached.

Component health (gas-path degradation) enters as changes to the calibrated compressor
flow capacity and the compressor and turbine polytropic efficiencies. The rated
normalisation (rated fuel, shaft power, exhaust temperature) always comes from the clean
calibrated engine, so a degraded map and a clean map share the same per-unit bases.
:class:`HealthMaps` combines a clean map with one map per health parameter at a reference
deterioration, linearly (first-order superposition), so health can change continuously
without rebuilding maps. The linearisation error is tested against direct cycle solutions.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import NamedTuple

from turbineiq.engineering import CALIBRATED_6B03, simulate_real_gas_cycle

SPEED_GRID: tuple[float, ...] = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0, 1.05, 1.1)
AIR_FACTOR_GRID: tuple[float, ...] = (0.7, 0.8, 0.9, 1.0)
_FIRING_POINTS = 30
_FIRING_MAX_K = 1900.0
_PR_EXPONENT = 0.31  # effective (gamma - 1) / (gamma * eta_p) for the N^2 work scaling


class Health(NamedTuple):
    """Gas-path health deltas relative to the clean calibrated engine.

    ``compressor_flow`` is the fractional change in compressor flow capacity (-0.02 is a
    2 percent loss); the efficiencies are absolute changes in polytropic efficiency
    (-0.01 is one point). A compressor flow-capacity change also scales the pressure ratio
    (see the module docstring). Turbine flow capacity is not a parameter.
    """

    compressor_flow: float = 0.0
    compressor_efficiency: float = 0.0
    turbine_efficiency: float = 0.0

    def is_clean(self) -> bool:
        return not any(self)


CLEAN = Health()
#: Reference deteriorations used to build the per-parameter sensitivity maps.
HEALTH_REFERENCE = Health(
    compressor_flow=-0.04, compressor_efficiency=-0.02, turbine_efficiency=-0.02
)
#: Ranges accepted for health deltas (beyond these the linear superposition is not checked).
HEALTH_LIMITS = Health(compressor_flow=-0.10, compressor_efficiency=-0.05, turbine_efficiency=-0.05)


def igv_air_factor(igv_position: float) -> float:
    """Air-flow factor for an IGV position in [0, 1] (0 closed, 1 fully open). Illustrative."""

    return 0.7 + 0.3 * min(1.0, max(0.0, igv_position))


def pressure_ratio_at_speed(rated_pressure_ratio: float, speed_pu: float) -> float:
    """Pressure ratio at reduced speed, from compressor specific work scaling with N^2."""

    x_rated = rated_pressure_ratio**_PR_EXPONENT
    return (1.0 + speed_pu**2 * (x_rated - 1.0)) ** (1.0 / _PR_EXPONENT)


def degraded_pressure_ratio(pressure_ratio: float, compressor_flow: float) -> float:
    """Pressure ratio after a compressor flow-capacity change (see the module docstring)."""

    if compressor_flow == 0.0:
        return pressure_ratio  # keeps the clean engine bit-for-bit as calibrated
    return 1.0 + (pressure_ratio - 1.0) * (1.0 + compressor_flow)


@dataclass(frozen=True)
class _Row:
    fuel_pu: tuple[float, ...]
    power_pu: tuple[float, ...]
    exhaust_k: tuple[float, ...]
    compressor_discharge_k: float  # independent of fuel flow at a given speed and IGV


def _interp(row: _Row, wf: float) -> tuple[float, float]:
    fuel = row.fuel_pu
    i = bisect_right(fuel, wf) - 1
    i = min(max(i, 0), len(fuel) - 2)  # extrapolate linearly beyond either end
    w = (wf - fuel[i]) / (fuel[i + 1] - fuel[i])
    power = row.power_pu[i] + w * (row.power_pu[i + 1] - row.power_pu[i])
    exhaust = row.exhaust_k[i] + w * (row.exhaust_k[i + 1] - row.exhaust_k[i])
    return power, exhaust


def _bracket(grid: tuple[float, ...], x: float) -> tuple[int, float]:
    if x <= grid[0]:
        return 0, 0.0
    if x >= grid[-1]:
        return len(grid) - 2, 1.0
    i = bisect_right(grid, x) - 1
    return i, (x - grid[i]) / (grid[i + 1] - grid[i])


@dataclass(frozen=True)
class OperatingMaps:
    """Shaft power and exhaust temperature versus speed, air factor and fuel flow."""

    ambient_temperature_c: float
    rows: tuple[tuple[_Row, ...], ...]  # rows[speed index][air-factor index]
    rated_shaft_power_mw: float
    rated_electrical_power_mw: float
    rated_fuel_kg_s: float
    rated_exhaust_k: float
    drivetrain_efficiency: float
    fuel_lhv_kj_kg: float
    rated_pressure_ratio: float
    compressor_inlet_pressure_kpa: float
    health: Health = CLEAN

    def lookup(self, speed_pu: float, air_factor: float, fuel_pu: float) -> tuple[float, float]:
        """Return (shaft power in per unit of rated shaft power, exhaust temperature in K).

        Below the lowest tabulated speed the power is scaled with ``N^3`` (drag-like).
        """

        n = max(speed_pu, 0.0)
        n_tab = min(max(n, SPEED_GRID[0]), SPEED_GRID[-1])
        i, u = _bracket(SPEED_GRID, n_tab)
        j, v = _bracket(AIR_FACTOR_GRID, air_factor)
        p00, t00 = _interp(self.rows[i][j], fuel_pu)
        p01, t01 = _interp(self.rows[i][j + 1], fuel_pu)
        p10, t10 = _interp(self.rows[i + 1][j], fuel_pu)
        p11, t11 = _interp(self.rows[i + 1][j + 1], fuel_pu)
        p0 = p00 + v * (p01 - p00)
        p1 = p10 + v * (p11 - p10)
        t0 = t00 + v * (t01 - t00)
        t1 = t10 + v * (t11 - t10)
        power = p0 + u * (p1 - p0)
        exhaust = t0 + u * (t1 - t0)
        if n < SPEED_GRID[0]:
            power *= (n / SPEED_GRID[0]) ** 3
        return power, exhaust

    def compressor_discharge(self, speed_pu: float, air_factor: float) -> tuple[float, float]:
        """Return (compressor discharge temperature in K, discharge pressure in kPa).

        Both follow the map assumptions above: the pressure ratio depends on speed and on
        the compressor flow-capacity health delta, not on IGV position or firing
        temperature. Below the lowest tabulated speed the values are held at that speed's.
        """

        n_tab = min(max(speed_pu, SPEED_GRID[0]), SPEED_GRID[-1])
        i, u = _bracket(SPEED_GRID, n_tab)
        j, v = _bracket(AIR_FACTOR_GRID, air_factor)
        r = self.rows
        c0 = r[i][j].compressor_discharge_k + v * (
            r[i][j + 1].compressor_discharge_k - r[i][j].compressor_discharge_k
        )
        c1 = r[i + 1][j].compressor_discharge_k + v * (
            r[i + 1][j + 1].compressor_discharge_k - r[i + 1][j].compressor_discharge_k
        )
        pressure = self.compressor_inlet_pressure_kpa * degraded_pressure_ratio(
            pressure_ratio_at_speed(self.rated_pressure_ratio, n_tab), self.health.compressor_flow
        )
        return c0 + u * (c1 - c0), pressure

    def fuel_for_power(
        self, power_pu: float, speed_pu: float = 1.0, air_factor: float = 1.0
    ) -> float:
        """Invert the map: fuel flow (per unit) that gives ``power_pu`` of shaft power."""

        lo, hi = 0.0, 2.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self.lookup(speed_pu, air_factor, mid)[0] < power_pu:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def electrical_mw(self, shaft_power_pu: float) -> float:
        return shaft_power_pu * self.rated_shaft_power_mw * self.drivetrain_efficiency


@lru_cache(maxsize=64)
def _build(ambient_key: float, health: Health = CLEAN) -> OperatingMaps:
    base = CALIBRATED_6B03
    rated = simulate_real_gas_cycle(base)  # per-unit bases: always the clean engine
    engine = replace(
        base,
        compressor_polytropic_efficiency=base.compressor_polytropic_efficiency
        + health.compressor_efficiency,
        turbine_polytropic_efficiency=base.turbine_polytropic_efficiency
        + health.turbine_efficiency,
    )
    t_base = base.ambient_temperature_c + 273.15
    t_amb = ambient_key + 273.15
    rows: list[tuple[_Row, ...]] = []
    for n in SPEED_GRID:
        per_speed: list[_Row] = []
        pr = degraded_pressure_ratio(
            pressure_ratio_at_speed(base.pressure_ratio, n), health.compressor_flow
        )
        for g in AIR_FACTOR_GRID:
            air = base.air_mass_flow_kg_s * (1.0 + health.compressor_flow) * n * g * t_base / t_amb
            probe = replace(
                engine,
                ambient_temperature_c=ambient_key,
                pressure_ratio=pr,
                air_mass_flow_kg_s=air,
                effective_firing_temperature_k=1000.0,
            )
            t2 = simulate_real_gas_cycle(probe, allow_negative_work=True)
            t_lo = t2.compressor_discharge_temperature_k + 2.0
            fuel, power, exhaust = [], [], []
            for k in range(_FIRING_POINTS):
                t_fire = t_lo + (_FIRING_MAX_K - t_lo) * k / (_FIRING_POINTS - 1)
                try:
                    res = simulate_real_gas_cycle(
                        replace(probe, effective_firing_temperature_k=t_fire),
                        allow_negative_work=True,
                    )
                except ValueError:
                    continue  # outside the cycle model's range; skip the point
                fuel.append(res.fuel_mass_flow_kg_s / rated.fuel_mass_flow_kg_s)
                power.append(res.shaft_power_mw / rated.shaft_power_mw)
                exhaust.append(res.exhaust_temperature_k)
            per_speed.append(
                _Row(
                    tuple(fuel), tuple(power), tuple(exhaust), t2.compressor_discharge_temperature_k
                )
            )
        rows.append(tuple(per_speed))
    return OperatingMaps(
        ambient_temperature_c=ambient_key,
        rows=tuple(rows),
        rated_shaft_power_mw=rated.shaft_power_mw,
        rated_electrical_power_mw=rated.net_electrical_power_mw,
        rated_fuel_kg_s=rated.fuel_mass_flow_kg_s,
        rated_exhaust_k=rated.exhaust_temperature_k,
        drivetrain_efficiency=base.drivetrain_efficiency,
        fuel_lhv_kj_kg=base.fuel_lhv_kj_kg,
        rated_pressure_ratio=base.pressure_ratio,
        compressor_inlet_pressure_kpa=base.ambient_pressure_kpa
        * (1.0 - base.inlet_pressure_loss_fraction),
        health=health,
    )


def operating_maps(ambient_temperature_c: float = 15.0) -> OperatingMaps:
    """Return the cached maps for an ambient temperature (rounded to 0.5 C)."""

    return _build(_ambient_key(ambient_temperature_c))


def _ambient_key(ambient_temperature_c: float) -> float:
    if not -40.0 <= ambient_temperature_c <= 55.0:
        raise ValueError("ambient_temperature_c must be between -40 and 55 C")
    return round(ambient_temperature_c * 2.0) / 2.0


def single_parameter_health(index: int, value: float) -> Health:
    values = [0.0, 0.0, 0.0]
    values[index] = value
    return Health(*values)


def direct_health_maps(ambient_temperature_c: float, health: Health) -> OperatingMaps:
    """Maps built directly at ``health`` (no linearisation). Slower; used for checks."""

    return _build(_ambient_key(ambient_temperature_c), Health(*(float(h) for h in health)))


class HealthMaps:
    """Clean maps plus first-order health corrections from per-parameter sensitivity maps.

    For each health parameter a map is built at :data:`HEALTH_REFERENCE`; a lookup at
    health ``h`` returns ``clean + sum_i (h_i / ref_i) * (map_i - clean)``. Cross terms are
    neglected. With clean health it returns the clean map's values exactly.
    """

    def __init__(self, clean: OperatingMaps) -> None:
        self.clean = clean
        key = clean.ambient_temperature_c
        self._sensitivity = tuple(
            _build(key, single_parameter_health(i, HEALTH_REFERENCE[i])) for i in range(3)
        )

    def lookup(self, health: Health, speed_pu: float, air_factor: float, fuel_pu: float):
        p0, t0 = self.clean.lookup(speed_pu, air_factor, fuel_pu)
        if health.is_clean():
            return p0, t0
        power, exhaust = p0, t0
        for i, sens in enumerate(self._sensitivity):
            if health[i] == 0.0:
                continue
            w = health[i] / HEALTH_REFERENCE[i]
            p1, t1 = sens.lookup(speed_pu, air_factor, fuel_pu)
            power += w * (p1 - p0)
            exhaust += w * (t1 - t0)
        return power, exhaust

    def compressor_discharge(
        self, health: Health, speed_pu: float, air_factor: float
    ) -> tuple[float, float]:
        t0, p0 = self.clean.compressor_discharge(speed_pu, air_factor)
        if health.is_clean():
            return t0, p0
        temperature = t0
        for i in (0, 1):  # turbine health does not reach the compressor
            if health[i] == 0.0:
                continue
            t1, _ = self._sensitivity[i].compressor_discharge(speed_pu, air_factor)
            temperature += health[i] / HEALTH_REFERENCE[i] * (t1 - t0)
        # The pressure-ratio change is linear in flow capacity, so this part is exact.
        inlet = self.clean.compressor_inlet_pressure_kpa
        ratio = degraded_pressure_ratio(p0 / inlet, health.compressor_flow)
        return temperature, inlet * ratio


@lru_cache(maxsize=16)
def health_maps(ambient_temperature_c: float = 15.0) -> HealthMaps:
    """Cached :class:`HealthMaps` for an ambient temperature (rounded to 0.5 C)."""

    return HealthMaps(operating_maps(ambient_temperature_c))
