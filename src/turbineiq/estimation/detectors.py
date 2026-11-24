"""Baseline fault detectors on clean-twin residuals (roadmap WP4, diagnosis baselines).

These are the screens the health estimator is compared against. Each one reads only
:class:`~turbineiq.estimation.data.Observation` objects, forms the residual between the
four instrumented outputs and the :class:`~turbineiq.estimation.twin.QuasiSteadyTwin`
prediction for a *clean* engine at the measured inputs, and looks at it only while the
:class:`~turbineiq.estimation.steady.SteadyStateGate` is open. While the gate is closed
(start-up, load and ambient changes, and for ``window_s`` after any jump in power or exhaust
temperature) a detector holds its state and cannot signal, so a fault that shows only in
transients, such as a slow fuel valve, is invisible to it, and a step fault is seen no
earlier than one gate window after the step.

Three detectors, all on residuals standardised by a :class:`NoiseModel` fitted to healthy
runs:

* :class:`ResidualScreen`: per-channel moving mean of the standardised residual, compared
  with a fixed band, with a persistence rule (the band must be exceeded on the same side
  for several consecutive steady samples).
* :class:`CusumDetector`: a two-sided CUSUM per channel (Page's cumulative sum), ported
  from :func:`turbineiq.analytics.quality.detect_drift` of the earlier drift-detection
  change: standardised residual, clipped so that one spike cannot trigger it, accumulated
  with a slack ``k`` and compared with a decision interval ``h``. Here the reference level
  is the clean twin and the noise scale comes from healthy tuning runs, not from a warm-up
  segment of the same run, so a fault present from the start is still seen.
* :class:`MewmaDetector`: a multivariate EWMA chart on the whitened residual vector. Fuel
  meter noise enters the twin as an input and moves the power and exhaust residuals
  together (correlation about 0.89), so a statistic that knows the correlation sees a
  fouling or erosion signature, which moves them in opposite directions, far above noise.

Output semantics: ``update`` returns a :class:`DetectorOutput` for every observation.
``alarm`` is True on the sample at which the detector *signals*; the channel(s) that
signalled are then restarted from zero (a renewal), so a fault that persists signals again
after another accumulation period and a false-alarm rate is simply signals per steady hour.
A consumer that wants a latched alarm latches the first signal.

The default parameters were set on healthy runs only (the five ``clean_*`` scenarios with
seeds 1000-1019) for a target of one false alarm per 100 hours of steady operation; see
``docs/FAULT_DETECTION.md`` for the protocol, the grids that were searched and the results.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from turbineiq.simulation.maps import CLEAN, Health

from .data import Observation
from .steady import SteadyStateGate
from .twin import MEASUREMENTS, QuasiSteadyTwin, measured

CHANNELS: tuple[str, ...] = MEASUREMENTS  # power_mw, exhaust_k, cdt_k, cdp_kpa
N_CHANNELS = len(CHANNELS)

#: Target false-alarm rate used to set the default thresholds (signals per steady hour).
TARGET_FALSE_ALARMS_PER_HOUR = 0.01


@dataclass(frozen=True)
class DetectorOutput:
    t_s: float
    alarm: bool  # the detector signals at this sample (see the module docstring)
    statistic: float  # the detector's decision statistic after this sample
    channel: str | None  # residual channel that signalled (or leads the statistic)


# --------------------------------------------------------------------------- noise model
@dataclass(frozen=True)
class NoiseModel:
    """Location and scale of healthy clean-twin residuals, and their correlation.

    The scale of channel ``c`` is ``offset[c] + per_fuel[c] * fuel_kg_s``: fuel-meter noise
    (0.5 percent of the reading) dominates the power and exhaust residuals, so their spread
    grows with the measured fuel flow; the discharge temperature and pressure residuals do
    not depend on fuel. ``correlation`` is that of the standardised residuals.
    """

    location: tuple[float, ...]
    offset: tuple[float, ...]
    per_fuel: tuple[float, ...]
    correlation: tuple[tuple[float, ...], ...]

    def scale(self, fuel_kg_s: float | np.ndarray) -> np.ndarray:
        fuel = np.asarray(fuel_kg_s, dtype=float)[..., None]
        return np.asarray(self.offset) + np.asarray(self.per_fuel) * fuel

    def standardize(self, residual: np.ndarray, fuel_kg_s: float | np.ndarray) -> np.ndarray:
        return (np.asarray(residual, dtype=float) - np.asarray(self.location)) / self.scale(
            fuel_kg_s
        )

    def whitener(self) -> np.ndarray:
        """Matrix ``W`` with ``W @ z`` uncorrelated with unit variance for healthy ``z``."""

        return np.linalg.inv(np.linalg.cholesky(np.asarray(self.correlation)))

    @classmethod
    def fit(
        cls,
        residuals: np.ndarray,
        operating_fuel_kg_s: np.ndarray,
        measured_fuel_kg_s: np.ndarray | None = None,
        bins: int = 12,
    ) -> NoiseModel:
        """Fit to healthy steady-state residuals (rows) and their operating fuel flow.

        Location is the per-channel median. The scale is a weighted least-squares line
        through robust scales (1.4826 times the median absolute deviation) in bins of the
        operating fuel flow with equal counts; with too little spread it is a constant.

        The bins must use a noise-free operating point, such as the mean fuel flow over each
        steady segment (see :func:`healthy_residuals`): binning on the measured fuel itself
        selects the fuel-meter noise that drives the power and exhaust residuals and
        underestimates their spread by about a factor of two. The correlation is computed
        with the measured fuel (``measured_fuel_kg_s``, default the operating fuel), as the
        detectors standardise at run time.
        """

        r = np.asarray(residuals, dtype=float)
        fuel = np.asarray(operating_fuel_kg_s, dtype=float)
        runtime_fuel = fuel if measured_fuel_kg_s is None else np.asarray(measured_fuel_kg_s)
        if r.ndim != 2 or r.shape[1] != N_CHANNELS or len(r) != len(fuel) or len(r) < 100:
            raise ValueError("need at least 100 rows of four residuals and the fuel flow")
        location = np.median(r, axis=0)
        order = np.argsort(fuel)
        groups = [g for g in np.array_split(order, bins) if len(g) >= 20]
        centres = np.array([fuel[g].mean() for g in groups])
        weights = np.array([len(g) for g in groups], dtype=float)
        offset = np.empty(N_CHANNELS)
        per_fuel = np.empty(N_CHANNELS)
        for c in range(N_CHANNELS):
            scales = np.array([_robust_scale(r[g, c]) for g in groups])
            if np.ptp(centres) < 1e-3 * max(abs(centres.mean()), 1.0):
                offset[c], per_fuel[c] = float(np.average(scales, weights=weights)), 0.0
                continue
            design = np.column_stack([np.ones_like(centres), centres]) * np.sqrt(weights)[:, None]
            coef, *_ = np.linalg.lstsq(design, scales * np.sqrt(weights), rcond=None)
            offset[c], per_fuel[c] = float(coef[0]), float(coef[1])
        model = cls(tuple(location), tuple(offset), tuple(per_fuel), _identity())
        z = model.standardize(r, runtime_fuel)
        corr = np.corrcoef(z.T)
        return cls(
            tuple(float(v) for v in location),
            tuple(float(v) for v in offset),
            tuple(float(v) for v in per_fuel),
            tuple(tuple(float(v) for v in row) for row in corr),
        )


def _robust_scale(values: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def _identity() -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(i == j) for j in range(N_CHANNELS)) for i in range(N_CHANNELS))


#: Fitted with :meth:`NoiseModel.fit` on every steady sample of the five clean scenarios,
#: seeds 1000-1019 (646,039 samples, 179.5 steady hours), rounded. Units MW, K, K, kPa;
#: ``per_fuel`` per kg/s.
TUNED_NOISE = NoiseModel(
    location=(0.0010, -0.0141, -0.0025, 0.0115),
    offset=(0.0151, 0.3856, 0.6121, 3.3929),
    per_fuel=(0.09484, 0.7232, 0.0001, 0.0102),
    correlation=(
        (1.0, 0.896, 0.035, 0.036),
        (0.896, 1.0, -0.087, -0.103),
        (0.035, -0.087, 1.0, 0.382),
        (0.036, -0.103, 0.382, 1.0),
    ),
)


# --------------------------------------------------------------------------- residuals
class GatedResiduals:
    """Clean-twin residuals (measured minus predicted) while the steady-state gate is open.

    One instance can feed several detectors: a repeated call with the same observation
    object returns the cached result, so the gate advances once per observation.
    """

    def __init__(
        self,
        twin: QuasiSteadyTwin | None = None,
        gate: SteadyStateGate | None = None,
        health: Health = CLEAN,
    ) -> None:
        self.twin = twin or QuasiSteadyTwin()
        self.gate = gate or SteadyStateGate()
        self.health = health
        self._last: Observation | None = None
        self._result: np.ndarray | None = None

    def update(self, obs: Observation) -> np.ndarray | None:
        if obs is self._last:
            return self._result
        self._last = obs
        if self.gate.update(obs):
            predicted = self.twin.predict(self.health, obs).as_tuple()
            self._result = np.subtract(measured(obs), predicted)
        else:
            self._result = None
        return self._result


# --------------------------------------------------------------------------- cores
# The recursions work on arrays with any leading batch shape, so the same code runs one
# detector online and many independent chains at once when thresholds are calibrated.
@dataclass
class Step:
    signal: np.ndarray  # bool, batch shape
    statistic: np.ndarray  # float, batch shape
    channel: np.ndarray  # int, batch shape: channel that signalled or leads
    direction: np.ndarray  # int, batch shape: +1 residual above the twin, -1 below
    fired: np.ndarray  # bool, batch shape + (channels,)


class ScreenCore:
    """Moving mean of ``window`` steady samples per channel, scaled to unit variance, with a
    band ``threshold`` that must be exceeded on one side ``persistence`` times in a row."""

    def __init__(
        self, threshold: float, window: int, persistence: int, shape: tuple[int, ...] = ()
    ):
        if window < 1 or persistence < 1 or not threshold > 0:
            raise ValueError("window and persistence must be at least 1, threshold above 0")
        self.threshold = float(threshold)
        self.window = int(window)
        self.persistence = int(persistence)
        self._z = np.zeros((self.window, *shape, N_CHANNELS))
        self._sum = np.zeros((*shape, N_CHANNELS))
        self._count = 0
        self._pos = np.full((self.persistence, *shape, N_CHANNELS), -np.inf)
        self._neg = np.full((self.persistence, *shape, N_CHANNELS), -np.inf)
        self._i = 0

    def step(self, z: np.ndarray) -> Step:
        slot = self._count % self.window
        self._sum += z - self._z[slot]
        self._z[slot] = z
        self._count += 1
        mean = self._sum / math.sqrt(min(self._count, self.window))
        slot = self._i % self.persistence
        self._pos[slot], self._neg[slot] = mean, -mean
        self._i += 1
        up, down = self._pos.min(axis=0), self._neg.min(axis=0)
        per_channel = np.maximum(up, down)
        fired = per_channel >= self.threshold
        channel = per_channel.argmax(axis=-1)
        statistic = np.take_along_axis(per_channel, channel[..., None], -1)[..., 0]
        lead_up = np.take_along_axis(up >= down, channel[..., None], -1)[..., 0]
        self._pos = np.where(fired, -np.inf, self._pos)
        self._neg = np.where(fired, -np.inf, self._neg)
        return Step(
            fired.any(axis=-1),
            np.maximum(statistic, 0.0),
            channel,
            np.where(lead_up, 1, -1),
            fired,
        )


class CusumCore:
    """Two-sided CUSUM per channel on clipped standardised residuals, renewed on a signal."""

    def __init__(
        self, threshold: float, slack: float, clip: float = 4.0, shape: tuple[int, ...] = ()
    ):
        if not (threshold > 0 and slack >= 0 and clip > 0):
            raise ValueError("threshold and clip must be above 0, slack at least 0")
        self.threshold = float(threshold)
        self.slack = float(slack)
        self.clip = float(clip)
        self.upper = np.zeros((*shape, N_CHANNELS))
        self.lower = np.zeros((*shape, N_CHANNELS))

    def step(self, z: np.ndarray) -> Step:
        z = np.clip(z, -self.clip, self.clip)
        self.upper = np.maximum(0.0, self.upper + z - self.slack)
        self.lower = np.maximum(0.0, self.lower - z - self.slack)
        per_channel = np.maximum(self.upper, self.lower)
        fired = per_channel >= self.threshold
        channel = per_channel.argmax(axis=-1)
        statistic = np.take_along_axis(per_channel, channel[..., None], -1)[..., 0]
        lead_up = np.take_along_axis(self.upper >= self.lower, channel[..., None], -1)[..., 0]
        self.upper = np.where(fired, 0.0, self.upper)
        self.lower = np.where(fired, 0.0, self.lower)
        return Step(fired.any(axis=-1), statistic, channel, np.where(lead_up, 1, -1), fired)


class MewmaCore:
    """Multivariate EWMA of the whitened residual; ``T2 = |e|^2 (2 - lam) / lam``."""

    def __init__(
        self,
        threshold: float,
        smoothing: float,
        whitener: np.ndarray,
        shape: tuple[int, ...] = (),
    ):
        if not (threshold > 0 and 0 < smoothing <= 1):
            raise ValueError("threshold must be above 0 and smoothing in (0, 1]")
        self.threshold = float(threshold)
        self.smoothing = float(smoothing)
        self.whitener = np.asarray(whitener, dtype=float)
        self._norm = (2.0 - self.smoothing) / self.smoothing
        self.ewma = np.zeros((*shape, N_CHANNELS))  # whitened
        self.ewma_z = np.zeros((*shape, N_CHANNELS))  # per channel, for attribution only

    def step(self, z: np.ndarray) -> Step:
        lam = self.smoothing
        self.ewma = (1.0 - lam) * self.ewma + lam * (z @ self.whitener.T)
        self.ewma_z = (1.0 - lam) * self.ewma_z + lam * z
        statistic = self._norm * np.sum(self.ewma**2, axis=-1)
        signal = statistic >= self.threshold
        channel = np.abs(self.ewma_z).argmax(axis=-1)
        lead = np.take_along_axis(self.ewma_z, channel[..., None], -1)[..., 0]
        self.ewma = np.where(signal[..., None], 0.0, self.ewma)
        self.ewma_z = np.where(signal[..., None], 0.0, self.ewma_z)
        fired = signal[..., None] & (np.arange(N_CHANNELS) == channel[..., None])
        return Step(signal, statistic, channel, np.where(lead >= 0, 1, -1), fired)


# --------------------------------------------------------------------------- detectors
class _ResidualDetector:
    """Shared plumbing: gate, clean-twin residual, standardisation, output."""

    def __init__(self, core, noise: NoiseModel, source: GatedResiduals | None) -> None:
        self.core = core
        self.noise = noise
        self.source = source or GatedResiduals()
        self.statistic = 0.0
        self.last_direction = 0  # sign of the residual of the last signal (+1 above twin)
        self.last_fired: tuple[tuple[str, int], ...] = ()

    @property
    def threshold(self) -> float:
        return self.core.threshold

    def update(self, obs: Observation) -> DetectorOutput:
        residual = self.source.update(obs)
        if residual is None:
            return DetectorOutput(obs.t_s, False, self.statistic, None)
        z = self.noise.standardize(residual, obs.fuel_kg_s)
        step = self.core.step(z)
        self.statistic = float(step.statistic)
        alarm = bool(step.signal)
        channel = CHANNELS[int(step.channel)]
        if alarm:
            self.last_direction = int(step.direction)
            self.last_fired = tuple(
                (CHANNELS[c], int(np.sign(z[c])) or 1) for c in np.flatnonzero(step.fired)
            )
        return DetectorOutput(obs.t_s, alarm, self.statistic, channel)


#: Defaults chosen by the tuning protocol in ``docs/FAULT_DETECTION.md``.
SCREEN_WINDOW = 60
SCREEN_PERSISTENCE = 10
SCREEN_THRESHOLD = 4.6
CUSUM_SLACK = 0.5
CUSUM_CLIP = 4.0
CUSUM_THRESHOLD = 13.0
MEWMA_SMOOTHING = 0.05
MEWMA_THRESHOLD = 30.0


class ResidualScreen(_ResidualDetector):
    """Per-channel residual band with a moving mean and a persistence rule.

    ``statistic`` is, for the leading channel, the smallest band excursion (in standard
    deviations of the moving mean) over the last ``persistence`` steady samples on one side.
    """

    def __init__(
        self,
        threshold: float = SCREEN_THRESHOLD,
        window: int = SCREEN_WINDOW,
        persistence: int = SCREEN_PERSISTENCE,
        noise: NoiseModel = TUNED_NOISE,
        source: GatedResiduals | None = None,
    ) -> None:
        super().__init__(ScreenCore(threshold, window, persistence), noise, source)


class CusumDetector(_ResidualDetector):
    """Two-sided CUSUM per residual channel; ``statistic`` is the largest of the eight sums."""

    def __init__(
        self,
        threshold: float = CUSUM_THRESHOLD,
        slack: float = CUSUM_SLACK,
        clip: float = CUSUM_CLIP,
        noise: NoiseModel = TUNED_NOISE,
        source: GatedResiduals | None = None,
    ) -> None:
        super().__init__(CusumCore(threshold, slack, clip), noise, source)


class MewmaDetector(_ResidualDetector):
    """Multivariate EWMA (chi-square-like ``T2``) on the whitened residual vector.

    ``channel`` names the channel whose own standardised EWMA is largest in magnitude; the
    statistic itself is not tied to one channel.
    """

    def __init__(
        self,
        threshold: float = MEWMA_THRESHOLD,
        smoothing: float = MEWMA_SMOOTHING,
        noise: NoiseModel = TUNED_NOISE,
        source: GatedResiduals | None = None,
    ) -> None:
        super().__init__(MewmaCore(threshold, smoothing, noise.whitener()), noise, source)


# --------------------------------------------------------------------------- isolation
FAULT_CLASSES = (
    "compressor_fouling",
    "turbine_erosion",
    "fuel_meter",
    "power_sensor",
    "exhaust_sensor",
    "cdt_sensor",
    "cdp_sensor",
    "unknown",
)
_SENSOR_CLASS = {
    "power_mw": "power_sensor",
    "exhaust_k": "exhaust_sensor",
    "cdt_k": "cdt_sensor",
    "cdp_kpa": "cdp_sensor",
}


def classify_pattern(signs: Mapping[str, int]) -> str:
    """Name a fault from the signed residual channels that signalled (+1 above the twin).

    The rule follows the residual signatures of the clean twin at constant load (see the
    docs): compressor fouling lowers the discharge pressure and raises the exhaust and
    discharge temperatures; turbine erosion raises the exhaust and lowers the power with
    the compressor channels unchanged; a fuel meter reading high lowers both power and
    exhaust residuals (reading low raises both); a single channel on its own is that sensor.
    """

    s = {c: int(np.sign(signs.get(c, 0))) for c in CHANNELS}
    power, exhaust, cdt, cdp = (s[c] for c in CHANNELS)
    active = [c for c in CHANNELS if s[c]]
    if cdp < 0 and (exhaust > 0 or cdt > 0):
        return "compressor_fouling"
    if cdt == 0 and cdp == 0 and exhaust > 0 and power < 0:
        return "turbine_erosion"
    if cdt == 0 and cdp == 0 and power != 0 and exhaust == power:
        return "fuel_meter"
    if len(active) == 1:
        return _SENSOR_CLASS[active[0]]
    return "unknown"


@dataclass
class PatternIsolator:
    """Collects which channels a per-channel detector signals, and with which sign, for
    ``confirm_s`` seconds of steady operation after its first signal, then classifies the
    pattern with :func:`classify_pattern`. ``label`` stays ``None`` until then.

    A channel's sign is the one it signalled with most often in the window.
    """

    detector: _ResidualDetector = field(default_factory=CusumDetector)
    confirm_s: float = 300.0
    first_alarm_s: float | None = None
    label: str | None = None
    label_s: float | None = None
    _votes: dict[str, int] = field(default_factory=dict)
    _steady_s: float = 0.0
    _last_t: float | None = None

    def update(self, obs: Observation) -> DetectorOutput:
        out = self.detector.update(obs)
        steady = self.detector.source.update(obs) is not None
        if self.first_alarm_s is not None and self.label is None and steady:
            if self._last_t is not None:
                self._steady_s += obs.t_s - self._last_t
        if self.label is None and out.alarm:
            if self.first_alarm_s is None:
                self.first_alarm_s = obs.t_s
            for channel, sign in self.detector.last_fired:
                self._votes[channel] = self._votes.get(channel, 0) + sign
        if (
            self.first_alarm_s is not None
            and self.label is None
            and self._steady_s >= (self.confirm_s)
        ):
            self.label = classify_pattern(self._votes)
            self.label_s = obs.t_s
        self._last_t = obs.t_s if steady else None
        return out

    @property
    def votes(self) -> dict[str, int]:
        return dict(self._votes)


# --------------------------------------------------------------------------- calibration
def healthy_residuals(
    streams: Iterable[Sequence[Observation]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Steady-state clean-twin residuals over healthy streams, with the operating fuel flow
    (mean over each contiguous steady segment) and the measured fuel flow of every row.
    ``NoiseModel.fit(*healthy_residuals(streams))`` refits the noise model."""

    rows: list[np.ndarray] = []
    operating: list[float] = []
    fuel: list[float] = []
    for observations in streams:
        source = GatedResiduals()
        segment: list[float] = []
        for obs in [*observations, None]:
            residual = None if obs is None else source.update(obs)
            if residual is None:
                if segment:
                    operating.extend([float(np.mean(segment))] * len(segment))
                segment = []
                continue
            rows.append(residual)
            segment.append(obs.fuel_kg_s)
            fuel.append(obs.fuel_kg_s)
    return np.array(rows).reshape(-1, N_CHANNELS), np.array(operating), np.array(fuel)


def bootstrap_signal_rate(
    make_core: Callable[[tuple[int, ...]], object],
    z_rows: np.ndarray,
    hours: float,
    chains: int = 1000,
    seed: int = 0,
    sample_s: float = 1.0,
) -> tuple[int, float]:
    """Signals per steady hour of a detector core fed rows drawn with replacement from
    standardised healthy residuals (``z_rows``), run as ``chains`` independent chains.

    Resampling single rows keeps the cross-channel correlation and the marginal shape of
    the healthy residuals but assumes no serial correlation; the healthy residuals of this
    plant have a lag-one autocorrelation below 0.02. Returns (signals, simulated hours).
    """

    rng = np.random.default_rng(seed)
    steps = max(1, int(round(hours * 3600.0 / sample_s / chains)))
    core = make_core((chains,))
    signals = 0
    for _ in range(steps):
        signals += int(core.step(z_rows[rng.integers(0, len(z_rows), chains)]).signal.sum())
    return signals, steps * chains * sample_s / 3600.0
