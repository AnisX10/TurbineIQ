import pandas as pd
import pytest

from turbineiq.synthetic import generate_scenario


def test_baseline_is_repeatable_with_same_seed() -> None:
    first = generate_scenario("baseline", seed=17, samples=32)
    second = generate_scenario("baseline", seed=17, samples=32)

    pd.testing.assert_frame_equal(first, second)
    assert first.attrs["seed"] == 17
    assert first["synthetic_data"].all()
    assert not first["sensor_fault_injected"].any()


def test_new_seed_changes_only_reproducible_measurement_noise() -> None:
    first = generate_scenario("baseline", seed=1, samples=32)
    second = generate_scenario("baseline", seed=2, samples=32)

    assert not first["observed_electrical_power_kw"].equals(second["observed_electrical_power_kw"])
    pd.testing.assert_series_equal(
        first["model_electrical_power_kw"], second["model_electrical_power_kw"]
    )


def test_warmer_ambient_scenario_reduces_mean_model_output() -> None:
    baseline = generate_scenario("baseline", seed=42, samples=96)
    warmer = generate_scenario("warm_ambient", seed=42, samples=96)

    assert warmer["ambient_temperature_c"].mean() > baseline["ambient_temperature_c"].mean()
    assert warmer["model_electrical_power_kw"].mean() < baseline["model_electrical_power_kw"].mean()
    assert warmer.attrs["synthetic_only"] is True


def test_compressor_efficiency_perturbation_is_explicit_and_modelled() -> None:
    baseline = generate_scenario("baseline", seed=42, samples=96)
    drift = generate_scenario("compressor_fouling", seed=42, samples=96)

    assert (
        drift["synthetic_true_compressor_efficiency"].iloc[-1]
        < drift["synthetic_true_compressor_efficiency"].iloc[0]
    )
    assert drift["compressor_efficiency_assumption"].nunique() == 1
    pd.testing.assert_series_equal(
        drift["model_electrical_power_kw"], baseline["model_electrical_power_kw"]
    )
    assert (
        drift["synthetic_truth_electrical_power_kw"].mean()
        < baseline["synthetic_truth_electrical_power_kw"].mean()
    )
    assert drift["power_residual_kw"].iloc[-1] < drift["power_residual_kw"].iloc[0]
    assert "not a real fault signature" in drift.attrs["scenario_description"]


def test_sensor_fault_is_one_labelled_measurement_perturbation() -> None:
    frame = generate_scenario("sensor_fault", seed=42, samples=48)
    baseline = generate_scenario("baseline", seed=42, samples=48)

    assert frame["sensor_fault_injected"].sum() == 1
    fault = frame.loc[frame["sensor_fault_injected"]].iloc[0]
    assert fault["sensor_fault_label"] == "power_sensor_spike"
    assert fault["observed_electrical_power_kw"] > fault["model_electrical_power_kw"]
    pd.testing.assert_series_equal(
        frame["model_electrical_power_kw"], baseline["model_electrical_power_kw"]
    )
    assert fault["exhaust_temperature_k"] == pytest.approx(
        baseline.loc[frame.index[frame["sensor_fault_injected"]][0], "exhaust_temperature_k"]
    )


@pytest.mark.parametrize(
    ("scenario_id", "seed", "samples"),
    [("unknown", 42, 96), ("baseline", -1, 96), ("baseline", 42, 7)],
)
def test_bad_scenario_options_are_rejected(scenario_id: str, seed: int, samples: int) -> None:
    with pytest.raises(ValueError):
        generate_scenario(scenario_id, seed=seed, samples=samples)
