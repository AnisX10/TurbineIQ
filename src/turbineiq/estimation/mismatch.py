"""Twin-plant mismatch: how much a slightly wrong twin calibration biases the health estimate.

With the default maps the twin is the plant's own model, so estimating health from it is
circular. Here the twin is built on a perturbed copy of the calibrated engine
(:func:`~turbineiq.simulation.maps.engine_health_maps`) while the plant keeps the
calibrated one. The perturbations are plausible calibration errors, chosen here and not
taken from any data set:

* drivetrain efficiency 0.5 % (relative) lower, about the uncertainty of a generator and
  gearbox loss figure;
* inlet or exhaust pressure loss 0.5 point higher (about 5 mbar of filter or stack loss);
* combustor pressure loss 0.5 point higher;
* cooling and leakage flow 0.5 point higher;
* air mass flow 1 % lower (the calibration fits it to a catalogue rating);
* site barometric pressure 1 kPa away from the twin's assumption (no barometer input).

:func:`steady_bias` gives the bias a fully converged estimator would have at one operating
point (weighted least squares on noise-free readings). :func:`evaluate` runs the
unscented Kalman filter on scenario streams, with and without mismatch, and scores it
against the ground truth; ``python -m turbineiq.estimation.mismatch`` writes the tables of
``docs/HEALTH_ESTIMATION.md``.
"""

from __future__ import annotations

import argparse
import math
import pickle
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import numpy as np

from turbineiq.engineering import CALIBRATED_6B03, RealGasInputs
from turbineiq.simulation.maps import CLEAN, Health, engine_health_maps

from .data import Observation, Truth, run_streams
from .observability import POINT, health_jacobian, steady_observation
from .twin import QuasiSteadyTwin
from .ukf import MODELS, HealthEstimate, UKFHealthEstimator, UKFSettings


def _scaled(**factors: float) -> Callable[[RealGasInputs], RealGasInputs]:
    def apply(engine: RealGasInputs) -> RealGasInputs:
        return replace(engine, **{k: getattr(engine, k) * v for k, v in factors.items()})

    return apply


def _shifted(**deltas: float) -> Callable[[RealGasInputs], RealGasInputs]:
    def apply(engine: RealGasInputs) -> RealGasInputs:
        return replace(engine, **{k: getattr(engine, k) + v for k, v in deltas.items()})

    return apply


def _barometer(delta_kpa: float) -> Callable[[RealGasInputs], RealGasInputs]:
    def apply(engine: RealGasInputs) -> RealGasInputs:
        p = engine.ambient_pressure_kpa
        # Mass flow at fixed inlet volume flow scales with inlet density (the maps do not).
        return replace(
            engine,
            ambient_pressure_kpa=p + delta_kpa,
            air_mass_flow_kg_s=engine.air_mass_flow_kg_s * (p + delta_kpa) / p,
        )

    return apply


@dataclass(frozen=True)
class Mismatch:
    name: str
    description: str
    perturb: Callable[[RealGasInputs], RealGasInputs]

    def engine(self, base: RealGasInputs = CALIBRATED_6B03) -> RealGasInputs:
        return self.perturb(base)


def _combine(*parts: Callable[[RealGasInputs], RealGasInputs]):
    def apply(engine: RealGasInputs) -> RealGasInputs:
        for part in parts:
            engine = part(engine)
        return engine

    return apply


_DRIVETRAIN = _scaled(drivetrain_efficiency=0.995)
_INLET = _shifted(inlet_pressure_loss_fraction=0.005)
_COMBUSTOR = _shifted(combustor_pressure_loss_fraction=0.005)
_AIR = _scaled(air_mass_flow_kg_s=0.99)

