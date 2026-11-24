"""Fault detection from the online health estimate (roadmap WP4, research question RQ2).

RQ2 asks whether online health estimation detects degradation earlier than residual and
CUSUM screens at an equal false-alarm rate. :class:`HealthShiftDetector` is the detector on
the estimator's side of that comparison. It runs a
:class:`~turbineiq.estimation.ukf.UKFHealthEstimator` and, after each measurement update,
tests whether the estimated health has left the clean engine, with the Wald statistic

    d2 = x' P^-1 x

where ``x`` is the posterior mean of the three health deltas and ``P`` its covariance. The
alarm is on while ``d2`` has exceeded ``threshold`` for ``persist`` consecutive updates.
Between updates (gate closed: start-up, load and ambient changes) the alarm and statistic
are held, so, like the residual detectors, it cannot signal during transients.

When the alarm is on, :attr:`HealthShiftDetector.label` names the degradation kind whose
signature the estimate matches: ``turbine_erosion`` when the turbine-efficiency loss
dominates (in standard deviations), ``compressor_fouling`` when the compressor flow or
efficiency loss dominates, and ``unexplained`` when the dominant shift is an improvement,
which no modelled degradation produces (a sensor fault can). The estimator cannot see a
sensor fault as such: a bias on an output it explains with health absorbs into the health
estimate (see ``docs/HEALTH_ESTIMATION.md``), so the label of a sensor fault is wrong by
construction. ``channel`` is the health parameter that leads the statistic, not a sensor.

The default threshold was set on healthy tuning streams only (the five ``clean_*``
scenarios, seeds 1000-1019) for the same design false-alarm rate as the residual
detectors, one per 100 steady hours; see :data:`DEFAULT_THRESHOLD` and
``docs/WP4_RESULTS.md``. On those streams ``d2`` has a median of about 1.3, below the 2.4
of a chi-square with three degrees of freedom: the filter's covariance includes the
random-walk process noise, which healthy runs do not have, so it is conservative.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import Observation
from .ukf import HEALTH_NAMES, UKFHealthEstimator, UKFSettings

#: Wald threshold and persistence (consecutive 10 s updates); see the module docstring.
#: On 100 healthy tuning streams (179.5 steady hours) with persistence 3 the alarm rate was
#: 0.37 per hour at 6.0, 0.10 at 7.0, 0.017 at 8.0 and zero from 8.5; a log-linear fit of
#: the tail puts 0.01 per hour at 8.4, so 8.5 is the design point for 0.01 per hour.
DEFAULT_THRESHOLD = 8.5
DEFAULT_PERSIST = 3


@dataclass(frozen=True)
class HealthShiftOutput:
    t_s: float
    alarm: bool
    statistic: float  # Wald statistic d2 of the latest update (NaN before the first)
    channel: str | None  # health parameter with the largest |mean| / std


def wald_statistic(mean: np.ndarray, cov: np.ndarray) -> float:
    """``mean' cov^-1 mean``: the squared Mahalanobis distance of the estimate from clean."""

    return float(mean @ np.linalg.solve(cov, mean))


def classify_shift(mean: np.ndarray, std: np.ndarray) -> str:
    """Degradation kind whose signature the standardised shift ``mean / std`` matches."""

    z = np.asarray(mean) / np.asarray(std)
    lead = int(np.argmax(np.abs(z)))
    if z[lead] > 0.0:
        return "unexplained"
    if HEALTH_NAMES[lead] == "turbine_efficiency":
        return "turbine_erosion"
    return "compressor_fouling"


class HealthShiftDetector:
    """Alarm when the UKF health estimate departs from the clean engine (Wald test)."""

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        persist: int = DEFAULT_PERSIST,
        *,
        estimator: UKFHealthEstimator | None = None,
        settings: UKFSettings | None = None,
    ) -> None:
        if threshold <= 0.0 or persist < 1:
            raise ValueError("threshold must be positive and persist at least 1")
        self.threshold = threshold
        self.persist = persist
        self.estimator = estimator or UKFHealthEstimator(settings)
        self._updates = 0
        self._above = 0
        self._alarm = False
        self._statistic = float("nan")
        self._channel: str | None = None
        self.label: str | None = None

    def update(self, obs: Observation) -> HealthShiftOutput:
        est = self.estimator
        est.update(obs)
        if est.updates != self._updates:
            self._updates = est.updates
            mean = est.x.copy()
            std = np.sqrt(np.clip(np.diag(est.P), 1e-30, None))
            self._statistic = wald_statistic(mean, est.P)
            self._channel = HEALTH_NAMES[int(np.argmax(np.abs(mean) / std))]
            self._above = self._above + 1 if self._statistic > self.threshold else 0
            self._alarm = self._above >= self.persist
            if self._alarm:
                self.label = classify_shift(mean, std)
        return HealthShiftOutput(obs.t_s, self._alarm, self._statistic, self._channel)
