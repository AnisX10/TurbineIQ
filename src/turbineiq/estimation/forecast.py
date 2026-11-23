"""Forecast of component health and performance with an uncertainty band (roadmap WP4).

Input is a time series of health estimates (``t_s``, ``mean`` and ``std`` as
:class:`~turbineiq.simulation.maps.Health`), which an estimator produces only at steady
state, so it has gaps. Output is a forecast of the health some time ahead with a band at a
stated coverage, and, by propagating an ensemble through the quasi-steady twin, a band on
steady-state performance at a fixed operating point.

Trend model (one independent filter per health parameter)
    A local-linear-trend Kalman filter with state (level, rate). The rate follows a small
    random walk (the level can take one too, off by default). Time runs in hours. Why this
    rather than least squares on a sliding window: the filter takes irregular sampling and
    gaps without special cases (the prediction over a gap widens the band by the process
    noise), it gives the covariance of level and rate directly, and its forecast variance
    grows with the horizon in a stated way. A window fit needs a window length chosen against
    the same trade-off and gives no allowance for a rate change inside the horizon.

Rate changes
    Faults start and stop growing abruptly; a rate walk large enough to follow that makes
    the band several times too wide while the rate is steady. So the walk is kept small and
    the filter watches an exponentially weighted mean of its normalised innovations: when
    it leaves its expected range (``rate_change_sigma``), the rate's variance is reopened to
    its prior and the rate is re-learned from the next estimates.

Estimator errors
    Successive estimates from a filter are not independent, and part of an estimator's error
    (model mismatch, a slowly drifting sensor) does not average out at all. Two settings
    cover this: each estimate enters with variance ``variance_inflation * std**2``, and the
    forecast adds ``(persistent_fraction * std)**2`` (``std`` of the latest estimate) for the
    part of the error that stays. Estimates closer together than ``min_interval_s`` are
    skipped. These settings are tuned, not derived; see docs/DEGRADATION_FORECAST.md.

Steps (a wash) and outliers
    An estimate whose innovation is beyond ``shift_sigma`` standard deviations is held
    back. If the next ``shift_confirm - 1`` estimates are also beyond it on the same side,
    the level restarts at the first of them and the rate is kept: an offline wash removes
    the fouling but not its cause. Otherwise the held estimate is dropped as an outlier.
    The test allows for at most ``shift_test_interval_s`` of process noise, because after a
    long shutdown the predicted spread would hide the step and the update would read it as
    a rate.
    :meth:`DegradationForecaster.reset_level` does the same on request (a logged wash).

The cap
    Degradation stops at a maximum severity (:data:`~turbineiq.simulation.maps.HEALTH_LIMITS`
    matches the fault model's maxima), so forecasts are clipped there: the band edges are
    clipped and the mean is that of the clipped normal distribution. Health is not clipped
    at zero (no better than new), so that a clean parameter is not covered by construction.

Clock
    ``t_s`` can be any monotone clock. In the simulator, degradation grows only while air
    flows; with clock time the filter assumes it goes on through a shutdown, which only
    matters when the rate is not zero. Passing operating hours instead removes that.

The module also holds a documented generator of synthetic estimates (ground truth plus noise
and a random-walk bias) for use until the real estimator exists, and the evaluation used in
the write-up (``python -m turbineiq.estimation.forecast --help``). Results from synthetic
estimates say how the forecaster behaves on inputs with the stated error model, not how it
will behave on the estimator's output.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import NamedTuple, Protocol

import numpy as np

from turbineiq.simulation.maps import HEALTH_LIMITS, Health
from turbineiq.simulation.plant import PlantParameters

from .data import Observation, Truth, run_streams, split_rows
from .steady import SteadyStateGate
from .twin import QuasiSteadyTwin

PARAMETERS: tuple[str, ...] = Health._fields
_NORMAL = statistics.NormalDist()
_S_PER_H = 3600.0


class HealthEstimateLike(Protocol):
    """What the forecaster reads from an estimate (the estimator's output type fits)."""

    t_s: float
    mean: Health
    std: Health


def _z(coverage: float) -> float:
    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be between 0 and 1")
    return _NORMAL.inv_cdf(0.5 + 0.5 * coverage)


def _clipped_mean(loc: float, scale: float, floor: float) -> float:
    """Mean of max(X, floor) for X ~ N(loc, scale^2)."""

    if scale <= 0.0:
        return max(loc, floor)
    a = (floor - loc) / scale
    below = _NORMAL.cdf(a)
    return floor * below + loc * (1.0 - below) + scale * _NORMAL.pdf(a)


# ----------------------------------------------------------------------------- trend model
@dataclass(frozen=True)
class TrendConfig:
    """Settings of :class:`DegradationForecaster`. Rates are per hour.

    The defaults were chosen on synthetic estimates from the tuning seeds (1000-1002) of the
    three scenarios in docs/DEGRADATION_FORECAST.md and must be re-tuned for real estimates.
    """

    min_interval_s: float = 60.0  # estimates closer than this to the last one are skipped
    rate_prior_std: Health = Health(0.02, 0.01, 0.01)  # rate before any data, per hour
    rate_walk: Health = Health(0.005, 0.0025, 0.0025)  # rate change std over one hour, per h
    level_walk: Health = Health(0.0, 0.0, 0.0)  # level change std over one hour
    variance_inflation: float = 1.0  # estimate variance used = this * std**2
    persistent_fraction: float = 1.0  # forecast adds (this * std)**2 of the latest estimate
    shift_sigma: float = 4.0  # innovation beyond this many sigma is held as a possible step
    shift_confirm: int = 2  # this many in a row on the same side make a step (level restart)
    shift_test_interval_s: float = 600.0  # the step test counts process noise up to this gap
    rate_change_weight: float = 0.2  # weight of the newest innovation in the drift average
    rate_change_sigma: float = 2.0  # drift beyond this many of its sigma reopens the rate
    floor: Health = HEALTH_LIMITS  # the cap: maximum degradation of each parameter
    coverage: float = 0.9  # default coverage of the band
    min_std: float = 1e-5  # floor on a reported std

    def __post_init__(self) -> None:
        if self.shift_confirm < 1:
            raise ValueError("shift_confirm must be at least 1")
        if self.variance_inflation <= 0.0 or self.persistent_fraction < 0.0:
            raise ValueError("variance_inflation must be positive, persistent_fraction >= 0")
        _z(self.coverage)


class _Pending(NamedTuple):
    t_h: float
    z: float
    r: float
    sign: float


class _Trend:
    """Local-linear-trend Kalman filter for one parameter. Time in hours."""

    def __init__(self, index: int, config: TrendConfig) -> None:
        self.c = config
        self.rate_prior_var = config.rate_prior_std[index] ** 2
        self.qr = config.rate_walk[index] ** 2  # rate random walk, variance per hour
        self.ql = config.level_walk[index] ** 2  # level random walk, variance per hour
        a = config.rate_change_weight
        self.drift_limit = config.rate_change_sigma * math.sqrt(a / (2.0 - a))
        self.drift = 0.0  # exponentially weighted mean of normalised innovations
        self.rate_changes: list[float] = []  # times (h) at which the rate was reopened
        self.t_h: float | None = None
        self.x = [0.0, 0.0]  # level, rate
        self.p = [0.0, 0.0, 0.0]  # P00, P01, P11
        self.restart_level = True  # the next estimate (re)initialises the level
        self.pending: list[_Pending] = []
        self.shifts: list[tuple[float, float]] = []  # (t_h, size)
        self.outliers = 0

    def predicted(self, t_h: float, max_dt: float = math.inf) -> tuple[list[float], list[float]]:
        """State and covariance (P00, P01, P11) at ``t_h``; the covariance is propagated
        over at most ``max_dt`` hours (used by the step test only)."""

        assert self.t_h is not None
        dt = t_h - self.t_h
        x0, x1 = self.x
        p00, p01, p11 = self.p
        qr, ql = self.qr, self.ql
        d = min(dt, max_dt)
        return (
            [x0 + dt * x1, x1],
            [
                p00 + 2.0 * d * p01 + d * d * p11 + qr * d**3 / 3.0 + ql * d,
                p01 + d * p11 + qr * d * d / 2.0,
                p11 + qr * d,
            ],
        )

    def _init_level(self, t_h: float, z: float, r: float) -> None:
        if self.t_h is None:
            rate, rate_var = 0.0, self.rate_prior_var
        else:
            x, p = self.predicted(t_h)
            rate, rate_var = x[1], p[2]
        self.t_h, self.x, self.p = t_h, [z, rate], [r, 0.0, rate_var]
        self.restart_level = False
        self.drift = 0.0

    def _correct(self, t_h: float, z: float, r: float) -> None:
        x, p = self.predicted(t_h)
        p00, p01, p11 = p
        s = p00 + r
        k0, k1 = p00 / s, p01 / s
        nu = z - x[0]
        self.t_h = t_h
        self.x = [x[0] + k0 * nu, x[1] + k1 * nu]
        self.p = [p00 * r / s, p01 * r / s, p11 - k1 * p01]
        # Rate change: innovations that keep one sign mean the rate is out of date (a fault
        # started or stopped growing). Then the rate's variance is reopened to its prior, so
        # the filter re-learns it in minutes while the rate walk can stay small.
        a = self.c.rate_change_weight
        self.drift = (1.0 - a) * self.drift + a * nu / math.sqrt(s)
        if abs(self.drift) > self.drift_limit:
            self.p[2] += self.rate_prior_var
            self.drift = 0.0
            self.rate_changes.append(t_h)

    def update(self, t_h: float, z: float, r: float) -> str:
        shift_sigma, confirm = self.c.shift_sigma, self.c.shift_confirm
        test_dt = self.c.shift_test_interval_s / _S_PER_H
        if self.restart_level:
            self._init_level(t_h, z, r)
            return "init"
        # The step test: a long gap would widen the prediction enough to hide a step (a
        # wash during a shutdown), and the update would then take the step as a rate. So
        # the test allows for at most ``test_dt`` of process noise.
        x, p = self.predicted(t_h, test_dt)
        nu = z - x[0]
        if abs(nu) <= shift_sigma * math.sqrt(p[0] + r):
            self.outliers += len(self.pending)
            self.pending.clear()
            self._correct(t_h, z, r)
            return "update"
        sign = 1.0 if nu > 0.0 else -1.0
        if self.pending and self.pending[0].sign != sign:
            self.outliers += len(self.pending)
            self.pending.clear()
        self.pending.append(_Pending(t_h, z, r, sign))
        if len(self.pending) < confirm:
            return "pending"
        first, *rest = self.pending
        self.pending = []
        before = self.predicted(first.t_h)[0][0]
        self._init_level(first.t_h, first.z, first.r)
        self.shifts.append((first.t_h, first.z - before))
        for item in rest:
            self._correct(item.t_h, item.z, item.r)
        return "shift"

    def forecast(self, t_h: float) -> tuple[float, float]:
        x, p = self.predicted(t_h)
        return x[0], p[0]


@dataclass(frozen=True)
class HealthForecast:
    """Health at ``issued_s + horizon_s``: a normal distribution per parameter, clipped at
    ``floor`` (the cap). ``lower``/``upper`` bound the central ``coverage`` band and
    ``mean`` is the clipped distribution's mean. Parameters are treated as independent."""

    issued_s: float
    horizon_s: float
    last_estimate_s: float
    coverage: float
    mean: Health
    lower: Health
    upper: Health
    loc: Health  # mean of the normal distribution before clipping
    scale: Health  # its standard deviation
    floor: Health

    @property
    def target_s(self) -> float:
        return self.issued_s + self.horizon_s

    def band(self, coverage: float) -> tuple[Health, Health]:
        """The central band at another coverage (clipped at the floor)."""

        z = _z(coverage)
        lo = (max(m - z * s, f) for m, s, f in zip(self.loc, self.scale, self.floor, strict=True))
        hi = (max(m + z * s, f) for m, s, f in zip(self.loc, self.scale, self.floor, strict=True))
        return Health(*lo), Health(*hi)

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        """``n`` health samples, shape (n, 3), by Latin hypercube sampling of each parameter
        (stratified, so the band edges of a small ensemble are less noisy)."""

        u = (rng.permuted(np.tile(np.arange(n), (3, 1)), axis=1).T + rng.random((n, 3))) / n
        z = np.vectorize(_NORMAL.inv_cdf)(np.clip(u, 1e-12, 1.0 - 1e-12))
        x = np.asarray(self.loc) + z * np.asarray(self.scale)
        return np.maximum(x, np.asarray(self.floor))


class DegradationForecaster:
    """Level and rate of each health parameter from estimates, and forecasts from them."""

    def __init__(self, config: TrendConfig | None = None) -> None:
        self.config = config or TrendConfig()
        c = self.config
        self._trends = [_Trend(i, c) for i in range(3)]
        self._last_used_s: float | None = None
        self._last_std = np.zeros(3)
        self.used = 0
        self.skipped = 0

    # ------------------------------------------------------------------ input
    def update(self, estimate: HealthEstimateLike) -> bool:
        """Take one estimate. Returns False if it was skipped (too soon or out of order)."""

        t_s = float(estimate.t_s)
        last = self._last_used_s
        if last is not None and t_s - last < self.config.min_interval_s - 1e-9:
            self.skipped += 1
            return False
        c = self.config
        std = np.maximum(np.asarray(estimate.std, dtype=float), c.min_std)
        if not (np.all(np.isfinite(std)) and np.all(np.isfinite(np.asarray(estimate.mean)))):
            raise ValueError("estimate mean and std must be finite")
        t_h = t_s / _S_PER_H
        for i, trend in enumerate(self._trends):
            trend.update(t_h, float(estimate.mean[i]), c.variance_inflation * std[i] ** 2)
        self._last_used_s = t_s
        self._last_std = std
        self.used += 1
        return True

    def reset_level(self, parameters: Iterable[int] = (0, 1)) -> None:
        """Restart the level of these parameters at the next estimate, keeping the rate (for
        a logged maintenance action; the default is the two compressor parameters)."""

        for i in parameters:
            self._trends[i].restart_level = True
            self._trends[i].pending.clear()

    # ------------------------------------------------------------------ state
    def _require(self) -> float:
        if self._last_used_s is None:
            raise ValueError("no estimate yet")
        return self._last_used_s

    @property
    def last_estimate_s(self) -> float | None:
        return self._last_used_s

    @property
    def level(self) -> Health:
        self._require()
        return Health(*(t.x[0] for t in self._trends))

    @property
    def rate_per_h(self) -> Health:
        self._require()
        return Health(*(t.x[1] for t in self._trends))

    @property
    def rate_std_per_h(self) -> Health:
        self._require()
        return Health(*(math.sqrt(max(t.p[2], 0.0)) for t in self._trends))

    @property
    def shifts(self) -> list[tuple[float, str, float]]:
        """Detected level steps: (time in s, parameter, size)."""

        out = [
            (t_h * _S_PER_H, PARAMETERS[i], size)
            for i, trend in enumerate(self._trends)
            for t_h, size in trend.shifts
        ]
        return sorted(out)

    @property
    def rate_changes(self) -> list[tuple[float, str]]:
        """Times (s) at which a parameter's rate was found out of date and reopened."""

        out = [
            (t_h * _S_PER_H, PARAMETERS[i])
            for i, trend in enumerate(self._trends)
            for t_h in trend.rate_changes
        ]
        return sorted(out)

    @property
    def outliers(self) -> int:
        return sum(t.outliers for t in self._trends)

    # ------------------------------------------------------------------ output
    def forecast(
        self, horizon_s: float, *, now_s: float | None = None, coverage: float | None = None
    ) -> HealthForecast:
        """Health ``horizon_s`` after ``now_s`` (default: the time of the last estimate used).

        Estimates still held as a possible step are not used.
        """

        last = self._require()
        issued = last if now_s is None else float(now_s)
        if horizon_s < 0.0 or issued < last:
            raise ValueError("the horizon must be >= 0 and now_s not before the last estimate")
        c = self.config
        cov = c.coverage if coverage is None else coverage
        z = _z(cov)
        t_h = (issued + horizon_s) / _S_PER_H
        loc, scale = [], []
        for i, trend in enumerate(self._trends):
            m, v = trend.forecast(t_h)
            v += (c.persistent_fraction * self._last_std[i]) ** 2
            loc.append(m)
            scale.append(math.sqrt(max(v, 0.0)))
        floor = c.floor
        return HealthForecast(
            issued_s=issued,
            horizon_s=float(horizon_s),
            last_estimate_s=last,
            coverage=cov,
            mean=Health(
                *(_clipped_mean(m, s, f) for m, s, f in zip(loc, scale, floor, strict=True))
            ),
            lower=Health(*(max(m - z * s, f) for m, s, f in zip(loc, scale, floor, strict=True))),
            upper=Health(*(max(m + z * s, f) for m, s, f in zip(loc, scale, floor, strict=True))),
            loc=Health(*loc),
            scale=Health(*scale),
            floor=floor,
        )


# ----------------------------------------------------------------------------- performance
@dataclass(frozen=True)
class OperatingPoint:
    """Where performance is evaluated: a requested load at an ambient, rated speed, IGV open.

    ``load_mw=None`` asks for base load. A load the unit cannot reach below the exhaust
    temperature limit is met as far as the limit allows, as the plant's control does.
    """

    load_mw: float | None = None
    ambient_temperature_c: float = 15.0
    speed_pu: float = 1.0
    igv_position: float = 1.0  # the auto schedule opens the IGV fully from 95 percent speed


class Performance(NamedTuple):
    power_mw: float
    fuel_kg_s: float
    exhaust_k: float


def exhaust_limit_k(twin: QuasiSteadyTwin, ambient_temperature_c: float) -> float:
    """The plant's exhaust temperature control limit (rated exhaust plus the margin)."""

    clean = twin.maps(ambient_temperature_c).clean
    return clean.rated_exhaust_k + PlantParameters().temperature_limit_margin_k


def _root(f, lo: float, hi: float, tol: float = 1e-9) -> float:
    """Root of an increasing function on [lo, hi] (Illinois false position; the twin's
    maps are piecewise linear in fuel, so this converges in a few steps)."""

    flo, fhi = f(lo), f(hi)
    if flo > 0.0 or fhi < 0.0:
        raise ValueError("the operating point is outside the fuel range searched")
    side = 0
    for _ in range(100):
        x = (lo * fhi - hi * flo) / (fhi - flo)
        fx = f(x)
        if abs(fx) < tol or hi - lo < tol:
            return x
        if fx < 0.0:
            lo, flo = x, fx
            if side == -1:
                fhi /= 2.0
            side = -1
        else:
            hi, fhi = x, fx
            if side == 1:
                flo /= 2.0
            side = 1
    return x


def steady_performance(
    health: Sequence[float], point: OperatingPoint, twin: QuasiSteadyTwin | None = None
) -> tuple[Performance, bool]:
    """Steady power, fuel flow and exhaust temperature at ``point`` for ``health``, and
    whether the unit is on the exhaust temperature limit there."""

    twin = twin or QuasiSteadyTwin()
    h = Health(*(float(v) for v in health))
    rated_fuel = twin.maps(point.ambient_temperature_c).clean.rated_fuel_kg_s
    template = Observation(
        t_s=0.0,
        state="loaded",
        breaker_closed=True,
        load_setpoint_mw=point.load_mw if point.load_mw is not None else math.inf,
        ambient_temperature_c=point.ambient_temperature_c,
        igv_position=point.igv_position,
        power_mw=math.nan,
        exhaust_k=math.nan,
        speed_pu=point.speed_pu,
        cdt_k=math.nan,
        cdp_kpa=math.nan,
        fuel_kg_s=0.0,
    )

    def at(fuel: float):
        return twin.predict(h, replace(template, fuel_kg_s=fuel))

    lo, hi = 0.2 * rated_fuel, 2.0 * rated_fuel
    limit = exhaust_limit_k(twin, point.ambient_temperature_c)
    fuel_limit = _root(lambda f: at(f).exhaust_k - limit, lo, hi)
    fuel, on_limit = fuel_limit, True
    if point.load_mw is not None:
        fuel_load = _root(lambda f: at(f).power_mw - point.load_mw, lo, hi)
        if fuel_load <= fuel_limit:
            fuel, on_limit = fuel_load, False
    p = at(fuel)
    return Performance(p.power_mw, fuel, p.exhaust_k), on_limit


@dataclass(frozen=True)
class PerformanceForecast:
    """Steady performance at ``point`` at the health forecast's target time (ensemble)."""

    issued_s: float
    horizon_s: float
    coverage: float
    point: OperatingPoint
    mean: Performance
    lower: Performance
    upper: Performance
    on_limit_share: float  # share of the ensemble on the exhaust temperature limit
    samples: int


def forecast_performance(
    forecast: HealthForecast,
    point: OperatingPoint,
    *,
    twin: QuasiSteadyTwin | None = None,
    n_samples: int = 200,
    seed: int = 0,
    coverage: float | None = None,
) -> PerformanceForecast:
    """Propagate an ensemble drawn from ``forecast`` through the twin at ``point``.

    The band is the ensemble's central ``coverage`` quantile range (default: the health
    forecast's coverage). Health parameters are sampled independently.
    """

    twin = twin or QuasiSteadyTwin()
    cov = forecast.coverage if coverage is None else coverage
    _z(cov)
    rng = np.random.default_rng(seed)
    results, limits = [], 0
    for h in forecast.sample(n_samples, rng):
        perf, on_limit = steady_performance(h, point, twin)
        results.append(perf)
        limits += on_limit
    arr = np.asarray(results)
    q = np.quantile(arr, [0.5 - 0.5 * cov, 0.5 + 0.5 * cov], axis=0)
    return PerformanceForecast(
        issued_s=forecast.issued_s,
        horizon_s=forecast.horizon_s,
        coverage=cov,
        point=point,
        mean=Performance(*(float(v) for v in arr.mean(axis=0))),
        lower=Performance(*(float(v) for v in q[0])),
        upper=Performance(*(float(v) for v in q[1])),
        on_limit_share=limits / n_samples,
        samples=n_samples,
    )


# ----------------------------------------------------------------------------- synthetic input
@dataclass(frozen=True)
class SyntheticEstimate:
    """A stand-in for an estimator output, built from ground truth (not an estimate)."""

    t_s: float
    mean: Health
    std: Health


#: Defaults of :func:`synthetic_estimates`: white noise per estimate, and the standard
#: deviation that the random-walk bias reaches after one hour. Plausible sizes, not measured.
SYNTHETIC_NOISE_STD = Health(0.0015, 0.0010, 0.0010)
SYNTHETIC_BIAS_WALK = Health(0.0010, 0.0007, 0.0007)


def synthetic_estimates(
    observations: Sequence[Observation],
    truths: Sequence[Truth],
    *,
    seed: int = 0,
    interval_s: float = 60.0,
    noise_std: Health = SYNTHETIC_NOISE_STD,
    bias_walk: Health = SYNTHETIC_BIAS_WALK,
    reported_std: Health | None = None,
    gate: SteadyStateGate | None = None,
) -> list[SyntheticEstimate]:
    """Synthetic health estimates from a scenario's ground truth, for testing a forecaster.

    An estimate is produced every ``interval_s`` while ``gate`` (default: the shared
    :class:`SteadyStateGate` on the observations) reports steady state, so the series has
    the gaps a real estimator's output would have. Its mean is the true health plus a bias
    that follows a random walk in time (standard deviation ``bias_walk`` after one hour,
    starting at zero at the first observation and running through gaps) plus independent
    Gaussian noise ``noise_std``. The reported ``std`` is ``reported_std``, by default
    ``sqrt(noise_std**2 + bias_walk**2)`` (the error of one estimate an hour into the run).
    Deterministic for a given ``seed``. There is no estimator lag or model mismatch here.
    """

    if len(observations) != len(truths):
        raise ValueError("observations and truths must have the same length")
    rng = np.random.default_rng(seed)
    gate = gate or SteadyStateGate()
    noise = np.asarray(noise_std, dtype=float)
    walk = np.asarray(bias_walk, dtype=float)
    std = (
        Health(*(float(v) for v in np.sqrt(noise**2 + walk**2)))
        if reported_std is None
        else reported_std
    )
    bias = np.zeros(3)
    t_bias = observations[0].t_s if observations else 0.0
    last = -math.inf
    out: list[SyntheticEstimate] = []
    for obs, truth in zip(observations, truths, strict=True):
        if not gate.update(obs) or obs.t_s - last < interval_s - 1e-9:
            continue
        dt_h = (obs.t_s - t_bias) / _S_PER_H
        bias = bias + walk * math.sqrt(max(dt_h, 0.0)) * rng.standard_normal(3)
        t_bias = obs.t_s
        mean = np.asarray(truth.health, dtype=float) + bias + noise * rng.standard_normal(3)
        out.append(SyntheticEstimate(obs.t_s, Health(*(float(v) for v in mean)), std))
        last = obs.t_s
    return out


# ----------------------------------------------------------------------------- evaluation
#: Scenarios of the evaluation and the load at which their performance is forecast.
EVALUATION_LOADS_MW: dict[str, float] = {
    "fouling_progressive_base_load": 47.0,  # requested; the unit is on the temperature limit
    "fouling_progressive_ambient_swing": 35.0,
    "fouled_unit_offline_wash": 40.0,
}
TUNING_SEEDS = (1000, 1001, 1002)
EVALUATION_SEED_OFFSETS = (0, 10000, 20000, 30000, 40000)  # added to the bank seed
LEVELS = (0.5, 0.8, 0.9, 0.95)


@dataclass(frozen=True)
class ForecastRecord:
    run: str
    origin_s: float
    horizon_s: float
    category: str  # see category()
    parameter: str
    truth: float
    mean: float
    loc: float
    scale: float
    floor: float
    persistence: float  # the latest estimate, held constant


@dataclass(frozen=True)
class PerformanceRecord:
    run: str
    origin_s: float
    horizon_s: float
    category: str
    quantity: str
    truth: float
    mean: float
    lower: float
    upper: float


#: Labels of :func:`category`, in order of time since the last ground-truth event.
CATEGORIES = ("event_in_horizon", "event_0_10_min_ago", "event_10_30_min_ago", "stable")


def category(origin_s: float, target_s: float, events: Sequence[float]) -> str:
    """Label a forecast by the ground-truth fault events around it (scoring only):
    an event inside the horizon, an event 0-10 or 10-30 minutes before the origin, or none
    in the 30 minutes before the origin or inside the horizon (stable)."""

    if any(origin_s < e <= target_s for e in events):
        return "event_in_horizon"
    since = [origin_s - e for e in events if e <= origin_s]
    if since and min(since) < 600.0:
        return "event_0_10_min_ago"
    if since and min(since) < 1800.0:
        return "event_10_30_min_ago"
    return "stable"


def evaluate_run(
    estimates: Sequence[HealthEstimateLike],
    truths: Sequence[Truth],
    *,
    run: str,
    events: Sequence[float] = (),
    config: TrendConfig | None = None,
    horizons_s: Sequence[float] = (1800.0, 3600.0),
    origin_step_s: float = 300.0,
    warmup_s: float = 900.0,
    max_age_s: float = 300.0,
    point: OperatingPoint | None = None,
    twin: QuasiSteadyTwin | None = None,
    n_samples: int = 200,
) -> tuple[list[ForecastRecord], list[PerformanceRecord]]:
    """Forecast from a grid of origins and score against the true health at the target.

    Origins lie on multiples of ``origin_step_s`` from ``warmup_s`` after the first estimate
    to the end of the run minus the horizon, and only where an estimate arrived within
    ``max_age_s`` (the unit is running steadily). ``events`` are ground-truth fault times,
    used only to label each forecast. With ``point``, the performance at that operating point
    is also forecast and compared with the twin at the true health.
    """

    if not estimates:
        return [], []
    forecaster = DegradationForecaster(config)
    times = np.array([t.t_s for t in truths])
    true_health = np.array([tuple(t.health) for t in truths])
    end_s = float(times[-1])
    first = estimates[0].t_s + warmup_s
    origin = math.ceil(first / origin_step_s) * origin_step_s
    records: list[ForecastRecord] = []
    perf_records: list[PerformanceRecord] = []
    k, latest = 0, None
    twin = twin or QuasiSteadyTwin()
    while origin <= end_s - min(horizons_s):
        while k < len(estimates) and estimates[k].t_s <= origin:
            forecaster.update(estimates[k])
            latest = estimates[k]
            k += 1
        if latest is not None and origin - latest.t_s <= max_age_s:
            for horizon in horizons_s:
                target = origin + horizon
                if target > end_s:
                    continue
                j = int(np.searchsorted(times, target, side="right")) - 1
                truth = true_health[j]
                label = category(origin, target, events)
                fc = forecaster.forecast(horizon, now_s=origin)
                for i, name in enumerate(PARAMETERS):
                    records.append(
                        ForecastRecord(
                            run,
                            origin,
                            horizon,
                            label,
                            name,
                            float(truth[i]),
                            fc.mean[i],
                            fc.loc[i],
                            fc.scale[i],
                            fc.floor[i],
                            float(latest.mean[i]),
                        )
                    )
                if point is not None:
                    pf = forecast_performance(fc, point, twin=twin, n_samples=n_samples)
                    actual, _ = steady_performance(truth, point, twin)
                    for i, name in enumerate(Performance._fields):
                        perf_records.append(
                            PerformanceRecord(
                                run,
                                origin,
                                horizon,
                                label,
                                name,
                                actual[i],
                                pf.mean[i],
                                pf.lower[i],
                                pf.upper[i],
                            )
                        )
        origin += origin_step_s
    return records, perf_records


def _covered(rec: ForecastRecord, level: float) -> bool:
    z = _z(level)
    lo = max(rec.loc - z * rec.scale, rec.floor)
    hi = max(rec.loc + z * rec.scale, rec.floor)
    return lo <= rec.truth <= hi


def _coverage_interval(hits_by_run: Mapping[str, list[bool]]) -> tuple[float, float]:
    """Pooled coverage and two standard errors from the spread of per-run coverage
    (forecasts within a run are correlated, so runs are the independent units)."""

    per_run = [sum(h) / len(h) for h in hits_by_run.values() if h]
    pooled = sum(sum(h) for h in hits_by_run.values()) / sum(len(h) for h in hits_by_run.values())
    if len(per_run) < 2:
        return pooled, math.nan
    return pooled, 2.0 * statistics.stdev(per_run) / math.sqrt(len(per_run))


def summarize_health(
    records: Sequence[ForecastRecord], keys: Sequence[str] = ("horizon_s", "parameter")
) -> list[dict]:
    """Error and coverage per group (``keys`` are ForecastRecord fields). Errors are in
    percent of flow capacity or efficiency points (health x 100)."""

    groups: dict[tuple, list[ForecastRecord]] = {}
    for rec in records:
        groups.setdefault(tuple(getattr(rec, k) for k in keys), []).append(rec)
    rows = []
    for key, recs in sorted(groups.items()):
        err = np.array([r.mean - r.truth for r in recs]) * 100.0
        pers = np.array([r.persistence - r.truth for r in recs]) * 100.0
        row = dict(zip(keys, key, strict=True))
        row.update(
            n=len(recs),
            runs=len({r.run for r in recs}),
            bias=float(err.mean()),
            mae=float(np.abs(err).mean()),
            rmse=float(np.sqrt((err**2).mean())),
            persistence_mae=float(np.abs(pers).mean()),
        )
        for level in LEVELS:
            hits: dict[str, list[bool]] = {}
            for r in recs:
                hits.setdefault(r.run, []).append(_covered(r, level))
            cov, ci = _coverage_interval(hits)
            row[f"cov{int(level * 100)}"] = cov
            if level == 0.9:
                row["cov90_2se"] = ci
        z = _z(0.9)
        row["width90"] = float(np.mean([2 * z * r.scale for r in recs]) * 100.0)
        rows.append(row)
    return rows


def summarize_performance(
    records: Sequence[PerformanceRecord], keys: Sequence[str] = ("horizon_s", "quantity")
) -> list[dict]:
    groups: dict[tuple, list[PerformanceRecord]] = {}
    for rec in records:
        groups.setdefault(tuple(getattr(rec, k) for k in keys), []).append(rec)
    rows = []
    for key, recs in sorted(groups.items()):
        err = np.array([r.mean - r.truth for r in recs])
        hits: dict[str, list[bool]] = {}
        for r in recs:
            hits.setdefault(r.run, []).append(r.lower - 1e-9 <= r.truth <= r.upper + 1e-9)
        cov, ci = _coverage_interval(hits)
        row = dict(zip(keys, key, strict=True))
        row.update(
            n=len(recs),
            bias=float(err.mean()),
            mae=float(np.abs(err).mean()),
            rmse=float(np.sqrt((err**2).mean())),
            cov90=cov,
            cov90_2se=ci,
            width90=float(np.mean([r.upper - r.lower for r in recs])),
        )
        rows.append(row)
    return rows


def _streams(scenario_id: str, seed: int, traces: Path | None):
    from turbineiq.simulation.scenarios import scenario

    item = scenario(scenario_id)
    if traces is not None:
        names = [f"{scenario_id}@{seed}.csv"] + (
            [f"{scenario_id}.csv"] if seed == item.seed else []
        )
        for name in names:
            path = traces / name
            if path.exists():
                with path.open(newline="") as fh:
                    return split_rows(csv.DictReader(fh))
    return run_streams(item, seed=seed)  # about 20 s for a two-hour scenario


def evaluate(
    seeds: str = "evaluation",
    *,
    traces: Path | None = None,
    replicates: int = 10,
    performance_replicates: int = 0,
    config: TrendConfig | None = None,
    scenarios: Sequence[str] = tuple(EVALUATION_LOADS_MW),
) -> tuple[list[ForecastRecord], list[PerformanceRecord]]:
    """The write-up's evaluation on synthetic estimates.

    ``seeds="tuning"`` uses simulation seeds 1000-1002, ``"evaluation"`` the bank seed and
    bank seed + 10000 k (k = 1..4). Each simulation gets ``replicates`` synthetic-estimate
    draws (estimate seed = simulation seed * 100 + replicate); the first
    ``performance_replicates`` of them also get a performance forecast.
    """

    from turbineiq.simulation.scenarios import scenario

    records: list[ForecastRecord] = []
    perf: list[PerformanceRecord] = []
    twin = QuasiSteadyTwin()
    for sid in scenarios:
        item = scenario(sid)
        sim_seeds = (
            TUNING_SEEDS if seeds == "tuning" else [item.seed + d for d in EVALUATION_SEED_OFFSETS]
        )
        events = sorted({float(e["t_s"]) for e in item.fault_events()})
        point = OperatingPoint(load_mw=EVALUATION_LOADS_MW.get(sid, 35.0))
        for sim_seed in sim_seeds:
            observations, truths = _streams(sid, sim_seed, traces)
            for r in range(replicates):
                estimates = synthetic_estimates(observations, truths, seed=sim_seed * 100 + r)
                recs, prec = evaluate_run(
                    estimates,
                    truths,
                    run=f"{sid}@{sim_seed}#{r}",
                    events=events,
                    config=config,
                    point=point if r < performance_replicates else None,
                    twin=twin,
                )
                records.extend(recs)
                perf.extend(prec)
    return records, perf


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate the degradation forecast")
    parser.add_argument("--seeds", choices=("tuning", "evaluation"), default="evaluation")
    parser.add_argument("--traces", type=Path, help="folder of <id>.csv / <id>@<seed>.csv")
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument("--performance-replicates", type=int, default=2)
    parser.add_argument("--out", type=Path, help="write the summaries as JSON here")
    args = parser.parse_args(argv)
    records, perf = evaluate(
        args.seeds,
        traces=args.traces,
        replicates=args.replicates,
        performance_replicates=args.performance_replicates,
    )
    summary = {
        "inputs": "synthetic estimates (ground truth + noise + random-walk bias)",
        "seeds": args.seeds,
        "config": asdict(TrendConfig()),
        "health": _grouped_health(records),
        "performance": _grouped_performance(perf),
    }
    text = json.dumps(summary, indent=1, default=float)
    if args.out:
        args.out.write_text(text)
    print(text)


def _scenario_of(run: str) -> str:
    return run.split("@")[0]


def _no_event(records):
    return [r for r in records if r.category != "event_in_horizon"]


def _grouped_health(records: Sequence[ForecastRecord]) -> dict[str, list[dict]]:
    """Pooled, pooled without forecasts across an event, by category, and per scenario."""

    cat = ("horizon_s", "parameter", "category")
    out: dict[str, list[dict]] = {
        "all": summarize_health(records),
        "all_but_event_in_horizon": summarize_health(_no_event(records)),
        "all_by_category": summarize_health(records, cat),
    }
    for sid in sorted({_scenario_of(r.run) for r in records}):
        sub = [r for r in records if _scenario_of(r.run) == sid]
        out[sid] = summarize_health(sub, cat)
        out[f"{sid}/all_but_event_in_horizon"] = summarize_health(_no_event(sub))
    return out


def _grouped_performance(records: Sequence[PerformanceRecord]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for sid in sorted({_scenario_of(r.run) for r in records}):
        sub = [r for r in records if _scenario_of(r.run) == sid]
        out[sid] = summarize_performance(sub, ("horizon_s", "quantity", "category"))
        out[f"{sid}/all_but_event_in_horizon"] = summarize_performance(_no_event(sub))
    return out


if __name__ == "__main__":
    main()
