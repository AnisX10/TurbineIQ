# Baseline fault detection (WP4)

Research question RQ2 asks whether the health estimator detects degradation earlier than
residual and CUSUM screens *at an equal false-alarm rate*. This document describes those
screens, how they were tuned, and how they perform on the scenario bank
(`docs/SCENARIO_BANK.md`). Everything here is simulated; no number is a property of a
real 6B.03.

- Code: `src/turbineiq/estimation/detectors.py`. Tests: `tests/test_estimation_detectors.py`.
- Registry names (harness): `ResidualScreen`, `CusumDetector`, `MewmaDetector`,
  `PatternIsolator`, all with no-argument constructors and the tuned defaults.

## What the detectors see

Each detector reads only `Observation` objects. At every sample it advances a
`SteadyStateGate` (default settings: 120 s window, power spread ≤ 0.25 MW, exhaust spread
≤ 1.5 K, unchanged setpoint, IGV and ambient). While the gate is open it forms the
residual of the four instrumented outputs against the `QuasiSteadyTwin` prediction for a
**clean** engine at the measured speed, fuel flow, IGV and ambient:

    r = (power, exhaust T, CDT, CDP)_measured − twin(CLEAN, obs)

and standardises it with a noise model fitted to healthy runs (below). While the gate is
closed a detector holds its state and cannot signal. When the unit leaves the loaded state
(shutdown or trip) the detector's memory is cleared, because a wash or repair can happen
while it is down.

`update(obs)` returns `DetectorOutput(t_s, alarm, statistic, channel)` for every
observation. `alarm` is True on the sample at which the detector **signals**; the
channel(s) that signalled then restart from zero (a renewal). A fault that persists
therefore gives a train of pulses, and the false-alarm rate is simply signals per hour.
`channel` is the residual channel that signalled (`power_mw`, `exhaust_k`, `cdt_k`,
`cdp_kpa`), the leading channel otherwise, and `None` while the gate is closed.

### Healthy residuals (tuning seeds)

On 646,039 steady samples (179.5 h) of the five clean scenarios with seeds 1000–1019 the
residuals have near-zero median (power 0.001 MW, exhaust −0.014 K, CDT −0.003 K,
CDP 0.011 kPa) and a lag-one autocorrelation below 0.02 on every channel. The fuel-flow
meter's 0.5 % noise enters the twin as an input, so it dominates the power and exhaust
residuals and moves them together (correlation 0.896); CDT and CDP do not depend on fuel
in the twin and correlate 0.38 with each other through the speed reading. The spread of
the power and exhaust residuals grows with fuel flow, so the noise model scale is

| Channel | Scale model (σ) | σ at 35 MW (2.17 kg/s) | σ at the temperature limit (2.76 kg/s) |
| --- | --- | --- | --- |
| Power | 0.0151 + 0.0948·fuel MW | 0.221 MW | 0.277 MW |
| Exhaust T | 0.386 + 0.723·fuel K | 1.95 K | 2.38 K |
| CDT | 0.612 K | 0.61 K | 0.61 K |
| CDP | 3.39 + 0.010·fuel kPa | 3.42 kPa | 3.42 kPa |

The scale is fitted by weighted least squares through robust scales (1.4826 × median
absolute deviation) in bins of the *operating* fuel flow, the mean over each steady
segment. Binning on the measured fuel itself would select its noise and halve the
apparent power and exhaust spread (by a factor of about two in narrow bins). Standardised with this model, the tuning residuals have
a standard deviation between 0.996 and 1.002 on each channel.

A caution for anyone else tuning on these seeds: the five clean scenarios run with the
same seed share one measurement-noise sequence (the standardised residuals of
`clean_part_load@1013` and `clean_base_load@1013` correlate 1.00 sample for sample). The
100 tuning runs are therefore 20 independent noise sequences, each replayed under five
operating profiles. The bank seeds and the evaluation seeds are distinct per scenario, so
the evaluation runs do not share noise.

