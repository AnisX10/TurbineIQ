# WP4 results: health estimation, detection and forecast

Roadmap WP4 makes the twin follow a degrading plant (levels 1 to 3 on the DNV-RP-A204
scale): it estimates the gas-path health online, detects and names faults, and forecasts
degradation with an uncertainty band. This page collects the results and answers
research question RQ2 as far as the evidence allows:

> **RQ2.** Does online health-parameter estimation keep the twin within sensor-noise
> tracking error under injected compressor fouling and turbine erosion, and does it detect
> degradation earlier than residual and CUSUM screens at an equal false-alarm rate?

**Everything here is simulated.** The plant is the WP2 dynamic model with WP3 fault
injection; nothing is plant data. The twin is built on the same maps as the plant, so the
main results are circular by construction (section 6 covers the twin–plant mismatch).

## 1. What WP4 consists of

| Piece | Code | Write-up |
| --- | --- | --- |
| Observations, quasi-steady twin, steady-state gate | `estimation/data.py`, `twin.py`, `steady.py` | this page |
| Benchmark harness (seeds, stream cache, metrics, runner) | `estimation/benchmark.py`, `scripts/run_estimation_benchmark.py` | `ESTIMATION_BENCHMARK.md` |
| Health estimator (unscented Kalman filter), observability, mismatch study | `estimation/ukf.py`, `observability.py`, `mismatch.py` | `HEALTH_ESTIMATION.md` |
| Residual detectors (screen, CUSUM, MEWMA) and fault-pattern isolator | `estimation/detectors.py` | `FAULT_DETECTION.md` |
| Estimator-based detector (Wald test on the UKF estimate) | `estimation/health_detector.py` | this page |
| Degradation and performance forecast | `estimation/forecast.py` | `DEGRADATION_FORECAST.md` |
| Threshold check on training runs | `scripts/tune_detection_thresholds.py` | this page |

Every estimator and detector sees only `Observation` values: unit state, breaker, load
setpoint, ambient temperature, IGV position and the six instrument readings with their
faults and noise. None of them sees the ground truth.

## 2. How it was evaluated

- **Evaluation set.** The 19 scenarios of the seeded bank (`SCENARIO_BANK.md`), each run
  with five seeds: its bank seed and seed + 10000·k for k = 1..4. That gives 95 runs:
  25 clean, 25 degradation, 5 maintenance, 35 sensor faults and 5 slow-valve runs.
- **Training set.** Seeds 1000 to 1999 only. Every threshold and setting was chosen on
  training runs. No evaluation run was used for any choice.
- **One harness.** All numbers in sections 3 to 5 come from one harness
  (`benchmark.py`), with the same streams, the same metric code and the same counting of
  false alarms for every entry. Means are over the five seeds; ± is a 95 % Student t
  half-width (t = 2.776 for five runs).
- **Recorded output.** `docs/evidence/wp4/benchmark.md` holds the full tables of the run
  behind this page and `benchmark_summary.json` its summaries, model fingerprint and
  commit.

## 3. Does the self-calibrating twin track within sensor noise?

The tracking metric (`score_tracking`) compares the twin's prediction error with the
estimated health against its error with the true health. It uses the four outputs (power,
exhaust temperature, compressor discharge temperature and pressure) on steady samples
after convergence. With the true health, only measurement noise is left, so a ratio of 1
means the twin tracks to within sensor noise. The clean, un-updated twin is shown for
comparison.

