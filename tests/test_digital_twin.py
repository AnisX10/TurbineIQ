import pandas as pd
import pytest

from turbineiq.synthetic import generate_scenario
from turbineiq.twin import DigitalTwinRun, create_synthetic_twin


def test_synthetic_twin_tracks_model_and_observation_at_selected_sample() -> None:
    twin = create_synthetic_twin("sensor_fault", seed=42)
    snapshot = twin.snapshot_at(48)

    assert twin.asset_id == "TIQ-SYNTH-GT-001"
    assert snapshot.data_provenance == "seeded synthetic scenario"
    assert snapshot.sensor_fault_label == "power_sensor_spike"
    assert snapshot.residual_screen_flag is True
    assert snapshot.synthetic_observed_power_kw > snapshot.model_electrical_power_kw
    assert snapshot.scenario_name == "Power-sensor spike"


def test_synthetic_twin_is_repeatable_for_same_scenario_and_seed() -> None:
    first = create_synthetic_twin("warm_ambient", seed=17).snapshot_at(20)
    second = create_synthetic_twin("warm_ambient", seed=17).snapshot_at(20)

    assert first == second


def test_synthetic_twin_rejects_real_or_unlabeled_rows() -> None:
    history = generate_scenario("baseline", seed=42)
    history["synthetic_data"] = False
    analyzed = history.copy()

    with pytest.raises(ValueError, match="synthetic data only"):
        DigitalTwinRun(
            scenario_id="baseline",
            scenario_name="Baseline",
            seed=42,
            history=history,
            analyzed_history=analyzed,
        )


def test_synthetic_twin_validates_sample_index() -> None:
    twin = create_synthetic_twin(samples=8)

    with pytest.raises(ValueError, match="sample_index"):
        twin.snapshot_at(8)

    with pytest.raises(ValueError, match="sample_index"):
        twin.snapshot_at(-1)


def test_snapshot_export_is_json_friendly() -> None:
    snapshot = create_synthetic_twin().snapshot_at(0).to_dict()

    assert isinstance(snapshot["timestamp_utc"], str)
    assert isinstance(snapshot["residual_screen_flag"], bool)
    assert pd.Timestamp(snapshot["timestamp_utc"]).tzinfo is not None
    assert [component["component_id"] for component in snapshot["components"]] == [
        "inlet",
        "compressor",
        "combustor",
        "turbine",
        "shaft",
        "generator",
    ]


def test_compressor_drift_is_compared_to_fixed_reference_model() -> None:
    twin = create_synthetic_twin("compressor_fouling", seed=42)
    first = twin.snapshot_at(0)
    last = twin.snapshot_at(twin.sample_count - 1)

    assert first.compressor_efficiency_assumption == last.compressor_efficiency_assumption
    assert last.synthetic_true_compressor_efficiency < first.synthetic_true_compressor_efficiency
    assert last.synthetic_observed_power_kw < last.model_electrical_power_kw
    assert last.power_residual_kw < 0
    assert last.scenario_perturbation_label == "synthetic_compressor_efficiency_drift"

    compressor = next(item for item in last.components if item.component_id == "compressor")
    assert compressor.status == "scenario_perturbation"
    assert compressor.metrics[0].reference_value == last.compressor_efficiency_assumption


def test_run_payload_contains_timeline_and_component_provenance() -> None:
    payload = create_synthetic_twin("baseline", seed=17, samples=8).to_payload(3)

    assert payload["run"]["synthetic_only"] is True
    assert payload["run"]["sample_count"] == 8
    assert payload["snapshot"]["sample_index"] == 3
    assert len(payload["timeline"]) == 8
    compressor = next(
        component
        for component in payload["snapshot"]["components"]
        if component["component_id"] == "compressor"
    )
    assert compressor["metrics"][0]["provenance"] == "Known synthetic scenario truth"