### Residual signatures

Residual shifts at constant load from the twin (noise-free), in physical units and in σ at
35 MW:

| Cause | Power | Exhaust T | CDT | CDP |
| --- | --- | --- | --- | --- |
| 1 % compressor fouling, 35 MW | −0.27 MW (−1.2σ) | +6.1 K (+3.1σ) | +1.15 K (+1.9σ) | −11.8 kPa (−3.5σ) |
| 1 % fouling on the temperature limit | −0.32 MW | +7.0 K | +1.15 K | −11.8 kPa |
| 1 pt turbine erosion, 35 MW | −0.75 MW (−3.4σ) | +4.9 K (+2.5σ) | 0 | 0 |
| Fuel meter reading 1 % high, 35 MW | −0.42 MW (−1.9σ) | −3.7 K (−1.9σ) | 0 | 0 |
| Power transducer +1 MW | +1 MW (+4.5σ) | 0 | 0 | 0 |
| CDT sensor +3.5 K | 0 | 0 | +3.5 K (+5.7σ) | 0 |
| CDP sensor −35 kPa | 0 | 0 | 0 | −35 kPa (−10σ) |

The exhaust residual of fouling is smaller than the true exhaust rise (+6.1 K against
+8.5 K per percent) because the clean twin is evaluated at the higher measured fuel flow.
Fouling and erosion move power and exhaust in *opposite* directions, against the
fuel-noise correlation; that is why a statistic that knows the correlation does so much
better than per-channel ones.

## The three detectors

**Residual screen** (`ResidualScreen`). Per channel, the mean of the last `window`
standardised steady residuals, scaled by √n so that it is unit-normal when healthy. The
channel signals when this mean stays beyond ±`threshold` on one side for `persistence`
consecutive steady samples. This generalises the project's existing robust-z screen
(`analytics.quality.detect_anomalies`, median and MAD over the whole frame), which is not
causal and has no smoothing or persistence.

**Per-channel CUSUM** (`CusumDetector`). Two one-sided CUSUMs (Page, 1954) per channel on
the standardised residual clipped to ±4σ: `S⁺ ← max(0, S⁺ + z − k)`,
`S⁻ ← max(0, S⁻ − z − k)`, signal when either reaches `h`. This ports
`analytics.quality.detect_drift` from the earlier drift-detection branch (commit 38a7a5a):
same recursion and the same clipping, so that one spike cannot trigger it. Two changes: the
reference level is the clean twin rather than the median of a warm-up segment of the same
run (a warm-up baseline absorbs a fault present from the start, such as
`fouled_unit_offline_wash`), and the noise scale comes from the healthy tuning runs rather
than from successive differences in the warm-up. The ported defaults (k = 1, h = 10, set
for 96-sample synthetic frames) would give far more than one false alarm per 100 h at 1 Hz,
so k and h were retuned.

**MEWMA** (`MewmaDetector`, optional multivariate statistic). The standardised residual
vector is whitened with the Cholesky factor of the healthy correlation matrix, smoothed
with an EWMA of weight λ, and `T² = |e|² (2 − λ)/λ` (asymptotically χ² with four degrees of
freedom when healthy) is compared with a limit (Lowry et al., 1992). `channel` names the
channel whose own standardised EWMA is largest; the statistic is not tied to one channel.

## Tuning protocol (healthy seeds 1000–1019 only)

Target: **0.01 signals per steady hour** (one false alarm per 100 h of gate-open
operation), the same for every detector.

1. Run the five clean scenarios with seeds 1000–1019 (100 runs, 179.5 steady hours) and fit
   the noise model to their steady residuals.
2. For each candidate design, set the threshold for the target rate by simulation: many
   independent chains fed with rows drawn with replacement from the standardised tuning
   residuals (`bootstrap_signal_rate`). Row resampling keeps the cross-channel correlation
   and the shape of the healthy distribution; it assumes no serial correlation, which the
   lag-one autocorrelation (< 0.02) supports. 4,000 simulated hours per grid point, then
   40,000 hours for the chosen designs.
