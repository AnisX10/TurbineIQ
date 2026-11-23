"""Online gas-path health estimation with an unscented Kalman filter (roadmap WP4).

The three health deltas of :class:`~turbineiq.simulation.maps.Health` (compressor flow
capacity, compressor and turbine polytropic efficiency) are the filter states. They follow
a random walk, and the quasi-steady twin is the measurement model, so the filter only
learns from steady operation: each observation passes a
:class:`~turbineiq.estimation.steady.SteadyStateGate`, and only observations taken while
the gate is open are used. Steady observations are averaged over short batches (10 s by
default) and each batch mean is one measurement update.

The estimator sees :class:`~turbineiq.estimation.data.Observation` objects only, never
ground truth. Its noise model is the instrument accuracy in :data:`INSTRUMENT_NOISE`
(equal to the simulator's measurement noise, which a real estimator would take from the
instrument data sheets) plus the noise that the readings used as model *inputs* push
through the twin. The latter makes the residuals of the four predicted channels
correlated, so the measurement covariance is a full matrix, recomputed at each update.

Two measurement formulations are provided (see :mod:`.observability` for why the default
is the power-input one):

* :class:`FuelInputModel` -- the twin as given: measured fuel flow and speed in; electrical
  power, exhaust temperature, compressor discharge temperature and pressure out.
* :class:`PowerInputModel` -- measured electrical power and speed in; fuel flow, exhaust
  temperature, compressor discharge temperature and pressure out (the twin is inverted for
  the fuel flow that gives the measured power).

Tuning (process noise, prior, batch length, innovation-triggered inflation) was done on
scenario seeds 1000 to 1002 only; see ``docs/HEALTH_ESTIMATION.md``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np

from turbineiq.simulation.maps import Health

from .data import Observation
from .steady import SteadyStateGate
from .twin import QuasiSteadyTwin

HEALTH_NAMES = ("compressor_flow", "compressor_efficiency", "turbine_efficiency")

#: Instrument accuracy assumed by the estimator, one standard deviation per reading, as
#: (absolute, relative) parts. These equal the simulator's measurement noise.
INSTRUMENT_NOISE: dict[str, tuple[float, float]] = {
    "power_mw": (0.0, 0.002),
    "exhaust_k": (0.5, 0.0),
    "speed_pu": (0.0005, 0.0),
    "cdt_k": (0.5, 0.0),
    "cdp_kpa": (0.0, 0.002),
    "fuel_kg_s": (0.0, 0.005),
}


def instrument_sigma(channel: str, value: float) -> float:
    """One-sigma noise of a single reading of ``channel`` at ``value``."""

    absolute, relative = INSTRUMENT_NOISE[channel]
    return math.hypot(absolute, relative * abs(value))


def _health(x: Sequence[float]) -> Health:
    return Health(float(x[0]), float(x[1]), float(x[2]))


class _TwinModel:
    """Common part of the two measurement formulations."""

    name = ""
    outputs: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()

    def __init__(self, twin: QuasiSteadyTwin | None = None) -> None:
        self.twin = twin or QuasiSteadyTwin()

    def predict(self, health: Sequence[float], obs: Observation) -> np.ndarray:
        raise NotImplementedError

    def measured(self, obs: Observation) -> np.ndarray:
        return np.array([getattr(obs, name) for name in self.outputs], dtype=float)

    def input_jacobian(self, health: Sequence[float], obs: Observation) -> np.ndarray:
        """d(prediction)/d(input reading), one column per entry of :attr:`inputs`.

        Central differences with a step of one instrument sigma (a statistical
        linearisation over the range the input noise actually spans).
        """

        columns = []
        for name in self.inputs:
            value = getattr(obs, name)
            step = instrument_sigma(name, value)
            hi = self.predict(health, replace(obs, **{name: value + step}))
            lo = self.predict(health, replace(obs, **{name: value - step}))
            columns.append((hi - lo) / (2.0 * step))
        return np.column_stack(columns)

    def noise_covariance(
        self, health: Sequence[float], obs: Observation, *, correlated: bool = True
    ) -> np.ndarray:
        """Covariance of one sample's residual ``measured - predicted`` at the true health.

        Output-reading noise plus input-reading noise propagated through the twin. With
        ``correlated=False`` only the diagonal is kept (the residual variances without
        their correlation), which is what a per-channel noise model would use.
        """

        out_var = np.array([instrument_sigma(n, getattr(obs, n)) ** 2 for n in self.outputs])
        in_var = np.array([instrument_sigma(n, getattr(obs, n)) ** 2 for n in self.inputs])
        jac = self.input_jacobian(health, obs)
        cov = np.diag(out_var) + jac @ np.diag(in_var) @ jac.T
        return cov if correlated else np.diag(np.diag(cov))


class FuelInputModel(_TwinModel):
    """The quasi-steady twin as given: fuel flow and speed in, power and three others out."""

    name = "fuel_input"
    outputs = ("power_mw", "exhaust_k", "cdt_k", "cdp_kpa")
    inputs = ("fuel_kg_s", "speed_pu")

    def predict(self, health: Sequence[float], obs: Observation) -> np.ndarray:
        return np.array(self.twin.predict(_health(health), obs).as_tuple())


class PowerInputModel(_TwinModel):
    """Electrical power and speed in; fuel flow, exhaust T, discharge T and p out.

    For each health the twin is inverted for the fuel flow at which it predicts the
    measured power. The twin's power is piecewise linear and increasing in fuel flow, so a
    secant iteration started from the measured fuel flow converges in a few steps; the
    result does not depend on the starting point.
    """

    name = "power_input"
    outputs = ("fuel_kg_s", "exhaust_k", "cdt_k", "cdp_kpa")
    inputs = ("power_mw", "speed_pu")
    tolerance_mw = 1e-7

    def fuel_for_power(self, health: Health, obs: Observation) -> tuple[float, Observation]:
        target = obs.power_mw

        def power(fuel: float) -> tuple[float, Observation]:
            at = replace(obs, fuel_kg_s=fuel)
            return self.twin.predict(health, at).power_mw - target, at

        rated = self.twin.maps(obs.ambient_temperature_c).clean.rated_fuel_kg_s
        f0 = obs.fuel_kg_s if math.isfinite(obs.fuel_kg_s) and obs.fuel_kg_s > 0.0 else rated
        f1 = f0 * 1.01
        r0, _ = power(f0)
        r1, at1 = power(f1)
        for _ in range(30):
            if abs(r1) < self.tolerance_mw or r1 == r0:
                break
            f2 = f1 - r1 * (f1 - f0) / (r1 - r0)
            f0, r0 = f1, r1
            f1 = f2
            r1, at1 = power(f1)
        return f1, at1

    def predict(self, health: Sequence[float], obs: Observation) -> np.ndarray:
        h = _health(health)
        fuel, at = self.fuel_for_power(h, obs)
        p = self.twin.predict(h, at)
        return np.array([fuel, p.exhaust_k, p.cdt_k, p.cdp_kpa])


MODELS = {FuelInputModel.name: FuelInputModel, PowerInputModel.name: PowerInputModel}


@dataclass(frozen=True)
class HealthEstimate:
    """Filter output after one observation.

    ``mean`` and ``std`` are the posterior mean and standard deviation of the three health
    deltas (fractions, as in :class:`Health`). ``steady`` is True when the steady-state
    gate was open for this observation, so the estimate is being updated from it.
    """

    t_s: float
    mean: Health
    std: Health
    steady: bool


@dataclass(frozen=True)
class UKFSettings:
    """Tuning of :class:`UKFHealthEstimator` (chosen on seeds 1000 to 1002).

    Process noise is a random walk: the variance of each health delta grows by
    ``process_std_per_h**2`` per hour of operation. ``prior_std`` is the uncertainty
    before any steady data. ``batch_s`` steady samples are averaged into one update.
    When the normalised innovation squared of a batch exceeds ``inflation_nis`` (a sign
    that the health has moved faster than the random walk allows) the covariance is
    inflated by ``inflation_factor`` before the update, never beyond the prior.
    """

    model: str = PowerInputModel.name
    prior_std: tuple[float, float, float] = (0.03, 0.015, 0.015)
    process_std_per_h: tuple[float, float, float] = (0.01, 0.005, 0.005)
    batch_s: float = 10.0
    min_batch_s: float = 5.0
    inflation_nis: float | None = 30.0
    inflation_factor: float = 4.0
    restart_std: tuple[float, float, float] | None = None
    correlated_noise: bool = True
    alpha: float = 1.0
    beta: float = 2.0
    kappa: float = 0.0


class UKFHealthEstimator:
    """Unscented Kalman filter for the gas-path health deltas.

    Call :meth:`update` with every observation in time order. It returns ``None`` until
    the first measurement update (until then the estimate is only the prior) and a
    :class:`HealthEstimate` afterwards.
    """

    def __init__(
        self,
        settings: UKFSettings | None = None,
        *,
        twin: QuasiSteadyTwin | None = None,
        gate: SteadyStateGate | None = None,
    ) -> None:
        self.settings = s = settings or UKFSettings()
        if s.model not in MODELS:
            raise ValueError(f"model must be one of {', '.join(MODELS)}")
        self.model: _TwinModel = MODELS[s.model](twin)
        self.gate = gate or SteadyStateGate()
        self.x = np.zeros(3)
        self.P = np.diag(np.square(s.prior_std))
        self._p_max = self.P.copy()
        self._q_per_s = np.diag(np.square(s.process_std_per_h)) / 3600.0
        self._buffer: list[Observation] = []
        self._last_t: float | None = None
        self._was_loaded = False
        self.updates = 0
        self.last_nis: float | None = None
        self.last_innovation: np.ndarray | None = None
        n = 3
        self._lambda = s.alpha**2 * (n + s.kappa) - n
        wm = np.full(2 * n + 1, 1.0 / (2.0 * (n + self._lambda)))
        wc = wm.copy()
        wm[0] = self._lambda / (n + self._lambda)
        wc[0] = wm[0] + (1.0 - s.alpha**2 + s.beta)
        self._wm, self._wc = wm, wc

    # ------------------------------------------------------------------ public
    def update(self, obs: Observation) -> HealthEstimate | None:
        self._time_update(obs)
        steady = self.gate.update(obs)
        if steady:
            self._buffer.append(obs)
            if self._span(self._buffer) >= self.settings.batch_s - 1e-9:
                self._flush()
        elif self._buffer:
            self._flush()
        if self.updates == 0:
            return None
        return self.estimate(obs.t_s, steady)

    def estimate(self, t_s: float, steady: bool = False) -> HealthEstimate:
        std = np.sqrt(np.clip(np.diag(self.P), 0.0, None))
        return HealthEstimate(t_s, _health(self.x), _health(std), steady)

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _span(batch: list[Observation]) -> float:
        # Samples are 1 s apart in the bank; count a batch by its covered time.
        if len(batch) < 2:
            return float(len(batch))
        return batch[-1].t_s - batch[0].t_s + (batch[1].t_s - batch[0].t_s)

    def _time_update(self, obs: Observation) -> None:
        s = self.settings
        if self._last_t is not None:
            dt = max(0.0, obs.t_s - self._last_t)
            self.P = self.P + self._q_per_s * dt
        self._last_t = obs.t_s
        loaded = obs.state == "loaded" and obs.breaker_closed
        if loaded and not self._was_loaded and self.updates > 0 and s.restart_std is not None:
            # A new loading after a stop: maintenance (a wash) may have changed the health.
            self.P = self.P + np.diag(np.square(s.restart_std))
        self._was_loaded = loaded

    def _capped(self, cov: np.ndarray) -> np.ndarray:
        """Scale rows and columns so that no variance exceeds the prior's (stays PD)."""

        ratio = np.sqrt(np.diag(self._p_max) / np.diag(cov))
        d = np.minimum(1.0, ratio)
        return cov * np.outer(d, d)

    def _flush(self) -> None:
        batch, self._buffer = self._buffer, []
        if self._span(batch) < self.settings.min_batch_s - 1e-9:
            return
        self._measurement_update(_mean_observation(batch), len(batch))

    def _sigma_points(self) -> np.ndarray:
        n = self.x.size
        cov = (n + self._lambda) * self.P
        try:
            root = np.linalg.cholesky(cov)
        except np.linalg.LinAlgError:
            vals, vecs = np.linalg.eigh(0.5 * (cov + cov.T))
            root = vecs @ np.diag(np.sqrt(np.clip(vals, 1e-18, None)))
        points = [self.x]
        for i in range(n):
            points.append(self.x + root[:, i])
        for i in range(n):
            points.append(self.x - root[:, i])
        return np.array(points)

    def _measurement_update(self, obs: Observation, samples: int) -> None:
        s = self.settings
        z = self.model.measured(obs)
        R = self.model.noise_covariance(self.x, obs, correlated=s.correlated_noise) / samples
        zhat, S, Pxz = self._predict_measurement(obs, R)
        innovation = z - zhat
        nis = float(innovation @ np.linalg.solve(S, innovation))
        if s.inflation_nis is not None and nis > s.inflation_nis:
            # The health moved faster than the random walk allows: forget faster.
            self.P = self._capped(self.P * s.inflation_factor)
            zhat, S, Pxz = self._predict_measurement(obs, R)
            innovation = z - zhat
        gain = np.linalg.solve(S.T, Pxz.T).T
        self.x = self.x + gain @ innovation
        self.P = self.P - gain @ S @ gain.T
        self.P = 0.5 * (self.P + self.P.T)
        self.updates += 1
        self.last_nis = nis
        self.last_innovation = innovation

    def _predict_measurement(
        self, obs: Observation, R: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        points = self._sigma_points()
        Z = np.array([self.model.predict(p, obs) for p in points])
        zhat = self._wm @ Z
        dz = Z - zhat
        dx = points - self.x
        S = (self._wc[:, None] * dz).T @ dz + R
        Pxz = (self._wc[:, None] * dx).T @ dz
        return zhat, S, Pxz


def _mean_observation(batch: list[Observation]) -> Observation:
    """One observation whose readings and inputs are the batch means."""

    last = batch[-1]
    n = float(len(batch))
    fields = ("igv_position", "power_mw", "exhaust_k", "speed_pu", "cdt_k", "cdp_kpa", "fuel_kg_s")
    means = {name: math.fsum(getattr(o, name) for o in batch) / n for name in fields}
    return replace(last, **means)
