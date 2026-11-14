import pytest

from turbineiq.engineering import CycleInputs, compare_to_published, simulate_cycle


def _rows(report: dict[str, object]) -> dict[str, dict[str, object]]:
    return {row["key"]: row for row in report["rows"]}  # type: ignore[index, union-attr]


def test_comparison_reports_published_values_exactly():
    rows = _rows(compare_to_published())
    assert rows["net_output"]["published"] == 45.0
    assert rows["lhv_efficiency"]["published"] == 33.4
    assert rows["pressure_ratio"]["published"] == 12.8
    assert rows["exhaust_temperature"]["published"] == 561.0
    assert rows["exhaust_flow"]["published"] == 145.1


def test_comparison_matches_a_direct_model_run():
    inputs = CycleInputs()
    result = simulate_cycle(inputs)
    rows = _rows(compare_to_published(inputs))
    assert rows["net_output"]["model"] == pytest.approx(result.electrical_power_kw / 1000)
    assert rows["exhaust_temperature"]["model"] == pytest.approx(
        result.states[3].temperature_k - 273.15
    )
    assert rows["exhaust_flow"]["model"] == pytest.approx(
        inputs.air_mass_flow_kg_s + result.fuel_mass_flow_kg_s
    )
    assert rows["pressure_ratio"]["model"] == inputs.pressure_ratio


def test_difference_fields_are_consistent():
    for row in compare_to_published()["rows"]:  # type: ignore[union-attr]
        assert row["difference"] == pytest.approx(row["model"] - row["published"])
        expected = row["difference"] / row["published"] * 100
        assert row["difference_percent"] == pytest.approx(expected)


def test_the_gap_is_stated_not_hidden():
    report = compare_to_published()
    rows = _rows(report)
    assert report["calibrated"] is False
    assert "uncalibrated" in str(report["statement"])
    # Guard: if the model is ever recalibrated, this test must change together with the label.
    assert rows["net_output"]["difference_percent"] < -30
