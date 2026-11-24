"""WP4: fault detection from the UKF health estimate (HealthShiftDetector)."""

from __future__ import annotations

import numpy as np
import pytest

from turbineiq.estimation import Observation, run_streams
from turbineiq.estimation.health_detector import (
    HealthShiftDetector,
    classify_shift,
    wald_statistic,
)
from turbineiq.simulation.scenarios import Scenario, ScriptStep


def _obs(t):
    return Observation(t, "loaded", True, 35.0, 15.0, 1.0, 35.0, 800.0, 1.0, 600.0, 1000.0, 2.0)


class _Stub:
    """An estimator stand-in that makes one measurement update per observation."""

    def __init__(self, means, std=0.001):
        self._means = iter(means)
        self.updates = 0
        self.x = np.zeros(3)
        self.P = np.eye(3) * std**2

    def update(self, obs):
        self.x = np.asarray(next(self._means), dtype=float)
        self.updates += 1


def test_wald_statistic_and_shift_labels():
    cov = np.diag([4.0, 1.0, 1.0])
    assert wald_statistic(np.array([2.0, 1.0, 0.0]), cov) == pytest.approx(2.0)
    std = np.array([0.0003, 0.00015, 0.00015])
    assert classify_shift(np.array([-0.03, -0.015, 0.0]), std) == "compressor_fouling"
    assert classify_shift(np.array([0.0, 0.0, -0.015]), std) == "turbine_erosion"
    assert classify_shift(np.array([0.0, 0.004, 0.0]), std) == "unexplained"


def test_alarm_needs_persistence_and_clears_below_the_threshold():
    big, small = (0.0, 0.0, -0.01), (0.0, 0.0, 0.0)  # d2 = 100 vs 0 with std 0.001
    sequence = [big, big, small, big, big, big, small]
    detector = HealthShiftDetector(threshold=25.0, persist=3, estimator=_Stub(sequence))
    alarms = [detector.update(_obs(float(t))).alarm for t in range(len(sequence))]
    assert alarms == [False, False, False, False, False, True, False]
    assert detector.label == "turbine_erosion"
    with pytest.raises(ValueError):
        HealthShiftDetector(threshold=0.0)


def test_holds_its_output_between_estimator_updates():
    stub = _Stub([(0.0, 0.0, -0.01)])
    detector = HealthShiftDetector(threshold=25.0, persist=1, estimator=stub)
    first = detector.update(_obs(0.0))
    stub.update = lambda obs: None  # no new measurement update
    second = detector.update(_obs(1.0))
    assert first.alarm and second.alarm and second.statistic == first.statistic
    assert second.channel == "turbine_efficiency"


# A short scenario: loaded from about 237 s, 3 percent fouling at 600 s, end at 1,200 s.
SHORT = Scenario(
    "short_fouling",
    "degradation",
    "Test scenario: 3 percent fouling at 600 s.",
    77,
    1200.0,
    (
        ScriptStep(0.0, "start"),
        ScriptStep(300.0, "set_load", {"mw": 35.0, "ramp_mw_per_min": 60.0}),
        ScriptStep(
            600.0,
            "inject_degradation",
            {"kind": "compressor_fouling", "severity_pct": 3.0, "rate_pct_per_h": None},
        ),
    ),
)


def test_detects_and_labels_a_fouling_step_on_a_simulated_run():
    observations, _ = run_streams(SHORT, 1000)
    detector = HealthShiftDetector()
    outputs = [detector.update(obs) for obs in observations]
    before = [o for o in outputs if o.t_s < 600.0]
    after = [o for o in outputs if o.t_s >= 600.0 and o.alarm]
    assert not any(o.alarm for o in before)
    assert after, "the fouling step was not detected"
    # The gate is closed for about two minutes after the step; detection follows soon after.
    assert after[0].t_s - 600.0 < 300.0
    assert detector.label == "compressor_fouling"
