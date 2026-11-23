"""Degradation-trend forecast: trend, gaps, steps, the cap, calibration, performance."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from turbineiq.estimation import Observation, Truth
from turbineiq.estimation.forecast import (
    DegradationForecaster,
    HealthForecast,
    OperatingPoint,
    SyntheticEstimate,
    TrendConfig,
    evaluate_run,
    exhaust_limit_k,
    forecast_performance,
    steady_performance,
    summarize_health,
    synthetic_estimates,
)
from turbineiq.estimation.twin import QuasiSteadyTwin
from turbineiq.simulation.faults import DEGRADATIONS, FOULING_EFFICIENCY_RATIO
from turbineiq.simulation.maps import HEALTH_LIMITS, Health

STD = Health(0.0015, 0.001, 0.001)


def fouling(severity: float) -> Health:
    return Health(-severity, -FOULING_EFFICIENCY_RATIO * severity, 0.0)


def noisy_series(truth_at, times, rng, std=STD):
    out = []
    for t in times:
        mean = np.asarray(truth_at(t)) + np.asarray(std) * rng.standard_normal(3)
        out.append(SyntheticEstimate(float(t), Health(*map(float, mean)), std))
    return out


WHITE = TrendConfig(persistent_fraction=0.0)  # inputs below have no persistent error


def test_a_linear_trend_is_recovered_and_forecast():
    rng = np.random.default_rng(1)
    rate = 0.03  # 3 percent per hour, as in fouling_progressive_base_load
    f = DegradationForecaster(WHITE)
    for e in noisy_series(lambda t: fouling(rate * t / 3600), range(0, 5400, 60), rng):
        f.update(e)
    assert f.rate_per_h[0] == pytest.approx(-rate, abs=3 * f.rate_std_per_h[0])
    assert f.rate_per_h[1] == pytest.approx(-rate / 2, abs=3 * f.rate_std_per_h[1])
    fc = f.forecast(3600.0)
    truth = fouling(rate * (fc.target_s) / 3600)
    for i in range(3):
        assert fc.lower[i] <= truth[i] <= fc.upper[i]
        assert fc.lower[i] <= fc.mean[i] <= fc.upper[i]
    assert abs(fc.mean[0] - truth[0]) < 0.005
    lo50, hi50 = fc.band(0.5)
    assert all(hi50[i] - lo50[i] < fc.upper[i] - fc.lower[i] for i in range(3))


def test_estimates_too_close_together_are_skipped():
    f = DegradationForecaster(TrendConfig(min_interval_s=60.0))
    e = SyntheticEstimate(0.0, Health(), STD)
    assert f.update(e) is True
    assert f.update(replace(e, t_s=30.0)) is False
    assert f.update(replace(e, t_s=60.0)) is True
    assert (f.used, f.skipped) == (2, 1)
    with pytest.raises(ValueError):
        f.forecast(-1.0)
    with pytest.raises(ValueError):
        DegradationForecaster().forecast(60.0)


def test_a_gap_widens_the_band_and_the_trend_carries_through():
    rng = np.random.default_rng(2)
    truth_at = lambda t: fouling(0.02 * t / 3600)  # noqa: E731
    f = DegradationForecaster(WHITE)
    for e in noisy_series(truth_at, range(0, 3600, 60), rng):
        f.update(e)
    before = f.forecast(0.0)
    after_gap = f.forecast(1800.0)  # a 30-minute gap with no estimates (a load change)
    assert after_gap.scale[0] > 2 * before.scale[0]
    for e in noisy_series(truth_at, range(5400, 6000, 60), rng):
        f.update(e)
    assert f.shifts == []  # a gap alone is not a step
    assert f.level[0] == pytest.approx(truth_at(5940)[0], abs=0.003)


def test_an_offline_wash_restarts_the_level_and_keeps_the_rate():
    rng = np.random.default_rng(3)
    f = DegradationForecaster(WHITE)
    for e in noisy_series(lambda t: fouling(0.03), range(0, 1800, 60), rng):
        f.update(e)
    # Shut down, washed, back at steady state 40 minutes later: fouling gone.
    for e in noisy_series(lambda t: fouling(0.0), range(4200, 4800, 60), rng):
        f.update(e)
    shifted = {name for _, name, _ in f.shifts}
    assert shifted == {"compressor_flow", "compressor_efficiency"}
    assert all(size > 0 for _, _, size in f.shifts)
    assert abs(f.rate_per_h[0]) < 0.01  # the step was not taken as a rate
    fc = f.forecast(1800.0)
    assert fc.lower[0] <= 0.0 <= fc.upper[0] and abs(fc.mean[0]) < 0.008


def test_a_single_outlier_is_dropped_not_taken_as_a_step():
    rng = np.random.default_rng(4)
    f = DegradationForecaster(WHITE)
    series = noisy_series(lambda t: Health(), range(0, 3600, 60), rng)
    series[30] = replace(series[30], mean=Health(0.05, 0.0, 0.0))
    for e in series:
        f.update(e)
    assert f.shifts == [] and f.outliers == 1
    assert abs(f.level[0]) < 0.002


def test_a_logged_wash_restarts_the_level_on_request():
    f = DegradationForecaster(WHITE)
    for t in range(0, 1800, 60):
        f.update(SyntheticEstimate(float(t), fouling(0.03), STD))
    f.reset_level()
    f.update(SyntheticEstimate(1860.0, Health(), STD))
    assert f.level[0] == 0.0 and f.level[1] == 0.0
    assert f.level[2] == pytest.approx(0.0, abs=1e-9)


def test_forecasts_stop_at_the_degradation_cap():
    assert HEALTH_LIMITS == Health(
        -DEGRADATIONS["compressor_fouling"] / 100,
        -FOULING_EFFICIENCY_RATIO * DEGRADATIONS["compressor_fouling"] / 100,
        -DEGRADATIONS["turbine_erosion"] / 100,
    )
    f = DegradationForecaster(WHITE)
    for t in range(0, 3600, 60):
        f.update(SyntheticEstimate(float(t), fouling(0.08 + 0.01 * t / 3600), STD))
    fc = f.forecast(4 * 3600.0)  # the linear trend would pass the cap
    assert fc.loc[0] < HEALTH_LIMITS[0]
    assert fc.lower[0] == HEALTH_LIMITS[0]
    assert HEALTH_LIMITS[0] <= fc.mean[0] <= fc.upper[0]
    assert (fc.sample(200, np.random.default_rng(0))[:, 0] >= HEALTH_LIMITS[0]).all()


def test_the_band_is_calibrated_when_the_error_model_holds():
    """Constant-rate trends with white noise of the reported size, and a filter whose model
    matches (almost no rate walk): 90 % bands cover about 90 %."""

    still = Health(1e-5, 1e-5, 1e-5)
    config = TrendConfig(persistent_fraction=0.0, rate_walk=still, level_walk=still)
    rng = np.random.default_rng(5)
    hits, total = 0, 0
    for _ in range(150):
        rate = rng.uniform(0.0, 0.03)
        truth_at = lambda t, r=rate: fouling(r * t / 3600)  # noqa: E731
        f = DegradationForecaster(config)
        for e in noisy_series(truth_at, range(0, 3600, 60), rng):
            f.update(e)
        fc = f.forecast(1800.0)
        truth = truth_at(fc.target_s)
        hits += sum(fc.lower[i] <= truth[i] <= fc.upper[i] for i in range(3))
        total += 3
    assert 0.85 <= hits / total <= 0.95  # 450 forecasts: binomial 2 sigma is 0.03


def _steady_streams(duration_s: float, health_at, gap=(None, None)):
    observations, truths = [], []
    for t in np.arange(0.0, duration_s + 1.0, 1.0):
        running = not (gap[0] is not None and gap[0] <= t < gap[1])
        observations.append(
            Observation(
                float(t),
                "loaded" if running else "standstill",
                running,
                35.0,
                15.0,
                1.0,
                35.0,
                800.0,
                1.0,
                650.0,
                1200.0,
                2.2,
            )
        )
        truths.append(Truth(float(t), health_at(t), "", 0.05, 35.0, 800.0, 2.2, 650.0))
    return observations, truths


def test_synthetic_estimates_follow_the_steady_state_gate_and_the_noise_model():
    obs, truths = _steady_streams(7200.0, lambda t: fouling(0.02 * t / 3600), gap=(3000, 4000))
    a = synthetic_estimates(obs, truths, seed=7)
    assert a == synthetic_estimates(obs, truths, seed=7)
    times = np.array([e.t_s for e in a])
    assert times[0] >= 120.0 and not ((times >= 3000) & (times < 4120)).any()
    assert np.all(np.diff(times) >= 60.0)
    err = np.array([np.subtract(e.mean, truths[int(e.t_s)].health) for e in a])
    assert np.abs(err.mean(axis=0)).max() < 0.004  # noise plus a slow bias, no offset
    assert 0.0008 < err[:, 1].std() < 0.003
    assert a[0].std[0] == pytest.approx(math.hypot(0.0015, 0.0010))


def test_evaluation_labels_forecasts_around_events():
    obs, truths = _steady_streams(5400.0, lambda t: fouling(0.03 * max(t - 1800.0, 0.0) / 3600))
    est = synthetic_estimates(obs, truths, seed=1)
    records, perf = evaluate_run(est, truths, run="x", events=[1800.0])
    cats = {(r.origin_s, r.horizon_s): r.category for r in records}
    assert cats[(1200.0, 1800.0)] == "event_in_horizon"
    assert cats[(2100.0, 1800.0)] == "recent_event"
    assert cats[(3600.0, 1800.0)] == "stable"
    assert perf == []
    rows = summarize_health(records)
    assert {r["parameter"] for r in rows} == {
        "compressor_flow",
        "compressor_efficiency",
        "turbine_efficiency",
    }
    assert all(0.0 <= r["cov90"] <= 1.0 and r["mae"] >= 0.0 for r in rows)


@pytest.fixture(scope="module")
def twin():
    return QuasiSteadyTwin()


def test_base_load_output_is_set_by_the_exhaust_temperature_limit(twin):
    point = OperatingPoint(load_mw=47.0)
    clean, on_limit = steady_performance(Health(), point, twin)
    assert on_limit
    assert clean.exhaust_k == pytest.approx(exhaust_limit_k(twin, 15.0), abs=1e-3)
    assert clean.power_mw == pytest.approx(46.1, abs=0.3)  # SCENARIO_BANK.md: 46.1 MW
    fouled, _ = steady_performance(fouling(0.045), point, twin)
    assert -6.0 < fouled.power_mw - clean.power_mw < -3.5  # the bank shows -4.8 MW


def test_part_load_fouling_costs_fuel_and_exhaust_temperature(twin):
    point = OperatingPoint(load_mw=35.0)
    clean, on_limit = steady_performance(Health(), point, twin)
    fouled, _ = steady_performance(fouling(0.03), point, twin)
    assert not on_limit and clean.power_mw == pytest.approx(35.0, abs=1e-6)
    assert fouled.fuel_kg_s > clean.fuel_kg_s and fouled.exhaust_k > clean.exhaust_k + 10.0


def _forecast(loc: Health, scale: Health) -> HealthForecast:
    return HealthForecast(0.0, 1800.0, 0.0, 0.9, loc, loc, loc, loc, scale, HEALTH_LIMITS)


def test_the_performance_band_comes_from_the_health_ensemble(twin):
    point = OperatingPoint(load_mw=35.0)
    sharp = forecast_performance(_forecast(fouling(0.02), Health(0.0, 0.0, 0.0)), point, twin=twin)
    exact, _ = steady_performance(fouling(0.02), point, twin)
    assert sharp.lower.fuel_kg_s == pytest.approx(exact.fuel_kg_s, abs=1e-9)
    assert sharp.upper.exhaust_k == pytest.approx(exact.exhaust_k, abs=1e-6)
    wide = forecast_performance(
        _forecast(fouling(0.02), Health(0.004, 0.002, 0.002)), point, twin=twin, n_samples=100
    )
    assert wide.lower.fuel_kg_s < exact.fuel_kg_s < wide.upper.fuel_kg_s
    assert wide.lower.exhaust_k < exact.exhaust_k < wide.upper.exhaust_k
    assert wide.on_limit_share == 0.0 and wide.samples == 100


def test_a_fault_that_starts_growing_reopens_the_rate():
    rng = np.random.default_rng(6)
    onset = 3600.0
    truth_at = lambda t: fouling(0.03 * max(t - onset, 0.0) / 3600)  # noqa: E731
    f = DegradationForecaster(WHITE)
    for e in noisy_series(truth_at, range(0, int(onset) + 1500, 60), rng):
        f.update(e)
    flow_changes = [t for t, name in f.rate_changes if name == "compressor_flow"]
    assert any(onset < t <= onset + 900 for t in flow_changes)
    assert f.rate_per_h[0] == pytest.approx(-0.03, abs=0.01)  # learned within 25 minutes
    still = TrendConfig(persistent_fraction=0.0, rate_change_sigma=math.inf)
    g = DegradationForecaster(still)
    for e in noisy_series(truth_at, range(0, int(onset) + 1500, 60), np.random.default_rng(6)):
        g.update(e)
    assert g.rate_changes == [] and g.rate_per_h[0] > f.rate_per_h[0]  # slower without it
