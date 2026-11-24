# Estimation benchmark (WP4)

One harness scores every health estimator and fault detector of roadmap WP4 the same way:
on the same streams, with the same seeds and with the same metric code. The streams are
simulated runs of the scenario bank (`docs/SCENARIO_BANK.md`). Nothing here is plant data.

- Code: `src/turbineiq/estimation/benchmark.py` (seeds, stream cache, registry, runs,
  metrics, summaries).
- Runner: `scripts/run_estimation_benchmark.py`.
- Tests: `tests/test_estimation_benchmark.py`.

## What an estimator or detector may see

An entry sees one `Observation` at a time, in time order, through `update(obs)`. It sees
nothing else: no `Truth`, no scenario id and no fault events. An `Observation` holds the
unit state, breaker, load setpoint, ambient temperature, IGV position and the six
instrument readings (sensor faults and noise included).

| Kind | `update(obs)` returns | Fields used |
| --- | --- | --- |
| Estimator | an estimate or `None` | `t_s`, `mean: Health`, `std: Health` (fractions) |
| Detector | an output or `None` | `t_s`, `alarm: bool`, `statistic: float`, `channel: str \| None` |

- **Hold.** Whatever an entry returns stays in force until it returns something else
  (zero-order hold). `None` keeps the previous output. Before the first output there is no
  estimate and the alarm is off.
- **No look-ahead.** An output whose `t_s` is later than the observation it answers raises
  an error.
- **Fresh instances.** Each (scenario, seed) stream gets a new instance from a
  no-argument factory.
- **Errors.** An exception is recorded in that run's result (`error`) and the benchmark
  continues.
- **Optional `label`.** If a detector instance has a `label` attribute, its value at the
  end of the run is scored as an isolation label (see below).

The `oracle` entry is the only one built with the truth stream, through a separate code
path (`Entry.needs_truth`). It is not an estimator. It exists to check that the metrics
give a perfect score to a perfect answer.

## Seeds

- **Tuning** uses seeds 1000–1999 only (`--seeds tune:N` gives 1000 .. 1000+N-1).
- **Evaluation** runs each bank scenario five times: with its bank seed, and with
  seed + 10000·k for k = 1..4. For example, `fouling_step_part_load` runs with seeds 201,
  10201, 20201, 30201 and 40201. That makes 19 × 5 = 95 streams.
- No evaluation seed is in the tuning range (`is_evaluation_seed`).
- An explicit `--seeds` list may contain only tuning seeds or that scenario's own
  evaluation seeds.
- `--seeds eval:N` uses the first N trials; `bank` is the same as `eval:1`.

## Streams and cache

A stream is `run_scenario` of the scenario with the given seed, recorded every second. It
is stored as a gzip CSV with the columns of `trace_rows`, and split back into
observations and truth with `split_rows`.

Cache files go to `data/estimation/cache/` (git-ignored; `--cache-dir` changes it). Each
file is named `<id>__seed<seed>[__until<s>]__<hash>.csv.gz`. The hash covers three
things:

- the cache format;
- the scenario definition: script, duration, ambient and record interval. The id, label
  and description are left out;
- a fingerprint of the code in `turbineiq.simulation` and `turbineiq.engineering`. The
  fingerprint hashes each module's syntax tree without comments or docstrings, plus the
  package data files.

So a changed script or a changed plant model gives new keys and new streams. Editing a
comment does not.

- Missing streams are generated with a process pool (`--workers`, default 2).
- Files are written atomically.
- A truncated stream (`--until-s`) is cut from the full cached stream when that exists.

`--bank-traces DIR` copies existing bank traces (`DIR/<id>.csv`, bank seeds) into the
cache. A trace is accepted only if all of these hold:

- its header and row count match the scenario;
- its first 600 s are identical, as text, to a fresh run of the current code.

That check does not see a model change that acts only after 600 s. It does cover fouling
physics, because `fouled_unit_offline_wash` is fouled from t = 0.

Measured for the reference run below (4-CPU container shared with three other jobs):

- The 19 bank traces were seeded in 25 s. Separately, `fouling_step_part_load` was
  regenerated in full and was byte-identical to its bank trace.