| Scenario (5 seeds each) | Clean twin / noise, worst channel | UKF-updated twin / noise, worst channel | Health error RMS: flow (%) / ηc (pt) / ηt (pt) |
| --- | --- | --- | --- |
| 3 % fouling step, 35 MW | 10.0 (discharge pressure) | 1.00 | 0.02 / 0.01 / 0.01 |
| Fouling ramp 3 %/h, base load | 9.4 | 1.02 | 0.05 / 0.02 / 0.02 |
| Fouling ramp 2 %/h, ambient steps | 6.3 | 1.01 | 0.04 / 0.02 / 0.02 |
| 1.5 pt erosion step | 4.8 (power) | 1.01 | 0.02 / 0.01 / 0.01 |
| Fouling, then erosion | 7.3 | 1.01 | 0.02 / 0.01 / 0.01 |
| Fouled unit, offline wash | 4.0 | 1.01 | 0.02 / 0.01 / 0.01 |
| Five clean scenarios | 1.0 | 1.00 to 1.01 | 0.02 / 0.01 / 0.01 |

**Answer, first half of RQ2: yes, with an exact twin.** The updated twin's error is at
most 2 % above the noise floor in every degradation scenario. The clean twin is 4 to 10
times above it. After a step the estimate is inside a ±0.5 % / ±0.5 pt band for good
within 144 ± 6 s (fouling) and 142 ± 1 s (erosion).

**What this does not show:**

- **The result is circular.** The twin and the plant share their maps. With a plausibly
  mis-calibrated twin the absolute health is off by up to 0.6 % flow capacity, 0.2 point
  ηc and 0.5 point ηt, or 0.33 point ηc for a 1 kPa barometric error. The change since a
  healthy baseline stays within 0.05 % / 0.02 pt (section 6).
- **During ramps the stated uncertainty is too small.** In the 3 %/h base-load ramp the 2σ
  band covers the truth only 69 % of the time, because the estimate lags the ramp by a few
  hundredths of a point. In steady scenarios coverage is about 98 %.
- **The estimator absorbs sensor faults.** It cannot tell a biased reading from a health
  change. It fits the faulty channel and mispredicts the others:

  | Sensor fault | Health error (ηt) |
  | --- | --- |
  | Stuck exhaust thermocouple | 6.9 points |
  | +1 MW power transducer bias | 0.75 point |
  | −35 kPa discharge-pressure bias | −2.3 % flow capacity |

  A self-calibrating twin therefore needs the sensor-fault isolation of section 4 in
  front of it. Otherwise it "calibrates" itself onto a broken instrument.

## 4. Does estimation detect degradation earlier, at an equal false-alarm rate?

### 4.1 Setting every detector to the same rate

The design rate is one false alarm per 100 steady hours (0.01 per hour) for every
detector. Each was set on the same healthy training data: the five clean scenarios with
seeds 1000 to 1019, which is 100 runs and 179.5 steady hours.

- **Residual screen, CUSUM and MEWMA.** These work on clean-twin residuals. Each threshold
  was set by bootstrap resampling of the standardised healthy residuals (40,000 simulated
  hours). The design (window, slack, smoothing) is the one with the shortest delay on
  synthetic fouling and erosion signatures. See `FAULT_DETECTION.md`.
- **Estimator-based detector (`ukf_shift`).** It runs the UKF and computes the Wald
  statistic d² = x′P⁻¹x of the estimate against the clean engine after each 10 s update.
  It alarms when d² stays above the threshold for 3 consecutive updates. On the training
  runs the alarm rate was:

  | Threshold | Alarm rate (per steady hour) |
  | --- | --- |
  | 6.0 | 0.37 |
  | 7.0 | 0.10 |
  | 8.0 | 0.017 |
  | 8.5 | 0 |

  A log-linear fit to the tail puts 0.01 per hour at 8.4, so the threshold is 8.5.
  - That is an extrapolation from three events. The UKF is too slow to bootstrap the way
    the residual detectors were.
  - Persistence (consecutive updates) barely matters for delay. At each value's own
    0.01-per-hour threshold (13.9 for 1 update, 10.4 for 2, 8.4 for 3, 7.4 for 4, 7.0
    for 5), the mean delay on the training-seed fouling ramps (seeds 1000 to 1002 of the
    two ramp scenarios) was 116, 118, 123, 126 and 136 s.
  - 3 was kept as a guard against a single bad 10 s batch. The healthy training runs
    contain no such batch, so they do not test that choice.
