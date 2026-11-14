import pytest

from turbineiq.analytics import assess_data_quality, detect_anomalies, detect_drift, screen_residual
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


SEEDS = range(25)


def _first_drift_index(scenario_id: str, seed: int) -> int | None:
    flagged = detect_drift(generate_scenario(scenario_id, seed=seed, samples=96))
    indexes = flagged.index[flagged["drift_flag"]]
    return int(indexes[0]) if len(indexes) else None


def test_global_mad_screen_misses_the_slow_compressor_drift() -> None:
    """The original screen cannot see a ramp; this documents why drift needs its own detector."""

    frame = generate_scenario("compressor_fouling", seed=42, samples=96)

    assert not detect_anomalies(frame)["anomaly_flag"].any()
    assert frame["power_residual_kw"].min() < -2000


@pytest.mark.parametrize("seed", SEEDS)
def test_drift_detector_catches_compressor_drift_early(seed: int) -> None:
    first = _first_drift_index("compressor_fouling", seed)

    assert first is not None
    assert 16 <= first <= 40


@pytest.mark.parametrize("scenario_id", ["baseline", "warm_ambient", "sensor_fault"])
def test_drift_detector_has_no_false_alarms_on_clean_or_spike_scenarios(scenario_id: str) -> None:
    for seed in SEEDS:
        assert _first_drift_index(scenario_id, seed) is None, (scenario_id, seed)


def test_drift_detector_is_causal() -> None:
    frame = generate_scenario("compressor_fouling", seed=42, samples=96)
    full = detect_drift(frame)
    truncated = detect_drift(frame.iloc[:50])

    assert truncated["drift_flag"].tolist() == full["drift_flag"].iloc[:50].tolist()
    assert truncated["drift_score"].tolist() == pytest.approx(full["drift_score"].iloc[:50])


def test_drift_detector_reports_direction_and_never_flags_warmup() -> None:
    flagged = detect_drift(generate_scenario("compressor_fouling", seed=7, samples=96))

    assert not flagged["drift_flag"].iloc[:16].any()
    assert set(flagged.loc[flagged["drift_flag"], "drift_direction"]) == {"below reference"}
    assert (flagged["drift_score"] >= 0).all()


def test_drift_detector_handles_short_frames_without_flags() -> None:
    result = detect_drift(generate_scenario("compressor_fouling", seed=1, samples=12))

    assert not result["drift_flag"].any()


def test_screen_residual_labels_spikes_and_drift_separately() -> None:
    spike = screen_residual(generate_scenario("sensor_fault", seed=42, samples=96))
    drift = screen_residual(generate_scenario("compressor_fouling", seed=42, samples=96))

    assert set(spike.loc[spike["anomaly_flag"], "screen_reason"]) == {"spike"}
    assert drift["spike_flag"].sum() == 0
    assert set(drift.loc[drift["anomaly_flag"], "screen_reason"]) == {"drift"}
    assert drift["anomaly_flag"].sum() > 50


@pytest.mark.parametrize(
    "kwargs",
    [
        {"column": "missing"},
        {"warmup_samples": 2},
        {"slack": 0},
        {"decision_threshold": -1},
        {"noise_inflation": 0},
    ],
)
def test_drift_detector_rejects_bad_arguments(kwargs: dict) -> None:
    frame = generate_scenario("baseline", seed=1, samples=32)

    with pytest.raises(ValueError):
        detect_drift(frame, **kwargs)