3. Choose the design by detection delay on **synthetic** faults: the residual signatures
   of 0.5 % fouling and 0.5 pt erosion steps and of 1 %/h fouling and 1 pt/h erosion ramps
   (from the twin, at 35 MW) added to the same bootstrap rows after a 600 s healthy
   burn-in, 400 chains each. The criterion is the mean delay over the four cases, which
   the ramps dominate: real step faults also wait about two minutes for the gate, so a few
   seconds on a step do not matter. The sensor faults played no part in the choice.
4. Check the chosen thresholds on the actual tuning runs (with their transients and gate
   gaps). No evaluation run was used for any choice.

Grid (threshold for 0.01/h on 4,000 bootstrap hours; mean delays in seconds):

| Detector | Design | Threshold | Foul step 0.5 % | Foul ramp 1 %/h | Erosion step 0.5 pt | Erosion ramp 1 pt/h | Mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CUSUM | k = 0.1 | 53.0 | 29 | 376 | 30 | 385 | 205 |
| CUSUM | **k = 0.15** | 38.0 | 22 | 365 | 23 | 377 | **197** |
| CUSUM | k = 0.25 | 24.7 | 15 | 393 | 16 | 408 | 208 |
| CUSUM | k = 0.5 | 12.8 | 10 | 521 | 10 | 551 | 273 |
| CUSUM | k = 1.0 | 6.5 | 8 | 801 | 9 | 855 | 418 |
| CUSUM | k = 1.5 | 4.2 | 12 | 1074 | 15 | 1140 | 560 |
| MEWMA | λ = 0.005 | 25.3 | 9 | 203 | 8 | 179 | 100 |
| MEWMA | **λ = 0.01** | 27.0 | 7 | 194 | 6 | 169 | **94** |
| MEWMA | λ = 0.02 | 28.7 | 5 | 200 | 4 | 172 | 95 |
| MEWMA | λ = 0.05 | 29.6 | 4 | 236 | 3 | 195 | 109 |
| MEWMA | λ = 0.2 | 30.6 | 2 | 364 | 2 | 295 | 166 |
| Screen | window 1, persistence 1 | 4.63 | 279 | 1629 | 561 | 1826 | 1074 |
| Screen | window 1, persistence 10 | 0.73 | 21 | 1013 | 26 | 1073 | 533 |
| Screen | window 10, persistence 10 | 3.16 | 15 | 697 | 15 | 752 | 370 |
| Screen | window 60, persistence 10 | 4.17 | 26 | 471 | 27 | 493 | 254 |
| Screen | window 120, persistence 10 | 4.32 | 35 | 412 | 35 | 432 | 228 |
| Screen | **window 300, persistence 10** | 4.36 | 49 | 396 | 50 | 406 | **225** |
| Screen | window 300, persistence 30 | 3.99 | 65 | 398 | 66 | 408 | 234 |
| Screen | window 600, persistence 10 | 4.40 | 66 | 460 | 68 | 467 | 265 |
| Screen | window 1200, persistence 10 | 4.24 | 66 | 521 | 69 | 535 | 298 |

The full screen grid was windows {1, 10, 30, 60, 120, 300, 600, 1200} × persistence
{1, 10, 30} (window 1 with persistence 30 was not run; persistence 5 was run for window 1);
the rows left out are all slower than the chosen design. The best CUSUM slack (0.15σ) is
well below the textbook 0.5σ because the faults that take longest to catch are slow ramps.

Final defaults, with the rate on 40,000 bootstrap hours and on the 100 tuning runs:

