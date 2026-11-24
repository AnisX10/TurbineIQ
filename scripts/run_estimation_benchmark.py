"""Score health estimators and fault detectors on the scenario bank (roadmap WP4).

    PYTHONPATH=src python scripts/run_estimation_benchmark.py --list
    PYTHONPATH=src python scripts/run_estimation_benchmark.py \\
        --estimator oracle --estimator clean --detector never \\
        --out results/benchmark.json --markdown results/benchmark.md
    PYTHONPATH=src python scripts/run_estimation_benchmark.py --estimator ukf \\
        --scenarios 'fouling_*' --scenarios category:sensor --seeds eval:2

Names come from the registry in ``turbineiq.estimation.benchmark`` (``--list``) or are given
as ``module:attribute``. A name whose module is not on this branch is skipped with a
message. Streams are generated on demand into the cache (``--workers`` processes) and
reused; ``--bank-traces`` first copies existing bank traces (bank seeds) into the cache.
See ``docs/ESTIMATION_BENCHMARK.md`` for the protocol and the metric definitions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from turbineiq.estimation.benchmark import (
    DEFAULT_CACHE_DIR,
    DEFAULT_SETTLE_S,
    DEFAULT_TOLERANCE,
    REGISTRY,
    ScoringConfig,
    ensure_streams,
    format_markdown,
    load_entry,
    run_benchmark,
    seed_cache_from_traces,
    seeds_for,
    select_scenarios,
)


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _list() -> None:
    for entry in REGISTRY.values():
        resolved = load_entry(entry)
        status = "available" if resolved.available else "missing"
        print(f"{entry.kind:9s} {entry.name:8s} {status:9s} {entry.target}")
        print(f"{'':28s} {entry.description}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--estimator", action="append", default=[], metavar="NAME")
    parser.add_argument("--detector", action="append", default=[], metavar="NAME")
    parser.add_argument(
        "--scenarios",
        action="append",
        metavar="PATTERN",
        help="scenario id, glob or category:<name> (repeatable, comma-separated); default all",
    )
    parser.add_argument(
        "--seeds",
        default="eval",
        help="eval (5 trials, default), eval:N, bank, tune:N or a list of seeds",
    )
    parser.add_argument("--workers", type=int, default=2, help="processes (default 2)")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--bank-traces", type=Path, help="seed the cache from <dir>/<id>.csv")
    parser.add_argument("--until-s", type=float, help="truncate every stream (quick runs)")
    parser.add_argument("--settle-s", type=float, default=DEFAULT_SETTLE_S)
    parser.add_argument(
        "--tolerance",
        type=float,
        nargs=3,
        default=[100 * t for t in DEFAULT_TOLERANCE],
        metavar=("FLOW_PCT", "ETA_C_PTS", "ETA_T_PTS"),
        help="convergence band in percent / points (default 0.5 0.5 0.5)",
    )
    parser.add_argument("--out", type=Path, help="JSON results file")
    parser.add_argument("--markdown", type=Path, help="Markdown table file")
    parser.add_argument("--generate-only", action="store_true", help="only fill the cache")
    parser.add_argument("--list", action="store_true", help="list registry entries and exit")
    args = parser.parse_args(argv)

    if args.list:
        _list()
        return 0
    if not (args.estimator or args.detector or args.generate_only):
        parser.error("give at least one --estimator or --detector (or --generate-only)")
    try:
        scenarios = select_scenarios(args.scenarios)
        for item in scenarios:
            seeds_for(item, args.seeds)
    except ValueError as exc:
        parser.error(str(exc))

    def say(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    if args.bank_traces:
        report = seed_cache_from_traces(args.bank_traces, args.cache_dir, scenarios, progress=say)
        say(f"bank traces: { {k: len(v) for k, v in report.items()} }")
    if args.generate_only:
        pairs = [(item, seed) for item in scenarios for seed in seeds_for(item, args.seeds)]
        stats = ensure_streams(
            pairs, args.cache_dir, workers=args.workers, until_s=args.until_s, progress=say
        )
        say(f"streams: {stats}")
        return 0

    config = ScoringConfig(
        settle_s=args.settle_s, tolerance=tuple(t / 100.0 for t in args.tolerance)
    )
    results = run_benchmark(
        args.estimator,
        args.detector,
        scenarios,
        seed_policy=args.seeds,
        cache_dir=args.cache_dir,
        workers=args.workers,
        until_s=args.until_s,
        config=config,
        progress=say,
    )
    results["meta"]["git_commit"] = _git_commit()
    markdown = format_markdown(results)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1) + "\n")
        say(f"wrote {args.out}")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown)
        say(f"wrote {args.markdown}")
    if not args.markdown:
        print(markdown)
    errors = sum(1 for run in results["runs"] if "error" in run)
    if errors:
        say(f"{errors} run(s) failed; see the results")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
