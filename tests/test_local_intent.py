import pytest

from turbineiq.agent.local_intent import (
    find_scenarios,
    parse_cycle_overrides,
    parse_seed,
    refers_explicitly_to_selection,
    refers_to_selection,
    refers_to_whole_run,
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the efficiency at pressure ratio 18?", {"pressure_ratio": 18}),
        (
            "pressure ratio of 14 with turbine efficiency 0.88",
            {"pressure_ratio": 14, "turbine_efficiency": 0.88},
        ),
        ("compressor efficiency 82%", {"compressor_efficiency": 0.82}),
        ("compressor efficiency of 82", {"compressor_efficiency": 0.82}),
        ("turbine inlet temperature 1400 K", {"turbine_inlet_temperature_k": 1400}),
        ("What if the air flow is 120 kg/s?", {"air_mass_flow_kg_s": 120}),
        ("ambient temperature 303 K", {"ambient_temperature_c": pytest.approx(29.85)}),
        ("output at 35 °C", {"ambient_temperature_c": 35}),
        ("Why is the compressor degrading?", {}),
        ("What does the +23.4 kW residual mean?", {}),
    ],
)
def test_parse_cycle_overrides(question: str, expected: dict) -> None:
    assert parse_cycle_overrides(question) == expected


def test_turbine_inlet_temperature_is_not_mistaken_for_ambient() -> None:
    overrides = parse_cycle_overrides("turbine inlet temperature 1500 C")

    assert overrides == {"turbine_inlet_temperature_k": pytest.approx(1773.15)}


def test_find_scenarios_returns_them_in_question_order() -> None:
    assert find_scenarios("Compare warm ambient against baseline") == ["warm_ambient", "baseline"]
    assert find_scenarios("tell me about compressor fouling") == ["compressor_fouling"]
    assert find_scenarios("what is Brayton efficiency") == []


def test_parse_seed_defaults_and_bounds() -> None:
    assert parse_seed("use seed 7") == 7
    assert parse_seed("no seed here") == 42
    assert parse_seed("seed 99999999999") == 42


def test_selection_and_run_wording() -> None:
    assert refers_to_selection("What does the residual mean?")
    assert not refers_to_selection("What if the pressure ratio were 18?")
    assert refers_explicitly_to_selection("explain this sample")
    assert refers_explicitly_to_selection("metrics at sample 48")
    assert not refers_explicitly_to_selection("explain the residual")
    assert refers_to_whole_run("How many samples are flagged?")
    assert refers_to_whole_run("Summarise the whole run")
    assert not refers_to_whole_run("Explain this sample")
