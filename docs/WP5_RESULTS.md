# WP5 results: prescriptive and autonomous layer

Roadmap WP5 adds digital-twin levels 4 and 5 on top of the WP4 estimator: the layer
recommends actions (advisory) or takes them itself inside a guarded envelope (autonomous).
This page collects the evaluation and answers research question RQ3 as far as the evidence
allows:

> **RQ3.** Under twin–plant model mismatch, what measurable benefit does a prescriptive
> layer give over a fixed policy, and can autonomous operation be bounded with zero
> hard-limit violations?

**Everything here is simulated.** The plant is the WP2 dynamic model with WP3 fault
injection. The operator is a simulated operator whose behaviour is an assumption. The
twin is a deliberately mismatched copy of the plant model (WP4 `combined` perturbation),
but the mismatch comes only from that perturbation set.

## 1. What WP5 consists of

| Piece | Code |
| --- | --- |
| Twin monitor: exhaust-free UKF, mismatch index, thermocouple check, model exhaust | `prescription/monitor.py` |
| Predictive twin for forward (what-if) runs | `prescription/twin.py` |
| Safety guard: hard limits, rate limits, twin-trust checks | `prescription/guard.py` |
| Supervisor: modes, the three decision problems, decision log | `prescription/supervisor.py` |
| Scenario runner with a simulated operator, true-value scoring | `prescription/runner.py` |
| Evaluation harness (this page) | `prescription/evaluation.py`, `scripts/run_prescription_benchmark.py` |

The three decision problems:

- **(a) `load_setpoint`.** Load setpoint and IGV position inside the dispatcher's band
  (demand ± 2 MW) with the lowest twin heat rate, screened against the exhaust temperature
  limit and forward-run on the twin. Default objective `track_demand`: hold the demand and
  pick the best IGV; use the band only when the demand is not reachable.
- **(b) `compressor_wash`.** Offline wash when the fuel cost of the estimated fouling
  exceeds the average cost per hour of an optimal wash cycle, sqrt(2 W a).
- **(c) `exhaust_feedback`.** Switch the temperature control to the twin's model exhaust
  when the thermocouple disagrees with the twin (mean residual > 12 K, or scatter > 2 K)
  while the other channels agree.

The modes: **manual** (the layer only watches; this is the fixed baseline policy: the IGV
follows its auto schedule, the setpoint follows dispatch, no wash, no substitution),
**advisory** (every recommendation waits for the operator) and **autonomous** (a
recommendation the guard approves is applied at once; one it rejects is escalated to the
operator).

## 2. How it was evaluated

- **Runs.** A run is a scenario, a mode, a seed and the layer's settings
  (`RunSpec`). The runner drives the scenario second by second; scheduled load requests
  are applied as the operator would and become the layer's demand. Scores use the
  plant's true values from the first load request (t = 300 s) to the end.
- **Simulated operator** (`OperatorModel`, an assumption). It acts on an open
  recommendation 300 s after it was raised, accepts it if the guard approved it, rejects
  it if not, except a wash, which it always accepts.
- **Seeds.** Test seeds 2000–2004 for every reported number; seeds 2000–2002 for the
  secondary experiments. The thermocouple-check thresholds were checked on tuning seeds
  1000–1004 (inside the WP4 tuning range). No setting was chosen on a test seed.
- **Pairing.** Every advisory or autonomous run is compared with the manual run of the
  same scenario and seed (same plant, script and noise).
- **Intervals.** Two 95 % percentile bootstraps are given. The first resamples seeds
  within each scenario. **The seeds change only sensor noise, and the layer's decisions
  are the same for every seed of a scenario, so this interval is very narrow and says
  almost nothing.** The second resamples the 19 scenarios (per-scenario means). It shows
  how much the result depends on which operating situations are in the bank. It is the
  interval to quote.
- **Hard-limit violation.** True exhaust temperature more than 5 K above the temperature
  control limit (`VIOLATION_MARGIN_K`, an alarm level chosen here; the trip is 40 K above
  the limit). Trips are counted separately. Because the plant's own controller already
  overshoots the limit by 7.7 K for 17 s when the dispatcher ramps at 60 MW/min onto it,
  manual runs have violations too. The comparison that matters is with manual: violation
  seconds the layer adds, and violation seconds it removes.
