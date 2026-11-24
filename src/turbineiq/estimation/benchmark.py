"""A common benchmark for health estimators and fault detectors on the scenario bank (WP4).

Every estimator and detector is scored the same way: on the same observation streams, with
the same seeds and with the metric functions below. The module has four parts.

* **Seeds** (:func:`seeds_for`). Tuning uses seeds 1000-1999 only. Evaluation uses, for
  each bank scenario, its bank seed and ``seed + 10000 * k`` for ``k = 1..4`` (five trials).
* **Streams and cache** (:func:`ensure_streams`, :func:`load_streams`). A stream is one run
  of a scenario with one seed, stored as a gzip CSV with the columns of
  :func:`~turbineiq.simulation.scenarios.trace_rows`. The file name holds the scenario id,
  the seed and a hash of the scenario definition and of the simulation code (comments and
  docstrings excluded), so changing a script or the plant model invalidates the cache.
* **Runs** (:func:`run_estimator`, :func:`run_detector`). Objects under test see only
  :class:`~turbineiq.estimation.data.Observation` values, one at a time and in order. What
  one returns stays in force (zero-order hold) until it returns something else.
* **Metrics** (:func:`score_estimates`, :func:`score_detections`, :func:`summarize`), with
  numpy only. The exact definitions are in each docstring and in
  ``docs/ESTIMATION_BENCHMARK.md``.

The reference entries (:class:`OracleEstimator`, :class:`CleanEstimator`,
:class:`NeverDetector`) exist to test the harness. The oracle reads ground truth and is not
an estimator.
"""

from __future__ import annotations

import ast
import csv
import fnmatch
import gzip
import hashlib
import importlib
import io
import json
import math
import os
import platform
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from turbineiq.simulation.maps import Health
from turbineiq.simulation.scenarios import SCENARIOS, Scenario, run_scenario, trace_rows

from .data import Observation, Truth, scenario_with_seed, split_rows
from .steady import SteadyStateGate

# ----------------------------------------------------------------------------------- seeds

TUNING_SEEDS = range(1000, 2000)
EVALUATION_STRIDE = 10_000
EVALUATION_TRIALS = 5


def evaluation_seeds(item: Scenario, trials: int = EVALUATION_TRIALS) -> list[int]:
    """The evaluation seeds of a bank scenario: its bank seed, then ``+ 10000 * k``."""

    if not 1 <= trials <= EVALUATION_TRIALS:
        raise ValueError(f"evaluation trials must be 1..{EVALUATION_TRIALS}")
    return [item.seed + EVALUATION_STRIDE * k for k in range(trials)]


def is_evaluation_seed(seed: int, scenarios: Iterable[Scenario] = SCENARIOS) -> bool:
    return any(seed in evaluation_seeds(item) for item in scenarios)


def seeds_for(item: Scenario, policy: str) -> list[int]:
    """Seeds for one scenario under a seed policy.

    ``eval`` (all five evaluation trials), ``eval:N`` (the first N), ``bank`` (the bank seed
    only, same as ``eval:1``), ``tune:N`` (tuning seeds 1000 .. 1000+N-1) or an explicit
    comma-separated list, which must lie in the tuning range or be evaluation seeds of this
    scenario.
    """

    policy = policy.strip()
    if policy == "eval":
        return evaluation_seeds(item)
    if policy == "bank":
        return evaluation_seeds(item, 1)
    if policy.startswith("eval:"):
        return evaluation_seeds(item, int(policy[5:]))
    if policy.startswith("tune:"):
        n = int(policy[5:])
        if not 1 <= n <= len(TUNING_SEEDS):
            raise ValueError(f"tune:N needs 1 <= N <= {len(TUNING_SEEDS)}")
        return list(TUNING_SEEDS[:n])
    seeds = [int(part) for part in policy.split(",") if part.strip()]
    allowed = set(evaluation_seeds(item))
    bad = [s for s in seeds if s not in TUNING_SEEDS and s not in allowed]
    if not seeds or bad:
        raise ValueError(
            f"seed policy {policy!r}: seeds must be tuning seeds (1000-1999) or evaluation "
            f"seeds of {item.id} {sorted(allowed)}"
        )
    return seeds


# ------------------------------------------------------------------------- stream cache

CACHE_FORMAT = 1
DEFAULT_CACHE_DIR = Path("data/estimation/cache")
#: Code whose behaviour determines a stream; its fingerprint is part of every cache key.
MODEL_PACKAGES = ("turbineiq.simulation", "turbineiq.engineering")


def scenario_definition(item: Scenario) -> dict[str, Any]:
    """The parts of a scenario that determine its streams (apart from the seed).

    The id, category and description are labels and are left out; the seed is keyed
    separately because one definition is run with many seeds.
    """

    return {
        "duration_s": item.duration_s,
        "ambient_temperature_c": item.ambient_temperature_c,
        "record_interval_s": item.record_interval_s,
        "script": [step.to_dict() for step in item.script],
    }


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return tree


def source_fingerprint(source: str) -> str:
    """Hash of Python source ignoring comments, docstrings, layout and line numbers."""

    dump = ast.dump(_strip_docstrings(ast.parse(source)), include_attributes=False)
    return hashlib.sha256(dump.encode()).hexdigest()


_MODEL_FINGERPRINT: str | None = None


def model_fingerprint() -> str:
    """Fingerprint of the simulation code and its data files (cached per process)."""

    global _MODEL_FINGERPRINT
    if _MODEL_FINGERPRINT is None:
        digest = hashlib.sha256()
        for package in MODEL_PACKAGES:
            root = Path(importlib.import_module(package).__file__).parent
            for path in sorted(root.rglob("*.py")):
                digest.update(f"{package}/{path.relative_to(root).as_posix()}\0".encode())
                digest.update(source_fingerprint(path.read_text()).encode())
            for path in sorted(root.rglob("*.json")):
                digest.update(f"{package}/{path.relative_to(root).as_posix()}\0".encode())
                digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode())
        _MODEL_FINGERPRINT = digest.hexdigest()
    return _MODEL_FINGERPRINT


