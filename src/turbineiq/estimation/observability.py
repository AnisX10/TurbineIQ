"""Observability of the gas-path health parameters from the four steady-state readings.

For a steady operating point the twin's predictions are differentiated numerically with
respect to the three health deltas. The Jacobian is whitened with the covariance of one
sample's residual (instrument noise on the predicted readings plus the noise of the input
readings pushed through the twin), and its singular values, condition number and the
Cramer-Rao bound show how well, and in which directions, a single sample constrains the
health. Health is counted in points (0.01) for all three parameters: one percent of flow
capacity or one point of polytropic efficiency.

Two formulations are compared (:class:`~turbineiq.estimation.ukf.FuelInputModel`, the
twin as given, and :class:`~turbineiq.estimation.ukf.PowerInputModel`, with measured power
as the input and fuel flow predicted). With the full residual covariance they carry the
same information: one residual vector is an invertible linear map of the other (to first
order), so the Fisher information, singular values and bounds agree. They differ when the
noise model keeps only the residual variances (a diagonal covariance), and then the
estimator's actual spread follows from the sandwich formula, reported here as
``diag_std``.

Run ``PYTHONPATH=src python -m turbineiq.estimation.observability`` for the table that is
quoted in ``docs/HEALTH_ESTIMATION.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from turbineiq.simulation.maps import CLEAN, Health, igv_air_factor
from turbineiq.simulation.plant import PlantParameters

from .data import Observation
from .twin import QuasiSteadyTwin
from .ukf import FuelInputModel, PowerInputModel

POINT = 0.01  # health is reported per point (1 % flow capacity or 1 efficiency point)

#: Operating points: (ambient C, electrical load MW, or None for temperature-limited base load).
OPERATING_POINTS: tuple[tuple[float, float | None], ...] = (
    (15.0, 25.0),
    (15.0, 35.0),
    (15.0, 40.0),
    (15.0, None),
    (5.0, 35.0),
    (5.0, None),
    (30.0, 25.0),
    (30.0, 35.0),
    (30.0, None),
)


def steady_observation(
    ambient_c: float,
    load_mw: float | None,
    health: Health = CLEAN,
    twin: QuasiSteadyTwin | None = None,
) -> Observation:
    """A noise-free steady observation of the twin at an operating point.

    Rated speed and open IGV (the auto schedule while loaded). ``load_mw=None`` is base
    load: the fuel flow at which the exhaust reaches the temperature-control limit (10 K
    above the calibrated rated exhaust temperature, as in the plant). A load above what
    the limit allows raises ``ValueError``.
    """

    twin = twin or QuasiSteadyTwin()
    maps = twin.maps(ambient_c)
    clean = maps.clean
    g = igv_air_factor(1.0)
    limit_k = clean.rated_exhaust_k + PlantParameters().temperature_limit_margin_k

    def exhaust(fuel_pu: float) -> float:
        return maps.lookup(health, 1.0, g, fuel_pu)[1]

    def power_mw(fuel_pu: float) -> float:
        return clean.electrical_mw(maps.lookup(health, 1.0, g, fuel_pu)[0])

    fuel_max = _bisect(lambda f: exhaust(f) - limit_k)
    if load_mw is None:
        fuel_pu = fuel_max
    else:
        fuel_pu = _bisect(lambda f: power_mw(f) - load_mw)
        if fuel_pu > fuel_max:
            raise ValueError(f"{load_mw} MW is above base load at {ambient_c} C")
    base = Observation(
        t_s=0.0,
        state="loaded",
        breaker_closed=True,
        load_setpoint_mw=load_mw if load_mw is not None else 1e3,
        ambient_temperature_c=ambient_c,
        igv_position=1.0,
        power_mw=0.0,
        exhaust_k=0.0,
        speed_pu=1.0,
        cdt_k=0.0,
        cdp_kpa=0.0,
        fuel_kg_s=fuel_pu * clean.rated_fuel_kg_s,
    )
    p = twin.predict(health, base)
    return replace(
        base, power_mw=p.power_mw, exhaust_k=p.exhaust_k, cdt_k=p.cdt_k, cdp_kpa=p.cdp_kpa
    )


def _bisect(f, lo: float = 0.05, hi: float = 2.0) -> float:
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if f(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def health_jacobian(model, obs: Observation, health: Health = CLEAN, step: float = 0.002):
    """d(prediction)/d(health) by central differences, per point of health (m x 3)."""

    columns = []
    for i in range(3):
        hi = np.array(health, dtype=float)
        lo = hi.copy()
        hi[i] += step
        lo[i] -= step
        columns.append((model.predict(hi, obs) - model.predict(lo, obs)) / (2.0 * step) * POINT)
    return np.column_stack(columns)


@dataclass(frozen=True)
class Observability:
    """Information in one steady sample about the health (all in points)."""

    model: str
    ambient_c: float
    load_mw: float  # electrical power at the point
    base_load: bool
    jacobian: np.ndarray  # m x 3, output units per point
    residual_std: np.ndarray  # one-sample residual std per output
    singular_values: np.ndarray  # of the whitened Jacobian (full covariance), per point
    condition_number: float
    weak_direction: np.ndarray  # unit vector in (flow, comp eff, turb eff) space
    crb_std: np.ndarray  # Cramer-Rao std per parameter for one sample (full covariance)
    crb_correlation: np.ndarray  # 3 x 3 correlation of that bound
    diag_std: np.ndarray  # actual std of an estimator that uses only the variances

    def per_window(self, samples: int) -> np.ndarray:
        """Cramer-Rao std per parameter after averaging ``samples`` independent samples."""

        return self.crb_std / np.sqrt(samples)


def analyse(model, obs: Observation, health: Health = CLEAN) -> Observability:
    jac = health_jacobian(model, obs, health)
    cov = model.noise_covariance(health, obs, correlated=True)
    chol = np.linalg.cholesky(cov)
    white = np.linalg.solve(chol, jac)
    _, sv, vt = np.linalg.svd(white, full_matrices=False)
    info = white.T @ white
    crb = np.linalg.inv(info)
    crb_std = np.sqrt(np.diag(crb))
    corr = crb / np.outer(crb_std, crb_std)
    # An estimator weighted by the variances only (diagonal covariance): sandwich formula.
    d_inv = np.diag(1.0 / np.diag(cov))
    a = np.linalg.inv(jac.T @ d_inv @ jac)
    sandwich = a @ jac.T @ d_inv @ cov @ d_inv @ jac @ a
    weak = vt[-1] * np.sign(vt[-1][np.argmax(np.abs(vt[-1]))])
    clean = model.twin.maps(obs.ambient_temperature_c).clean
    limit_k = clean.rated_exhaust_k + PlantParameters().temperature_limit_margin_k
    return Observability(
        model=model.name,
        ambient_c=obs.ambient_temperature_c,
        load_mw=obs.power_mw,
        base_load=abs(obs.exhaust_k - limit_k) < 1e-3,
        jacobian=jac,
        residual_std=np.sqrt(np.diag(cov)),
        singular_values=sv,
        condition_number=float(sv[0] / sv[-1]),
        weak_direction=weak,
        crb_std=crb_std,
        crb_correlation=corr,
        diag_std=np.sqrt(np.diag(sandwich)),
    )


def observability_table(
    points: tuple[tuple[float, float | None], ...] = OPERATING_POINTS,
    health: Health = CLEAN,
    twin: QuasiSteadyTwin | None = None,
) -> list[Observability]:
    twin = twin or QuasiSteadyTwin()
    rows = []
    for ambient_c, load_mw in points:
        try:
            obs = steady_observation(ambient_c, load_mw, health, twin)
        except ValueError:
            continue
        for model in (FuelInputModel(twin), PowerInputModel(twin)):
            rows.append(analyse(model, obs, health))
    return rows


def _fmt(values, digits: int = 3) -> str:
    return ", ".join(f"{v:.{digits}f}" for v in values)


def main() -> None:
    rows = observability_table()
    print("Per-sample information (health in points; window = 600 averaged samples)\n")
    print(
        "| model | ambient C | power MW | singular values | cond. | weak direction "
        "(flow, ηc, ηt) | CRB std 1 sample | CRB std 600 samples | diag-R std 1 sample |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        load = f"{r.load_mw:.1f}" + (" (base)" if r.base_load else "")
        print(
            f"| {r.model} | {r.ambient_c:g} | {load} | {_fmt(r.singular_values, 2)} | "
            f"{r.condition_number:.1f} | {_fmt(r.weak_direction, 2)} | {_fmt(r.crb_std)} | "
            f"{_fmt(r.per_window(600))} | {_fmt(r.diag_std)} |"
        )
    print("\nJacobians (output change per point of each health parameter) and residual std:")
    for r in rows:
        print(f"\n{r.model}, {r.ambient_c:g} C, {r.load_mw:.1f} MW:")
        print("  residual std:", _fmt(r.residual_std))
        names = (
            ("power", "exhaust", "cdt", "cdp")
            if r.model == "fuel_input"
            else ("fuel", "exhaust", "cdt", "cdp")
        )
        for name, row in zip(names, r.jacobian, strict=True):
            print(f"  {name:8s}", _fmt(row))
        print("  CRB correlation:\n", np.array2string(r.crb_correlation, precision=3))


if __name__ == "__main__":
    main()