MISMATCHES: dict[str, Mismatch] = {
    m.name: m
    for m in (
        Mismatch("drivetrain", "drivetrain efficiency x 0.995 (-0.5 %)", _DRIVETRAIN),
        Mismatch("inlet_loss", "inlet pressure loss 1.0 -> 1.5 %", _INLET),
        Mismatch(
            "exhaust_loss",
            "exhaust pressure loss 1.0 -> 1.5 %",
            _shifted(exhaust_pressure_loss_fraction=0.005),
        ),
        Mismatch("combustor_loss", "combustor pressure loss 4.0 -> 4.5 %", _COMBUSTOR),
        Mismatch(
            "cooling",
            "cooling flow 8.0 -> 8.5 % of compressor flow",
            _shifted(cooling_flow_fraction=0.005),
        ),
        Mismatch("air_flow", "air mass flow x 0.99 (-1 %)", _AIR),
        Mismatch("barometer", "ambient pressure 1 kPa below the site's", _barometer(-1.0)),
        Mismatch(
            "combined",
            "drivetrain -0.5 %, inlet and combustor pressure loss +0.5 point, air flow -1 %",
            _combine(_DRIVETRAIN, _INLET, _COMBUSTOR, _AIR),
        ),
    )
}


@lru_cache(maxsize=16)
def mismatched_twin(engine: RealGasInputs) -> QuasiSteadyTwin:
    """A quasi-steady twin built on ``engine`` (the plant keeps the calibrated engine)."""

    return QuasiSteadyTwin(maps_for_ambient=lambda ambient_c: engine_health_maps(engine, ambient_c))


def twin_for(mismatch: str | None) -> QuasiSteadyTwin:
    if mismatch is None:
        return QuasiSteadyTwin()
    return mismatched_twin(MISMATCHES[mismatch].engine())


# ---------------------------------------------------------------------- steady-state bias
@dataclass(frozen=True)
class SteadyBias:
    ambient_c: float
    load_mw: float | None
    bias: np.ndarray  # converged estimate minus true health (fractions)
    nis: float  # one-sample normalised residual left after the fit (unexplained mismatch)


def steady_bias(
    twin: QuasiSteadyTwin,
    ambient_c: float,
    load_mw: float | None,
    plant_health: Health = CLEAN,
    model: str = "power_input",
) -> SteadyBias:
    """Bias of a converged estimator using ``twin`` against the calibrated plant.

    The plant reading is noise free; the health is the weighted least-squares fit of the
    twin to it (Gauss-Newton), weighted by the one-sample residual covariance as in the
    filter. With infinite steady data the filter converges to the same point.
    """

    obs = steady_observation(ambient_c, load_mw, plant_health, QuasiSteadyTwin())
    m = MODELS[model](twin)
    theta = np.array(plant_health, dtype=float)
    z = m.measured(obs)
    for _ in range(10):
        weight = np.linalg.inv(m.noise_covariance(theta, obs))
        jac = health_jacobian(m, obs, Health(*theta)) / POINT
        r = z - m.predict(theta, obs)
        step = np.linalg.solve(jac.T @ weight @ jac, jac.T @ weight @ r)
        theta = theta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    r = z - m.predict(theta, obs)
    nis = float(r @ np.linalg.solve(m.noise_covariance(theta, obs), r))
    return SteadyBias(ambient_c, load_mw, theta - np.array(plant_health), nis)


# ---------------------------------------------------------------------- scoring
#: Convergence tolerance per health parameter (flow capacity in fraction, efficiencies in
#: points as fractions). The thesis target is 0.3 point on efficiency.
TOLERANCE = (0.006, 0.003, 0.003)
SETTLE_S = 1200.0  # error statistics start this long after an onset


@dataclass(frozen=True)
class Segment:
    """A stretch of a scenario scored on its own: onset (or start) to end."""

    start_s: float
    end_s: float
    baseline: bool = True  # whether the 10 minutes before start are healthy and steady