- `scripts/tune_detection_thresholds.py` reproduces both procedures from the training
  runs (section 7).

**Measured false alarms on the evaluation runs.** These are 44.9 steady hours in the clean
scenarios plus 24.2 steady hours before onset in the fault scenarios.

| Detector | False alarms |
| --- | --- |
| Screen | 0 |
| CUSUM | 0 |
| UKF Wald test | 0 |
| MEWMA | 1, in `clean_ambient_swing` (0.02 per hour over the clean runs) |

Zero events in 69 hours only bounds a rate below about 0.04 per hour (rule of three). This
set cannot show that the four rates are equal. It shows that none is far above the design
rate.

### 4.2 Detection delay

Seconds from the ground-truth onset to the first alarm. Means over five seeds, with 95 %
t half-widths. Every fault below was detected in 5 of 5 runs by every detector.

| Scenario | Residual screen | CUSUM | MEWMA | UKF Wald test |
| --- | --- | --- | --- | --- |
| 3 % fouling step | 142 ± 1 | 135 ± 1 | **2 ± 0** | 148 ± 1 |
| Fouling ramp 3 %/h, base load | 229 ± 32 | 184 ± 28 | **114 ± 20** | **114 ± 20** |
| Fouling ramp 2 %/h, ambient steps | 295 ± 24 | 253 ± 26 | **148 ± 16** | **156 ± 34** |
| 1.5 pt erosion step | 149 ± 5 | 135 ± 2 | **3 ± 1** | 152 ± 1 |
| Fouling, then erosion | 141 ± 1 | 129 ± 1 | **27 ± 67** | 143 ± 0 |
| Fouled from t = 0, offline wash | 469 ± 0 | 469 ± 0 | **461 ± 0** | 489 ± 0 |
| Mean over the 25 degradation runs | 191 | 167 | **59** | 143 |

- **Steps.** A step in exhaust temperature closes the steady-state gate for about two
  minutes. The screen, CUSUM and UKF all wait for it to reopen; the UKF also waits for
  three 10 s updates, so it is 2 to 17 s behind the screen and CUSUM. The MEWMA fires on the first one to three samples after the step,
  before the gate's 120 s window registers the jump. That is a real advantage of a
  per-sample multivariate statistic, but it depends on the gate's latency.
- **Ramps (the realistic case).** The UKF test is 70 to 139 s (38 to 50 %) earlier than
  the screen and CUSUM. It matches the MEWMA within the seed spread. That fits the method:
  the Wald test on a filtered health estimate and the MEWMA on whitened residuals both
  pool all four channels with their correlation. The screen and CUSUM test each channel
  alone.
- **The wash scenario** is fouled from t = 0, so its delay is mostly start-up. All four
  detectors wait for the first steady window after loading.

**Answer, second half of RQ2: partly.** At the same design false-alarm rate, the
estimator-based test detects gradual degradation earlier than the univariate residual
screen and CUSUM, by 38 to 50 %. It detects steps about as fast as they do, 2 to 17 s
later. It is not earlier than a multivariate residual chart (MEWMA): equal on ramps
and slower on steps. So the gain comes from using all channels together, which a
residual chart can also do, not from the estimation as such. What estimation adds is
section 4.3.

### 4.3 Naming the fault

| Detector | Degradation runs named correctly | Sensor-fault runs named correctly |
| --- | --- | --- |
| UKF Wald test | 25/25, plus 4/5 wash runs | 0/31 |
| Pattern isolator (CUSUM signs across channels) | 25/25, plus 5/5 wash runs | 30/30 |