| Detector | Parameters | Threshold | Bootstrap rate | Tuning runs (179.5 steady h) |
| --- | --- | --- | --- | --- |
| `ResidualScreen` | window 300, persistence 10 | 4.39 | 0.0100 /h (398 signals) | 0 signals |
| `CusumDetector` | k = 0.15, clip ±4σ | 38.0 | 0.0100 /h (398 signals) | 0 signals |
| `MewmaDetector` | λ = 0.01 | 27.2 | 0.0099 /h (395 signals at 27.19) | 5 signals, one event |

The five MEWMA signals on the tuning runs are one noise event: all five clean scenarios of
seed 1013 signal at t = 1284 s, where the 300 s mean of the CDT and CDP residuals is
−0.21σ and −0.17σ (−3.6 and −3.0 standard errors of that mean). It counts as one event in
about 36 independent noise hours (see the caution above), which is unusual but not
implausible at 0.01/h (probability of one or more about 0.3).

## Evaluation (bank seeds and seed + 10000·k, k = 1–4)

Every scenario of the bank was run with five seeds: its bank seed and the bank seed plus
10,000, 20,000, 30,000 and 40,000 (95 runs). The bank-seed runs are the committed traces.
Detectors ran through their public `update(obs)`; ground truth was used only for scoring.
A signal counts as a false alarm when no fault is active at that sample (clean runs, the
part of fault runs before onset, and after the wash in `fouled_unit_offline_wash`). The
detection delay runs from the first fault event to the first signal at or after it while a
fault is active; a run without one is a miss.

### False alarms

| Data | Healthy steady hours | Screen | CUSUM | MEWMA |
| --- | --- | --- | --- | --- |
| Five clean scenarios × 5 seeds | 44.9 h (48.4 loaded h) | 0 | 0 | 1 (`clean_ambient_swing`, seed 20104, t = 5413 s, exhaust low) |
| All healthy steady time (clean runs, pre-onset, post-wash) | 75.9 h (83.7 loaded h) | 0 | 0 | 1 |
| Rate, all healthy time (95 % Poisson interval) | | 0 /h (0–0.049) | 0 /h (0–0.049) | 0.013 /h (0.0003–0.073) |

76 hours cannot confirm a rate of 0.01/h (about 0.8 false alarms are expected per
detector); they show that none of the detectors is far above it on the evaluation
profiles, including load cycling, fast load steps, base load and ambient steps. The
calibration itself rests on the bootstrap.

A first evaluation without the reset on shutdown gave the screen 285 false alarms (and the
MEWMA one) after the wash in `fouled_unit_offline_wash`: its 300-sample window carried the
fouled residuals from before the stop into the washed restart. The reset fixed this; every
other number was unchanged.

### Detection delay and misses

Delay in seconds after the first fault event, median (min–max) over the five seeds, with
the channel that signalled first (count of seeds):