SEGMENTS: dict[str, tuple[Segment, ...]] = {
    "clean_part_load": (Segment(0.0, 7200.0, False),),
    "clean_base_load": (Segment(0.0, 7200.0, False),),
    "clean_load_cycling": (Segment(0.0, 7200.0, False),),
    "clean_ambient_swing": (Segment(0.0, 7200.0, False),),
    "clean_fast_load_steps": (Segment(0.0, 7200.0, False),),
    "fouling_step_part_load": (Segment(1800.0, 7200.0),),
    "fouling_progressive_base_load": (Segment(1800.0, 7200.0),),
    "fouling_progressive_ambient_swing": (Segment(1800.0, 7200.0),),
    "erosion_step_part_load": (Segment(1800.0, 7200.0),),
    "fouling_then_erosion": (Segment(1800.0, 3600.0), Segment(3600.0, 7200.0, False)),
    "fouled_unit_offline_wash": (Segment(0.0, 1800.0, False), Segment(3600.0, 9000.0, False)),
    "exhaust_tc_drift_base_load": (Segment(1800.0, 7200.0),),
    "exhaust_tc_stuck_load_increase": (Segment(1800.0, 7200.0),),
    "exhaust_tc_noise": (Segment(1800.0, 7200.0),),
    "power_transducer_bias": (Segment(1800.0, 7200.0),),
    "fuel_meter_drift": (Segment(1800.0, 7200.0),),
    "cdt_sensor_bias": (Segment(1800.0, 7200.0),),
    "cdp_sensor_bias": (Segment(1800.0, 7200.0),),
    "slow_fuel_valve_load_steps": (Segment(1800.0, 7200.0),),
}

DEGRADATION = (
    "fouling_step_part_load",
    "fouling_progressive_base_load",
    "fouling_progressive_ambient_swing",
    "erosion_step_part_load",
    "fouling_then_erosion",
    "fouled_unit_offline_wash",
)
CLEAN_SCENARIOS = (
    "clean_part_load",
    "clean_base_load",
    "clean_load_cycling",
    "clean_ambient_swing",
    "clean_fast_load_steps",
)
SENSOR = (
    "exhaust_tc_drift_base_load",
    "exhaust_tc_stuck_load_increase",
    "exhaust_tc_noise",
    "power_transducer_bias",
    "fuel_meter_drift",
    "cdt_sensor_bias",
    "cdp_sensor_bias",
    "slow_fuel_valve_load_steps",
)


def run_estimator(
    estimator: UKFHealthEstimator, observations: Iterable[Observation]
) -> list[HealthEstimate | None]:
    return [estimator.update(obs) for obs in observations]


@dataclass(frozen=True)
class SegmentScore:
    """Scores of one segment of one run. Errors are estimate minus truth, in fractions."""

    convergence_s: tuple[float | None, ...]  # per parameter; None if never within tolerance
    mean_error: tuple[float, ...]  # over steady estimates from start + SETTLE_S to end
    max_abs_error: tuple[float, ...]
    rms_error: tuple[float, ...]
    final_error: tuple[float, ...]  # mean over the last 10 minutes of steady estimates
    change_error: tuple[float, ...] | None  # final change since the pre-onset baseline
    samples: int
    nis_exceed: float  # share of updates in the window whose NIS exceeded the 99.9 % bound


def score_segment(
    estimates: Sequence[HealthEstimate | None],
    truths: Sequence[Truth],
    segment: Segment,
    nis: Sequence[float | None] | None = None,
    tolerance: Sequence[float] = TOLERANCE,
) -> SegmentScore:
    rows = [
        (e, t, n)
        for e, t, n in zip(estimates, truths, nis or [None] * len(truths), strict=True)
        if e is not None and e.steady and segment.start_s <= e.t_s <= segment.end_s
    ]
    errors = np.array([np.subtract(e.mean, t.health) for e, t, _ in rows]).reshape(-1, 3)
    times = np.array([e.t_s for e, _, _ in rows])
    convergence: list[float | None] = []
    for i in range(3):
        bad = np.nonzero(np.abs(errors[:, i]) > tolerance[i])[0]
        if len(times) == 0:
            convergence.append(None)
        elif len(bad) == 0:
            convergence.append(max(0.0, times[0] - segment.start_s))
        elif bad[-1] == len(times) - 1:
            convergence.append(None)
        else:
            convergence.append(float(times[bad[-1] + 1] - segment.start_s))
    window = errors[times >= segment.start_s + SETTLE_S] if len(times) else errors
    last = errors[times >= times[-1] - 600.0] if len(times) else errors
    change = None
    if segment.baseline:
        before = [
            np.subtract(e.mean, t.health)
            for e, t in zip(estimates, truths, strict=True)
            if e is not None and e.steady and segment.start_s - 600.0 <= e.t_s < segment.start_s
        ]
        if before and len(last):
            change = tuple(np.mean(last, axis=0) - np.mean(before, axis=0))
    exceed = [n > _CHI2_999_4DOF for _, _, n in rows if n is not None]

    def stat(fn, data):
        return tuple(float(v) for v in fn(data)) if len(data) else (math.nan,) * 3

    return SegmentScore(
        convergence_s=tuple(convergence),
        mean_error=stat(lambda d: np.mean(d, axis=0), window),
        max_abs_error=stat(lambda d: np.max(np.abs(d), axis=0), window),
        rms_error=stat(lambda d: np.sqrt(np.mean(d**2, axis=0)), window),
        final_error=stat(lambda d: np.mean(d, axis=0), last),
        change_error=change,
        samples=len(window),
        nis_exceed=sum(exceed) / len(exceed) if exceed else math.nan,
    )


