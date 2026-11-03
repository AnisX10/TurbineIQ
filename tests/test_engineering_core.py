from math import isfinite

import pytest

from turbineiq.engineering import CycleInputs, simulate_cycle


def test_reference_case_has_consistent_four_state_cycle() -> None:
    result = simulate_cycle()

    assert [state.name for state in result.states] == ["1", "2", "3", "4"]
    assert result.states[0].pressure_kpa == pytest.approx(101.325)
    assert result.states[1].pressure_kpa == pytest.approx(101.325 * 12)
    assert result.states[2].pressure_kpa < result.states[1].pressure_kpa
    assert result.states[3].pressure_kpa == pytest.approx(result.states[0].pressure_kpa)
    assert result.states[1].temperature_k > result.states[0].temperature_k
    assert result.states[3].temperature_k > result.states[0].temperature_k
    assert all(isfinite(state.temperature_k) for state in result.states)


def test_power_fuel_and_efficiency_identities_are_consistent() -> None:
    inputs = CycleInputs()
    result = simulate_cycle(inputs)

    assert result.net_specific_work_kj_per_kg_air == pytest.approx(
        result.turbine_specific_work_kj_per_kg_air - result.compressor_specific_work_kj_per_kg_air
    )
    assert result.net_cycle_power_kw == pytest.approx(
        result.net_specific_work_kj_per_kg_air * inputs.air_mass_flow_kg_s
    )
    assert result.shaft_power_kw == pytest.approx(
        result.net_cycle_power_kw * inputs.mechanical_efficiency
    )
    assert result.electrical_power_kw == pytest.approx(
        result.shaft_power_kw * inputs.generator_efficiency
    )
    assert result.fuel_input_power_kw == pytest.approx(
        result.fuel_mass_flow_kg_s * inputs.fuel_lhv_kj_kg
    )
    assert 0 < result.electrical_efficiency < 1
    assert result.heat_rate_kj_per_kwh == pytest.approx(
        result.fuel_input_power_kw / result.electrical_power_kw * 3600
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pressure_ratio", 1.0, "pressure_ratio"),
        ("air_mass_flow_kg_s", 0.0, "air_mass_flow"),
        ("compressor_efficiency", 1.1, "compressor_efficiency"),
        ("combustor_pressure_loss_fraction", 1.0, "combustor_pressure_loss"),
        ("gamma_air", 1.0, "gamma_air"),
    ],
)
def test_invalid_inputs_are_rejected(field: str, value: float, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        CycleInputs(**{field: value})


def test_non_finite_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        CycleInputs(pressure_ratio=float("nan"))


def test_net_negative_work_case_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-positive net cycle work"):
        simulate_cycle(CycleInputs(turbine_inlet_temperature_k=700.0))


def test_result_can_be_serialized_for_agent_tools() -> None:
    payload = simulate_cycle().to_dict()

    assert payload["model_name"] == "Simplified single-shaft open-cycle Brayton model"
    assert len(payload["states"]) == 4
    assert isinstance(payload["assumptions"], list)