| Scenario | Screen | CUSUM | MEWMA |
| --- | --- | --- | --- |
| `fouling_step_part_load` (3 %) | 141 (140–143); CDP− 3, CDT+ 2 | 134 (133–135); exhaust+ 4, CDT+ 1 | 1 (1–1); CDP− 3, CDT+ 2 |
| `fouling_progressive_base_load` (3 %/h) | 231 (198–265); CDP− 4 | 187 (155–211); CDP− 4 | 108 (99–135); CDP− 3 |
| `fouling_progressive_ambient_swing` (2 %/h) | 292 (269–316); CDP− 4 | 251 (221–277); exhaust+ 4 | 147 (134–162); CDT+ 2 |
| `erosion_step_part_load` (1.5 pt) | 148 (144–154); power− 4 | 134 (133–136); power− 4 | 2 (1–3); power− 4 |
| `fouling_then_erosion` | 140 (139–141); CDP− 5 | 128 (127–129); CDP− 3 | 2 (1–123); CDP− 2 |
| `fouled_unit_offline_wash` (fouled from t = 0) | 468 (468–468); CDP− 4 | 468 (468–468); exhaust+ 5 | 460 (460–460); CDP− 5 |
| `exhaust_tc_drift_base_load` (−10 K/h) | 363 (298–461); exhaust− 5 | 352 (268–425); exhaust− 5 | 212 (172–267); exhaust− 5 |
| `exhaust_tc_stuck_load_increase` | 740 (740–741); exhaust− 5 | 739 (737–739); exhaust− 5 | 730 (730–730); exhaust− 5 |
| `exhaust_tc_noise` (3 K) | **missed 5/5** | **missed 5/5** | 1/5 detected (30 s); missed 4/5 |
| `power_transducer_bias` (+1 MW) | 131 (128–134); power+ 5 | 116 (113–116); power+ 5 | 3 (1–4); power+ 5 |
| `fuel_meter_drift` (+3 %/h) | 306 (247–366); exhaust− 4 | 285 (212–357); exhaust− 3, power− 2 | 286 (208–353); power− 3 |
| `cdt_sensor_bias` (+3.5 K) | 23 (21–26); CDT+ 5 | 9 (7–10); CDT+ 5 | 6 (5–7); CDT+ 5 |
| `cdp_sensor_bias` (−35 kPa) | 15 (15–16); CDP− 5 | 9 (8–9); CDP− 5 | 3 (2–3); CDP− 5 |
| `slow_fuel_valve_load_steps` | **missed 5/5** | **missed 5/5** | **missed 5/5** |

What drives these numbers:

- **The gate sets the floor for step faults that move power or exhaust.** A fouling or
  erosion step raises the exhaust within seconds, the gate shuts and reopens about two
  minutes later; the screen and CUSUM signal in the first few samples after that
  (128–148 s). The MEWMA usually fires on the first one to three samples after the step,
  before the gate's spread test has noticed it, because the CDP drop or the
  power/exhaust pattern is many standard deviations in one sample once the correlation is
  known. The same happens for the +1 MW power transducer step. Faults that do not move
  power or exhaust (CDT and CDP sensor biases) leave the gate open and are caught in
  2–26 s.
- **Ramps** are where the detectors differ: the MEWMA detects progressive fouling in
  about 100–150 s, roughly 40 % sooner than the per-channel CUSUM and half the screen's
  delay. For the fuel-meter drift all three are similar (about 290 s), because that
  signature moves power and exhaust together, along the fuel-noise direction that the
  whitening down-weights.
- `fouled_unit_offline_wash` is fouled from t = 0; the unit loads at 300 s and the gate
  first opens at about 460 s, so all three signal at the first steady samples.
- `exhaust_tc_stuck_load_increase`: while the load is unchanged, a stuck reading differs
  from the truth only by noise and is not detected; after the load is raised at 2400 s the
  gate reopens at about 2530 s and all detectors signal at once (exhaust far below the
  twin).
- **Misses.** The slow fuel valve has no steady-state effect, and the gate removes the
  transients in which it shows, so no steady-state screen can see it. The 3 K exhaust
  noise keeps the exhaust spread above the gate's 1.5 K limit, so the gate stays shut
  (at most 36 steady seconds after onset per run) and the detectors never look; the one
  MEWMA detection came 30 s after onset, while the gate window still held mostly
  pre-fault samples. A screen of this kind would need a separate check on the gate
  being shut for a long time at constant inputs.

### Isolation: can the look-alike faults be told apart?

Yes, on this bank, with a simple rule on the channel pattern. `PatternIsolator` records,
for 300 s of steady time after a detector's first signal, which channels signal and with
which sign, and then applies `classify_pattern`:

1. CDP low together with exhaust or CDT high → `compressor_fouling`;
2. exhaust high and power low with CDT and CDP quiet → `turbine_erosion`;
3. power and exhaust both low (or both high) with CDT and CDP quiet → `fuel_meter`;
4. a single channel alone → that sensor (`power_sensor`, `exhaust_sensor`, `cdt_sensor`,
   `cdp_sensor`);
5. anything else → `unknown`.

