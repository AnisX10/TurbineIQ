"""Run the seeded scenario bank and write its logs, manifest and (optionally) CSV traces.

    python scripts/build_scenario_bank.py                      # logs + manifest
    python scripts/build_scenario_bank.py --traces data/scenarios/traces
    python scripts/build_scenario_bank.py --only fouling_step_part_load --traces /tmp/t

Logs (config + event log + digest) are small and committed; each one replays with
``turbineiq.simulation.replay``. Traces are regenerated on demand (1 s samples of the
measured channels next to the ground truth) and are not committed. Digests are exact on
the machine and Python build that produced them; another platform can differ in the last
bits of floating point and so in the digest, which the manifest records.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
import time
from pathlib import Path

from turbineiq.simulation.scenarios import SCENARIOS, run_scenario, trace_rows


def _summary(snapshot: dict) -> dict:
    measured = snapshot["measured"]
    return {
        "state": snapshot["state"],
        "true_electrical_power_mw": round(snapshot["electrical_power_mw"], 4),
        "true_exhaust_temperature_c": round(snapshot["exhaust_temperature_c"], 3),
        "true_heat_rate_kj_per_kwh": None
        if snapshot["heat_rate_kj_per_kwh"] is None
        else round(snapshot["heat_rate_kj_per_kwh"], 2),
        "measured_electrical_power_mw": round(measured["electrical_power_mw"], 4),
        "measured_exhaust_temperature_c": round(measured["exhaust_temperature_k"] - 273.15, 3),
        "limiter": snapshot["limiter"],
        "trip_cause": snapshot["trip_cause"],
        "injected_faults": snapshot["injected_faults"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/scenarios"))
    parser.add_argument("--traces", type=Path, help="also write one CSV trace per scenario here")
    parser.add_argument("--only", action="append", help="run only these scenario ids")
    args = parser.parse_args()

    chosen = [s for s in SCENARIOS if not args.only or s.id in args.only]
    if args.only and len(chosen) != len(set(args.only)):
        parser.error("unknown scenario id in --only")
    logs_dir = args.out / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    if args.traces:
        args.traces.mkdir(parents=True, exist_ok=True)

    entries = []
    for item in chosen:
        start = time.perf_counter()
        session = run_scenario(item)
        elapsed = time.perf_counter() - start
        log = session.log()
        (logs_dir / f"{item.id}.json").write_text(json.dumps(log, indent=1) + "\n")
        if args.traces:
            rows = list(trace_rows(session))
            with (args.traces / f"{item.id}.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        entries.append(
            {
                "id": item.id,
                "category": item.category,
                "description": item.description,
                "seed": item.seed,
                "ambient_temperature_c": item.ambient_temperature_c,
                "duration_s": item.duration_s,
                "script": [step.to_dict() for step in item.script],
                "ground_truth_fault_events": item.fault_events(),
                "steps": log["steps"],
                "trace_digest": log["trace_digest"],
                "end_state": _summary(session.snapshot()),
                "run_seconds": round(elapsed, 1),
            }
        )
        print(f"{item.id:36s} {elapsed:6.1f} s  {log['trace_digest'][:16]}", flush=True)

    manifest = {
        "note": (
            "Simulated scenarios with injected faults. Ground truth is the fault events in "
            "each script; logs in logs/ replay with turbineiq.simulation.replay. Degradation "
            "rates are accelerated so a scenario fits in about two hours. Nothing here is "
            "plant data."
        ),
        "trace_format": log["trace_format"] if entries else None,
        "dt_s": session.dt if entries else None,
        "platform": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "system": platform.system(),
        },
        "scenarios": entries,
    }
    if args.only:
        print("--only given: manifest not written", file=sys.stderr)
    else:
        (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