- **The UKF Wald test** names fouling or erosion from which health parameter moved. It
  also gives the size directly, which no residual detector does.
  - It calls every detected sensor fault a degradation. That is the absorption described
    in section 3.
  - In one wash run the estimate overshot past clean after the restart that follows the
    wash. That raised a second alarm, labelled "unexplained", at 4,440 s. It is not
    counted as a false alarm, because it comes after the onset.
- **The pattern isolator** uses the twin's signatures (`FAULT_DETECTION.md`). It tells
  every look-alike sensor fault apart from fouling, because fouling moves all four
  channels and a sensor moves one. Its label arrives 5 to 17 minutes after onset.
- **Missed by everything:**
  - The slow fuel valve: it only shows in transients, and the gate removes them.
  - The 3 K exhaust-thermocouple noise: it keeps the gate shut, so nothing is examined.
    The MEWMA and the UKF test each caught it in 1 of 5 runs.

**Implication for the twin.** The isolator and the estimator do different jobs. A
deployable self-calibrating twin should use both: the residual isolator decides whether a
deviation is a sensor or the machine, and the estimator only updates health when it is
the machine. This combination is not built yet.

## 5. Forecast from the estimator's output

The forecaster (`DEGRADATION_FORECAST.md`) was built and tuned on synthetic estimates.
Here it is fed the UKF's own estimates.

**Training check.** First on training seeds 1000 to 1002, with 18 settings plus 2 wider
ones (rate-walk scale, rate-reopening threshold, persistent term).

- With the defaults, forecasts in stable periods over-cover: 100 % for a 90 % band.
- Coverage soon after a fault onset rises only with wider bands. Doubling the rate walk
  lifts the 60-minute coverage from 0.81 to 0.88, but widens every band by about 1.4 times.
- Several settings come within one or two points of 90 % at 30 minutes; none reaches it at
  60 minutes without the wider bands. The defaults were kept, because re-tuning would
  change little.

**Evaluation runs.** Three scenarios × five seeds, forecasts every 5 minutes. 90 % band
coverage and mean absolute error in percent or points, leaving out forecasts whose
horizon contains a new fault event:

| Horizon | Flow capacity: coverage / MAE | ηc: coverage / MAE | MAE of "no change" (persistence), flow / ηc |
| --- | --- | --- | --- |
| 30 min | 0.89 ± 0.05 / 0.20 | 0.89 ± 0.04 / 0.09 | 0.89 / 0.44 |
| 60 min | 0.80 ± 0.08 / 0.65 | 0.80 ± 0.08 / 0.30 | 1.87 / 0.94 |

- **Stable periods:** coverage 0.99 to 1.00; the 30-minute MAE is 0.06 % flow and 0.02
  point ηc.
- **10 to 30 minutes after an onset:** coverage 0.85 to 0.88.
- **0 to 10 minutes after an onset:** 0.45 to 0.50. A trend needs data to learn a new
  rate.
- **Available power at base load** (fouling ramp, through the twin): MAE 0.24 MW at 30
  minutes and 0.78 MW at 60 minutes, with 90 % band coverage of 0.85 and 0.71.

So the band is close to nominal at 30 minutes, too narrow at 60 minutes after a change of
rate, and too wide when nothing changes. A band that widens after a detected rate change
and narrows otherwise would fix both. It is listed as open work.

## 6. Twin–plant mismatch

`HEALTH_ESTIMATION.md` runs the filter with the twin built on deliberately mis-calibrated
maps. A set of combined calibration errors leaves an absolute bias of +0.56 % flow,
+0.17 pt ηc and +0.44 pt ηt, and a 1 kPa barometric error +1.07 % / +0.33 pt / −0.39 pt.
The change since a healthy baseline is right to within 0.05 % / 0.02 pt / 0.03 pt.

Two consequences for the results above:

- **Tracking.** The tracking result of section 3 holds for a *relative* twin, one
  re-baselined on a known healthy state. It does not hold for absolute health.
