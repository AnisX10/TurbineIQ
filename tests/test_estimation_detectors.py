"""WP4 baseline detectors: residual screen, per-channel CUSUM, MEWMA and pattern isolation.

The scenario runs here use tuning-range seeds (1000-1999) and short horizons; the
evaluation numbers in docs/FAULT_DETECTION.md come from the bank seeds and seed + 10000 k.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from turbineiq.estimation import run_streams
from turbineiq.estimation.detectors import (
    CHANNELS,
    TUNED_NOISE,
    CusumCore,
    CusumDetector,
    DetectorOutput,
    GatedResiduals,
    MewmaCore,
    MewmaDetector,
    NoiseModel,
    PatternIsolator,
    ResidualScreen,
    ScreenCore,
    bootstrap_signal_rate,
    classify_pattern,
)
from turbineiq.simulation.scenarios import ONSET_S, scenario

FACTORIES = {"screen": ResidualScreen, "cusum": CusumDetector, "mewma": MewmaDetector}


def _run(scenario_id: str, seed: int, until_s: float):
    observations, _ = run_streams(scenario(scenario_id), seed=seed, until_s=until_s)
    source = GatedResiduals()
    detectors = {name: make(source=source) for name, make in FACTORIES.items()}
    isolator = PatternIsolator(detectors["cusum"])
    outputs: dict[str, list[DetectorOutput]] = {name: [] for name in detectors}
    for obs in observations:
        outputs["cusum"].append(isolator.update(obs))
        for name in ("screen", "mewma"):
            outputs[name].append(detectors[name].update(obs))
    return observations, outputs, isolator


@pytest.fixture(scope="module")
def clean_run():
    return _run("clean_load_cycling", 1500, 3000.0)


@pytest.fixture(scope="module")
def fouling_run():
    return _run("fouling_step_part_load", 1501, 2500.0)


@pytest.fixture(scope="module")
def cdp_run():
    return _run("cdp_sensor_bias", 1502, 2400.0)


def _first_alarm(outputs: list[DetectorOutput], after_s: float = 0.0) -> DetectorOutput | None:
    return next((o for o in outputs if o.alarm and o.t_s >= after_s), None)


def test_outputs_are_causal_and_silent_while_the_gate_is_closed(clean_run):
    observations, outputs, _ = clean_run
    for name, series in outputs.items():
        assert [o.t_s for o in series] == [obs.t_s for obs in observations], name
        # Start-up: the unit loads at about 300 s and the gate needs 120 s of quiet data.
        assert all(o.channel is None and not o.alarm for o in series if o.t_s < 400.0), name
    with pytest.raises(dataclasses.FrozenInstanceError):
        outputs["cusum"][0].alarm = True  # type: ignore[misc]


def test_no_detector_signals_on_a_healthy_load_cycling_run(clean_run):
    _, outputs, isolator = clean_run
    for name, series in outputs.items():
        assert _first_alarm(series) is None, name
    assert isolator.label is None


def test_every_detector_sees_three_percent_fouling_within_minutes(fouling_run):
    _, outputs, _ = fouling_run
    delays = {}
    for name, series in outputs.items():
        assert _first_alarm(series, after_s=0.0).t_s >= ONSET_S, name  # nothing before onset
        delays[name] = _first_alarm(series, after_s=ONSET_S).t_s - ONSET_S
        assert delays[name] <= 400.0, (name, delays[name])
    # The discharge pressure drops at once, so the MEWMA fires in the first samples; the
    # exhaust rise then shuts the gate for about one window (120 s) before the per-channel
    # detectors have accumulated enough.
    assert delays["mewma"] <= 10.0
    assert delays["cusum"] >= 100.0 and delays["screen"] >= 100.0


def test_fouling_is_isolated_from_the_channel_pattern(fouling_run):
    _, _, isolator = fouling_run
    assert isolator.label == "compressor_fouling"
    votes = isolator.votes
    assert votes.get("cdp_kpa", 0) < 0 and votes.get("exhaust_k", 0) > 0


def test_a_discharge_pressure_sensor_bias_is_not_called_fouling(cdp_run):
    _, outputs, isolator = cdp_run
    first = _first_alarm(outputs["cusum"], after_s=ONSET_S)
    # The gate stays open through a sensor step, so the CUSUM sees it within seconds.
    assert first is not None and first.t_s - ONSET_S <= 10.0 and first.channel == "cdp_kpa"
    assert isolator.label == "cdp_sensor"


@pytest.mark.parametrize(
    ("signs", "label"),
    [
        ({"power_mw": -1, "exhaust_k": 1, "cdt_k": 1, "cdp_kpa": -1}, "compressor_fouling"),
        ({"exhaust_k": 1, "cdp_kpa": -1}, "compressor_fouling"),
        ({"power_mw": -1, "exhaust_k": 1}, "turbine_erosion"),
        ({"power_mw": -1, "exhaust_k": -1}, "fuel_meter"),
        ({"power_mw": 1}, "power_sensor"),
        ({"exhaust_k": -1}, "exhaust_sensor"),
        ({"cdt_k": 1}, "cdt_sensor"),
        ({"cdp_kpa": -1}, "cdp_sensor"),
        ({"cdt_k": 1, "power_mw": 1}, "unknown"),
        ({}, "unknown"),
    ],
)
def test_classify_pattern(signs, label):
    assert classify_pattern(signs) == label


def test_cusum_core_signals_a_shift_and_renews_the_channel():
    core = CusumCore(threshold=5.0, slack=0.5)
    z = np.array([0.0, 0.0, 2.0, 0.0])  # 2 sigma on cdt_k: 1.5 per sample net of slack
    steps = [core.step(z) for _ in range(4)]
    assert [bool(s.signal) for s in steps] == [False, False, False, True]
    assert CHANNELS[int(steps[-1].channel)] == "cdt_k" and int(steps[-1].direction) == 1
    assert core.upper[2] == 0.0  # renewed after the signal
    # A single huge spike is clipped and cannot trigger it alone.
    assert not CusumCore(threshold=5.0, slack=0.5).step(np.array([0.0, 50.0, 0.0, 0.0])).signal


def test_screen_needs_persistence_on_one_side():
    core = ScreenCore(threshold=3.0, window=1, persistence=3)
    flips = [np.array([4.0, 0, 0, 0]), np.array([-4.0, 0, 0, 0])] * 3
    assert not any(bool(core.step(z).signal) for z in flips)
    held = [bool(core.step(np.array([0, 0, 0, -4.0])).signal) for _ in range(3)]
    assert held == [False, False, True]


def test_batched_cores_match_single_chains():
    rng = np.random.default_rng(3)
    z = rng.normal(size=(200, 3, 4)) + np.array([0.0, 0.3, 0.0, -0.4])
    whitener = TUNED_NOISE.whitener()
    for make in (
        lambda shape: ScreenCore(2.5, 10, 3, shape),
        lambda shape: CusumCore(6.0, 0.5, 4.0, shape),
        lambda shape: MewmaCore(12.0, 0.1, whitener, shape),
    ):
        batch = make((3,))
        singles = [make(()) for _ in range(3)]
        for row in z:
            b = batch.step(row)
            for j, single in enumerate(singles):
                s = single.step(row[j])
                assert bool(s.signal) == bool(b.signal[j])
                assert float(s.statistic) == pytest.approx(float(b.statistic[j]))


def test_noise_model_fit_recovers_a_fuel_dependent_scale():
    rng = np.random.default_rng(7)
    fuel = np.repeat([1.7, 2.2, 2.8], 4000)
    scale = np.array([0.1, 0.8, 0.0, 0.0]) * fuel[:, None] + np.array([0.0, 0.5, 0.6, 3.4])
    residuals = rng.normal(size=(len(fuel), 4)) * scale
    model = NoiseModel.fit(residuals, fuel)
    assert np.allclose(model.per_fuel[:2], [0.1, 0.8], atol=0.04)
    for level in (0, 4000, 8000):
        assert np.allclose(model.scale(fuel[level]), scale[level], rtol=0.04)
    z = model.standardize(residuals, fuel)
    assert np.allclose(z.std(axis=0), 1.0, atol=0.05)


def test_default_thresholds_hold_the_target_rate_on_gaussian_noise():
    # Independent unit-normal rows with the tuned correlation: the defaults were set for
    # 0.01 signals per steady hour, so 2000 simulated hours give about 20 at most.
    rng = np.random.default_rng(11)
    rows = rng.normal(size=(200_000, 4)) @ np.linalg.cholesky(TUNED_NOISE.correlation).T
    detector_cores = {
        "screen": ResidualScreen().core,
        "cusum": CusumDetector().core,
        "mewma": MewmaDetector().core,
    }
    for name, core in detector_cores.items():
        signals, hours = bootstrap_signal_rate(
            lambda shape, c=core: _like(c, shape), rows, hours=2000.0, chains=500, seed=5
        )
        assert signals / hours < 0.05, name


def _like(core, shape):
    if isinstance(core, ScreenCore):
        return ScreenCore(core.threshold, core.window, core.persistence, shape)
    if isinstance(core, CusumCore):
        return CusumCore(core.threshold, core.slack, core.clip, shape)
    return MewmaCore(core.threshold, core.smoothing, core.whitener, shape)