_CHI2_999_4DOF = 18.47  # 99.9 % point of chi-square with 4 degrees of freedom


@dataclass
class RunResult:
    scenario: str
    seed: int
    mismatch: str | None
    segments: list[SegmentScore] = field(default_factory=list)


def score_run(
    scenario_id: str,
    seed: int,
    observations: Sequence[Observation],
    truths: Sequence[Truth],
    mismatch: str | None = None,
    settings: UKFSettings | None = None,
) -> RunResult:
    estimator = UKFHealthEstimator(settings, twin=twin_for(mismatch))
    estimates: list[HealthEstimate | None] = []
    nis: list[float | None] = []
    last_updates = 0
    for obs in observations:
        estimates.append(estimator.update(obs))
        fresh = estimator.updates != last_updates
        last_updates = estimator.updates
        nis.append(estimator.last_nis if fresh else None)
    result = RunResult(scenario_id, seed, mismatch)
    for segment in SEGMENTS[scenario_id]:
        result.segments.append(score_segment(estimates, truths, segment, nis))
    return result


# ---------------------------------------------------------------------- experiment driver
def evaluation_seeds(bank_seed: int) -> tuple[int, ...]:
    """The bank seed and bank seed + 10000 k for k = 1..4 (evaluation data only)."""

    return (bank_seed, *(bank_seed + 10000 * k for k in range(1, 5)))


