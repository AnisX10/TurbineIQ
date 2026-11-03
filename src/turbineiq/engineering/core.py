"""A transparent constant-property, open-cycle Brayton model.

All parameters are illustrative engineering assumptions. This is not an OEM
performance model and must not be used to set or verify real operating limits.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class CycleInputs:
    """Inputs for a simplified single-shaft gas-turbine study point.

    Temperatures are in kelvin unless a field explicitly ends in ``_c``.
    Pressures are absolute kPa; specific work and heat are kJ/kg.
    """

    ambient_temperature_c: float = 15.0
    ambient_pressure_kpa: float = 101.325
    pressure_ratio: float = 12.0
    air_mass_flow_kg_s: float = 100.0
    turbine_inlet_temperature_k: float = 1300.0
    compressor_efficiency: float = 0.85
    turbine_efficiency: float = 0.90
    combustor_pressure_loss_fraction: float = 0.04
    combustor_efficiency: float = 0.98
    mechanical_efficiency: float = 0.98
    generator_efficiency: float = 0.97
    cp_air_kj_kg_k: float = 1.005
    cp_gas_kj_kg_k: float = 1.15
    gamma_air: float = 1.40
    gamma_gas: float = 1.33
    fuel_lhv_kj_kg: float = 50000.0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")

        if self.ambient_temperature_c <= -273.15:
            raise ValueError("ambient_temperature_c must be above absolute zero")
        if self.ambient_pressure_kpa <= 0:
            raise ValueError("ambient_pressure_kpa must be greater than zero")
        if self.pressure_ratio <= 1:
            raise ValueError("pressure_ratio must be greater than 1")
        if self.air_mass_flow_kg_s <= 0:
            raise ValueError("air_mass_flow_kg_s must be greater than zero")
        if self.turbine_inlet_temperature_k <= self.ambient_temperature_c + 273.15:
            raise ValueError("turbine inlet temperature must exceed ambient temperature")

        for name in (
            "compressor_efficiency",
            "turbine_efficiency",
            "combustor_efficiency",
            "mechanical_efficiency",
            "generator_efficiency",
        ):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be greater than zero and at most 1")

        if not 0 <= self.combustor_pressure_loss_fraction < 1:
            raise ValueError("combustor_pressure_loss_fraction must be in [0, 1)")
        if self.cp_air_kj_kg_k <= 0 or self.cp_gas_kj_kg_k <= 0:
            raise ValueError("specific heat capacities must be greater than zero")
        for name in ("gamma_air", "gamma_gas"):
            if getattr(self, name) <= 1:
                raise ValueError(f"{name} must be greater than 1")
        if self.fuel_lhv_kj_kg <= 0:
            raise ValueError("fuel_lhv_kj_kg must be greater than zero")


@dataclass(frozen=True)
class StatePoint:
    name: str
    description: str
    temperature_k: float
    pressure_kpa: float

    def to_dict(self) -> dict[str, str | float]:
        return asdict(self)


@dataclass(frozen=True)
class CycleResult:
    model_name: str
    states: tuple[StatePoint, StatePoint, StatePoint, StatePoint]
    compressor_specific_work_kj_per_kg_air: float
    turbine_specific_work_kj_per_kg_air: float
    net_specific_work_kj_per_kg_air: float
    heat_added_kj_per_kg_air: float
    fuel_to_air_ratio_kg_per_kg_air: float
    compressor_power_kw: float
    turbine_power_kw: float
    net_cycle_power_kw: float
    shaft_power_kw: float
    electrical_power_kw: float
    fuel_mass_flow_kg_s: float
    fuel_input_power_kw: float
    thermal_efficiency: float
    electrical_efficiency: float
    heat_rate_kj_per_kwh: float
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-friendly values for the UI and tool-call results."""
        payload = asdict(self)
        payload["states"] = [state.to_dict() for state in self.states]
        payload["assumptions"] = list(self.assumptions)
        return payload