- The other 76 streams took 1,046 s wall time with 2 workers (2,085 CPU-s, 19 to 60 s
  each, depending on load).
- The full cache is 95 files, 43 MB.

## Metrics

Health errors are reported as 100 × (estimate − truth): percent of compressor flow
capacity, and points of compressor or turbine polytropic efficiency. A positive bias
means the estimate shows less deterioration than the truth. "The fouling efficiency
error" is the compressor-efficiency column, the efficiency part of fouling.

Two ground-truth times are used throughout:

- The **onset** is the time of the scenario's first ground-truth fault event
  (`Scenario.fault_events()`).
- **Loaded** means unit state `loaded` with the breaker closed.

Defaults are `settle_s` = 900 s and a tolerance of 0.5 % / 0.5 pt / 0.5 pt. Both are
command-line options and are recorded in the results.

### Health estimates (`score_estimates`)

- **Scoring window** ("after convergence"). Loaded samples, except those within
  `settle_s` after a ground-truth fault event or after the unit was synchronised. The
  window depends only on the scenario, so it is the same for every estimator.
- **Scored samples.** Samples in the window where an estimate is in force.
  `availability` = scored / window samples.
- **RMS and bias**, per parameter, over the scored samples: `rms = sqrt(mean(e²))` and
  `bias = mean(e)`.
- **2σ coverage**, per parameter: the share of scored samples with
  |estimate − truth| ≤ 2·std. `coverage_joint` requires all three parameters at once. A
  calibrated Gaussian estimate gives about 95.4 %. A zero std counts as covered only when
  the error is exactly zero.
- **Convergence time.**
  - Considered samples: loaded samples from the onset to the end of the run.
  - A sample is in band if an estimate is in force and every parameter is within the
    tolerance of the truth.
  - The convergence time is t* − onset, where t* is the first considered sample after the
    last out-of-band one. It is 0 if no considered sample is out of band.
  - If the last considered sample is out of band, the run did not converge
    (`converged = false`, `convergence_s = null`).
  - Clean scenarios have no onset, so convergence does not apply.
  - On a sensor or actuator scenario the true health stays clean, so the convergence time
    measures how long the fault pulls the estimate out of the band.

### Twin tracking (`score_tracking`)

This answers the first half of research question RQ2: does the twin, updated with the
estimated health, follow the instruments to within sensor noise?

- **Samples.** The scoring window above, with the shared `SteadyStateGate` open and an
  estimate in force, one sample every 10 s.
- **Residuals.** On each sample the `QuasiSteadyTwin` predicts power, exhaust temperature
  and compressor discharge temperature and pressure from the measured inputs, three
  times: with the estimated health, with the true health and with a clean engine.
- **Per channel.** `tracking_rms_*` is the RMS of measured minus predicted with the
  estimate. `tracking_floor_*` is the same with the true health: what measurement noise
  (including input-reading noise pushed through the twin) leaves even with perfect health
  knowledge. `tracking_ratio_*` = rms / floor. `tracking_ratio_max` is the worst channel.
- **Reading it.** A ratio of 1 means the twin tracks to within sensor noise.
  `tracking_clean_ratio_*` (and `_max`) is the same ratio for the clean, un-updated twin,
  which is what a twin without self-calibration would show.
- On a sensor-fault stream the floor includes the sensor fault, so the ratio there says
  how much worse than "perfect health knowledge" the estimate makes the twin, not whether
  it tracks the true plant.

### Detectors (`score_detections`, `score_isolation`)

- **Detection delay.** Time from the onset to the first sample at or after it with the
  alarm on. An alarm still on from before the onset gives a delay of 0, and it also counts
  as a pre-onset false alarm.
