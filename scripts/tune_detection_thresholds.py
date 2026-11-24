"""Check (or re-derive) the WP4 detector thresholds on healthy tuning streams only.

Every detector in the WP4 comparison is set for the same design false-alarm rate,
``TARGET_FALSE_ALARMS_PER_HOUR`` (one per 100 steady hours), on the same data: the five
clean bank scenarios with tuning seeds 1000-1019. This script reproduces that step.

* Residual detectors (``detectors.py``): refits the noise model, then estimates each
  detector's signal rate at its default threshold by bootstrap resampling of the
  standardised healthy residuals (``bootstrap_signal_rate``), and counts its signals on the
  tuning streams themselves.
* Estimator-based detector (``health_detector.py``): runs the UKF on each stream, counts
  alarm onsets of the Wald statistic against a grid of thresholds, and fits a log-linear
  tail to the rate to find the threshold for the design rate.

It only reads tuning seeds, never evaluation seeds. Streams come from (and go to) the
estimation benchmark's cache. The design grids (window, slack, smoothing, persistence)
are described in docs/FAULT_DETECTION.md and docs/WP4_RESULTS.md; this script checks the
chosen designs.

    PYTHONPATH=src python scripts/tune_detection_thresholds.py --out tuning.json
    PYTHONPATH=src python scripts/tune_detection_thresholds.py --seeds 2 --hours 2000  # quick
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from turbineiq.estimation import detectors as D
from turbineiq.estimation.benchmark import (
    DEFAULT_CACHE_DIR,
    TUNING_SEEDS,
    ensure_streams,
    load_streams,
)
from turbineiq.estimation.health_detector import (
    DEFAULT_PERSIST,
    DEFAULT_THRESHOLD,
    wald_statistic,
)
from turbineiq.estimation.steady import SteadyStateGate
from turbineiq.estimation.ukf import UKFHealthEstimator
from turbineiq.simulation.scenarios import SCENARIOS

TARGET = D.TARGET_FALSE_ALARMS_PER_HOUR


def residual_cores(noise: D.NoiseModel) -> dict[str, object]:
    return {
        "residual": lambda shape: D.ScreenCore(
            D.SCREEN_THRESHOLD, D.SCREEN_WINDOW, D.SCREEN_PERSISTENCE, shape
        ),
        "cusum": lambda shape: D.CusumCore(D.CUSUM_THRESHOLD, D.CUSUM_SLACK, D.CUSUM_CLIP, shape),
        "mewma": lambda shape: D.MewmaCore(
            D.MEWMA_THRESHOLD, D.MEWMA_SMOOTHING, noise.whitener(), shape
        ),
    }


def alarm_onsets(statistic: np.ndarray, threshold: float, persist: int) -> int:
    """Alarm onsets of 'statistic above threshold for persist consecutive updates'."""

    above, alarm, onsets = 0, False, 0
    for value in statistic:
        above = above + 1 if value > threshold else 0
        now = above >= persist
        onsets += int(now and not alarm)
        alarm = now
    return onsets


def wald_series(observations) -> np.ndarray:
    """The Wald statistic after each UKF measurement update."""

    estimator = UKFHealthEstimator()
    values, updates = [], 0
    for obs in observations:
        estimator.update(obs)
        if estimator.updates != updates:
            updates = estimator.updates
            values.append(wald_statistic(estimator.x, estimator.P))
    return np.array(values)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seeds", type=int, default=20, help="tuning seeds 1000..1000+N-1")
    parser.add_argument("--hours", type=float, default=40000.0, help="bootstrap hours")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--out", type=Path, help="write the results as JSON here")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    clean = [s for s in SCENARIOS if s.category == "baseline"]
    seeds = list(TUNING_SEEDS[: args.seeds])
    pairs = [(item, seed) for seed in seeds for item in clean]
    ensure_streams(pairs, args.cache_dir, workers=args.workers, progress=print)

    streams, steady_h = [], 0.0
    for item, seed in pairs:
        observations, _ = load_streams(item, seed, args.cache_dir)
        gate = SteadyStateGate()
        steady_h += sum(1 for obs in observations if gate.update(obs)) / 3600.0
        streams.append((f"{item.id}@{seed}", observations))
    print(f"{len(streams)} healthy streams, {steady_h:.1f} steady hours")
    result: dict = {"streams": len(streams), "seeds": seeds, "steady_h": steady_h}

    # Residual detectors: noise model, bootstrap rate at the defaults, signals on the data.
    rows, operating, fuel = D.healthy_residuals(obs for _, obs in streams)
    noise = D.NoiseModel.fit(rows, operating, fuel)
    result["noise_model"] = {"fitted": noise.__dict__, "default": D.TUNED_NOISE.__dict__}
    z = D.TUNED_NOISE.standardize(rows, fuel)
    result["residual_detectors"] = {}
    for name, make in residual_cores(D.TUNED_NOISE).items():
        signals, hours = D.bootstrap_signal_rate(make, z, args.hours, chains=4000, seed=1)
        factory = {"residual": D.ResidualScreen, "cusum": D.CusumDetector, "mewma": D.MewmaDetector}
        on_data = 0
        for _, observations in streams:
            detector = factory[name]()
            on_data += sum(detector.update(obs).alarm for obs in observations)
        rate = signals / hours
        result["residual_detectors"][name] = {
            "bootstrap_signals": signals,
            "bootstrap_hours": hours,
            "bootstrap_rate_per_h": rate,
            "signals_on_tuning_streams": on_data,
        }
        print(
            f"{name}: bootstrap {rate:.4f}/h ({signals} in {hours:.0f} h); "
            f"{on_data} signals on the tuning streams (target {TARGET}/h)"
        )

    # Estimator-based detector: alarm-rate curve of the Wald statistic and its tail.
    series = [wald_series(observations) for _, observations in streams]
    grid = np.round(np.arange(4.0, 15.01, 0.5), 2)
    curve = []
    for threshold in grid:
        onsets = sum(alarm_onsets(s, threshold, DEFAULT_PERSIST) for s in series)
        curve.append((float(threshold), onsets, onsets / steady_h))
    tail = [(h, math.log(rate)) for h, n, rate in curve if n >= 3][-4:]
    entry: dict = {"persist": DEFAULT_PERSIST, "curve": curve, "default": DEFAULT_THRESHOLD}
    if len(tail) >= 2:
        slope, intercept = np.polyfit([h for h, _ in tail], [v for _, v in tail], 1)
        entry["fit"] = {"intercept": float(intercept), "slope": float(slope)}
        entry["threshold_for_target"] = float((math.log(TARGET) - intercept) / slope)
    entry["onsets_at_default"] = sum(
        alarm_onsets(s, DEFAULT_THRESHOLD, DEFAULT_PERSIST) for s in series
    )
    result["ukf_shift"] = entry
    print(
        "ukf_shift: onsets per threshold "
        + " ".join(f"{h:g}:{n}" for h, n, _ in curve if n)
        + f"; tail fit gives {entry.get('threshold_for_target', float('nan')):.2f} for "
        f"{TARGET}/h (default {DEFAULT_THRESHOLD}); {entry['onsets_at_default']} onsets at "
        "the default"
    )
    result["wall_s"] = round(time.perf_counter() - started, 1)
    if args.out:
        args.out.write_text(json.dumps(result, indent=1, default=float))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