- **Recorded output.** `docs/evidence/wp5/benchmark.md` holds every table of the runs
  behind this page; `benchmark_summary.json` holds the summaries, per-run wash results,
  code fingerprint and commit. The per-run JSON cache (about 3.5 MB, some 600 runs) stays out of
  the repository.
- **Compute.** About 7.9 CPU-hours for the final round (285 main runs, 152 tuning runs,
  309 secondary runs incl. shared ones), 1.9 h wall on 4 processes. A two-hour scenario
  takes 35–45 s.

## 3. Thermocouple-check thresholds (tuning seeds)

All 19 scenarios, manual on seeds 1000–1004 and autonomous on 1000–1002.

| Scenarios | Max mean exhaust residual before suspicion | Max exhaust scatter | Thermocouple suspected |
| --- | --- | --- | --- |
| 5 clean, 5 degradation, wash, slow valve, CDT bias | 1.9–5.0 K | 0.54–0.74 K | never |
| Power transducer bias (+1 MW) | 6.9 K (manual), 8.8 K (autonomous) | 0.57 K | never |
| CDP sensor bias (−35 kPa) | 13.5–14.9 K | 0.55 K | all 8 runs, 140–155 s after the fault |
| Fuel meter drift (+3 %/h) | 12.4–13.1 K | 0.55 K | all 8 runs, 2260–2470 s after the fault |
| Exhaust TC drift (−10 K/h) | – | – | all runs, 3964–4214 s after onset |
| Exhaust TC stuck, load raised 10 min later | – | – | all runs, 819 s (manual) / 908 s (autonomous) |
| Exhaust TC noise (3 K) | – | 3.19 K | all runs, 98–118 s after onset |

**Decision: thresholds left at 12 K and 2 K.** The scatter threshold has a wide margin
(clean scatter ≤ 0.74 K, faulty 3.1–3.2 K). The residual threshold has no clean
setting. The CDP bias and the fuel-meter drift are absorbed by the health estimate as
fouling, which moves the twin's exhaust prediction by 12–15 K, so the thermocouple is
blamed for a fault elsewhere. Raising the threshold to 16 K would clear those 16 runs on
tuning seeds. But the −10 K/h drift (detected at about 12 K of drift, 66–70 min after onset)
would then be found about 95 min after onset, at the end of the two-hour scenario, and
the drift is the case where the check matters. On test seeds the false suspicion led to a
model-exhaust substitution in every advisory and autonomous CDP-bias and fuel-drift run,
with no violation following (0 s, true exhaust never above the limit).

The first tuning round found a **bug**: with a noisy thermocouple the steady-state gates
never opened, so the scatter check was unreachable (0 of 8 noise runs detected). Section 9
lists that and the other core fixes.

## 4. Main result: advisory and autonomous against manual

19 scenarios × 3 modes × 5 test seeds = 285 runs, default settings (twin `combined`,
operator delay 300 s, objective `track_demand`).

| Mode | Heat rate vs manual | 95 % CI, scenarios resampled | Energy vs manual (MWh/run) | Band compliance vs manual (pp) | Violation runs / s | Pairs with more / less violation than manual | Max over limit | Trips |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manual | – | – | – | – | 20 / 42 155 | – | 7.7 K | 0 |
| advisory | −1.69 % | [−2.12, −1.22] | −3.1 [−5.2, −1.2] | −1.74 [−3.36, −0.32] | 35 / 15 511 | 15 (+270 s) / 10 (−26 914 s) | 105.4 K | 0 |
| autonomous | −1.86 % | [−2.31, −1.36] | −2.9 [−5.1, −0.9] | −0.43 [−1.13, +0.31] | 15 / 12 217 | 0 / 10 (−29 938 s) | 7.7 K | 0 |

Heat rate equals fuel per MWh here (same fuel). Seed-resampled intervals are in the
evidence file (±0.002 %).

**Where the benefit comes from.** Almost all of it is problem (a) at part load:
closing the IGV to 0–40 % at 25–35 MW cuts the twin heat rate by 2.4–3.2 % (for example
clean_part_load −2.62 %, power_transducer_bias −3.21 %, erosion step −2.75 %). At base
load (47 MW, on the temperature limit with the IGV already open) there is nothing to gain:
clean_base_load ±0.00 %, fouling_progressive_base_load +0.02 %, exhaust drift +0.04 %.
The fixed policy is the bank's IGV auto schedule, and the gain is the model's part-load
IGV effect; it is not a validated number for a real 6B. At 35 MW, 2.6 % is about 80 $/h
of fuel at 8 $/GJ.