- **Missed detection.** No alarm at or after the onset before the end of the run.
- **False alarms.** A false alarm is an alarm onset: a sample with the alarm on that
  follows one with it off, or is on at the first sample. They are counted on the exposure.
  - Exposure is the whole run for clean scenarios, and the samples before the onset for
    fault scenarios.
  - `false_alarms_steady_per_h` counts onsets where the shared `SteadyStateGate` (default
    settings) is open, divided by the gate-open hours. This is the headline rate.
  - `false_alarms_loaded_per_h` does the same over all loaded samples, so alarms during
    load steps and ambient changes count too.
  - `alarm_fraction_steady` is the share of steady exposure with the alarm on. It catches
    one long alarm that the onset count would score as a single event.
  - A detector that signals in pulses (the WP4 detectors reset after each signal) gives
    one false alarm per pulse.
- **Channel** (scored only for sensor faults on the four twin outputs, and only if
  detected). The output `channel` at the first alarm after the onset must equal the faulty
  sensor's twin output (`power_mw`, `exhaust_k`, `cdt_k` or `cdp_kpa`).
- **Label** (scored only for detectors with a `label` attribute, faults with a label, and
  detected runs). The final `label` must equal `FAULT_LABELS` applied to the first fault
  event:
  - a degradation's kind;
  - `power_sensor`, `exhaust_sensor`, `cdt_sensor`, `cdp_sensor` or `fuel_meter` for a
    sensor fault.
  - The slow fuel valve has no label.

### Summary over seeds (`summarize`, `aggregate`)

- **Per scenario.** Each metric is averaged over the five trials, with a 95 % Student t
  interval: mean ± t(0.975, n−1)·sd/√n. t comes from a table up to 30 degrees of freedom
  and a series expansion beyond (no scipy).
- **What `n` counts.** Values that do not apply are left out of `n`: a delay of a missed
  detection, the convergence time of a run that did not converge, and rates with no
  exposure. The counts of detected and converged runs are reported next to them.
- **Width.** With five trials, t = 2.776, so the intervals are wide by design. A metric
  with zero spread over seeds shows ± 0.
- **Pooled false-alarm rate.** Total onsets divided by total steady hours. It is reported
  because the mean of per-seed rates over-weights short exposures.
- **Group rows** (`clean`, `fault`, `category:*`) average runs of different scenarios.
  They are shown without an interval, because their spread mixes scenario differences
  with seed noise.

## How to run

```bash
PYTHONPATH=src python scripts/run_estimation_benchmark.py --list   # registry and status
PYTHONPATH=src python scripts/run_estimation_benchmark.py \
    --estimator oracle --estimator clean --estimator ukf \
    --detector never --detector cusum --detector isolator \
    --out results/benchmark.json --markdown results/benchmark.md
# quick look: two scenarios, first trial, first 40 minutes
PYTHONPATH=src python scripts/run_estimation_benchmark.py --estimator ukf \
    --scenarios 'fouling_step*,category:sensor' --seeds bank --until-s 2400
```

- Scenarios are chosen by id, by glob, or by `category:<name>`. Options can be repeated
  or comma-separated.
- `--generate-only` only fills the cache.
- The JSON results hold the protocol, the git commit, the model fingerprint, every run's
  metrics and the summaries. The Markdown holds one table per entry.

### Registry

| Name | Kind | Target |
| --- | --- | --- |
| `oracle` | estimator | `benchmark:OracleEstimator`: reference only, reads truth |
| `clean` | estimator | `benchmark:CleanEstimator`: always `Health()`, zero std |
| `ukf` | estimator | `turbineiq.estimation.ukf:UKFHealthEstimator` |
| `never` | detector | `benchmark:NeverDetector`: never alarms |
| `residual` | detector | `turbineiq.estimation.detectors:ResidualScreen` |
| `cusum` | detector | `turbineiq.estimation.detectors:CusumDetector` |
| `mewma` | detector | `turbineiq.estimation.detectors:MewmaDetector` |
| `isolator` | detector | `turbineiq.estimation.detectors:PatternIsolator` |
| `ukf_shift` | detector | `turbineiq.estimation.health_detector:HealthShiftDetector` |

- Modules are imported only when a name is used.
- If the target module (or its package) is missing, or it lacks the attribute, the name
  is skipped with a message.
- An import error inside a module that exists is raised, not hidden.
- Any other class can be given as `module:attribute`.
- To register an entry, add one `Entry` line to `REGISTRY`.

## Reference results (full evaluation set)