- **Detection.** All detectors here test against the clean engine. With a mis-calibrated
  twin each would start with an offset. For the UKF test, the combined case alone puts the
  flow-capacity estimate about 17 of its standard deviations from clean, far above the
  threshold. The residual detectors would see constant residual offsets. All of them would
  need a commissioning baseline, and re-tuning on residuals from the mismatched twin. The
  detection comparison under mismatch has not been run.

## 7. Threshold check on all training runs

`scripts/tune_detection_thresholds.py` was run on the final code over the full training
set: 5 clean scenarios × seeds 1000–1019, 100 runs, 179.5 steady hours. It took 42 minutes
on the shared 4-CPU container, of which about 20 were spent generating the streams.

- **Noise model.** Refitting it reproduces the committed `TUNED_NOISE` to its rounding.
- **Residual detectors.** Bootstrap signal rate at the default thresholds, over 40,000
  simulated hours, and signals on the 100 training runs themselves:

  | Detector | Bootstrap rate (per steady hour) | Signals on the training runs |
  | --- | --- | --- |
  | Screen | 0.0086 | 0 |
  | CUSUM | 0.0102 | 0 |
  | MEWMA | 0.0098 | 5 |

  The MEWMA's five signals are one noise event that repeats in all five clean scenarios
  with seed 1013, because runs with the same seed share their noise (section 8).
- **UKF Wald test.** The alarm-onset curve is the one in section 4.1. The tail fit gives a
  threshold of 8.42 for 0.01 per hour, against the default of 8.5, with 0 onsets at the
  default.
- The output is recorded in `docs/evidence/wp4/tuning.json`.

## 8. Limits

- **Circular validation.** The plant and twin share structure and, in sections 3 to 5,
  parameters.
- **Accelerated degradation.** Percent per hour, not per month, with white 1 Hz noise.
  Absolute delays and forecast errors are optimistic. The ranking could change with slow,
  coloured drifts.
- **False-alarm resolution.** 69 evaluation hours cannot separate rates of 0.01 and 0.04
  per hour.
  - The training runs that share a seed share their noise sequence across the five clean
    scenarios. So the 100 training runs hold 20 independent noise sequences, not 100,
    which weakens the training-side rate estimates.
- **Single faults.** Neither the isolator nor the UKF test reports the erosion that
  follows fouling.
- **Gate blind spots.** Nothing is learned during transients. A noisy thermocouple can
  keep the gate shut indefinitely and silently.
- **No barometric input.** It is the largest single source of absolute bias (section 6).

## 9. Reproducing

```bash
# Benchmark (fills data/estimation/cache/ first; about 20 min to generate, then ~10 min)
PYTHONPATH=src python scripts/run_estimation_benchmark.py \
    --estimator oracle --estimator clean --estimator ukf \
    --detector never --detector residual --detector cusum --detector mewma \
    --detector isolator --detector ukf_shift \
    --out benchmark.json --markdown benchmark.md
# Thresholds from training runs only
PYTHONPATH=src python scripts/tune_detection_thresholds.py --out tuning.json
# Forecast from UKF estimates (uses the benchmark cache)
PYTHONPATH=src python -m turbineiq.estimation.forecast --seeds evaluation --estimates ukf \
    --cache-dir data/estimation/cache --performance-replicates 1
```

## 10. Open work after WP4

1. **Barometric input.** Add `ambient_pressure_kpa` to the observation, with a matching
   session input and plant effect. This needs regenerated bank traces, because it changes
   the plant.
2. **Isolate, then estimate.** Gate the UKF update on the isolator's verdict, so that sensor
   faults do not corrupt the health estimate.
3. **Commissioning baseline.** Test change against a recorded healthy baseline, and re-run
   the detection comparison with a mismatched twin.
4. **Forecast band.** Widen it after a detected rate change and narrow it otherwise.
5. **Gate diagnostics.** Report why the gate is closed, and flag long closures while the
   inputs are steady (the noisy-thermocouple blind spot).