The rule follows the signature table above; it was written from the twin's signatures,
not fitted to the evaluation runs. Results on the evaluation seeds (label after the
300 s window):

| Scenario | Expected | CUSUM-based | Screen-based | CUSUM pattern (all seeds) |
| --- | --- | --- | --- | --- |
| Fouling (step, two ramps, then erosion, wash) | compressor_fouling | 25/25 | 25/25 | CDP−, CDT+, exhaust+, power− (24/25; one ramp without power−) |
| `erosion_step_part_load` | turbine_erosion | 5/5 | 5/5 | exhaust+, power− |
| `fuel_meter_drift` | fuel_meter | 5/5 | 5/5 | exhaust−, power− |
| `exhaust_tc_drift_base_load`, `exhaust_tc_stuck_load_increase` | exhaust_sensor | 10/10 | 10/10 | exhaust− |
| `power_transducer_bias` | power_sensor | 5/5 | 5/5 | power+ |
| `cdt_sensor_bias` | cdt_sensor | 5/5 | 5/5 | CDT+ |
| `cdp_sensor_bias` | cdp_sensor | 5/5 | 5/5 | CDP− |
| `exhaust_tc_noise`, `slow_fuel_valve_load_steps` | | not detected | not detected | |

The CDT and CDP biases that each copy one channel of the 3 % fouling signature are not
called fouling, because fouling moves all four channels at once and a sensor moves one.
The label comes 300 s of steady time after the first signal: 307–1039 s after onset
(median 309 s for the CDT/CDP biases, 434 s for the fouling step, 487 and 551 s for the
fouling ramps, 1039 s for the stuck thermocouple, which is first seen after the load change). The MEWMA's `channel` is only the leading
channel and is not used for isolation.

## Limits

- **Single faults, one twin.** The rule assumes one fault at a time; `fouling_then_erosion`
  is labelled fouling and the later erosion is not reported. A sensor fault on a channel
  that fouling also moves, occurring together with fouling, would be absorbed. The twin is
  built on the same maps as the plant, so there is no model mismatch; with a mismatched
  twin the healthy residuals would carry operating-point-dependent biases, and the small
  CUSUM slack (0.15σ) and long screen window that won here would be the first to suffer.
  The thresholds must then be re-tuned on residuals from the mismatched twin.
- **Accelerated faults and 1 Hz white noise.** The delays above are seconds to minutes
  because the bank's ramps are percent per hour and the residual noise is white at 1 Hz;
  with realistic degradation rates (percent per month) and coloured noise (ambient,
  fouling-independent drifts) the ranking may change.
- **Gate effects.** Detection is blind during transients; step delays include one gate
  window; the exhaust-noise fault and the slow valve are missed by construction.
- **Small evaluation set for false alarms.** 76 healthy steady hours cannot resolve
  0.01/h; the bootstrap calibration assumes no serial correlation, which holds here.
- **Equal false-alarm rate.** All three were tuned to 0.01 signals per steady hour on the
  same data, as the comparison with the estimator requires; the estimator's own threshold
  should be set the same way (same seeds, same target, same counting of signals).

## Reproducing

`NoiseModel.fit(*healthy_residuals(streams))` refits the noise model from healthy
observation streams, and `bootstrap_signal_rate(make_core, z_rows, hours)` gives the
signal rate of a detector core (`ScreenCore`, `CusumCore`, `MewmaCore`, which accept a
batch shape) on resampled standardised residuals; bisecting the threshold on it reproduces
the defaults. The tuning and evaluation drivers used for this document were scratch
scripts and are not committed; the numbers above are from those runs (the bootstrap
numbers vary by a few percent with the random seed).

## References

- Page, E. S. (1954). Continuous inspection schemes. *Biometrika*, 41(1/2), 100–115.
- Lowry, C. A., Woodall, W. H., Champ, C. W., and Rigdon, S. E. (1992). A multivariate
  exponentially weighted moving average control chart. *Technometrics*, 34(1), 46–53.