def _base_id(item: Scenario) -> str:
    return item.id.split("@", 1)[0]


def _normal_until(item: Scenario, until_s: float | None) -> float | None:
    if until_s is None or until_s >= item.duration_s:
        return None
    if until_s <= 0.0:
        raise ValueError("until_s must be positive")
    return float(until_s)


def cache_key(
    item: Scenario, seed: int, until_s: float | None = None, fingerprint: str | None = None
) -> str:
    """File stem of a cached stream: ``<id>__seed<seed>[__until<s>]__<hash>``.

    The hash covers the cache format, :func:`scenario_definition` and
    :func:`model_fingerprint` (or ``fingerprint`` if given).
    """

    payload = {
        "format": CACHE_FORMAT,
        "scenario": scenario_definition(item),
        "model": model_fingerprint() if fingerprint is None else fingerprint,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    stem = f"{_base_id(item)}__seed{int(seed)}"
    until = _normal_until(item, until_s)
    if until is not None:
        stem += f"__until{until:g}"
    return f"{stem}__{digest}"


def cache_path(
    cache_dir: Path | str, item: Scenario, seed: int, until_s: float | None = None
) -> Path:
    return Path(cache_dir) / f"{cache_key(item, seed, until_s)}.csv.gz"


def _write_gzip_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as packed:
        packed.write(text.encode())
    os.replace(tmp, path)  # atomic, so a concurrent reader never sees half a file


def _rows_to_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def is_cached(
    cache_dir: Path | str, item: Scenario, seed: int, until_s: float | None = None
) -> bool:
    """True if the stream (or, for a truncated one, the full stream) is in the cache."""

    if cache_path(cache_dir, item, seed, until_s).exists():
        return True
    return _normal_until(item, until_s) is not None and cache_path(cache_dir, item, seed).exists()


def generate_stream(
    item: Scenario, seed: int, cache_dir: Path | str, until_s: float | None = None
) -> tuple[Path, float]:
    """Run one (scenario, seed) and write it to the cache. Returns the path and run time."""

    start = time.perf_counter()
    session = run_scenario(scenario_with_seed(item, seed), until_s=_normal_until(item, until_s))
    rows = list(trace_rows(session))
    path = cache_path(cache_dir, item, seed, until_s)
    _write_gzip_text(path, _rows_to_csv(rows))
    return path, time.perf_counter() - start


def _generate_job(args: tuple[Scenario, int, str, float | None]) -> tuple[str, int, str, float]:
    item, seed, cache_dir, until_s = args
    path, seconds = generate_stream(item, seed, cache_dir, until_s)
    return item.id, seed, str(path), seconds


def ensure_streams(
    pairs: Iterable[tuple[Scenario, int]],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    *,
    workers: int = 2,
    until_s: float | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Generate every (scenario, seed) stream that is not cached yet, ``workers`` at a time.

    Returns counts and the summed generation time (CPU seconds over the workers, not wall
    time).
    """

    pairs = list(pairs)
    missing = [
        (item, seed) for item, seed in pairs if not is_cached(cache_dir, item, seed, until_s)
    ]
    stats = {"streams": len(pairs), "cached": len(pairs) - len(missing), "generated": 0}
    jobs = [(item, seed, str(cache_dir), until_s) for item, seed in missing]
    start = time.perf_counter()
    run_seconds = 0.0
    if jobs:
        if workers > 1 and len(jobs) > 1:
            with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
                done = pool.map(_generate_job, jobs)
                for k, (sid, seed, _path, seconds) in enumerate(done, 1):
                    run_seconds += seconds
                    if progress:
                        progress(f"[{k}/{len(jobs)}] {sid} seed {seed}: {seconds:.1f} s")
        else:
            for k, job in enumerate(jobs, 1):
                sid, seed, _path, seconds = _generate_job(job)
                run_seconds += seconds
                if progress:
                    progress(f"[{k}/{len(jobs)}] {sid} seed {seed}: {seconds:.1f} s")
    stats["generated"] = len(jobs)
    stats["generation_cpu_s"] = round(run_seconds, 1)
    stats["wall_s"] = round(time.perf_counter() - start, 1)
    return stats


def _read_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as handle:
        return list(csv.DictReader(handle))


def load_streams(
    item: Scenario,
    seed: int,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    until_s: float | None = None,
    *,
    generate: bool = True,
) -> tuple[list[Observation], list[Truth]]:
    """Observation and truth streams of (scenario, seed), from the cache.

    A truncated stream (``until_s``) is cut from the full cached stream when that exists.
    A missing stream is generated in this process unless ``generate`` is false.
    """

    until = _normal_until(item, until_s)
    path = cache_path(cache_dir, item, seed, until)
    if not path.exists() and until is not None:
        full = cache_path(cache_dir, item, seed)
        if full.exists():
            rows = [row for row in _read_rows(full) if float(row["t_s"]) <= until + 1e-9]
            return split_rows(rows)
    if not path.exists():
        if not generate:
            raise FileNotFoundError(path)
        path, _ = generate_stream(item, seed, cache_dir, until)
    return split_rows(_read_rows(path))


def seed_cache_from_traces(
    trace_dir: Path | str,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    scenarios: Iterable[Scenario] = SCENARIOS,
    *,
    check_s: float = 600.0,
    progress: Callable[[str], None] | None = None,
) -> dict[str, list[str]]:
    """Put existing bank traces (``<trace_dir>/<id>.csv``, bank seed) into the cache.

    A trace is accepted only if its header and row count match the scenario and its first
    ``check_s`` seconds are identical, as text, to a fresh run of the current code; that
    catches a wrong seed, format or start-up model, not a change that acts only after the
    check window (pass ``check_s`` = the duration for a full check).
    """

    report: dict[str, list[str]] = {"seeded": [], "present": [], "rejected": [], "absent": []}
    for item in scenarios:
        source = Path(trace_dir) / f"{_base_id(item)}.csv"
        target = cache_path(cache_dir, item, item.seed)
        if target.exists():
            report["present"].append(item.id)
            continue
        if not source.exists():
            report["absent"].append(item.id)
            continue
        text = source.read_text(newline="")
        fresh = _rows_to_csv(list(trace_rows(run_scenario(item, until_s=check_s))))
        expected_rows = round(item.duration_s / item.record_interval_s) + 1
        lines = text.count("\n") - 1
        if not text.startswith(fresh) or lines != expected_rows:
            report["rejected"].append(item.id)
            if progress:
                progress(f"{item.id}: trace does not match the current code; not used")
            continue
        _write_gzip_text(target, text)
        report["seeded"].append(item.id)
        if progress:
            progress(f"{item.id}: seeded from {source}")
    return report


# ---------------------------------------------------------------------- reference entries


@dataclass(frozen=True)
class ReferenceEstimate:
    t_s: float
    mean: Health
    std: Health


@dataclass(frozen=True)
class ReferenceOutput:
    t_s: float
    alarm: bool
    statistic: float
    channel: str | None = None


class OracleEstimator:
    """NOT AN ESTIMATOR: returns the true health, read from the ground-truth stream.

    It exists only to check the metrics (a perfect answer must score zero error, zero
    convergence time and full coverage). It reports a zero standard deviation. The runner
    builds it with the truth stream through a separate code path (``Entry.needs_truth``);
    nothing under test is ever given truth.
    """

    def __init__(self, truths: Sequence[Truth]) -> None:
        self._health = {truth.t_s: truth.health for truth in truths}

    def update(self, obs: Observation) -> ReferenceEstimate:
        return ReferenceEstimate(obs.t_s, self._health[obs.t_s], Health())


class CleanEstimator:
    """Do-nothing baseline: always reports the clean engine, with zero standard deviation."""

    def update(self, obs: Observation) -> ReferenceEstimate:
        return ReferenceEstimate(obs.t_s, Health(), Health())


class NeverDetector:
    """Do-nothing baseline: never raises an alarm."""

    def update(self, obs: Observation) -> ReferenceOutput:
        return ReferenceOutput(obs.t_s, False, 0.0, None)


# ------------------------------------------------------------------------------- registry

ESTIMATOR = "estimator"
DETECTOR = "detector"


@dataclass(frozen=True)
class Entry:
    """A named estimator or detector: ``target`` is ``"module:attribute"``, a no-argument
    factory (usually the class), except that a ``needs_truth`` entry is called with the
    truth stream (reference entries only)."""

    name: str
    kind: str
    target: str
    description: str
    needs_truth: bool = False
    reference: bool = False


REGISTRY: dict[str, Entry] = {
    entry.name: entry
    for entry in (
        Entry(
            "oracle",
            ESTIMATOR,
            f"{__name__}:OracleEstimator",
            "Reference only, NOT an estimator: returns the true health (checks the metrics).",
            needs_truth=True,
            reference=True,
        ),
        Entry(
            "clean",
            ESTIMATOR,
            f"{__name__}:CleanEstimator",
            "Do-nothing baseline: always the clean engine, zero standard deviation.",
            reference=True,
        ),
        Entry(
            "ukf",
            ESTIMATOR,
            "turbineiq.estimation.ukf:UKFHealthEstimator",
            "Unscented Kalman filter on the quasi-steady twin.",
        ),
        Entry(
            "never",
            DETECTOR,
            f"{__name__}:NeverDetector",
            "Do-nothing baseline: never alarms.",
            reference=True,
        ),
        Entry(
            "residual",
            DETECTOR,
            "turbineiq.estimation.detectors:ResidualScreen",
            "Threshold screen on standardised twin residuals.",
        ),
        Entry(
            "cusum",
            DETECTOR,
            "turbineiq.estimation.detectors:CusumDetector",
            "CUSUM on twin residuals.",
        ),
        Entry(
            "mewma",
            DETECTOR,
            "turbineiq.estimation.detectors:MewmaDetector",
            "Multivariate EWMA on twin residuals.",
        ),
        Entry(
            "isolator",
            DETECTOR,
            "turbineiq.estimation.detectors:PatternIsolator",
            "CUSUM detection with fault-pattern isolation (scored through its label).",
        ),
    )
}

#: Isolation labels used by the detectors (``PatternIsolator.label``), per ground-truth
#: fault: degradation kind, or sensor channel of an injected sensor fault.
FAULT_LABELS = {
    "compressor_fouling": "compressor_fouling",
    "turbine_erosion": "turbine_erosion",
    "fuel_flow": "fuel_meter",
    "electrical_power": "power_sensor",
    "exhaust_temperature": "exhaust_sensor",
    "compressor_discharge_temperature": "cdt_sensor",
    "compressor_discharge_pressure": "cdp_sensor",
}
#: Detector channel names (``twin.MEASUREMENTS``) of the instrumented sensor channels.
SENSOR_CHANNELS = {
    "electrical_power": "power_mw",
    "exhaust_temperature": "exhaust_k",
    "compressor_discharge_temperature": "cdt_k",
    "compressor_discharge_pressure": "cdp_kpa",
}


def expected_isolation(item: Scenario) -> tuple[str | None, str | None]:
    """``(label, channel)`` a detector should name for the scenario's first fault event.

    The label follows :data:`FAULT_LABELS`; the channel is set only for a sensor fault on
    one of the four twin outputs. ``None`` where no label or channel applies (a clean
    scenario, the slow fuel valve, or a sensor without a twin output).
    """

    events = item.fault_events()
    if not events:
        return None, None
    first = events[0]
    params = first["params"]
    if first["command"] == "inject_degradation":
        return FAULT_LABELS.get(params["kind"]), None
    if first["command"] == "inject_sensor_fault":
        return FAULT_LABELS.get(params["channel"]), SENSOR_CHANNELS.get(params["channel"])
    return None, None


@dataclass(frozen=True)
class Resolved:
    entry: Entry
    factory: Callable[..., Any] | None
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.factory is not None


def load_entry(entry: Entry) -> Resolved:
    """Import an entry's factory. A missing module or attribute is reported, not raised.

    Only a missing *target* module (or one of its parent packages) counts as missing: an
    import error inside a module that exists is a bug in that module and is raised.
    """

    module_name, _, attr = entry.target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing and (module_name == missing or module_name.startswith(missing + ".")):
            return Resolved(
                entry,
                None,
                f"skipped {entry.kind} '{entry.name}': module {module_name} not found "
                "(not merged on this branch yet?)",
            )
        raise
    factory = getattr(module, attr, None) if attr else None
    if factory is None:
        return Resolved(
            entry,
            None,
            f"skipped {entry.kind} '{entry.name}': {module_name} has no attribute '{attr}'",
        )
    return Resolved(entry, factory)


def resolve(name: str, kind: str, registry: Mapping[str, Entry] = REGISTRY) -> Resolved:
    """Look a name up in the registry (or take ``module:attribute``) and import it lazily."""

    entry = registry.get(name)
    if entry is None:
        if ":" not in name:
            known = ", ".join(sorted(n for n, e in registry.items() if e.kind == kind))
            raise KeyError(f"unknown {kind} '{name}' (known: {known}; or give module:attribute)")
        entry = Entry(name, kind, name, "Given on the command line as module:attribute.")
    if entry.kind != kind:
        raise ValueError(f"'{name}' is a {entry.kind}, not a {kind}")
    return load_entry(entry)


# ------------------------------------------------------------------------------- running


def run_estimator(estimator: Any, observations: Sequence[Observation]) -> tuple[np.ndarray, ...]:
    """Feed the observations in order and return ``(mean, std)``, each ``(n, 3)``.

    Row ``i`` is the estimate in force at observation ``i``: the last one that ``update``
    returned at or before it (``None`` keeps the previous one), NaN before the first.
    Columns are the :class:`~turbineiq.simulation.maps.Health` fields. An estimate stamped
    later than the observation it answers is look-ahead and raises ``ValueError``.
    """

    n = len(observations)
    mean = np.full((n, 3), np.nan)
    std = np.full((n, 3), np.nan)
    current: tuple[tuple[float, ...], tuple[float, ...]] | None = None
    for i, obs in enumerate(observations):
        out = estimator.update(obs)
        if out is not None:
            if float(out.t_s) > obs.t_s + 1e-9:
                raise ValueError(f"estimate stamped {out.t_s} s answers observation {obs.t_s} s")
            current = (tuple(map(float, out.mean)), tuple(map(float, out.std)))
        if current is not None:
            mean[i], std[i] = current
    return mean, std


def run_detector(
    detector: Any, observations: Sequence[Observation]
) -> tuple[np.ndarray, np.ndarray, list[str | None]]:
    """Feed the observations in order and return ``(alarm, statistic, channel)`` per sample.

    Same zero-order hold as :func:`run_estimator`; before the first output the alarm is off,
    the statistic NaN and the channel ``None``.
    """

    n = len(observations)
    alarm = np.zeros(n, dtype=bool)
    statistic = np.full(n, np.nan)
    channel: list[str | None] = [None] * n
    current = None
    for i, obs in enumerate(observations):
        out = detector.update(obs)
        if out is not None:
            if float(out.t_s) > obs.t_s + 1e-9:
                raise ValueError(f"output stamped {out.t_s} s answers observation {obs.t_s} s")
            current = (bool(out.alarm), float(out.statistic), out.channel)
        if current is not None:
            alarm[i], statistic[i], channel[i] = current
    return alarm, statistic, channel


# ------------------------------------------------------------------------------- metrics

PARAMETERS = Health._fields  # compressor_flow, compressor_efficiency, turbine_efficiency
#: Reported units: flow capacity in percent, efficiencies in points (both = fraction * 100).
UNITS = {"compressor_flow": "pct", "compressor_efficiency": "pts", "turbine_efficiency": "pts"}
DEFAULT_SETTLE_S = 900.0
DEFAULT_TOLERANCE = (0.005, 0.005, 0.005)  # fractions: 0.5 percent / 0.5 points


@dataclass(frozen=True)
class StreamContext:
    """Ground truth of one stream on its sample grid, for scoring."""

    t_s: np.ndarray
    health: np.ndarray  # (n, 3) true health, fractions
    loaded: np.ndarray  # unit state "loaded" with the breaker closed
    steady: np.ndarray | None  # SteadyStateGate output (default settings), if computed
    event_times: tuple[float, ...]  # ground-truth fault events within the stream
    dt_s: float

    @property
    def onset_s(self) -> float | None:
        """The first ground-truth fault event, or ``None`` for a clean stream."""

        return self.event_times[0] if self.event_times else None

    @property
    def loading_times(self) -> tuple[float, ...]:
        start = self.loaded & ~np.concatenate(([False], self.loaded[:-1]))
        return tuple(float(t) for t in self.t_s[start])


def stream_context(
    item: Scenario,
    observations: Sequence[Observation],
    truths: Sequence[Truth],
    *,
    steady: bool = True,
) -> StreamContext:
    t_s = np.array([obs.t_s for obs in observations], dtype=float)
    end = float(t_s[-1]) if len(t_s) else 0.0
    gate = SteadyStateGate() if steady else None
    return StreamContext(
        t_s=t_s,
        health=np.array([tuple(truth.health) for truth in truths], dtype=float).reshape(-1, 3),
        loaded=np.array([obs.state == "loaded" and obs.breaker_closed for obs in observations]),
        steady=None if gate is None else np.array([gate.update(obs) for obs in observations]),
        event_times=tuple(float(e["t_s"]) for e in item.fault_events() if float(e["t_s"]) <= end),
        dt_s=float(item.record_interval_s),
    )


def scoring_window(ctx: StreamContext, settle_s: float = DEFAULT_SETTLE_S) -> np.ndarray:
    """Samples on which estimate error and coverage are scored ("after convergence").

    A sample is scored if the unit is loaded (state ``loaded``, breaker closed) and it is
    not within ``settle_s`` after a ground-truth fault event or after the unit was loaded
    (synchronised). The window is a property of the scenario, the same for every estimator.
    """

    mask = ctx.loaded.copy()
    for start in (*ctx.event_times, *ctx.loading_times):
        mask &= ~((ctx.t_s >= start) & (ctx.t_s < start + settle_s))
    return mask


def convergence_time(
    ctx: StreamContext, mean: np.ndarray, tolerance: Sequence[float] = DEFAULT_TOLERANCE
) -> float | None:
    """Seconds from the fault onset until the estimate stays in the tolerance band for good.

    Considered samples: from the onset (first ground-truth fault event) to the end of the
    stream, while the unit is loaded. A sample is in band if an estimate is in force and
    ``|estimate - truth| <= tolerance`` for all three parameters. The convergence time is
    ``t* - onset``, where ``t*`` is the first considered sample after the last one out of
    band (0 if none is out of band). Returns ``math.inf`` if the last considered sample is
    out of band (not converged within the run) and ``None`` if there is no onset or no
    considered sample (not applicable).
    """

    onset = ctx.onset_s
    if onset is None:
        return None
    considered = ctx.loaded & (ctx.t_s >= onset)
    if not considered.any():
        return None
    with np.errstate(invalid="ignore"):
        in_band = np.all(np.abs(mean - ctx.health) <= np.asarray(tolerance), axis=1)
    out = np.flatnonzero(considered & ~in_band)
    if out.size == 0:
        return 0.0
    later = np.flatnonzero(considered[out[-1] + 1 :])
    if later.size == 0:
        return math.inf
    return float(ctx.t_s[out[-1] + 1 + later[0]] - onset)


def score_estimates(
    ctx: StreamContext,
    mean: np.ndarray,
    std: np.ndarray,
    *,
    settle_s: float = DEFAULT_SETTLE_S,
    tolerance: Sequence[float] = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """Error, coverage and convergence of one health-estimate track against the truth.

    On the scored samples (:func:`scoring_window`, and an estimate in force), per parameter:
    ``rms_*`` = sqrt(mean(e^2)) and ``bias_*`` = mean(e), with e = 100 * (estimate - truth)
    (percent of flow capacity, points of efficiency; ``*_compressor_efficiency_pts`` is the
    efficiency part of fouling); ``coverage_*`` = share of samples with
    ``|estimate - truth| <= 2 std`` (``coverage_joint``: all three at once; nominal 0.954
    for a calibrated Gaussian estimate). ``availability`` = scored / window samples.
    ``convergence_s`` is :func:`convergence_time` (``None`` when not converged or not
    applicable; ``converged`` tells which).
    """

    window = scoring_window(ctx, settle_s)
    have = window & np.all(np.isfinite(mean), axis=1)
    error = mean[have] - ctx.health[have]
    result: dict[str, Any] = {
        "window_samples": int(window.sum()),
        "scored_samples": int(have.sum()),
        "availability": float(have.sum() / window.sum()) if window.any() else None,
    }
    with np.errstate(invalid="ignore"):
        covered = np.abs(error) <= 2.0 * std[have]
    for k, name in enumerate(PARAMETERS):
        unit = UNITS[name]
        e = 100.0 * error[:, k]
        result[f"rms_{name}_{unit}"] = float(np.sqrt(np.mean(e**2))) if e.size else None
        result[f"bias_{name}_{unit}"] = float(np.mean(e)) if e.size else None
        result[f"coverage_{name}"] = float(np.mean(covered[:, k])) if e.size else None
    result["coverage_joint"] = float(np.mean(np.all(covered, axis=1))) if error.size else None
    conv = convergence_time(ctx, mean, tolerance)
    result["converged"] = None if conv is None else math.isfinite(conv)
    result["convergence_s"] = conv if conv is not None and math.isfinite(conv) else None
    return result


_NO_LABEL = object()  # the detector has no ``label`` attribute


def score_isolation(
    item: Scenario, ctx: StreamContext, detection: Mapping[str, Any], label: Any = _NO_LABEL
) -> dict[str, Any]:
    """Whether a detector named the right channel and (if it has one) the right label.

    Expected values come from :func:`expected_isolation` for the first fault event.
    ``channel_correct``: the output channel at the first alarm at or after the onset equals
    the faulty sensor's twin output (scored only for sensor faults on the four twin outputs
    and only if detected). ``label_correct``: the detector's ``label`` attribute at the end
    of the run equals the expected label (scored only for entries that have ``label``, for
    faults with a label, and only if detected). ``None`` means not scored.
    """

    want_label, want_channel = expected_isolation(item) if ctx.onset_s is not None else (None,) * 2
    detected = bool(detection.get("detected"))
    result: dict[str, Any] = {"expected_label": want_label, "expected_channel": want_channel}
    result["channel_correct"] = (
        detection.get("channel_at_detection") == want_channel
        if want_channel is not None and detected
        else None
    )
    if label is not _NO_LABEL:
        result["label"] = label
        result["label_correct"] = (
            label == want_label if want_label is not None and detected else None
        )
    return result


def score_detections(
    ctx: StreamContext, alarm: np.ndarray, channel: Sequence[str | None] | None = None
) -> dict[str, Any]:
    """Detection delay, missed detection and false-alarm rates of one alarm track.

    * ``delay_s``: time from the onset (first ground-truth fault event) to the first sample
      at or after it with the alarm on; ``detected`` is false (a missed detection) if there
      is none before the end of the run. ``None`` for a clean stream.
    * False alarms are counted on the exposure: the whole stream for a clean scenario, the
      samples before the onset otherwise. A false alarm is an alarm onset (a sample with the
      alarm on after one with it off, or on at the first sample). ``false_alarms_steady``
      counts onsets at samples where the shared
      :class:`~turbineiq.estimation.steady.SteadyStateGate` (default settings) is open and
      ``steady_h`` is the open time; ``false_alarms_loaded`` / ``loaded_h`` do the same over
      all loaded samples (so transients count). Rates are per hour (``None`` with no
      exposure). ``alarm_fraction_steady`` is the share of steady exposure with the alarm on.
    """

    if ctx.steady is None:
        raise ValueError("score_detections needs a context built with steady=True")
    onset = ctx.onset_s
    result: dict[str, Any] = {"onset_s": onset}
    if onset is None:
        result.update(detected=None, delay_s=None, channel_at_detection=None)
        exposure = np.ones_like(ctx.loaded)
    else:
        hits = np.flatnonzero(alarm & (ctx.t_s >= onset))
        detected = hits.size > 0
        result["detected"] = detected
        result["delay_s"] = float(ctx.t_s[hits[0]] - onset) if detected else None
        result["channel_at_detection"] = channel[hits[0]] if detected and channel else None
        exposure = ctx.t_s < onset
    rising = alarm & ~np.concatenate(([False], alarm[:-1]))
    for label, where in (("steady", ctx.steady), ("loaded", ctx.loaded)):
        exposed = exposure & where
        hours = float(exposed.sum()) * ctx.dt_s / 3600.0
        count = int((rising & exposed).sum())
        result[f"false_alarms_{label}"] = count
        result[f"{label}_h"] = hours
        result[f"false_alarms_{label}_per_h"] = count / hours if hours > 0 else None
    steady_exposed = exposure & ctx.steady
    result["alarm_fraction_steady"] = (
        float(alarm[steady_exposed].mean()) if steady_exposed.any() else None
    )
    return result


# ------------------------------------------------------------------------------ summaries

_T975 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201,
         2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069,
         2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042)  # fmt: skip


def t_quantile_975(df: int) -> float:
    """Two-sided 95 % Student t quantile (table to 30 degrees of freedom, then a series)."""

    if df < 1:
        raise ValueError("df must be >= 1")
    if df <= len(_T975):
        return _T975[df - 1]
    z = 1.959964
    return (
        z
        + (z**3 + z) / (4 * df)
        + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)
        + (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * df**3)
    )


def summarize(values: Iterable[float | None]) -> dict[str, Any]:
    """Mean over trials with a 95 % Student t interval (``mean +/- t * sd / sqrt(n)``).

    ``None`` values (not applicable, not converged, not detected) are left out and ``n``
    counts the rest. With one value there is no interval. The t interval assumes roughly
    normal trial means; with five trials it is wide on purpose.
    """

    data = np.array([v for v in values if v is not None], dtype=float)
    n = int(data.size)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "half_width": None}
    mean = float(data.mean())
    if n == 1:
        return {"n": 1, "mean": mean, "sd": None, "half_width": None}
    sd = float(data.std(ddof=1))
    return {"n": n, "mean": mean, "sd": sd, "half_width": t_quantile_975(n - 1) * sd / n**0.5}


ESTIMATE_METRICS = (
    *(f"rms_{p}_{UNITS[p]}" for p in PARAMETERS),
    *(f"bias_{p}_{UNITS[p]}" for p in PARAMETERS),
    *(f"coverage_{p}" for p in PARAMETERS),
    "coverage_joint",
    "availability",
    "convergence_s",
)
DETECTION_METRICS = (
    "delay_s",
    "false_alarms_steady_per_h",
    "false_alarms_loaded_per_h",
    "alarm_fraction_steady",
)


def _count(runs: Sequence[Mapping[str, Any]], key: str, value: Any) -> int:
    return sum(1 for run in runs if run.get(key) is value)


def _pooled(runs: Sequence[Mapping[str, Any]], label: str) -> float | None:
    hours = sum(run[f"{label}_h"] for run in runs)
    count = sum(run[f"false_alarms_{label}"] for run in runs)
    return count / hours if hours > 0 else None


def _summary_block(kind: str, runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ok = [run for run in runs if "error" not in run]
    block: dict[str, Any] = {"trials": len(runs), "errors": len(runs) - len(ok)}
    metrics = ESTIMATE_METRICS if kind == ESTIMATOR else DETECTION_METRICS
    for key in metrics:
        block[key] = summarize(run.get(key) for run in ok)
    if kind == ESTIMATOR:
        block["converged"] = _count(ok, "converged", True)
        block["not_converged"] = _count(ok, "converged", False)
    else:
        block["detected"] = _count(ok, "detected", True)
        block["missed"] = _count(ok, "detected", False)
        for label in ("steady", "loaded"):
            block[f"pooled_false_alarms_{label}_per_h"] = _pooled(ok, label)
            block[f"{label}_h"] = sum(run[f"{label}_h"] for run in ok)
            block[f"false_alarms_{label}"] = sum(run[f"false_alarms_{label}"] for run in ok)
        for key in ("channel_correct", "label_correct"):
            block[key] = _count(ok, key, True)
            block[key.replace("correct", "scored")] = block[key] + _count(ok, key, False)
    return block


def aggregate(runs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per entry: a summary per scenario (over seeds) and per group of scenarios.

    Groups: ``clean`` (no fault event), ``fault`` (all others) and each category.
    """

    out: list[dict[str, Any]] = []
    keys = list(dict.fromkeys((run["kind"], run["name"]) for run in runs))
    for kind, name in keys:
        mine = [run for run in runs if (run["kind"], run["name"]) == (kind, name)]
        scenarios = list(dict.fromkeys(run["scenario"] for run in mine))
        per_scenario = {}
        for sid in scenarios:
            these = [run for run in mine if run["scenario"] == sid]
            per_scenario[sid] = {"category": these[0]["category"], **_summary_block(kind, these)}
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for run in mine:
            groups.setdefault("clean" if run["clean"] else "fault", []).append(run)
            groups.setdefault(f"category:{run['category']}", []).append(run)
        out.append(
            {
                "kind": kind,
                "name": name,
                "scenarios": per_scenario,
                "groups": {g: _summary_block(kind, rs) for g, rs in sorted(groups.items())},
            }
        )
    return out


# -------------------------------------------------------------------------------- runner


@dataclass(frozen=True)
class ScoringConfig:
    settle_s: float = DEFAULT_SETTLE_S
    tolerance: tuple[float, float, float] = DEFAULT_TOLERANCE


def select_scenarios(
    patterns: Sequence[str] | None, scenarios: Sequence[Scenario] = SCENARIOS
) -> list[Scenario]:
    """Bank scenarios matching any pattern: an id, a glob (``fouling_*``) or
    ``category:<name>``; comma-separated lists are split. None or empty selects all."""

    parts = [p.strip() for pattern in patterns or () for p in pattern.split(",") if p.strip()]
    if not parts:
        return list(scenarios)
    chosen: set[str] = set()
    for part in parts:
        if part.startswith("category:"):
            matched = [s.id for s in scenarios if s.category == part.split(":", 1)[1]]
        else:
            matched = [s.id for s in scenarios if fnmatch.fnmatchcase(s.id, part)]
        if not matched:
            raise ValueError(f"no scenario matches {part!r}")
        chosen.update(matched)
    return [s for s in scenarios if s.id in chosen]


def evaluate_stream(
    item: Scenario,
    seed: int,
    entries: Sequence[Entry],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    until_s: float | None = None,
    config: ScoringConfig = ScoringConfig(),
) -> list[dict[str, Any]]:
    """Run every entry on one (scenario, seed) stream and score it; one record per entry.

    Each entry gets a fresh instance. An exception inside an entry is recorded in its
    record (``error``) instead of stopping the benchmark.
    """

    observations, truths = load_streams(item, seed, cache_dir, until_s)
    ctx = stream_context(
        item, observations, truths, steady=any(e.kind == DETECTOR for e in entries)
    )
    records = []
    for entry in entries:
        record: dict[str, Any] = {
            "kind": entry.kind,
            "name": entry.name,
            "scenario": _base_id(item),
            "category": item.category,
            "clean": ctx.onset_s is None,
            "seed": seed,
        }
        start = time.perf_counter()
        try:
            resolved = load_entry(entry)
            if not resolved.available:
                raise RuntimeError(resolved.reason)
            if entry.needs_truth:
                # Separate path for reference entries that read ground truth (the oracle).
                # Nothing under test is built this way.
                instance = resolved.factory(truths)
            else:
                instance = resolved.factory()
            if entry.kind == ESTIMATOR:
                mean, std = run_estimator(instance, observations)
                record.update(
                    score_estimates(
                        ctx, mean, std, settle_s=config.settle_s, tolerance=config.tolerance
                    )
                )
            else:
                alarm, _statistic, channel = run_detector(instance, observations)
                record.update(score_detections(ctx, alarm, channel))
                label = getattr(instance, "label", _NO_LABEL)
                record.update(score_isolation(item, ctx, record, label))
        except Exception as exc:  # noqa: BLE001 - one failing entry must not stop the rest
            record["error"] = f"{type(exc).__name__}: {exc}"
        record["run_s"] = round(time.perf_counter() - start, 3)
        records.append(record)
    return records


def _evaluate_job(args: tuple) -> list[dict[str, Any]]:
    return evaluate_stream(*args)


def run_benchmark(
    estimators: Sequence[str] = (),
    detectors: Sequence[str] = (),
    scenarios: Sequence[Scenario] | None = None,
    *,
    seed_policy: str = "eval",
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    workers: int = 2,
    until_s: float | None = None,
    config: ScoringConfig = ScoringConfig(),
    registry: Mapping[str, Entry] = REGISTRY,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Generate (or load) the streams, run every available entry on each and score it.

    Entries whose module is missing are skipped and listed under ``skipped``.
    """

    resolved = [resolve(n, ESTIMATOR, registry) for n in estimators]
    resolved += [resolve(n, DETECTOR, registry) for n in detectors]
    skipped = [r.reason for r in resolved if not r.available]
    for reason in skipped:
        if progress:
            progress(reason)
    entries = [r.entry for r in resolved if r.available]
    chosen = list(SCENARIOS if scenarios is None else scenarios)
    pairs = [(item, seed) for item in chosen for seed in seeds_for(item, seed_policy)]
    started = time.perf_counter()
    stream_stats = ensure_streams(
        pairs, cache_dir, workers=workers, until_s=until_s, progress=progress
    )
    runs: list[dict[str, Any]] = []
    if entries:
        jobs = [(item, seed, entries, str(cache_dir), until_s, config) for item, seed in pairs]
        if workers > 1 and len(jobs) > 1:
            with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
                for records in pool.map(_evaluate_job, jobs):
                    runs.extend(records)
        else:
            for job in jobs:
                runs.extend(_evaluate_job(job))
    return {
        "meta": {
            "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "model_fingerprint": model_fingerprint(),
            "cache_format": CACHE_FORMAT,
            "wall_s": round(time.perf_counter() - started, 1),
        },
        "protocol": {
            "seed_policy": seed_policy,
            "scenarios": [item.id for item in chosen],
            "seeds": {item.id: seeds_for(item, seed_policy) for item in chosen},
            "until_s": until_s,
            "settle_s": config.settle_s,
            "tolerance": list(config.tolerance),
            "interval": "95 % Student t over trials (mean +/- t(0.975, n-1) * sd / sqrt(n))",
            "units": "error in percent of flow capacity / points of efficiency (fraction*100)",
        },
        "entries": [asdict(entry) for entry in entries],
        "skipped": skipped,
        "streams": stream_stats,
        "runs": runs,
        "summary": aggregate(runs),
    }


# ------------------------------------------------------------------------------ markdown


def _fmt(
    stat: Mapping[str, Any],
    digits: int = 2,
    scale: float = 1.0,
    unit: str = "",
    interval: bool = True,
) -> str:
    if not stat or stat.get("mean") is None:
        return "–"
    text = f"{stat['mean'] * scale:.{digits}f}"
    if interval and stat.get("half_width") is not None:
        text += f" ± {stat['half_width'] * scale:.{digits}f}"
    return text + unit


def _ratio(hits: int, total: int) -> str:
    return f"{hits}/{total}" if total else "–"


def _rate(value: float | None, digits: int = 2) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def format_markdown(results: Mapping[str, Any]) -> str:
    """Markdown tables of a :func:`run_benchmark` result (means ± 95 % t half-widths)."""

    protocol = results["protocol"]
    entries = {e["name"]: e for e in results["entries"]}
    tol = " / ".join(f"{100 * t:g}" for t in protocol["tolerance"])
    lines = [
        "# Estimation benchmark results",
        "",
        f"Created {results['meta']['created_utc']}; seed policy `{protocol['seed_policy']}`; "
        f"settle {protocol['settle_s']:g} s; convergence band {tol} (pct / pts / pts); "
        f"values are mean ± 95 % Student t half-width over trials.",
        "",
    ]
    if protocol.get("until_s"):
        lines += [f"Streams truncated at {protocol['until_s']:g} s.", ""]
    notes = list(results["skipped"])
    failed = [run for run in results["runs"] if "error" in run]
    notes += [
        f"error: {run['kind']} '{run['name']}' on {run['scenario']} seed {run['seed']}: "
        f"{run['error']}"
        for run in failed[:20]
    ]
    if len(failed) > 20:
        notes.append(f"... and {len(failed) - 20} more errors (see the JSON results)")
    lines += [f"- {note}" for note in notes] + ([""] if notes else [])
    for block in results["summary"]:
        entry = entries.get(block["name"], {})
        lines += [f"## {block['kind'].capitalize()} `{block['name']}`", ""]
        if entry.get("description"):
            lines += [entry["description"], ""]
        if block["kind"] == ESTIMATOR:
            lines += _estimator_table(block)
        else:
            lines += _detector_table(block)
        lines.append("")
    return "\n".join(lines)


def _estimator_table(block: Mapping[str, Any]) -> list[str]:
    head = (
        "| Scenario | n | RMS flow (%) | RMS ηc (pt) | RMS ηt (pt) | Bias flow (%) "
        "| Bias ηc (pt) | Bias ηt (pt) | 2σ coverage | Converged | Convergence (s) |"
    )
    rows = [head, "|" + " --- |" * 11]
    for label, s, ci in _rows(block):
        conv = s["converged"] + s["not_converged"]
        rows.append(
            "| "
            + " | ".join(
                [
                    label,
                    str(s["trials"] - s["errors"]),
                    *(_fmt(s[f"rms_{p}_{UNITS[p]}"], interval=ci) for p in PARAMETERS),
                    *(_fmt(s[f"bias_{p}_{UNITS[p]}"], interval=ci) for p in PARAMETERS),
                    _fmt(s["coverage_joint"], 1, 100.0, " %", ci),
                    f"{s['converged']}/{conv}" if conv else "–",
                    _fmt(s["convergence_s"], 0, interval=ci),
                ]
            )
            + " |"
        )
    return rows


def _rows(block: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any], bool]]:
    """Scenario rows (with intervals over seeds), then group rows (means only: a group
    mixes scenarios, so the spread of its runs is not a confidence interval)."""

    return [(f"`{sid}`", s, True) for sid, s in block["scenarios"].items()] + [
        (f"**{group}**", s, False) for group, s in block["groups"].items()
    ]


def _detector_table(block: Mapping[str, Any]) -> list[str]:
    head = (
        "| Scenario | n | Detected | Delay (s) | FA/h steady | FA/h loaded "
        "| Pooled FA/h steady | Steady h | Alarm share (steady) | Channel ok | Label ok |"
    )
    rows = [head, "|" + " --- |" * 11]
    for label, s, ci in _rows(block):
        tried = s["detected"] + s["missed"]
        rows.append(
            "| "
            + " | ".join(
                [
                    label,
                    str(s["trials"] - s["errors"]),
                    f"{s['detected']}/{tried}" if tried else "–",
                    _fmt(s["delay_s"], 0, interval=ci),
                    _fmt(s["false_alarms_steady_per_h"], interval=ci),
                    _fmt(s["false_alarms_loaded_per_h"], interval=ci),
                    _rate(s["pooled_false_alarms_steady_per_h"]),
                    f"{s['steady_h']:.1f}",
                    _fmt(s["alarm_fraction_steady"], 1, 100.0, " %", ci),
                    _ratio(s["channel_correct"], s["channel_scored"]),
                    _ratio(s["label_correct"], s["label_scored"]),
                ]
            )
            + " |"
        )
    return rows
