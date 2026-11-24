"""WP4 health estimation: observability, the unscented Kalman filter and twin mismatch."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from turbineiq.engineering import CALIBRATED_6B03
from turbineiq.estimation import run_streams
from turbineiq.estimation.mismatch import MISMATCHES, steady_bias, twin_for
from turbineiq.estimation.observability import analyse, steady_observation
from turbineiq.estimation.ukf import (
    FuelInputModel,
    HealthEstimate,
    PowerInputModel,
    UKFHealthEstimator,
)
from turbineiq.simulation.maps import CLEAN, Health, engine_health_maps, health_maps
from turbineiq.simulation.scenarios import scenario

FOULING_3 = Health(-0.03, -0.015, 0.0)


@pytest.fixture(scope="module")
def fouling_streams():
    # 3 % fouling at 1800 s, 35 MW; 25 minutes of fouled operation are enough to converge.
    return run_streams(scenario("fouling_step_part_load"), until_s=3300.0)


@pytest.fixture(scope="module")
def fouling_estimates(fouling_streams):
    observations, _ = fouling_streams
    estimator = UKFHealthEstimator()
    return [estimator.update(obs) for obs in observations]


def test_engine_maps_reproduce_the_default_maps_for_the_calibrated_engine():
    mine, default = engine_health_maps(CALIBRATED_6B03, 15.0), health_maps(15.0)
    assert mine.clean == default.clean
    assert mine._sensitivity == default._sensitivity


def test_the_two_formulations_carry_the_same_information():
    obs = steady_observation(15.0, 35.0)
    fuel, power = analyse(FuelInputModel(), obs), analyse(PowerInputModel(), obs)
    np.testing.assert_allclose(fuel.singular_values, power.singular_values, rtol=1e-4)
    assert fuel.condition_number < 10.0
    # Every parameter is observable from one sample to better than 0.3 point (1 sigma) ...
    assert np.all(power.crb_std < 0.3)
    # ... and ignoring the residual correlation costs the power-input form far less.
    assert power.diag_std[2] < fuel.diag_std[2]
    assert power.diag_std[2] / power.crb_std[2] < 1.05


def test_power_input_model_inverts_the_twin():
    obs = steady_observation(15.0, 35.0, FOULING_3)
    predicted = PowerInputModel().predict(FOULING_3, obs)
    assert predicted[0] == pytest.approx(obs.fuel_kg_s, rel=1e-6)
    np.testing.assert_allclose(predicted[1:], (obs.exhaust_k, obs.cdt_k, obs.cdp_kpa), atol=1e-6)


def test_no_estimate_before_steady_data_and_none_ahead_of_time(fouling_streams):
    observations, _ = fouling_streams
    estimator = UKFHealthEstimator()
    first = None
    for obs in observations[:900]:
        out = estimator.update(obs)
        if out is not None:
            assert isinstance(out, HealthEstimate) and out.t_s == obs.t_s
            first = first or out
    assert first is not None and first.t_s >= 420.0  # loaded, then a full quiet window
    assert dataclasses.is_dataclass(first)
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.t_s = 0.0  # type: ignore[misc]


def test_tracks_a_fouling_step_without_mismatch(fouling_streams, fouling_estimates):
    _, truths = fouling_streams
    pairs = [(e, t) for e, t in zip(fouling_estimates, truths, strict=True) if e and e.steady]
    clean = [np.subtract(e.mean, t.health) for e, t in pairs if 900.0 <= e.t_s < 1800.0]
    fouled = [np.subtract(e.mean, t.health) for e, t in pairs if e.t_s >= 2700.0]
    assert clean and fouled
    for errors in (np.array(clean), np.array(fouled)):
        assert np.max(np.abs(errors[:, 0])) < 0.006  # flow capacity within 0.6 %
        assert np.max(np.abs(errors[:, 1:])) < 0.003  # efficiencies within 0.3 point
    last = fouling_estimates[-1]
    assert last.std.compressor_efficiency < 0.001
    assert abs(last.mean.compressor_efficiency - FOULING_3.compressor_efficiency) < 0.002


def test_a_mismatched_twin_biases_the_estimate_as_predicted(fouling_streams):
    observations, truths = fouling_streams
    twin = twin_for("combined")
    predicted = steady_bias(twin, 15.0, 35.0, FOULING_3).bias
    estimator = UKFHealthEstimator(twin=twin)
    errors = [
        np.subtract(e.mean, t.health)
        for obs, t in zip(observations, truths, strict=True)
        if (e := estimator.update(obs)) is not None and e.steady and e.t_s >= 2700.0
    ]
    np.testing.assert_allclose(np.mean(errors, axis=0), predicted, atol=0.0005)
    assert abs(predicted[0]) > 0.003  # the mismatch is not negligible for flow capacity


def test_cooling_flow_is_invisible_to_the_map_model():
    # Cooling air bypasses the combustor and is mixed back before the turbine, so at a
    # given fuel flow the cycle does not change: no bias, whatever the cooling fraction.
    bias = steady_bias(twin_for("cooling"), 15.0, 35.0, CLEAN).bias
    assert np.max(np.abs(bias)) < 1e-4
    assert MISMATCHES["exhaust_loss"].engine().exhaust_pressure_loss_fraction == pytest.approx(
        0.015
    )