def load_streams(scenario_id: str, seed: int, cache: Path | None):
    """Streams of a scenario run, from a pickle cache when present (written when missing)."""

    from turbineiq.simulation.scenarios import scenario

    path = None if cache is None else cache / f"{scenario_id}@{seed}.pkl"
    if path is not None and path.exists():
        with open(path, "rb") as fh:
            return pickle.load(fh)
    streams = run_streams(scenario(scenario_id), seed=seed)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(streams, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return streams


def evaluate(
    scenario_ids: Sequence[str],
    seeds_for: Callable[[str], Sequence[int]],
    mismatches: Sequence[str | None] = (None, "combined"),
    cache: Path | None = None,
    settings: UKFSettings | None = None,
) -> list[RunResult]:
    results = []
    for sid in scenario_ids:
        for seed in seeds_for(sid):
            observations, truths = load_streams(sid, seed, cache)
            for mismatch in mismatches:
                results.append(score_run(sid, seed, observations, truths, mismatch, settings))
    return results


def _pts(x: float) -> str:
    return "n/a" if x is None or not math.isfinite(x) else f"{100.0 * x:+.2f}"


def _summary(results: list[RunResult], segment: int) -> dict[str, str]:
    scores = [r.segments[segment] for r in results]
    out: dict[str, str] = {}
    for i, name in enumerate(("flow", "eta_c", "eta_t")):
        means = [s.mean_error[i] for s in scores]
        worst = max(s.max_abs_error[i] for s in scores)
        conv = [s.convergence_s[i] for s in scores]
        conv_txt = (
            "never"
            if all(c is None for c in conv)
            else f"{statistics.median(c for c in conv if c is not None) / 60:.0f}"
            + ("" if all(c is not None for c in conv) else f" ({sum(c is None for c in conv)} not)")
        )
        out[f"{name}_mean"] = _pts(statistics.mean(means))
        out[f"{name}_max"] = _pts(worst).lstrip("+")
        out[f"{name}_conv"] = conv_txt
        changes = [s.change_error[i] for s in scores if s.change_error is not None]
        out[f"{name}_change"] = _pts(statistics.mean(changes)) if changes else "n/a"
        out[f"{name}_final"] = _pts(statistics.mean(s.final_error[i] for s in scores))
    out["nis"] = f"{100 * statistics.mean(s.nis_exceed for s in scores):.0f} %"
    return out


def markdown_tables(results: list[RunResult]) -> str:
    lines = [
        "Errors in points (estimate minus truth, x100); mean over seeds of the window mean "
        "(from 20 min after onset), worst absolute error over seeds, median convergence time "
        "in minutes to stay within 0.6 % flow / 0.3 point efficiency, and final change error "
        "relative to the 10 min before onset.",
        "",
        "| scenario | segment | twin | flow mean / max | ηc mean / max | ηt mean / max "
        "| conv. min (flow, ηc, ηt) | change err (flow, ηc, ηt) | NIS > 99.9 % |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    keys = sorted({(r.scenario, r.mismatch or "") for r in results}, key=lambda k: k)
    order = {sid: i for i, sid in enumerate(SEGMENTS)}
    keys.sort(key=lambda k: (order.get(k[0], 99), k[1]))
    for sid, mismatch in keys:
        group = [r for r in results if r.scenario == sid and (r.mismatch or "") == mismatch]
        for seg_index, seg in enumerate(SEGMENTS[sid]):
            s = _summary(group, seg_index)
            lines.append(
                f"| {sid} | {seg.start_s:.0f}-{seg.end_s:.0f} s | {mismatch or 'exact'} "
                f"| {s['flow_mean']} / {s['flow_max']} | {s['eta_c_mean']} / {s['eta_c_max']} "
                f"| {s['eta_t_mean']} / {s['eta_t_max']} "
                f"| {s['flow_conv']}, {s['eta_c_conv']}, {s['eta_t_conv']} "
                f"| {s['flow_change']}, {s['eta_c_change']}, {s['eta_t_change']} | {s['nis']} |"
            )
    return "\n".join(lines)


def bias_markdown(model: str = "power_input") -> str:
    from .observability import OPERATING_POINTS

    lines = [
        "| mismatch | point | flow bias | ηc bias | ηt bias | NIS left |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, mismatch in MISMATCHES.items():
        twin = mismatched_twin(mismatch.engine())
        for ambient_c, load_mw in OPERATING_POINTS:
            try:
                b = steady_bias(twin, ambient_c, load_mw, model=model)
            except ValueError:
                continue
            point = f"{ambient_c:g} C, " + ("base" if load_mw is None else f"{load_mw:g} MW")
            lines.append(
                f"| {name} | {point} | {_pts(b.bias[0])} | {_pts(b.bias[1])} | "
                f"{_pts(b.bias[2])} | {b.nis:.2f} |"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    from turbineiq.simulation.scenarios import scenario

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=None, help="stream pickle directory")
    parser.add_argument("--only", nargs="*", default=None, help="scenario ids")
    parser.add_argument("--bias", action="store_true", help="print the steady bias table only")
    parser.add_argument("--mismatch", nargs="*", default=["none", "combined"])
    args = parser.parse_args(argv)
    if args.bias:
        print(bias_markdown())
        return
    ids = args.only or list(SEGMENTS)
    mismatches = [None if m == "none" else m for m in args.mismatch]
    results = evaluate(
        ids, lambda sid: evaluation_seeds(scenario(sid).seed), mismatches, cache=args.cache
    )
    print(markdown_tables(results))


if __name__ == "__main__":
    main()
