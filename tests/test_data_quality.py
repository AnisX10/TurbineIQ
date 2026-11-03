import pytest

from turbineiq.analytics import assess_data_quality, detect_anomalies
from turbineiq.synthetic import generate_scenario


def test_generated_baseline_passes_quality_checks() -> None:
    frame = generate_scenario("baseline", seed=42, samples=32)

    report = assess_data_quality(frame)

    assert report.passes
    assert report.row_count == 32
    assert report.missing_cells == 0
    assert report.duplicate_timestamps == 0
    assert report.non_synthetic_rows == 0
    assert report.to_dict()["passes"] is True


def test_quality_report_finds_missing_duplicate_order_and_invalid_values() -> None:
    frame = generate_scenario("baseline", seed=42, samples=24)
    frame.loc[0, "observed_electrical_power_kw"] = float("nan")
    frame.loc[1, "ambient_pressure_kpa"] = -1
    frame.loc[2, "timestamp_utc"] = frame.loc[0, "timestamp_utc"]

    report = assess_data_quality(frame)

    assert not report.passes
    assert report.missing_cells == 1
    assert report.duplicate_timestamps == 1
    assert report.out_of_order_timestamps >= 1
    assert report.invalid_numeric_counts["ambient_pressure_kpa"] == 1


def test_quality_report_finds_flatline_and_missing_synthetic_label() -> None:
    frame = generate_scenario("baseline", seed=7, samples=16)
    frame["observed_electrical_power_kw"] = 25.0
    frame = frame.drop(columns="synthetic_data")

    report = assess_data_quality(frame)

    assert "observed_electrical_power_kw" in report.flatline_columns
    assert report.non_synthetic_rows == len(frame)
    assert any("no synthetic_data label" in finding for finding in report.findings)


def test_robust_detector_flags_injected_sensor_spike_without_reading_label() -> None:
    frame = generate_scenario("sensor_fault", seed=42, samples=96)
    flagged = detect_anomalies(frame, column="power_residual_kw")

    fault_index = frame.index[frame["sensor_fault_injected"]][0]
    assert bool(flagged.loc[fault_index, "anomaly_flag"])
    assert flagged.loc[fault_index, "robust_z_score"] > 3.5
    assert "anomaly_method" in flagged


@pytest.mark.parametrize(("column", "threshold"), [("missing", 3.5), ("power_residual_kw", 0)])
def test_anomaly_detector_rejects_missing_column_or_bad_threshold(
    column: str, threshold: float
) -> None:
    frame = generate_scenario("baseline", seed=1, samples=16)

    with pytest.raises(ValueError):
        detect_anomalies(frame, column=column, threshold=threshold)
