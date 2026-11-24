"""What the layer knows about the plant: health estimate, twin agreement, thermocouple trust.

:class:`TwinMonitor` takes one :class:`~turbineiq.estimation.data.Observation` per second
(instrument readings and known operating inputs only) and keeps:

* an unscented Kalman filter for the three health deltas, built on the twin's engine (a
  perturbed copy of the calibrated one) and **without the exhaust temperature** among its
  measurements, so a failed exhaust thermocouple cannot drag the health estimate with it
  (checked on the bank: the estimate with and without the exhaust channel agree to within
  0.001 on fouling and erosion steps, and the exhaust-free one moves about a third as far on
  the thermocouple-drift scenario);
* a degradation forecaster on those estimates (for the wash decision);
* steady-state residuals of every channel against the quasi-steady twin at the estimated
  health, averaged over a window: the non-exhaust channels give the **model mismatch
  index** the guard checks, and the exhaust channel gives the **thermocouple check**;
* a model-based exhaust temperature (the twin's prediction from measured fuel flow, speed,
  IGV and ambient at the estimated health, through a first-order lag standing in for the
  thermocouple lag) that can replace the thermocouple in the temperature control.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from turbineiq.engineering import RealGasInputs
from turbineiq.estimation.data import Observation
from turbineiq.estimation.forecast import DegradationForecaster
from turbineiq.estimation.mismatch import MISMATCHES, mismatched_twin
from turbineiq.estimation.steady import SteadyStateGate
from turbineiq.estimation.twin import MEASUREMENTS, QuasiSteadyTwin, measured
from turbineiq.estimation.ukf import (
    HealthEstimate,
    PowerInputModel,
    UKFHealthEstimator,
    instrument_sigma,
)
from turbineiq.simulation.maps import CLEAN, Health

DEFAULT_TWIN_ENGINE = "combined"


def twin_engine(name: str | None = DEFAULT_TWIN_ENGINE) -> RealGasInputs:
    """The engine the layer's twin is built on: a WP4 mismatch case, or the plant's own."""

    from turbineiq.engineering import CALIBRATED_6B03

    if name is None:
        return CALIBRATED_6B03
    return MISMATCHES[name].engine()


class ExhaustFreeModel(PowerInputModel):
    """The power-input measurement model without the exhaust temperature channel."""

    name = "power_input_no_exhaust"
    outputs = ("fuel_kg_s", "cdt_k", "cdp_kpa")

    def predict(self, health, obs: Observation) -> np.ndarray:
        return super().predict(health, obs)[[0, 2, 3]]


def observation_from_snapshot(snap: dict[str, Any]) -> Observation:
    """The layer's view of a session snapshot: inputs it knows and instrument readings."""

    m = snap["measured"]
    return Observation(
        t_s=float(snap["t_s"]),
        state=str(snap["state"]),
        breaker_closed=bool(snap["breaker_closed"]),
        load_setpoint_mw=float(snap["load_setpoint_mw"]),
        ambient_temperature_c=float(snap["ambient_temperature_c"]),
        igv_position=float(snap["igv_position"]),
        power_mw=float(m["electrical_power_mw"]),
        exhaust_k=float(m["exhaust_temperature_k"]),
        speed_pu=float(m["speed_pu"]),
        cdt_k=float(m["compressor_discharge_temperature_k"]),
        cdp_kpa=float(m["compressor_discharge_pressure_kpa"]),
        fuel_kg_s=float(m["fuel_flow_kg_s"]),
    )


@dataclass(frozen=True)
class MonitorSettings:
    residual_window_s: float = 120.0
    #: Mean exhaust residual (K) beyond which the thermocouple is distrusted. Twin mismatch
    #: alone leaves a few kelvin; 3 % fouling, which the estimate absorbs, leaves less.
    exhaust_residual_k: float = 12.0
    #: Exhaust reading scatter (K, standard deviation about a 10 s mean) beyond which the
    #: thermocouple is distrusted as noisy; the instrument's own noise is 0.5 K.
    exhaust_scatter_k: float = 2.0
    #: Consecutive steady windows a thermocouple symptom must persist.
    exhaust_persist: int = 3
    thermocouple_lag_s: float = 3.0


