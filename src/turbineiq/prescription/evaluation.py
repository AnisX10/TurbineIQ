"""Evaluation of the prescriptive layer on the scenario bank (roadmap WP5, research question RQ3).

One run is a :class:`RunSpec`: a scenario (from the bank, or the wash study defined here),
an autonomy mode, a noise seed and the layer's settings. :func:`run_one` drives it with
:func:`~turbineiq.prescription.runner.run_supervised` and reduces it to a JSON-able result:
the true-value score, the decision log (compact), counters, skipped script steps, the
thermocouple response times and the twin-trust statistics. Results are cached per run as
JSON (:func:`ensure_results`), keyed by the spec and a fingerprint of the code that
determines them, and run ``workers`` at a time in separate processes.

Aggregation (:func:`paired_differences`, :func:`bootstrap_ci`, :func:`summarise_main` and
friends) compares each mode with the manual run of the same scenario and seed: the plant,
the noise and the script are identical, so the paired difference isolates the layer.
Confidence intervals are percentile bootstraps that resample seeds within each scenario
(the scenario mix is the bank's and stays fixed).

Seeds: thresholds are checked on tuning seeds (:data:`TUNING_SEEDS`, inside the WP4 tuning
range 1000-1999); results are reported on :data:`TEST_SEEDS`, which no choice was made on.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from turbineiq.engineering import RealGasInputs
from turbineiq.estimation.benchmark import model_fingerprint, source_fingerprint
from turbineiq.estimation.data import scenario_with_seed
from turbineiq.estimation.mismatch import MISMATCHES, Mismatch
from turbineiq.simulation.scenarios import (
    GROUND_TRUTH_COMMANDS,
    LOAD_AT_S,
    ONSET_S,
    SCENARIOS,
    Scenario,
    ScriptStep,
)

from .guard import GuardLimits
from .monitor import DEFAULT_TWIN_ENGINE, twin_engine
from .runner import OperatorModel, RunRecord, run_supervised, score
from .supervisor import Economics, SupervisorConfig

RESULT_FORMAT = 1
DEFAULT_CACHE_DIR = Path("data/prescription/cache")
TUNING_SEEDS: tuple[int, ...] = tuple(range(1000, 1005))
TEST_SEEDS: tuple[int, ...] = tuple(range(2000, 2005))
MODES: tuple[str, ...] = ("manual", "advisory", "autonomous")
#: Scores start when the dispatcher first asks for load; the start-up before is the same in
#: every mode.
SCORE_FROM_S = LOAD_AT_S
EXHAUST_SCENARIOS: tuple[str, ...] = (
    "exhaust_tc_drift_base_load",
    "exhaust_tc_stuck_load_increase",
    "exhaust_tc_noise",
)

# ----------------------------------------------------------------------------- mismatch

LARGE_MISMATCH = "combined_x3"


def _combined_x3(engine: RealGasInputs) -> RealGasInputs:
    """Three times the ``combined`` perturbation of WP4 (each part tripled)."""

    return replace(
        engine,
        drivetrain_efficiency=engine.drivetrain_efficiency * (1.0 - 3 * 0.005),
        inlet_pressure_loss_fraction=engine.inlet_pressure_loss_fraction + 3 * 0.005,
        combustor_pressure_loss_fraction=engine.combustor_pressure_loss_fraction + 3 * 0.005,
        air_mass_flow_kg_s=engine.air_mass_flow_kg_s * (1.0 - 3 * 0.01),
    )


def register_large_mismatch() -> None:
    """Add :data:`LARGE_MISMATCH` to the WP4 mismatch registry (in this process only)."""

    if LARGE_MISMATCH not in MISMATCHES:
        MISMATCHES[LARGE_MISMATCH] = Mismatch(
            LARGE_MISMATCH,
            "3 x combined: drivetrain -1.5 %, inlet and combustor pressure loss +1.5 point, "
            "air flow -3 %",
            _combined_x3,
        )


register_large_mismatch()

# ----------------------------------------------------------------------------- wash study

WASH_STUDY_LOAD_MW = 40.0
WASH_STUDY_RATE_PCT_PER_H = 2.0
WASH_STUDY_FOULING_H = 6.0
WASH_STUDY_DURATION_S = ONSET_S + WASH_STUDY_FOULING_H * 3600.0
#: Timing of a scripted offline wash: the rotor reaches standstill about 860 s after a stop
#: from 40 MW, and the breaker closes about 237 s after a start.
STOP_TO_WASH_S = 900.0
WASH_TO_START_S = 60.0
START_TO_LOAD_S = 300.0
WASH_INTERVALS_H: tuple[float, ...] = (0.75, 1.0, 1.5, 2.0, 3.0)


def wash_study_scenario(interval_h: float | None = None) -> Scenario:
    """Progressive fouling at 2 %/h for 6 h at 40 MW and 15 C; with ``interval_h`` the
    operator stops, washes and restarts the unit every ``interval_h`` hours of fouling."""

    script = [
        ScriptStep(0.0, "start"),
        ScriptStep(LOAD_AT_S, "set_load", {"mw": WASH_STUDY_LOAD_MW, "ramp_mw_per_min": 60.0}),
        ScriptStep(
            ONSET_S,
            "inject_degradation",
            {
                "kind": "compressor_fouling",
                "severity_pct": 0.0,
                "rate_pct_per_h": WASH_STUDY_RATE_PCT_PER_H,
            },
        ),
    ]
    if interval_h is None:
        sid = "wash_study_never"
        text = "no wash"
    else:
        sid = f"wash_study_every_{interval_h:g}h"
        text = f"a scripted offline wash every {interval_h:g} h"
        k = 1
        while True:
            t = ONSET_S + k * interval_h * 3600.0
            if t + STOP_TO_WASH_S + WASH_TO_START_S + START_TO_LOAD_S >= WASH_STUDY_DURATION_S:
                break
            script += [
                ScriptStep(t, "stop"),
                ScriptStep(t + STOP_TO_WASH_S, "wash_compressor"),
                ScriptStep(t + STOP_TO_WASH_S + WASH_TO_START_S, "start"),
                ScriptStep(
                    t + STOP_TO_WASH_S + WASH_TO_START_S + START_TO_LOAD_S,
                    "set_load",
                    {"mw": WASH_STUDY_LOAD_MW, "ramp_mw_per_min": 10.0},
                ),
            ]
            k += 1
    return Scenario(
        sid,
        "maintenance",
        f"Compressor fouling grows at {WASH_STUDY_RATE_PCT_PER_H:g} %/h for "
        f"{WASH_STUDY_FOULING_H:g} h at {WASH_STUDY_LOAD_MW:g} MW, 15 C, with {text}.",
        601,
        WASH_STUDY_DURATION_S,
        tuple(script),
    )


def get_scenario(scenario_id: str) -> Scenario:
    for item in SCENARIOS:
        if item.id == scenario_id:
            return item
    if scenario_id == "wash_study_never":
        return wash_study_scenario(None)
    prefix = "wash_study_every_"
    if scenario_id.startswith(prefix) and scenario_id.endswith("h"):
        return wash_study_scenario(float(scenario_id[len(prefix) : -1]))
    raise KeyError(scenario_id)


# ----------------------------------------------------------------------------- runs


@dataclass(frozen=True)
class RunSpec:
    scenario_id: str
    mode: str
    seed: int
    twin_engine: str | None = DEFAULT_TWIN_ENGINE
    operator_delay_s: float = 300.0
    load_objective: str = "track_demand"
    autonomous_wash: bool = False
    igv_options: tuple[str | float, ...] | None = None  # None: the supervisor's default
    until_s: float | None = None

    def config(self) -> SupervisorConfig:
        cfg = SupervisorConfig(
            twin_engine=self.twin_engine,
            load_objective=self.load_objective,
            limits=GuardLimits(autonomous_wash=self.autonomous_wash),
        )
        if self.igv_options is not None:
            cfg = replace(cfg, igv_options=tuple(self.igv_options))
        return cfg

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["igv_options"] = None if self.igv_options is None else list(self.igv_options)
        return d

    def key(self) -> str:
        item = get_scenario(self.scenario_id)
        engine = None if self.twin_engine is None else repr(twin_engine(self.twin_engine))
        payload = json.dumps(
            {
                "format": RESULT_FORMAT,
                "spec": self.to_dict(),
                "engine": engine,
                "scenario": {
                    "duration_s": item.duration_s,
                    "ambient_c": item.ambient_temperature_c,
                    "script": [s.to_dict() for s in item.script],
                },
                "code": code_fingerprint(),
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        engine_tag = "exact" if self.twin_engine is None else self.twin_engine
        return f"{self.scenario_id}__{self.mode}__s{self.seed}__{engine_tag}__{digest}"


_CODE_FINGERPRINT: str | None = None
#: Modules whose code determines a run (the evaluation's own aggregation is not among them;
#: a change to what :func:`run_one` records bumps :data:`RESULT_FORMAT` instead).
_CORE_MODULES = ("guard", "monitor", "runner", "supervisor", "twin")


def code_fingerprint() -> str:
    global _CODE_FINGERPRINT
    if _CODE_FINGERPRINT is None:
        digest = hashlib.sha256(model_fingerprint().encode())
        here = Path(__file__).parent
        for name in _CORE_MODULES:
            digest.update(source_fingerprint((here / f"{name}.py").read_text()).encode())
        est = Path(importlib.import_module("turbineiq.estimation").__file__).parent
        for path in sorted(est.glob("*.py")):
            if path.name in ("benchmark.py",):
                continue
            digest.update(path.name.encode())
            digest.update(source_fingerprint(path.read_text()).encode())
        _CODE_FINGERPRINT = digest.hexdigest()
    return _CODE_FINGERPRINT


class _Observer:
    """Per-second statistics from the supervisor and the plant truth (never acts)."""

    def __init__(self) -> None:
        self.first_suspect_s: float | None = None
        self.max_abs_exhaust_residual_k = 0.0
        self.max_exhaust_scatter_k = 0.0
        self.mismatch: list[float] = []
        self.model_exhaust: list[float | None] = []
        self.substitute_s = 0
        self.fouling_pct: list[float] = []
        self.washes = 0
        self._last_fouling = 0.0

    def __call__(self, t: float, session, sup) -> None:
        st = sup.status
        if st is not None:
            if st.exhaust_suspect and self.first_suspect_s is None:
                self.first_suspect_s = t
            if not st.exhaust_suspect:
                if st.exhaust_residual_k is not None:
                    self.max_abs_exhaust_residual_k = max(
                        self.max_abs_exhaust_residual_k, abs(st.exhaust_residual_k)
                    )
                if st.exhaust_scatter_k is not None and st.loaded:
                    self.max_exhaust_scatter_k = max(
                        self.max_exhaust_scatter_k, st.exhaust_scatter_k
                    )
            if st.loaded and st.mismatch_index is not None:
                self.mismatch.append(st.mismatch_index)
            self.model_exhaust.append(st.model_exhaust_k)
        else:
            self.model_exhaust.append(None)
        if sup.substitute_active:
            self.substitute_s += 1
        fouling = float(session.plant.faults.degradation["compressor_fouling"].severity_pct)
        if fouling < self._last_fouling - 0.05:
            self.washes += 1
        self._last_fouling = fouling
        self.fouling_pct.append(fouling)


def _initial_status(mode: str, approved: bool) -> str:
    if mode == "autonomous":
        return "applied" if approved else "escalated"
    return "pending" if approved else "escalated"


def _compact_decision(d) -> dict[str, Any]:
    v = d.verdict
    out = {
        "id": d.id,
        "t_s": d.t_s,
        "problem": d.problem,
        "mode": d.mode,
        "approved": bool(v["approved"]),
        "initial_status": _initial_status(d.mode, bool(v["approved"])),
        "status": d.status,
        "failed_checks": [c["name"] for c in v["checks"] if not c["passed"]],
        "guard_reason": v["reason"],
        "resolved_t_s": d.resolved_t_s,
        "resolved_by": d.resolved_by,
        "summary": d.summary,
        "actions": d.actions,
    }
    obj = d.objective or {}
    if d.problem == "load_setpoint":
        out["heat_rate_gain_pct"] = obj.get("heat_rate_gain_pct")
        out["proposed"] = obj.get("proposed")
    elif d.problem == "compressor_wash":
        for k in (
            "loss_usd_per_h",
            "threshold_usd_per_h",
            "optimal_interval_h",
            "fouling_flow_delta",
            "loss_growth_usd_per_h2",
        ):
            out[k] = obj.get(k)
    elif d.problem == "exhaust_feedback":
        out["exhaust_residual_k"] = obj.get("exhaust_residual_k")
        out["exhaust_scatter_k"] = obj.get("exhaust_scatter_k")
    return out


def _fault_onset(item: Scenario) -> float | None:
    times = [s.t_s for s in item.script if s.command in GROUND_TRUTH_COMMANDS]
    later = [t for t in times if t > 0.0]
    if later:
        return min(later)
    return min(times) if times else None


def _exhaust_onset(item: Scenario) -> float | None:
    for s in item.script:
        if s.command == "inject_sensor_fault" and s.params.get("channel") == "exhaust_temperature":
            return s.t_s
    return None


def _soft_sensor_error(rec: RunRecord, obs: _Observer) -> dict[str, Any]:
    errs = []
    for i, m in enumerate(obs.model_exhaust):
        if m is None or rec.state[i] != "loaded":
            continue
        errs.append(m - rec.exhaust_k[i])
    if not errs:
        return {"n": 0}
    a = np.abs(errs)
    return {
        "n": len(errs),
        "mean_k": float(np.mean(errs)),
        "mae_k": float(np.mean(a)),
        "p95_abs_k": float(np.percentile(a, 95)),
        "max_abs_k": float(np.max(a)),
    }


def run_one(spec: RunSpec) -> dict[str, Any]:
    """Run one spec and reduce it to a JSON-able result (see module doc)."""

    base = get_scenario(spec.scenario_id)
    item = scenario_with_seed(base, spec.seed)
    cfg = spec.config()
    obs = _Observer()
    started = time.perf_counter()
    session, sup, rec = run_supervised(
        item,
        spec.mode,
        config=cfg,
        operator=OperatorModel(delay_s=spec.operator_delay_s),
        until_s=spec.until_s,
        observer=obs,
    )
    wall = time.perf_counter() - started
    onset = _fault_onset(base)
    tc_onset = _exhaust_onset(base)
    scores = score(rec, cfg.demand_band_mw, from_s=SCORE_FROM_S)
    eco = cfg.economics
    scores["fuel_cost_usd"] = scores["fuel_kg"] * rec.lhv_kj_kg / 1.0e6 * eco.fuel_price_usd_per_gj
    decisions = [_compact_decision(d) for d in sup.decisions]

    tc: dict[str, Any] = {"onset_s": tc_onset, "first_suspect_s": obs.first_suspect_s}
    fb = [d for d in decisions if d["problem"] == "exhaust_feedback"]
    if fb:
        tc["decision_t_s"] = fb[0]["t_s"]
        applied = [
            d
            for d in fb
            if d["status"] in ("applied", "accepted") and d["resolved_t_s"] is not None
        ]
        tc["applied_t_s"] = applied[0]["resolved_t_s"] if applied else None
    else:
        tc["decision_t_s"] = tc["applied_t_s"] = None
    ref = tc_onset
    for k, name in (
        ("first_suspect_s", "first_suspect"),
        ("decision_t_s", "decision"),
        ("applied_t_s", "applied"),
    ):
        v = tc[k]
        tc[f"{name}_after_onset_s"] = None if v is None or ref is None else v - ref

    mm = obs.mismatch
    trust = {
        "mismatch_samples": len(mm),
        "mismatch_median": statistics.median(mm) if mm else None,
        "mismatch_p95": float(np.percentile(mm, 95)) if mm else None,
        "mismatch_max": max(mm) if mm else None,
        "mismatch_share_over_limit": (
            sum(1 for x in mm if x > cfg.limits.max_mismatch_index) / len(mm) if mm else None
        ),
    }
    after_onset = None
    if onset is not None and onset > SCORE_FROM_S:
        after_onset = score(rec, cfg.demand_band_mw, from_s=onset)
    return {
        "format": RESULT_FORMAT,
        "spec": spec.to_dict(),
        "key": spec.key(),
        "category": base.category,
        "fault_onset_s": onset,
        "wall_s": wall,
        "score": scores,
        "score_after_onset": after_onset,
        "decisions": decisions,
        "counters": dict(sup.counters),
        "skipped": rec.skipped,
        "thermocouple": {
            **tc,
            "max_abs_exhaust_residual_k": obs.max_abs_exhaust_residual_k,
            "max_exhaust_scatter_k": obs.max_exhaust_scatter_k,
            "substitute_s": obs.substitute_s,
            "soft_sensor_error": _soft_sensor_error(rec, obs),
        },
        "trust": trust,
        "wash": {
            "washes": obs.washes,
            "max_fouling_pct": max(obs.fouling_pct) if obs.fouling_pct else 0.0,
            "mean_fouling_pct": statistics.fmean(obs.fouling_pct) if obs.fouling_pct else 0.0,
            "last_evaluation": sup.last_wash_evaluation,
        },
        "final_state": rec.state[-1] if rec.state else None,
    }


# ----------------------------------------------------------------------------- cache


def cache_path(cache_dir: Path | str, spec: RunSpec) -> Path:
    return Path(cache_dir) / f"{spec.key()}.json"


def _job(args: tuple[RunSpec, str]) -> tuple[str, float]:
    spec, cache_dir = args
    result = run_one(spec)
    path = cache_path(cache_dir, spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, default=_json_default))
    tmp.replace(path)
    return str(path), result["wall_s"]


def _json_default(o: Any) -> Any:
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


def ensure_results(
    specs: Sequence[RunSpec],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    workers: int = 4,
    progress: bool = True,
) -> dict[str, Any]:
    """Run every spec that is not cached yet, ``workers`` processes at a time."""

    unique = list(dict.fromkeys(specs))
    missing = [s for s in unique if not cache_path(cache_dir, s).exists()]
    stats = {"runs": len(unique), "cached": len(unique) - len(missing), "computed": 0}
    started = time.perf_counter()
    jobs = [(s, str(cache_dir)) for s in missing]
    if jobs:
        if workers <= 1:
            for job in jobs:
                _job(job)
                stats["computed"] += 1
        else:
            with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
                futures = [pool.submit(_job, job) for job in jobs]
                for fut in as_completed(futures):
                    path, wall = fut.result()
                    stats["computed"] += 1
                    if progress:
                        print(
                            f"[{stats['computed']}/{len(jobs)}] {Path(path).name} {wall:.0f} s",
                            flush=True,
                        )
    stats["wall_s"] = time.perf_counter() - started
    return stats


def load_results(specs: Iterable[RunSpec], cache_dir: Path | str = DEFAULT_CACHE_DIR) -> list:
    out = []
    for spec in dict.fromkeys(specs):
        path = cache_path(cache_dir, spec)
        if path.exists():
            out.append(json.loads(path.read_text()))
    return out


# ----------------------------------------------------------------------------- experiments


def main_specs(seeds: Sequence[int] = TEST_SEEDS) -> list[RunSpec]:
    return [RunSpec(s.id, m, seed) for s in SCENARIOS for m in MODES for seed in seeds]


def tuning_specs() -> list[RunSpec]:
    specs = [RunSpec(s.id, "manual", seed) for s in SCENARIOS for seed in TUNING_SEEDS]
    specs += [RunSpec(s.id, "autonomous", seed) for s in SCENARIOS for seed in TUNING_SEEDS[:3]]
    return specs


SECONDARY_SEEDS: tuple[int, ...] = TEST_SEEDS[:3]
DELAY_SCENARIOS = (
    "clean_part_load",
    "clean_load_cycling",
    "clean_ambient_swing",
    "fouling_progressive_base_load",
    "fouled_unit_offline_wash",
    "exhaust_tc_drift_base_load",
    "exhaust_tc_stuck_load_increase",
)
DELAYS_S = (60.0, 300.0, 900.0)
MISMATCH_SCENARIOS = (
    "clean_part_load",
    "clean_load_cycling",
    "clean_ambient_swing",
    "fouling_progressive_ambient_swing",
    "erosion_step_part_load",
    "exhaust_tc_drift_base_load",
    "exhaust_tc_stuck_load_increase",
)
TWIN_ENGINES: tuple[str | None, ...] = (None, DEFAULT_TWIN_ENGINE, LARGE_MISMATCH)
OBJECTIVE_SCENARIOS = (
    "clean_part_load",
    "clean_base_load",
    "clean_load_cycling",
    "clean_ambient_swing",
    "fouling_step_part_load",
    "exhaust_tc_stuck_load_increase",
)


def delay_specs() -> list[RunSpec]:
    return [
        RunSpec(sid, "advisory", seed, operator_delay_s=d)
        for sid in DELAY_SCENARIOS
        for d in DELAYS_S
        for seed in SECONDARY_SEEDS
    ]


def mismatch_specs() -> list[RunSpec]:
    return [
        RunSpec(sid, mode, seed, twin_engine=e)
        for sid in MISMATCH_SCENARIOS
        for e in TWIN_ENGINES
        for mode in ("advisory", "autonomous")
        for seed in SECONDARY_SEEDS
    ]


def objective_specs() -> list[RunSpec]:
    return [
        RunSpec(sid, "autonomous", seed, load_objective=obj)
        for sid in OBJECTIVE_SCENARIOS
        for obj in ("track_demand", "heat_rate")
        for seed in SECONDARY_SEEDS
    ]


WASH_LAYER_IGV = ("auto",)  # the layer may not touch the IGV here, so only the wash differs


def wash_specs() -> list[RunSpec]:
    specs = []
    for seed in SECONDARY_SEEDS:
        specs.append(RunSpec("wash_study_never", "manual", seed))
        for h in WASH_INTERVALS_H:
            specs.append(RunSpec(f"wash_study_every_{h:g}h", "manual", seed))
        specs.append(
            RunSpec(
                "wash_study_never",
                "autonomous",
                seed,
                autonomous_wash=True,
                igv_options=WASH_LAYER_IGV,
            )
        )
        specs.append(RunSpec("wash_study_never", "advisory", seed, igv_options=WASH_LAYER_IGV))
    return specs


def manual_baselines(specs: Iterable[RunSpec]) -> list[RunSpec]:
    """The manual runs the specs are compared with (manual ignores the layer's settings)."""

    return [RunSpec(s.scenario_id, "manual", s.seed) for s in specs]


EXPERIMENTS = {
    "tuning": tuning_specs,
    "main": main_specs,
    "delay": lambda: delay_specs() + manual_baselines(delay_specs()),
    "mismatch": lambda: mismatch_specs() + manual_baselines(mismatch_specs()),
    "objective": lambda: objective_specs() + manual_baselines(objective_specs()),
    "wash": wash_specs,
}

# ----------------------------------------------------------------------------- statistics


def bootstrap_ci(
    values: Sequence[float],
    groups: Sequence[Any] | None = None,
    *,
    n_boot: int = 10_000,
    level: float = 0.95,
    seed: int = 0,
) -> dict[str, float | int | None]:
    """Mean and percentile-bootstrap interval; with ``groups``, resampling is within groups
    (stratified), so every resample keeps the same number of values per group."""

    x = np.asarray([v for v in values], dtype=float)
    if x.size == 0:
        return {"n": 0, "mean": None, "lo": None, "hi": None}
    rng = np.random.default_rng(seed)
    if groups is None:
        idx = rng.integers(0, x.size, size=(n_boot, x.size))
        means = x[idx].mean(axis=1)
    else:
        by: dict[Any, list[int]] = defaultdict(list)
        for i, g in enumerate(groups):
            by[g].append(i)
        total = np.zeros(n_boot)
        for members in by.values():
            m = np.asarray(members)
            pick = rng.integers(0, m.size, size=(n_boot, m.size))
            total += x[m[pick]].sum(axis=1)
        means = total / x.size
    a = (1.0 - level) / 2.0
    return {
        "n": int(x.size),
        "mean": float(x.mean()),
        "lo": float(np.quantile(means, a)),
        "hi": float(np.quantile(means, 1.0 - a)),
    }


def _pct(new: float | None, ref: float | None) -> float | None:
    if new is None or ref is None or ref == 0:
        return None
    return 100.0 * (new - ref) / ref


def paired_differences(
    results: Sequence[dict[str, Any]],
    baselines: Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Each non-manual result against the manual run of the same scenario and seed."""

    base = {
        (r["spec"]["scenario_id"], r["spec"]["seed"]): r
        for r in (baselines if baselines is not None else results)
        if r["spec"]["mode"] == "manual"
    }
    out = []
    for r in results:
        sp = r["spec"]
        if sp["mode"] == "manual":
            continue
        b = base.get((sp["scenario_id"], sp["seed"]))
        if b is None:
            continue
        s, m = r["score"], b["score"]
        fpm = s["fuel_kg"] / s["energy_mwh"] if s["energy_mwh"] else None
        fpm_b = m["fuel_kg"] / m["energy_mwh"] if m["energy_mwh"] else None
        band = (
            None
            if s["band_compliance"] is None or m["band_compliance"] is None
            else 100.0 * (s["band_compliance"] - m["band_compliance"])
        )
        out.append(
            {
                "scenario_id": sp["scenario_id"],
                "category": r["category"],
                "seed": sp["seed"],
                "mode": sp["mode"],
                "spec": sp,
                "heat_rate_pct": _pct(s["heat_rate_kj_per_kwh"], m["heat_rate_kj_per_kwh"]),
                "fuel_per_mwh_pct": _pct(fpm, fpm_b),
                "fuel_kg": s["fuel_kg"] - m["fuel_kg"],
                "energy_mwh": s["energy_mwh"] - m["energy_mwh"],
                "band_pp": band,
                "violation_s": s["violation_s"] - m["violation_s"],
                "over_limit_k_s": s["over_limit_k_s"] - m["over_limit_k_s"],
            }
        )
    return out


def _ci_of(rows: Sequence[dict[str, Any]], field: str, seed: int = 0) -> dict[str, Any]:
    pairs = [(r[field], r["scenario_id"]) for r in rows if r[field] is not None]
    return bootstrap_ci([p[0] for p in pairs], [p[1] for p in pairs], seed=seed)


def _initial_counts(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_problem: dict[str, Counter] = defaultdict(Counter)
    final: dict[str, Counter] = defaultdict(Counter)
    reasons: Counter = Counter()
    for r in results:
        for d in r["decisions"]:
            by_problem[d["problem"]][d["initial_status"]] += 1
            final[d["problem"]][d["status"]] += 1
            if not d["approved"]:
                reasons.update(d["failed_checks"])
    total = Counter()
    for c in by_problem.values():
        total.update(c)
    n = sum(total.values())
    applied = total.get("applied", 0) + total.get("pending", 0)
    return {
        "decisions": n,
        "by_problem_initial": {k: dict(v) for k, v in by_problem.items()},
        "by_problem_final": {k: dict(v) for k, v in final.items()},
        "approved_share": applied / n if n else None,
        "escalated": total.get("escalated", 0),
        "escalation_reasons": dict(reasons.most_common()),
    }


def violation_summary(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    s = [r["score"] for r in results]
    return {
        "runs": len(s),
        "runs_with_violation": sum(1 for x in s if x["violation_s"] > 0),
        "violation_s": sum(x["violation_s"] for x in s),
        "runs_over_limit": sum(1 for x in s if x["over_limit_s"] > 0),
        "over_limit_k_s": sum(x["over_limit_k_s"] for x in s),
        "max_over_limit_k": max((x["max_over_limit_k"] for x in s), default=0.0),
        "trips": sum(x["trips"] for x in s),
    }


def _by(results: Iterable[dict[str, Any]], *fields: str) -> dict[tuple, list]:
    out: dict[tuple, list] = defaultdict(list)
    for r in results:
        out[tuple(r["spec"][f] for f in fields)].append(r)
    return out


def _mean(xs: Iterable[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return statistics.fmean(v) if v else None


def tc_summary(results: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for (sid, mode), group in sorted(_by(results, "scenario_id", "mode").items()):
        if sid not in EXHAUST_SCENARIOS:
            continue
        tcs = [r["thermocouple"] for r in group]
        rows.append(
            {
                "scenario_id": sid,
                "mode": mode,
                "runs": len(group),
                "suspect_after_onset_s": [t["first_suspect_after_onset_s"] for t in tcs],
                "decision_after_onset_s": [t["decision_after_onset_s"] for t in tcs],
                "applied_after_onset_s": [t["applied_after_onset_s"] for t in tcs],
                "violation_s": [r["score"]["violation_s"] for r in group],
                "max_over_limit_k": [r["score"]["max_over_limit_k"] for r in group],
                "over_limit_k_s": [r["score"]["over_limit_k_s"] for r in group],
                "soft_sensor_mae_k": _mean(t["soft_sensor_error"].get("mae_k") for t in tcs),
            }
        )
    return rows


def false_positive_summary(results: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for (sid, mode), group in sorted(_by(results, "scenario_id", "mode").items()):
        tcs = [r["thermocouple"] for r in group]
        rows.append(
            {
                "scenario_id": sid,
                "mode": mode,
                "runs": len(group),
                "exhaust_fault": sid in EXHAUST_SCENARIOS,
                "suspect_runs": sum(1 for t in tcs if t["first_suspect_s"] is not None),
                "suspect_after_onset_s": [t["first_suspect_after_onset_s"] for t in tcs],
                "max_abs_exhaust_residual_k": max(t["max_abs_exhaust_residual_k"] for t in tcs),
                "max_exhaust_scatter_k": max(t["max_exhaust_scatter_k"] for t in tcs),
                "mismatch_p95": max((r["trust"]["mismatch_p95"] or 0.0) for r in group),
            }
        )
    return rows


def summarise_main(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    diffs = paired_differences(results)
    by_mode = defaultdict(list)
    for d in diffs:
        by_mode[d["mode"]].append(d)
    out: dict[str, Any] = {"modes": {}, "per_scenario": [], "per_category": []}
    res_by_mode = defaultdict(list)
    for r in results:
        res_by_mode[r["spec"]["mode"]].append(r)
    for mode in MODES:
        rows = by_mode.get(mode, [])
        entry: dict[str, Any] = {
            "violations": violation_summary(res_by_mode.get(mode, [])),
            "decisions": _initial_counts(res_by_mode.get(mode, [])),
            "runs": len(res_by_mode.get(mode, [])),
        }
        if rows:
            for f in ("heat_rate_pct", "fuel_per_mwh_pct", "energy_mwh", "fuel_kg", "band_pp"):
                entry[f] = _ci_of(rows, f)
            worse = [r for r in rows if r["violation_s"] > 0]
            entry["violation_vs_manual"] = {
                "pairs": len(rows),
                "pairs_more_violation": len(worse),
                "extra_violation_s": sum(r["violation_s"] for r in worse),
                "scenarios_more_violation": sorted({r["scenario_id"] for r in worse}),
                "pairs_less_violation": sum(1 for r in rows if r["violation_s"] < 0),
                "violation_s_saved": -sum(r["violation_s"] for r in rows if r["violation_s"] < 0),
            }
        out["modes"][mode] = entry
    for (sid, mode), rows in sorted(
        _by_rows(diffs, "scenario_id", "mode").items(), key=lambda kv: kv[0]
    ):
        hr = [r["heat_rate_pct"] for r in rows if r["heat_rate_pct"] is not None]
        out["per_scenario"].append(
            {
                "scenario_id": sid,
                "category": rows[0]["category"],
                "mode": mode,
                "n": len(rows),
                "heat_rate_pct_mean": _mean(hr),
                "heat_rate_pct_min": min(hr) if hr else None,
                "heat_rate_pct_max": max(hr) if hr else None,
                "energy_mwh_mean": _mean(r["energy_mwh"] for r in rows),
                "band_pp_mean": _mean(r["band_pp"] for r in rows),
                "violation_s_diff_mean": _mean(r["violation_s"] for r in rows),
            }
        )
    for (cat, mode), rows in sorted(_by_rows(diffs, "category", "mode").items()):
        out["per_category"].append(
            {"category": cat, "mode": mode, "heat_rate_pct": _ci_of(rows, "heat_rate_pct")}
        )
    out["tc"] = tc_summary(results)
    return out


def _by_rows(rows: Iterable[dict[str, Any]], *fields: str) -> dict[tuple, list]:
    out: dict[tuple, list] = defaultdict(list)
    for r in rows:
        out[tuple(r[f] for f in fields)].append(r)
    return out


def scenario_mode_table(results: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per scenario and mode: mean heat rate, energy, band, violations, decisions."""

    rows = []
    for (sid, mode), group in sorted(_by(results, "scenario_id", "mode").items()):
        sc = [r["score"] for r in group]
        dec = _initial_counts(group)
        rows.append(
            {
                "scenario_id": sid,
                "mode": mode,
                "runs": len(group),
                "heat_rate": _mean(x["heat_rate_kj_per_kwh"] for x in sc),
                "energy_mwh": _mean(x["energy_mwh"] for x in sc),
                "band": _mean(x["band_compliance"] for x in sc),
                "violation_s": sum(x["violation_s"] for x in sc),
                "max_over_limit_k": max(x["max_over_limit_k"] for x in sc),
                "trips": sum(x["trips"] for x in sc),
                "decisions": dec["decisions"],
                "escalated": dec["escalated"],
                "skipped_steps": sum(len(r["skipped"]) for r in group),
            }
        )
    return rows


def summarise_secondary(
    name: str, results: Sequence[dict[str, Any]], baselines: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Grouped by the varied setting: heat-rate change vs manual, violations, decisions."""

    field = {
        "delay": "operator_delay_s",
        "mismatch": "twin_engine",
        "objective": "load_objective",
    }[name]
    diffs = paired_differences(results, baselines)
    rows = []
    groups = _by(results, "mode", field)
    for (mode, value), group in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        drows = [d for d in diffs if d["mode"] == mode and d["spec"][field] == value]
        dec = _initial_counts(group)
        mm = [r["trust"]["mismatch_median"] for r in group if r["trust"]["mismatch_median"]]
        share = [
            r["trust"]["mismatch_share_over_limit"]
            for r in group
            if r["trust"]["mismatch_share_over_limit"] is not None
        ]
        rows.append(
            {
                "mode": mode,
                field: value,
                "runs": len(group),
                "heat_rate_pct": _ci_of(drows, "heat_rate_pct"),
                "energy_mwh": _ci_of(drows, "energy_mwh"),
                "band_pp": _ci_of(drows, "band_pp"),
                "violations": violation_summary(group),
                "decisions": dec,
                "mismatch_median": _mean(mm),
                "mismatch_share_over_limit": _mean(share),
                "tc": [
                    {
                        "scenario_id": r["spec"]["scenario_id"],
                        "seed": r["spec"]["seed"],
                        **{
                            k: r["thermocouple"][k]
                            for k in (
                                "first_suspect_after_onset_s",
                                "decision_after_onset_s",
                                "applied_after_onset_s",
                            )
                        },
                        "violation_s": r["score"]["violation_s"],
                        "max_over_limit_k": r["score"]["max_over_limit_k"],
                    }
                    for r in group
                    if r["spec"]["scenario_id"] in EXHAUST_SCENARIOS
                ],
            }
        )
    return rows


def wash_policy(spec: dict[str, Any]) -> str:
    sid = spec["scenario_id"]
    if spec["mode"] == "manual":
        return "never" if sid == "wash_study_never" else sid.replace("wash_study_", "")
    return f"layer ({spec['mode']})"


def summarise_wash(results: Sequence[dict[str, Any]], eco: Economics | None = None) -> dict:
    """Total cost per policy: fuel cost scaled to a common energy plus washes x effective cost.

    Washing stops the unit, so policies deliver different energy. The fuel cost is therefore
    taken per MWh and multiplied by the energy of the no-wash run of the same seed; the lost
    production and outage are what the (time-compressed) wash cost stands for.
    """

    eco = eco or Economics()
    w = eco.effective_wash_cost_usd
    never = {
        r["spec"]["seed"]: r
        for r in results
        if r["spec"]["scenario_id"] == "wash_study_never" and r["spec"]["mode"] == "manual"
    }
    per_run = []
    for r in results:
        sp = r["spec"]
        ref = never.get(sp["seed"])
        s = r["score"]
        if ref is None or not s["energy_mwh"]:
            continue
        e_ref = ref["score"]["energy_mwh"]
        fuel_cost_eq = s["fuel_cost_usd"] / s["energy_mwh"] * e_ref
        washes = r["wash"]["washes"]
        wash_dec = [d for d in r["decisions"] if d["problem"] == "compressor_wash"]
        per_run.append(
            {
                "policy": wash_policy(sp),
                "seed": sp["seed"],
                "washes": washes,
                "energy_mwh": s["energy_mwh"],
                "fuel_cost_usd": s["fuel_cost_usd"],
                "fuel_cost_eq_usd": fuel_cost_eq,
                "wash_cost_usd": washes * w,
                "total_cost_usd": fuel_cost_eq + washes * w,
                "heat_rate": s["heat_rate_kj_per_kwh"],
                "mean_fouling_pct": r["wash"]["mean_fouling_pct"],
                "max_fouling_pct": r["wash"]["max_fouling_pct"],
                "wash_decision_times_s": [d["t_s"] for d in wash_dec],
                "optimal_interval_h_at_decision": [d.get("optimal_interval_h") for d in wash_dec],
                "loss_growth_usd_per_h2": [d.get("loss_growth_usd_per_h2") for d in wash_dec],
                "violation_s": s["violation_s"],
                "skipped": len(r["skipped"]),
            }
        )
    by_seed_never = {
        row["seed"]: row["total_cost_usd"] for row in per_run if row["policy"] == "never"
    }
    policies = []
    for pol, rows in _by_rows(per_run, "policy").items():
        pol = pol[0]
        saving = [by_seed_never[r["seed"]] - r["total_cost_usd"] for r in rows]
        policies.append(
            {
                "policy": pol,
                "runs": len(rows),
                "washes_mean": _mean(r["washes"] for r in rows),
                "energy_mwh_mean": _mean(r["energy_mwh"] for r in rows),
                "fuel_cost_eq_mean": _mean(r["fuel_cost_eq_usd"] for r in rows),
                "wash_cost_mean": _mean(r["wash_cost_usd"] for r in rows),
                "total_cost_mean": _mean(r["total_cost_usd"] for r in rows),
                "saving_vs_never": bootstrap_ci(saving),
                "mean_fouling_pct": _mean(r["mean_fouling_pct"] for r in rows),
                "heat_rate_mean": _mean(r["heat_rate"] for r in rows),
                "violation_s": sum(r["violation_s"] for r in rows),
                "first_wash_h_after_onset": _mean(
                    (r["wash_decision_times_s"][0] - ONSET_S) / 3600.0
                    for r in rows
                    if r["wash_decision_times_s"]
                ),
                "optimal_interval_h_at_decision": _mean(
                    x for r in rows for x in r["optimal_interval_h_at_decision"]
                ),
            }
        )
    order = {"never": 0}
    policies.sort(key=lambda p: (order.get(p["policy"], 1), p["policy"]))
    growth = [x for r in per_run for x in r["loss_growth_usd_per_h2"] if x]
    a = _mean(growth)
    formula = None
    if a:
        t_sim = math.sqrt(2.0 * w / a)
        formula = {
            "wash_cost_usd": eco.wash_cost_usd,
            "time_compression": eco.time_compression,
            "effective_wash_cost_usd": w,
            "loss_growth_usd_per_h2_sim": a,
            "optimal_interval_h_sim": t_sim,
            "optimal_interval_h_service": t_sim * eco.time_compression,
            "optimal_interval_days_service": t_sim * eco.time_compression / 24.0,
        }
    return {"per_run": per_run, "policies": policies, "formula": formula}


# ----------------------------------------------------------------------------- markdown


def _f(x: Any, nd: int = 2) -> str:
    if x is None:
        return "–"
    if isinstance(x, float):
        if math.isnan(x):
            return "–"
        return f"{x:.{nd}f}"
    return str(x)


def _ci(c: dict[str, Any] | None, nd: int = 2) -> str:
    if not c or c.get("mean") is None:
        return "–"
    return f"{c['mean']:+.{nd}f} [{c['lo']:+.{nd}f}, {c['hi']:+.{nd}f}]"


def _list(xs: Sequence[float | None], nd: int = 0) -> str:
    v = [x for x in xs if x is not None]
    if not v:
        return "none"
    if len(v) < len(xs):
        tail = f" ({len(xs) - len(v)} none)"
    else:
        tail = ""
    return f"{statistics.fmean(v):.{nd}f} ({min(v):.{nd}f}–{max(v):.{nd}f}){tail}"


def table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def markdown_main(summary: dict[str, Any], table_rows: list[dict[str, Any]]) -> str:
    parts = ["## Main experiment: modes against manual\n"]
    rows = []
    for mode, e in summary["modes"].items():
        v = e["violations"]
        d = e["decisions"]
        rows.append(
            [
                mode,
                e["runs"],
                _ci(e.get("heat_rate_pct"), 3),
                _ci(e.get("fuel_per_mwh_pct"), 3),
                _ci(e.get("energy_mwh"), 3),
                _ci(e.get("band_pp"), 2),
                f"{v['runs_with_violation']} / {_f(v['violation_s'], 0)} s",
                (
                    "–"
                    if "violation_vs_manual" not in e
                    else f"{e['violation_vs_manual']['pairs_more_violation']} "
                    f"(+{_f(e['violation_vs_manual']['extra_violation_s'], 0)} s) / "
                    f"{e['violation_vs_manual']['pairs_less_violation']} "
                    f"(-{_f(e['violation_vs_manual']['violation_s_saved'], 0)} s)"
                ),
                _f(v["max_over_limit_k"], 1),
                v["trips"],
                d["decisions"],
                _f(d["approved_share"], 3),
            ]
        )
    parts.append(
        table(
            [
                "Mode",
                "Runs",
                "Heat rate vs manual (%)",
                "Fuel/MWh vs manual (%)",
                "Energy vs manual (MWh)",
                "Band compliance vs manual (pp)",
                "Runs with violation / violation time",
                "Pairs with more / less violation than manual",
                "Max over limit (K)",
                "Trips",
                "Decisions",
                "Guard-approved share",
            ],
            rows,
        )
    )
    parts.append(
        "\nMean over scenario-seed pairs [95 % bootstrap interval, seeds resampled within "
        "scenario]. Negative heat rate is better.\n"
    )
    parts.append("\n### Decisions and escalation reasons\n")
    rows = []
    for mode, e in summary["modes"].items():
        d = e["decisions"]
        for prob, counts in sorted(d["by_problem_initial"].items()):
            fin = d["by_problem_final"].get(prob, {})
            rows.append(
                [
                    mode,
                    prob,
                    ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
                    ", ".join(f"{k} {v}" for k, v in sorted(fin.items())),
                ]
            )
    parts.append(table(["Mode", "Problem", "Raised as", "Final status"], rows))
    parts.append("\n")
    rows = [
        [mode, ", ".join(f"{k} {v}" for k, v in e["decisions"]["escalation_reasons"].items())]
        for mode, e in summary["modes"].items()
    ]
    parts.append(table(["Mode", "Failed guard checks (count over decisions)"], rows))
    parts.append("\n\n### Per category, heat rate vs manual (%)\n")
    parts.append(
        table(
            ["Category", "Mode", "Heat rate vs manual (%)"],
            [
                [r["category"], r["mode"], _ci(r["heat_rate_pct"], 3)]
                for r in summary["per_category"]
            ],
        )
    )
    parts.append("\n\n### Per scenario and mode (means over seeds)\n")
    rows = []
    hr_by = {(r["scenario_id"], r["mode"]): r for r in summary["per_scenario"]}
    for r in table_rows:
        p = hr_by.get((r["scenario_id"], r["mode"]))
        hr = (
            "–"
            if p is None or p["heat_rate_pct_mean"] is None
            else f"{p['heat_rate_pct_mean']:+.2f} ({p['heat_rate_pct_min']:+.2f}…"
            f"{p['heat_rate_pct_max']:+.2f})"
        )
        rows.append(
            [
                r["scenario_id"],
                r["mode"],
                _f(r["heat_rate"], 0),
                hr,
                _f(r["energy_mwh"], 2),
                _f(r["band"], 3),
                _f(r["violation_s"], 0),
                _f(r["max_over_limit_k"], 1),
                r["trips"],
                r["decisions"],
                r["escalated"],
                r["skipped_steps"],
            ]
        )
    parts.append(
        table(
            [
                "Scenario",
                "Mode",
                "Heat rate (kJ/kWh)",
                "vs manual % (min…max)",
                "Energy (MWh)",
                "Band",
                "Violation s (sum)",
                "Max over limit K",
                "Trips",
                "Decisions",
                "Escalated",
                "Skipped steps",
            ],
            rows,
        )
    )
    parts.append("\n\n### Exhaust thermocouple scenarios\n")
    parts.append(markdown_tc(summary["tc"]))
    return "\n".join(parts) + "\n"


def markdown_tc(rows: list[dict[str, Any]]) -> str:
    return (
        table(
            [
                "Scenario",
                "Mode",
                "Suspect after onset (s)",
                "Decision after onset (s)",
                "Applied after onset (s)",
                "Violation s",
                "Max over limit (K)",
                "Over limit (K·s)",
                "Soft-sensor MAE (K)",
            ],
            [
                [
                    r["scenario_id"],
                    r["mode"],
                    _list(r["suspect_after_onset_s"]),
                    _list(r["decision_after_onset_s"]),
                    _list(r["applied_after_onset_s"]),
                    _list(r["violation_s"]),
                    _list(r["max_over_limit_k"], 1),
                    _list(r["over_limit_k_s"]),
                    _f(r["soft_sensor_mae_k"], 1),
                ]
                for r in rows
            ],
        )
        + "\n\nMean (min–max) over seeds; `none` = never happened.\n"
    )


def markdown_false_positives(rows: list[dict[str, Any]]) -> str:
    return (
        table(
            [
                "Scenario",
                "Mode",
                "Runs",
                "Runs with TC suspected",
                "Suspect after onset (s)",
                "Max abs exhaust residual (K, before suspicion)",
                "Max exhaust scatter (K)",
                "Mismatch index p95 (max over runs)",
            ],
            [
                [
                    r["scenario_id"],
                    r["mode"],
                    r["runs"],
                    r["suspect_runs"],
                    _list(r["suspect_after_onset_s"]) if r["exhaust_fault"] else "–",
                    _f(r["max_abs_exhaust_residual_k"], 1),
                    _f(r["max_exhaust_scatter_k"], 2),
                    _f(r["mismatch_p95"], 2),
                ]
                for r in rows
            ],
        )
        + "\n"
    )


def markdown_secondary(name: str, rows: list[dict[str, Any]]) -> str:
    field = {"delay": "operator_delay_s", "mismatch": "twin_engine", "objective": "load_objective"}[
        name
    ]
    out = table(
        [
            "Mode",
            field,
            "Runs",
            "Heat rate vs manual (%)",
            "Energy vs manual (MWh)",
            "Band vs manual (pp)",
            "Violation runs / s",
            "Max over limit (K)",
            "Decisions",
            "Approved share",
            "Mismatch index (median)",
            "Share of time mismatch > 3",
        ],
        [
            [
                r["mode"],
                "exact (None)" if r[field] is None else r[field],
                r["runs"],
                _ci(r["heat_rate_pct"], 3),
                _ci(r["energy_mwh"], 3),
                _ci(r["band_pp"], 2),
                f"{r['violations']['runs_with_violation']} / "
                f"{_f(r['violations']['violation_s'], 0)}",
                _f(r["violations"]["max_over_limit_k"], 1),
                r["decisions"]["decisions"],
                _f(r["decisions"]["approved_share"], 3),
                _f(r["mismatch_median"], 2),
                _f(r["mismatch_share_over_limit"], 3),
            ]
            for r in rows
        ],
    )
    out += "\n\nEscalation reasons:\n\n"
    out += table(
        ["Mode", field, "Failed checks"],
        [
            [
                r["mode"],
                "exact (None)" if r[field] is None else r[field],
                ", ".join(f"{k} {v}" for k, v in r["decisions"]["escalation_reasons"].items())
                or "none",
            ]
            for r in rows
        ],
    )
    tc_rows = [(r, t) for r in rows for t in r["tc"]]
    if tc_rows:
        out += "\n\nExhaust scenarios:\n\n"
        out += table(
            [
                "Mode",
                field,
                "Scenario",
                "Seed",
                "Suspect after onset (s)",
                "Decision (s)",
                "Applied (s)",
                "Violation s",
                "Max over limit K",
            ],
            [
                [
                    r["mode"],
                    "exact (None)" if r[field] is None else r[field],
                    t["scenario_id"],
                    t["seed"],
                    _f(t["first_suspect_after_onset_s"], 0),
                    _f(t["decision_after_onset_s"], 0),
                    _f(t["applied_after_onset_s"], 0),
                    _f(t["violation_s"], 0),
                    _f(t["max_over_limit_k"], 1),
                ]
                for r, t in sorted(
                    tc_rows, key=lambda x: (x[0]["mode"], str(x[0][field]), x[1]["scenario_id"])
                )
            ],
        )
    return out + "\n"


def markdown_wash(summary: dict[str, Any]) -> str:
    out = table(
        [
            "Policy",
            "Runs",
            "Washes",
            "Energy (MWh)",
            "Fuel cost at common energy ($)",
            "Wash cost ($)",
            "Total ($)",
            "Saving vs never ($) [95 % CI]",
            "Mean fouling (%)",
            "First layer wash (h after onset)",
        ],
        [
            [
                p["policy"],
                p["runs"],
                _f(p["washes_mean"], 1),
                _f(p["energy_mwh_mean"], 1),
                _f(p["fuel_cost_eq_mean"], 0),
                _f(p["wash_cost_mean"], 0),
                _f(p["total_cost_mean"], 0),
                _ci(p["saving_vs_never"], 0),
                _f(p["mean_fouling_pct"], 2),
                _f(p["first_wash_h_after_onset"], 2),
            ]
            for p in summary["policies"]
        ],
    )
    f = summary.get("formula")
    if f:
        out += (
            f"\n\nOptimal interval T* = sqrt(2 W / a): with the effective wash cost "
            f"W = {f['wash_cost_usd']:.0f} / {f['time_compression']:.0f} = "
            f"{f['effective_wash_cost_usd']:.1f} $ and the loss growth the layer estimated, "
            f"a = {f['loss_growth_usd_per_h2_sim']:.2f} $/h² (simulated time), "
            f"T* = {f['optimal_interval_h_sim']:.2f} h simulated, i.e. "
            f"{f['optimal_interval_h_service']:.0f} h ≈ {f['optimal_interval_days_service']:.0f}"
            " days of service.\n"
        )
    return out + "\n"


__all__ = [
    "DEFAULT_CACHE_DIR",
    "EXPERIMENTS",
    "LARGE_MISMATCH",
    "MODES",
    "RunSpec",
    "TEST_SEEDS",
    "TUNING_SEEDS",
    "bootstrap_ci",
    "ensure_results",
    "get_scenario",
    "load_results",
    "paired_differences",
    "run_one",
    "summarise_main",
    "summarise_wash",
    "wash_study_scenario",
]