def simulate_cycle(inputs: CycleInputs | None = None) -> CycleResult:
    """Calculate four state points and simple performance estimates.

    The compressor and turbine use constant ``cp`` and ``gamma`` relations.
    Combustor heat addition is estimated from the air-side temperature rise;
    fuel mass is then included as a small ``(1 + fuel/air)`` turbine-flow
    correction. Exhaust pressure is assumed equal to ambient pressure.
    """

    point = inputs or CycleInputs()
    t1 = point.ambient_temperature_c + 273.15
    p1 = point.ambient_pressure_kpa
    p2 = p1 * point.pressure_ratio
    t2_is = t1 * point.pressure_ratio ** ((point.gamma_air - 1) / point.gamma_air)
    t2 = t1 + (t2_is - t1) / point.compressor_efficiency

    p3 = p2 * (1 - point.combustor_pressure_loss_fraction)
    p4 = p1
    t3 = point.turbine_inlet_temperature_k
    expansion_ratio = p3 / p4
    if expansion_ratio <= 1:
        raise ValueError("turbine pressure ratio must be greater than 1 after combustor loss")
    t4_is = t3 * (1 / expansion_ratio) ** ((point.gamma_gas - 1) / point.gamma_gas)
    t4 = t3 - point.turbine_efficiency * (t3 - t4_is)

    heat_added = point.cp_air_kj_kg_k * (t3 - t2)
    if heat_added <= 0:
        raise ValueError("the selected inputs produce no positive combustor heat addition")
    fuel_ratio = heat_added / (point.combustor_efficiency * point.fuel_lhv_kj_kg)

    compressor_work = point.cp_air_kj_kg_k * (t2 - t1)
    turbine_work = (1 + fuel_ratio) * point.cp_gas_kj_kg_k * (t3 - t4)
    net_work = turbine_work - compressor_work
    if net_work <= 0:
        raise ValueError("the selected inputs produce non-positive net cycle work")

    compressor_power = compressor_work * point.air_mass_flow_kg_s
    turbine_power = turbine_work * point.air_mass_flow_kg_s
    net_cycle_power = net_work * point.air_mass_flow_kg_s
    shaft_power = net_cycle_power * point.mechanical_efficiency
    electrical_power = shaft_power * point.generator_efficiency
    fuel_mass_flow = fuel_ratio * point.air_mass_flow_kg_s
    fuel_input_power = fuel_mass_flow * point.fuel_lhv_kj_kg
    thermal_efficiency = net_cycle_power / (heat_added * point.air_mass_flow_kg_s)
    electrical_efficiency = electrical_power / fuel_input_power
    heat_rate = fuel_input_power / electrical_power * 3600

    states = (
        StatePoint("1", "Compressor inlet", t1, p1),
        StatePoint("2", "Compressor discharge", t2, p2),
        StatePoint("3", "Turbine inlet after heat addition", t3, p3),
        StatePoint("4", "Turbine exhaust", t4, p4),
    )
    assumptions = (
        "Constant specific heats and heat-capacity ratios are used in each component.",
        "Combustor heat input is approximated from the air-side temperature rise.",
        "Fuel mass is included as a (1 + fuel-to-air ratio) turbine-flow correction.",
        "Combustor pressure loss is a user-set study assumption; exhaust pressure equals ambient.",
        "Mechanical and generator efficiencies are applied after net cycle work.",
        "All inputs are illustrative; none are OEM specifications or operating limits.",
    )

    return CycleResult(
        model_name="Simplified single-shaft open-cycle Brayton model",
        states=states,
        compressor_specific_work_kj_per_kg_air=compressor_work,
        turbine_specific_work_kj_per_kg_air=turbine_work,
        net_specific_work_kj_per_kg_air=net_work,
        heat_added_kj_per_kg_air=heat_added,
        fuel_to_air_ratio_kg_per_kg_air=fuel_ratio,
        compressor_power_kw=compressor_power,
        turbine_power_kw=turbine_power,
        net_cycle_power_kw=net_cycle_power,
        shaft_power_kw=shaft_power,
        electrical_power_kw=electrical_power,
        fuel_mass_flow_kg_s=fuel_mass_flow,
        fuel_input_power_kw=fuel_input_power,
        thermal_efficiency=thermal_efficiency,
        electrical_efficiency=electrical_efficiency,
        heat_rate_kj_per_kwh=heat_rate,
        assumptions=assumptions,
    )