@dataclass(frozen=True)
class TwinStatus:
    """The monitor's view after the latest observation."""

    t_s: float
    loaded: bool
    steady: bool
    health: Health
    health_std: Health
    estimator_updates: int
    mismatch_index: float | None  # largest |mean residual| / one-sample sigma, non-exhaust
    residual_mean: dict[str, float] = field(default_factory=dict)
    exhaust_residual_k: float | None = None
    exhaust_scatter_k: float | None = None
    exhaust_suspect: bool = False
    exhaust_reason: str | None = None
    model_exhaust_k: float | None = None
    fouling_rate_per_h: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "t_s": self.t_s,
            "loaded": self.loaded,
            "steady": self.steady,
            "health": dict(self.health._asdict()),
            "health_std": dict(self.health_std._asdict()),
            "estimator_updates": self.estimator_updates,
            "mismatch_index": self.mismatch_index,
            "residual_mean": dict(self.residual_mean),
            "exhaust_residual_k": self.exhaust_residual_k,
            "exhaust_scatter_k": self.exhaust_scatter_k,
            "exhaust_suspect": self.exhaust_suspect,
            "exhaust_reason": self.exhaust_reason,
            "model_exhaust_k": self.model_exhaust_k,
            "fouling_rate_per_h": self.fouling_rate_per_h,
        }