**Energy is lower** with the layer, mainly because of washes (fouling_step_part_load,
fouling_then_erosion, cdp_sensor_bias, fouling_progressive_base_load: an offline wash
costs about 20 minutes of output) and, in the fouled-unit scenario, because the layer
washed at about 35 minutes. That made the scripted wash at 60 minutes moot; the runner
skipped and recorded those steps (5 per mode). The heat-rate comparison is per MWh, so
these outages do not inflate it.

**The CDP-bias wash is a false wash.** A −35 kPa discharge-pressure bias looks like
fouling to the estimator. The layer recommended a wash 39 s after the fault, the
simulated operator accepted it, and the plant found nothing to wash off (11.4 MWh lost
per run). Before a fix found in this evaluation, the unit then stayed at standstill for
the rest of the run.

### 4.1 Decisions and escalation

| | Load setpoint | Wash | Exhaust feedback | Total |
| --- | --- | --- | --- | --- |
| Autonomous: applied without operator | 212 | 0 | 25 | 237 (66 %) |
| Autonomous: escalated | 95 | 25 | 0 | 120 (34 %) |
| Advisory: guard-approved / rejected | 213 / 95 | 0 / 25 | 25 / 0 | 358 |

Escalation reasons (autonomous): `model_mismatch` 95, `shutdown_allowed` 25 (every wash,
by design), `meets_demand` 15, `health_converged` 10. **Every `model_mismatch` failure
was "no steady residuals yet"**: the first review after loading or after a restart,
before the 60 s residual window has data (superseded by an approved recommendation at
the next review). In 285 runs the mismatch index itself never stopped an action. The
`meets_demand` / `health_converged` cases are right after a wash restart.

### 4.2 Thermocouple faults (problem c)

| Scenario | Mode | Suspected after onset | Applied after onset | Violation s | Max over limit |
| --- | --- | --- | --- | --- | --- |
| Stuck at 35 MW, then 47 MW asked | manual | 819 s | never | 4784 | 7.7 K |
| | advisory | 821 s | 1121 s | 304 | 105.4 K |
| | autonomous | 908 s | 908 s | 0 | 0.0 K |
| Drift −10 K/h, base load | manual | 4180 s | never | 3613 | 7.7 K |
| | advisory | 4180 s | 4480 s | 2710 | 7.7 K |
| | autonomous | 4180 s | 4180 s | 2409 | 7.7 K |
| Noise 3 K | all | 98–118 s | at once / +300 s | 0 | 0.0 K |

Means over 5 seeds (the spread is under 100 s). The model exhaust follows the true exhaust
with a mean absolute error of 1.1–1.2 K in these runs.

- **Stuck sensor.** Autonomous mode substitutes 308 s after the load request and has no
  violation. In advisory mode the IGV was at 40 % when the dispatcher asked for 47 MW; the
  stuck reading hid the overfiring, and during the 300 s the simulated operator took to
  act, the true exhaust was up to 105 K above the limit (65 K above the trip level, which
  the trip protection could not see because it reads the same thermocouple).
- **Drift.** The check needs about 12 K of disagreement, which the drift reaches about
  70 minutes after onset. For the last 40 of those minutes the unit overfires by more than
  the 5 K alarm margin, in every mode. Substitution ends the exposure at detection (a
  third less violation time than manual); it does not prevent it.

### 4.3 Advisory mode adds violations, autonomous mode does not

In autonomous mode no scenario–seed pair had more violation time than its manual run
(0 of 95), and 10 had less (the exhaust scenarios). Every remaining autonomous violation
is also in manual (the plant's own 7.7 K overshoot at base-load ramps, and the drift
before detection). Advisory mode added violations in 15 pairs: clean_fast_load_steps,
clean_load_cycling and slow_fuel_valve_load_steps (up to 23 K over, 14–20 s per run). The
dispatcher changes the load every 20 minutes. An IGV recommendation for the previous
load is often superseded before the operator gets to it, so the IGV stays where an
earlier accepted recommendation put it when the next step comes. The guard checks the
layer's own actions, not the dispatcher's later steps on a state the layer left behind.

## 5. Secondary experiments (seeds 2000–2002)

### 5.1 Operator delay (advisory, 7 scenarios)

