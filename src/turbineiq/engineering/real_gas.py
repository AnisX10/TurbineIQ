"""Variable-property open-cycle model with cooling bleed and inlet/exhaust losses.

Compared with :mod:`turbineiq.engineering.core` this model uses temperature-dependent
ideal-gas properties (NASA-7 polynomials, species data in ``data/nasa7_species.json``),
a combustor energy balance on sensible enthalpy and the fuel lower heating value,
a fraction of compressor air that bypasses the combustor as turbine cooling flow,
and pressure losses at the inlet, combustor and exhaust. Compression and expansion
use a polytropic (small-stage) efficiency integrated with Runge-Kutta in ln p.

It is still a zero-dimensional steady-state model: no humidity, no dissociation, no
off-design component maps, and cooling air is simply mixed in before the turbine.
Parameters named ``effective_*`` therefore absorb effects the model leaves out and must
not be read as OEM firing temperatures or component efficiencies.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
from math import isfinite, log

T_REF_K = 298.15
_N_STEPS = 12

# Dry ISO air, mole fractions (CO2 neglected).
_AIR_MOLES = {"N2": 0.7809, "O2": 0.2095, "AR": 0.0096}
_FUEL_MOLAR_MASS = 16.043  # CH4, kg/kmol
_FUEL_LHV_KJ_KG = 50_000.0  # methane LHV, 298 K


@dataclass(frozen=True)
class RealGasInputs:
    """Inputs for the variable-property model. Temperatures in kelvin, pressures in kPa."""

    ambient_temperature_c: float = 15.0
    ambient_pressure_kpa: float = 101.325
    pressure_ratio: float = 12.8
    air_mass_flow_kg_s: float = 140.0
    effective_firing_temperature_k: float = 1400.0
    compressor_polytropic_efficiency: float = 0.88
    turbine_polytropic_efficiency: float = 0.88
    cooling_flow_fraction: float = 0.08
    combustor_efficiency: float = 0.995
    combustor_pressure_loss_fraction: float = 0.04
    inlet_pressure_loss_fraction: float = 0.01
    exhaust_pressure_loss_fraction: float = 0.01
    drivetrain_efficiency: float = 0.965
    fuel_lhv_kj_kg: float = _FUEL_LHV_KJ_KG

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
        if self.ambient_temperature_c <= -73.15 or self.ambient_temperature_c > 60:
            raise ValueError("ambient_temperature_c outside the supported range (-73 to 60 C)")
        if self.pressure_ratio <= 1 or self.air_mass_flow_kg_s <= 0:
            raise ValueError("pressure_ratio must exceed 1 and air flow must be positive")
        if not 700 <= self.effective_firing_temperature_k <= 2000:
            raise ValueError("effective_firing_temperature_k outside 700 to 2000 K")
        for name in (
            "compressor_polytropic_efficiency",
            "turbine_polytropic_efficiency",
            "combustor_efficiency",
            "drivetrain_efficiency",
        ):
            if not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        for name in (
            "cooling_flow_fraction",
            "combustor_pressure_loss_fraction",
            "inlet_pressure_loss_fraction",
            "exhaust_pressure_loss_fraction",
        ):
            if not 0 <= getattr(self, name) < 0.5:
                raise ValueError(f"{name} must be in [0, 0.5)")


@dataclass(frozen=True)
class RealGasResult:
    model_name: str
    compressor_discharge_temperature_k: float
    mixed_turbine_inlet_temperature_k: float
    exhaust_temperature_k: float
    fuel_to_air_ratio: float
    compressor_power_mw: float
    turbine_power_mw: float
    shaft_power_mw: float
    net_electrical_power_mw: float
    heat_added_mw: float
    fuel_mass_flow_kg_s: float
    fuel_input_power_mw: float
    lhv_efficiency: float
    heat_rate_kj_per_kwh: float
    exhaust_mass_flow_kg_s: float
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["assumptions"] = list(self.assumptions)
        return payload


@lru_cache(maxsize=1)
def _species() -> tuple[dict[str, dict[str, object]], float]:
    text = resources.files("turbineiq.engineering").joinpath("data/nasa7_species.json")
    data = json.loads(text.read_text(encoding="utf-8"))
    return data["species"], float(data["gas_constant_j_mol_k"])


def _merge(species: dict[str, dict[str, object]], frac: dict[str, float], key: str) -> list[float]:
    merged = [0.0] * 6
    for name, x in frac.items():
        coeffs = species[name][key]
        for i in range(6):
            merged[i] += x * coeffs[i]  # type: ignore[index]
    return merged


class _Mixture:
    """Ideal-gas mixture given by kilomoles of each species.

    NASA-7 coefficients are merged by mole fraction once, so property evaluation is a single
    polynomial per temperature range (all species share the 1000 K range break).
    """

    def __init__(self, kmol: dict[str, float]) -> None:
        species, r_mol = _species()
        self.kmol = {k: v for k, v in kmol.items() if v > 0}
        total = sum(self.kmol.values())
        self.mass = sum(v * float(species[k]["molar_mass_kg_kmol"]) for k, v in self.kmol.items())  # type: ignore[arg-type]
        self.molar_mass = self.mass / total
        self.r = r_mol * 1000.0 / self.molar_mass  # J/(kg K)
        frac = {k: v / total for k, v in self.kmol.items()}
        self._hi = _merge(species, frac, "coeffs_high")
        self._lo = _merge(species, frac, "coeffs_low")
        self._h_ref = self._h_mol(T_REF_K)

    def _coeffs(self, t: float) -> list[float]:
        return self._hi if t >= 1000.0 else self._lo

    def _h_mol(self, t: float) -> float:
        a = self._coeffs(t)
        return t * (a[0] + t * (a[1] / 2 + t * (a[2] / 3 + t * (a[3] / 4 + t * a[4] / 5)))) + a[5]

    def cp(self, t: float) -> float:
        """Specific heat, J/(kg K)."""
        a = self._coeffs(t)
        return (a[0] + t * (a[1] + t * (a[2] + t * (a[3] + t * a[4])))) * self.r

    def h(self, t: float) -> float:
        """Sensible enthalpy relative to 298.15 K, J/kg."""
        return (self._h_mol(t) - self._h_ref) * self.r


def _air(kmol_total: float = 1.0) -> _Mixture:
    return _Mixture({k: v * kmol_total for k, v in _AIR_MOLES.items()})


def _air_kmol_per_kg() -> float:
    mixture = _air(1.0)
    return 1.0 / mixture.mass


def _t_from_h(mix: _Mixture, h_target: float, t_guess: float) -> float:
    """Invert sensible enthalpy for temperature by Newton iteration."""
    t = t_guess
    for _ in range(60):
        f = mix.h(t) - h_target
        if abs(f) < 1e-3:
            return t
        t -= f / mix.cp(t)
    raise ValueError("temperature inversion did not converge")


def _polytropic_path(
    mix: _Mixture, t_in: float, pressure_ratio: float, eta: float, *, compress: bool
) -> float:
    """Exit temperature of a polytropic compression or expansion.

    Integrates the small-stage relation ``dT/d(ln p) = +-(eta^k) R T / cp(T)`` (k = -1 for
    compression, +1 for expansion) with fourth-order Runge-Kutta in ln p.
    """

    def slope(t: float) -> float:
        g = mix.r * t / mix.cp(t)
        return g / eta if compress else -eta * g

    h = log(pressure_ratio) / _N_STEPS
    t = t_in
    for _ in range(_N_STEPS):
        k1 = slope(t)
        k2 = slope(t + 0.5 * h * k1)
        k3 = slope(t + 0.5 * h * k2)
        k4 = slope(t + h * k3)
        t += h * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0
    return t


def simulate_real_gas_cycle(inputs: RealGasInputs | None = None) -> RealGasResult:
    p = inputs or RealGasInputs()
    t1 = p.ambient_temperature_c + 273.15
    p1 = p.ambient_pressure_kpa * (1 - p.inlet_pressure_loss_fraction)
    p2 = p1 * p.pressure_ratio
    p3 = p2 * (1 - p.combustor_pressure_loss_fraction)
    p4 = p.ambient_pressure_kpa * (1 + p.exhaust_pressure_loss_fraction)
    expansion_ratio = p3 / p4
    if expansion_ratio <= 1:
        raise ValueError("turbine expansion ratio must exceed 1 after losses")

    # Per 1 kg of compressor-inlet air.
    air_kmol = _air_kmol_per_kg()
    air = _air(air_kmol)
    t2 = _polytropic_path(
        air, t1, p.pressure_ratio, p.compressor_polytropic_efficiency, compress=True
    )
    compressor_work = air.h(t2) - air.h(t1)  # J per kg air

    xc = p.cooling_flow_fraction
    burner_air_kmol = air_kmol * (1 - xc)
    h_air_t2 = air.h(t2)

    def burned_gas(fuel_kg: float) -> _Mixture:
        n_f = fuel_kg / _FUEL_MOLAR_MASS
        kmol = {k: v * burner_air_kmol for k, v in _AIR_MOLES.items()}
        kmol["O2"] -= 2 * n_f
        if kmol["O2"] <= 0:
            raise ValueError("insufficient oxygen for the requested fuel flow")
        kmol["CO2"] = n_f
        kmol["H2O"] = 2 * n_f
        return _Mixture(kmol)

    def combustor_residual(fuel_kg: float) -> float:
        gas = burned_gas(fuel_kg)
        released = fuel_kg * p.combustor_efficiency * p.fuel_lhv_kj_kg * 1000.0
        # Burner air enters at T2 (sensible enthalpy of that air per kg total air).
        h_in = (1 - xc) * h_air_t2 + released
        return h_in - gas.mass * gas.h(p.effective_firing_temperature_k)

    # Secant iteration on the (nearly linear) combustor energy residual.
    f0, f1 = 0.015, 0.020
    r0, r1 = combustor_residual(f0), combustor_residual(f1)
    for _ in range(30):
        if r1 == r0:
            break
        f2 = f1 - r1 * (f1 - f0) / (r1 - r0)
        if not 0.0 < f2 < 0.05:
            raise ValueError("no fuel flow satisfies the combustor energy balance")
        f0, r0 = f1, r1
        f1, r1 = f2, combustor_residual(f2)
        if abs(f1 - f0) < 1e-13:
            break
    else:
        raise ValueError("combustor energy balance did not converge")
    fuel = f1

    # Mix cooling air (at T2) into the burned gas before the turbine.
    gas = burned_gas(fuel)
    kmol_mixed = dict(gas.kmol)
    for k, v in _AIR_MOLES.items():
        kmol_mixed[k] = kmol_mixed.get(k, 0.0) + v * air_kmol * xc
    turbine_gas = _Mixture(kmol_mixed)
    h_mixed = gas.mass * gas.h(p.effective_firing_temperature_k) + xc * h_air_t2
    t3 = _t_from_h(turbine_gas, h_mixed / turbine_gas.mass, p.effective_firing_temperature_k)

    t4 = _polytropic_path(
        turbine_gas, t3, expansion_ratio, p.turbine_polytropic_efficiency, compress=False
    )
    turbine_work = turbine_gas.mass * (turbine_gas.h(t3) - turbine_gas.h(t4))  # J per kg air

    net_shaft = turbine_work - compressor_work
    if net_shaft <= 0:
        raise ValueError("the selected inputs produce non-positive net work")
    mdot = p.air_mass_flow_kg_s
    electrical_mw = net_shaft * p.drivetrain_efficiency * mdot / 1e6
    fuel_mw = fuel * mdot * p.fuel_lhv_kj_kg / 1000.0
    efficiency = electrical_mw / fuel_mw

    assumptions = (
        "Ideal-gas mixtures with NASA-7 temperature-dependent properties (GRI-Mech 3.0 data).",
        "Dry ISO air; no humidity, CO2 in air or dissociation. Fuel is methane at 298 K.",
        "Combustor: sensible-enthalpy energy balance with combustor efficiency applied to LHV.",
        "Cooling flow bypasses the combustor and is mixed in before the turbine (no partial "
        "expansion credit), so effective_firing_temperature_k is an effective value.",
        "Polytropic efficiency from the small-stage relation (RK4 in ln p); fixed pressure losses.",
        "Drivetrain efficiency covers mechanical, gearbox and generator losses together.",
        "Parameters are fitted to public catalog ratings, not OEM data or limits.",
    )
    return RealGasResult(
        model_name="Variable-property open-cycle model (calibrated to public 6B.03 ratings)",
        compressor_discharge_temperature_k=t2,
        mixed_turbine_inlet_temperature_k=t3,
        exhaust_temperature_k=t4,
        fuel_to_air_ratio=fuel,
        compressor_power_mw=compressor_work * mdot / 1e6,
        turbine_power_mw=turbine_work * mdot / 1e6,
        shaft_power_mw=net_shaft * mdot / 1e6,
        net_electrical_power_mw=electrical_mw,
        heat_added_mw=fuel_mw * p.combustor_efficiency,
        fuel_mass_flow_kg_s=fuel * mdot,
        fuel_input_power_mw=fuel_mw,
        lhv_efficiency=efficiency,
        heat_rate_kj_per_kwh=3600.0 / efficiency,
        exhaust_mass_flow_kg_s=mdot * (1 + fuel),
        assumptions=assumptions,
    )


# Fit to the published GE 6B.03 ISO ratings (scripts/calibrate_cycle.py, cooling flow fixed
# at 8 percent). See docs/CALIBRATION.md for what the fit does and does not establish.
CALIBRATED_6B03 = RealGasInputs(
    air_mass_flow_kg_s=142.405396,
    effective_firing_temperature_k=1463.220349,
    compressor_polytropic_efficiency=0.874264,
    turbine_polytropic_efficiency=0.874264,
    drivetrain_efficiency=0.941750,
    cooling_flow_fraction=0.08,
)


def at_ambient(base: RealGasInputs, ambient_temperature_c: float) -> RealGasInputs:
    """Change ambient temperature at constant shaft speed.

    A single-shaft machine at fixed speed swallows roughly constant volumetric flow, so
    air mass flow scales with inlet density, ``m ~ p / T``. Firing temperature is held
    constant (no exhaust-temperature control curve), which is a stated simplification.
    """

    t = ambient_temperature_c + 273.15
    t_base = base.ambient_temperature_c + 273.15
    return replace(
        base,
        ambient_temperature_c=ambient_temperature_c,
        air_mass_flow_kg_s=base.air_mass_flow_kg_s * t_base / t,
    )


def with_overrides(inputs: RealGasInputs, **changes: float) -> RealGasInputs:
    return replace(inputs, **changes)