class TwinMonitor:
    def __init__(
        self,
        twin_engine_name: str | None = DEFAULT_TWIN_ENGINE,
        settings: MonitorSettings | None = None,
    ) -> None:
        self.settings = settings or MonitorSettings()
        self.engine_name = twin_engine_name
        self.engine = twin_engine(twin_engine_name)
        self.twin: QuasiSteadyTwin = (
            QuasiSteadyTwin() if twin_engine_name is None else mismatched_twin(self.engine)
        )
        self.estimator = UKFHealthEstimator(twin=self.twin)
        self.estimator.model = ExhaustFreeModel(self.twin)
        self.forecaster = DegradationForecaster()
        self.gate = SteadyStateGate()
        self.power_model = PowerInputModel(self.twin)
        self._residuals: deque[tuple[float, np.ndarray]] = deque()
        self._exhaust_window: deque[float] = deque(maxlen=10)
        self._scatter: deque[float] = deque(maxlen=12)
        self._suspect_count = 0
        self.exhaust_suspect = False
        self.exhaust_reason: str | None = None
        self._model_exhaust: float | None = None
        self._last_t: float | None = None
        self.last_estimate: HealthEstimate | None = None
        self.status: TwinStatus | None = None

    # ------------------------------------------------------------------ estimates
    @property
    def health(self) -> Health:
        est = self.last_estimate
        return est.mean if est is not None else CLEAN

    @property
    def health_std(self) -> Health:
        return self.estimator.estimate(self._last_t or 0.0).std

    def note_wash(self) -> None:
        """A logged offline wash: the compressor health may have jumped back."""

        s = self.estimator.settings.prior_std
        p = self.estimator.P
        p[0, 0] = max(p[0, 0], s[0] ** 2)
        p[1, 1] = max(p[1, 1], s[1] ** 2)
        self.forecaster.reset_level()

    # ------------------------------------------------------------------ update
    def update(self, obs: Observation) -> TwinStatus:
        s = self.settings
        dt = 1.0 if self._last_t is None else max(0.0, obs.t_s - self._last_t)
        self._last_t = obs.t_s
        estimate = self.estimator.update(obs)
        if estimate is not None:
            self.last_estimate = estimate
            if estimate.steady:
                self.forecaster.update(estimate)
        loaded = obs.state == "loaded" and obs.breaker_closed
        steady = self.gate.update(obs)
        health = self.health

        # Model exhaust temperature (soft sensor), lagged like a thermocouple.
        model_exhaust = None
        if loaded and obs.fuel_kg_s > 0:
            raw = self.twin.predict(health, obs).exhaust_k
            if self._model_exhaust is None:
                self._model_exhaust = raw
            else:
                a = min(1.0, dt / s.thermocouple_lag_s)
                self._model_exhaust += a * (raw - self._model_exhaust)
            model_exhaust = self._model_exhaust
        else:
            self._model_exhaust = None

        mismatch = None
        residual_mean: dict[str, float] = {}
        exhaust_residual = None
        scatter = None
        if not loaded:
            self._residuals.clear()
            self._exhaust_window.clear()
            self._scatter.clear()
        if steady:
            predicted = np.array(self.twin.predict(health, obs).as_tuple())
            self._residuals.append((obs.t_s, np.subtract(measured(obs), predicted)))
            while obs.t_s - self._residuals[0][0] > s.residual_window_s:
                self._residuals.popleft()
            self._exhaust_window.append(obs.exhaust_k)
            if len(self._exhaust_window) == self._exhaust_window.maxlen:
                self._scatter.append(statistics.pstdev(self._exhaust_window))
                self._exhaust_window.clear()
        if self._residuals and self._residuals[-1][0] - self._residuals[0][0] >= (
            0.5 * s.residual_window_s
        ):
            mean = np.mean([r for _, r in self._residuals], axis=0)
            residual_mean = {name: float(v) for name, v in zip(MEASUREMENTS, mean, strict=True)}
            values = dict(zip(MEASUREMENTS, measured(obs), strict=True))
            z = [
                abs(residual_mean[n]) / instrument_sigma(n, values[n])
                for n in MEASUREMENTS
                if n != "exhaust_k"
            ]
            mismatch = float(max(z))
            exhaust_residual = residual_mean["exhaust_k"]
        if self._scatter:
            scatter = float(statistics.median(self._scatter))

        if steady and not self.exhaust_suspect:
            symptom = None
            if exhaust_residual is not None and abs(exhaust_residual) > s.exhaust_residual_k:
                symptom = (
                    f"exhaust thermocouple reads {exhaust_residual:+.1f} K against the twin "
                    f"(limit {s.exhaust_residual_k:.0f} K) while the other channels agree"
                )
            elif scatter is not None and len(self._scatter) >= 6 and scatter > s.exhaust_scatter_k:
                symptom = (
                    f"exhaust thermocouple scatter {scatter:.1f} K (limit "
                    f"{s.exhaust_scatter_k:.1f} K, instrument noise 0.5 K)"
                )
            # Only blame the thermocouple when the rest of the twin still matches.
            if symptom and mismatch is not None and mismatch < 4.0:
                self._suspect_count += 1
                if self._suspect_count >= s.exhaust_persist * 10:
                    self.exhaust_suspect = True
                    self.exhaust_reason = symptom
            else:
                self._suspect_count = 0

        rate = None
        if self.forecaster.used >= 3:
            try:
                rate = float(self.forecaster.rate_per_h.compressor_flow)
            except Exception:  # noqa: BLE001 - forecaster not ready yet
                rate = None
        std = self.health_std
        self.status = TwinStatus(
            t_s=obs.t_s,
            loaded=loaded,
            steady=steady,
            health=health,
            health_std=std,
            estimator_updates=self.estimator.updates,
            mismatch_index=mismatch,
            residual_mean=residual_mean,
            exhaust_residual_k=exhaust_residual,
            exhaust_scatter_k=scatter,
            exhaust_suspect=self.exhaust_suspect,
            exhaust_reason=self.exhaust_reason,
            model_exhaust_k=model_exhaust,
            fouling_rate_per_h=rate if rate is None or math.isfinite(rate) else None,
        )
        return self.status

    def trust_thermocouple(self) -> None:
        """Operator says the thermocouple is repaired: clear the suspicion."""

        self.exhaust_suspect = False
        self.exhaust_reason = None
        self._suspect_count = 0

    # ------------------------------------------------------------------ steady what-if
    def steady_point(
        self, obs: Observation, power_mw: float, igv_position: float, health: Health | None = None
    ) -> tuple[float, float, float]:
        """Fuel (kg/s), exhaust (K) and heat rate (kJ/kWh) the twin predicts at a power and
        IGV position, at rated speed and the observation's ambient."""

        from dataclasses import replace

        h = self.health if health is None else health
        at = replace(obs, power_mw=power_mw, igv_position=igv_position, speed_pu=1.0)
        fuel, at_fuel = self.power_model.fuel_for_power(h, at)
        exhaust = self.twin.predict(h, at_fuel).exhaust_k
        lhv = self.twin.maps(obs.ambient_temperature_c).clean.fuel_lhv_kj_kg
        heat_rate = fuel * lhv * 3600.0 / (power_mw * 1000.0)
        return fuel, exhaust, heat_rate