| Delay | Heat rate vs manual (CI over scenarios) | Stuck TC: violation s / max | Drift TC: violation s |
| --- | --- | --- | --- |
| 60 s | −1.04 % [−1.99, −0.23] | 64 / 105 K | 2467–2516 |
| 300 s | −1.05 % [−1.84, −0.33] | 304 / 105 K | 2710–2758 |
| 900 s | −0.83 % [−1.56, −0.21] | 904 / 105 K | 3310–3361 |

The benefit shrinks with a slow operator. Exposure in the thermocouple scenarios grows
one-for-one with the delay. Even a 60 s operator does not prevent the 105 K peak.

### 5.2 Model mismatch (7 scenarios, advisory and autonomous)

Twin engine: exact (the plant's own model, circular), `combined` (WP4), and
`combined_x3` (built in `evaluation.py`: drivetrain −1.5 %, inlet and combustor
pressure loss +1.5 points, air flow −3 %).

| Twin | Autonomous heat rate vs manual (CI over scenarios) | Mismatch index median | Time with index > 3 | Escalations for mismatch | Violation runs / s | Trips |
| --- | --- | --- | --- | --- | --- | --- |
| exact | −1.83 % [−2.57, −1.01] | 0.19 | 0.2 % | 18 (start-up only) | 3 / 7695 | 0 |
| combined | −1.82 % [−2.56, −1.00] | 0.19 | 0.2 % | 18 (start-up only) | 3 / 7319 | 0 |
| combined_x3 | −1.72 % [−2.40, −0.92] | 0.20 | 0.2 % | 18 (start-up only) | 6 / 6859 | 0 |

**The mismatch index does not see the large mismatch.** Its median is the same for all
three twins. The three-parameter health estimate absorbs the engine perturbation, so
the residuals stay at noise level near the operating point. The layer therefore acted as
usual with the 3× twin and did not escalate for mismatch.

The first run of this experiment ended in a trip in the stuck-thermocouple scenario (all
3 seeds, advisory and autonomous). With the 3× twin, no IGV/load candidate passed the
exhaust screen when the dispatcher asked for 47 MW, so the layer proposed nothing and left
its earlier IGV 40 % setting in place. The stuck reading hid true exhaust about 100 K over
the limit, and when the model exhaust was switched in, the over-temperature protection
tripped the unit at once. **Fix (commit 6fb6065):** when no candidate passes the screen
while the IGV is in a manual position, the layer proposes returning the IGV to auto at
the present setpoint. The guard checks that fallback against a forward run of holding
(no trip, no hotter than holding, speed band), not the full forward set, because the
state it starts from is already outside the screen. With the fix, the 3× twin has no
trips. Autonomous mode substitutes 908 s after onset and the run overfires for about
304 s with a maximum of 7.6 K over the limit (the same maximum as the drift scenario).
Advisory mode still reaches 105 K during the operator delay, as with the other twins.
The small mismatch (`combined`) costs nothing against the exact twin; the 3× mismatch
costs about 0.1 point of the heat-rate gain.

### 5.3 Objective (autonomous, 6 scenarios)

| Objective | Heat rate vs manual | Energy vs manual | Band vs manual | Escalations | Violation runs / s |
| --- | --- | --- | --- | --- | --- |
| track_demand | −1.75 % | −2.4 MWh | −0.7 pp | 21 | 3 / 51 (all also in manual) |
| heat_rate | −1.75 % | −4.1 MWh | −1.3 pp | 27 | 6 / 75 (3 new: fouling step, 8 s at +5.6 K) |

Running anywhere in the band for the lowest heat rate gives no heat-rate gain over
tracking the demand. It delivers less, and its candidates trigger the guard more
often (27 escalations against 21; it is the only setting in which candidates failed
`no_trip`, `peak_exhaust`, `transient_exhaust` and `speed_band`, 6 times each). It also
produced the only autonomous violations not present in manual: 8 s at +5.6 K in each
fouling-step run. `track_demand` stays the default.

### 5.4 Wash timing (6 h of fouling at 2 %/h, 40 MW, 15 C)

Total cost = fuel cost scaled to the no-wash run's energy (fuel per MWh × that energy)
plus washes × the effective wash cost W = 30 000 $ / 720 = 41.7 $. The layer may not touch
the IGV here, so only the wash differs. Fixed policies are scripted operator washes every
N hours. Washes count as true fouling resets.

| Policy | Washes | Mean true fouling | Total cost | Saving vs no wash |
| --- | --- | --- | --- | --- |
| never | 0 | 5.39 % | 22 589 $ | – |
| every 0.75 h | 7 | 0.59 % | 22 803 $ | −214 $ |
| every 1 h | 5 | 0.84 % | 22 432 $ | +157 $ |
| every 1.5 h | 3 | 1.33 % | 22 197 $ | +391 $ |
| every 2 h | 2 | 1.80 % | 22 139 $ | **+450 $** |
| every 3 h | 1 | 2.75 % | 22 161 $ | +428 $ |
| layer, advisory (operator accepts after 300 s) | 3 | 1.72 % | 22 261 $ | +328 $ |
| layer, autonomous (`autonomous_wash=True`) | 3 | 1.60 % | 22 248 $ | +341 $ |

Three seeds per row; seeds change nothing visible.

**Optimal interval.** For a fouling loss rate that grows linearly, L(t) = a t, the long-run
cost per hour of washing every T hours is W/T + aT/2. It is lowest at **T\* = sqrt(2W/a)**,
where it equals sqrt(2Wa), the layer's wash threshold. With the loss growth the layer
estimated, a ≈ 45 $/h², T\* = 1.36 h of simulated time. The layer washed first 1.58 h after
onset (estimated fouling about 2.6 %), then about every 1.9–2.0 h including the outage.
**Time compression.** The bank's fouling is c = 720 times faster than in service, so
a_service = a / c. With the wash cost divided by c as well, T\*_sim = sqrt(2(W/c)/a) and
T\*_service = sqrt(2W/(a/c)) = c · T\*_sim, the same factor. T\* = 1.36 h simulated
corresponds to about 980 h (41 days) of service at 2 %/month fouling.

The layer's timing saves money against no washing. It is 110 $ (25 %) short of the best
fixed interval in this grid (2 h), and it lies between the 1 h and 1.5 h policies.
The empirical optimum is longer than T\* because the simulated outage is not time-compressed.
Each wash still costs about 20 minutes of standstill, start and ramp at poor heat rate,
and the restart fuel counts in the per-MWh fuel cost, so frequent washing is penalised
twice. The comparison of the layer with the fixed policies depends on this accounting.

## 6. Answer to RQ3

**Benefit under mismatch: yes, for the efficiency problem, with caveats.** With the
mismatched (`combined`) twin, autonomous mode lowers the heat rate by 1.86 % against
the fixed policy (95 % CI over scenarios −2.31 to −1.36 %), advisory by 1.69 %
(−2.12 to −1.22 %). Both intervals exclude zero. Fuel per MWh changes by the same amount. The benefit comes from part-load IGV
scheduling; at base load it is zero. The wash decision beats never washing (+341 $ over
6 h) but not the best fixed interval (+450 $). The thermocouple substitution reduces
overfiring exposure: to zero for a stuck sensor in autonomous mode, by a third for a
drift.

**Bounded autonomy with zero hard-limit violations: partly.**

- With the WP4 mismatch and the default objective: **no trips, and no violation that the
  manual baseline does not have** (0 of 95 pairs worse, 10 better). It is not zero in
  absolute terms: the plant's own controller overshoots the 5 K alarm margin at base-load
  ramps in every mode, and a thermocouple drift overfires by 5–12 K for about 40 minutes
  before the model-based check can see it.
- In advisory mode, operator delay produced violations up to 105 K that autonomous
  mode avoided. Keeping a human in the loop was not the safer choice in this simulation.
- **Graceful escalation under large mismatch was not shown.** The mismatch index
  stayed at noise level with a 3× mismatched twin, because the health estimate absorbs
  the mismatch. The layer never escalated for mismatch. A first run ended in a trip in
  one scenario (all 3 seeds); an IGV-schedule fallback removed it (section 5.2), so the
  final result is no trips, but the protection came from the fallback, not from the
  mismatch detection.
- The layer needed several fixes found by this evaluation before the autonomous result
  above held (section 9).

## 7. Limits

- **Simulated plant and simulated faults.** The heat-rate gain is the WP2 model's
  part-load IGV effect, not a measured one. Exhaust limit, trip and the 5 K alarm level
  are labelled assumptions.
- **Simulated operator.** A fixed 300 s delay and a fixed accept/reject rule. Real
  operators would, for example, open the IGV before a large load step, or refuse a wash
  that comes 39 s after a step change in a pressure reading. The advisory results depend
  directly on this model.
- **Seeds are almost irrelevant.** They change sensor noise only. The decisions are the
  same for every seed, so five seeds are effectively one run per scenario. The interval
  over scenarios measures the bank's composition, not repeat variability. A bank with
  random dispatch, ambient and fault timing would be needed for that.
- **Accelerated degradation and time-compressed prices.** Wash economics divide the wash
  cost by 720 to match the bank's fouling rate. The outage itself is not compressed.
- **Mismatch only from the perturbation set** (WP4 `combined` and its 3× version). Map
  shape errors, sensor calibration errors and dynamics mismatch were not tested.
- **Objective choices.** Heat rate only. No emissions, no start/stop cost beyond the wash
  cost, no reserve requirement. The demand band (±2 MW) is an assumption.
- **Sensor faults masquerading as degradation.** CDP bias and fuel-meter drift are
  absorbed as fouling (WP4 limitation). This causes a false wash and a false thermocouple
  suspicion. Neither caused a violation here, but the false wash costs 20 minutes of
  output.

## 8. Reproducing

```bash
# all experiments into a cache (about 2 h on 4 processes), then the tables
PYTHONPATH=src python scripts/run_prescription_benchmark.py run --cache-dir /tmp/wp5-cache --workers 4
PYTHONPATH=src python scripts/run_prescription_benchmark.py report --cache-dir /tmp/wp5-cache --out docs/evidence/wp5
# one experiment only: run main | tuning | delay | mismatch | objective | wash
PYTHONPATH=src python -m pytest -q tests/test_prescription_evaluation.py   # ~8 s
```

The cache key covers the run spec, the scenario script, the twin engine and a fingerprint
of the simulation, estimation and prescription-core code. A change to any of them reruns
the affected runs.

## 9. Core changes made during the evaluation

Each was found on tuning seeds or by inspecting a run, fixed, and the evaluation was then
rerun from scratch.

| Change | File | Evidence |
| --- | --- | --- |
| Steady-state gates ignore the exhaust reading | `monitor.py` | Noisy TC (3 K) kept both gates closed: 0/8 noise runs detected, estimator frozen. After: detected in 98–118 s. |
| Forward-run settling holds the load reference | `twin.py` | An IGV closure at the start of a 60 MW/min dispatcher ramp was checked 30 s (≈ 30 MW) into the ramp. It passed and overshot the limit by 8.7 K (clean_load_cycling, autonomous, tuning seeds). |
| New guard check `transient_exhaust` (peak ≤ limit + 3 K) | `guard.py` | Before, only the trip margin (limit + 15 K) bounded transients. With the twin fix, the same run is 14 K below the limit. |
| Reopen the IGV when the layer's part-load setting runs onto the limit | `supervisor.py` | The review returned early "on the limit but in band" (meant for base load). fouling_progressive_ambient_swing sat at IGV 40 % on the limit for 40 min, with 17 s at +8.9 K. After: IGV 60 % at 3000 s, no violation. |
| Restart after a refused wash; no further washes after one | `supervisor.py` | CDP bias: accepted wash refused by the plant, unit stranded at standstill (17.9 vs 67.0 MWh). After: restarts, 55.5 MWh. |
| Fall back to the IGV schedule when no candidate passes the screen; the guard checks it against holding | `supervisor.py`, `guard.py` | combined_x3, stuck TC at 47 MW: tripped in all 3 seeds (advisory and autonomous). After: no trips; autonomous 304 s at most 7.6 K over the limit. |
| `run_supervised(observer=...)` read-only hook | `runner.py` | Needed by the evaluation, no behaviour change. |

The `Supervisor` public API (constructor, `tick`, `set_mode`, `set_demand`, `accept`,
`reject`, `trust_thermocouple`, `summary`, `decisions`, `Decision.to_dict`) is unchanged.
`counters` gains `washes_refused` when a wash is refused.

## 10. Open work after WP5

- A mismatch check that the health estimate cannot absorb: residuals at operating
  points away from where the estimate converged (for example the forward-run prediction
  error after each applied action), or a bound on the estimated health against its
  plausible range.
- Make the guard account for the dispatcher. Hold or undo an IGV override before a
  scheduled load step, or check the band edges as well as the current demand.
- A thermocouple check that sees slow drifts sooner: a trend test on the exhaust
  residual rather than a level threshold.
- A randomised scenario bank (dispatch, ambient, fault timing) so that the intervals
  measure repeat variability.