The run used all 95 evaluation streams, the default settings and commit `aa5f23c`. It
took 209 s wall time with 2 workers, with all streams already cached. `ukf` and `cusum`
were skipped because their modules are not on this branch.

**`oracle`: not an estimator, a check of the metrics.**

- On all 19 scenarios × 5 seeds: RMS and bias 0.00, 2σ coverage 100 %, and convergence
  0 s on the 70 fault runs.

**`clean`: the do-nothing baseline.** It is exact wherever the true health is clean: the
five clean scenarios, the seven sensor scenarios and the slow valve. On those it scores
0.00 error, 100 % coverage and, where an onset exists, convergence 0 s. That is the bar a
real estimator has to match without false deterioration. Elsewhere:

| Scenario | RMS flow (%) | RMS ηc (pt) | RMS ηt (pt) | Bias flow (%) | Bias ηc (pt) | Bias ηt (pt) | 2σ coverage | Converged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fouling_step_part_load` | 2.80 | 1.40 | 0.00 | 2.61 | 1.31 | 0.00 | 12.8 % | 0/5 |
| `fouling_progressive_base_load` | 2.65 | 1.33 | 0.00 | 2.29 | 1.14 | 0.00 | 12.8 % | 0/5 |
| `fouling_progressive_ambient_swing` | 1.77 | 0.88 | 0.00 | 1.53 | 0.76 | 0.00 | 12.8 % | 0/5 |
| `erosion_step_part_load` | 0.00 | 0.00 | 1.40 | 0.00 | 0.00 | 1.31 | 12.8 % | 0/5 |
| `fouling_then_erosion` | 1.84 | 0.92 | 0.80 | 1.69 | 0.84 | 0.63 | 15.5 % | 0/5 |
| `fouled_unit_offline_wash` | 1.11 | 0.55 | 0.00 | 0.41 | 0.20 | 0.00 | 86.4 % | 5/5 (3,897 s) |

- The faults are deterministic, so these values are identical for all seeds (± 0.00).
- The coverage is the pre-onset share of the scoring window.
- The wash run "converges" because the truth is clean again after the wash. The clean
  estimator is in band from the reload at 3,897 s on.

**`never`: the do-nothing detector.**

- Detected 0 of 70 fault runs: every fault run is a missed detection.
- 0 false alarms in 44.9 steady hours on the clean scenarios and 24.2 steady hours before
  onset on the fault scenarios.
- By the rule of three, 0 events in 44.9 h bounds the true rate below about 0.07 per hour
  (95 %), and 69.1 steady hours in all bound it below about 0.04 per hour. That is the
  resolution this set has for false-alarm rates.
- Steady exposure per clean scenario over five seeds: 9.4 h (`clean_part_load`), 9.3 h
  (`clean_base_load`), 8.6 h (`clean_load_cycling`), 8.7 h (`clean_ambient_swing`) and
  8.8 h (`clean_fast_load_steps`). Each fault scenario has about 1.9 h before onset.
- `fouled_unit_offline_wash` has no exposure, because its onset is at t = 0.

## Limits

- **Convergence** is measured from the first fault event to the final state. In
  `fouling_then_erosion` the second event, at 60 min, resets it. In
  `fouled_unit_offline_wash` the final state is the clean, washed engine.
- **The wash scenario.** Its onset is t = 0, so its detection delay includes the start-up:
  the breaker closes at 237 s, the load is set at 300 s, and the steady gate needs a
  further quiet 120 s.
- **Isolation** scoring uses the first fault event only. It assumes the detectors' channel
  and label vocabulary (`SENSOR_CHANNELS`, `FAULT_LABELS`); a change there needs a change
  here.
- **Bank-trace check.** The check on seeded bank traces covers their first 600 s; one
  trace was checked in full.
- **Cache invalidation.** Any code change in `turbineiq.simulation` or
  `turbineiq.engineering` changes every cache key. Regenerating the 95 streams takes
  about 17 minutes with 2 workers.
- **Sample size.** Five trials per scenario give wide t intervals and coarse
  false-alarm-rate resolution (see above). Proportions (detected, converged) are reported
  as counts, without intervals.
