# Health estimation (WP4, self-calibration)

An online estimator of the three gas-path health parameters of the simulated GE 6B.03-class
unit from noisy instrument readings only, and a measurement of how well it tracks injected
degradation, with and without a deliberate twin-plant mismatch. Everything here runs on the
simulator of `DYNAMIC_MODEL.md` and the scenario bank of `SCENARIO_BANK.md`; nothing is
plant data.

- Code: `src/turbineiq/estimation/ukf.py` (filter and measurement models),
  `observability.py` (Jacobian and information analysis), `mismatch.py` (perturbed twins,
  steady-state bias, scoring and the evaluation driver), and the additive
  `engine_health_maps` helper in `src/turbineiq/simulation/maps.py`.
- Tests: `tests/test_estimation_ukf.py` (18 s on an idle machine, about 40 s under load; one
  55-minute simulation).
- Health is counted in **points**: 1 point is 1 % of compressor flow capacity or one point of
  polytropic efficiency (a health delta of −0.01).

## Formulation

**States.** The health deltas `x = (flow capacity, compressor efficiency, turbine
efficiency)` as fractions, the fields of `simulation.maps.Health`. They are three
independent random walks: the filter does not know the simulator's 2:1 fouling ratio.

**Process model.** `x(t + dt) = x(t) + w`, with `Var(w) = diag(q²) dt`, `q = (0.3, 0.15,
0.15)` points per square-root hour (tuned, below). Variance grows with elapsed time
whether or not the unit runs, so after a stop (and, for example, an offline wash) the
filter is more willing to move. Prior: zero (clean) with standard deviation (3, 1.5, 1.5) points.

**Measurement model.** The quasi-steady twin of `estimation/twin.py` in the *power-input*
form (`PowerInputModel`): the measured electrical power, speed, IGV position and ambient go
in, and the model predicts fuel flow, exhaust temperature, compressor discharge temperature
and pressure. For each candidate health the twin is inverted for the fuel flow at which it
predicts the measured power (a secant iteration on the piecewise-linear map, converged to
1e-7 MW). The twin as given (`FuelInputModel`: fuel in, power out) is kept and can be
selected; the observability section explains the choice.

**Noise model.** The covariance of one sample's residual is the instrument noise on the
four predicted readings plus the noise of the two input readings (power, speed) pushed
through the twin by a central difference of one instrument sigma. That makes it a full
4 × 4 matrix, recomputed at every update. Instrument sigmas are those of the simulator
(power 0.2 %, exhaust 0.5 K, discharge temperature 0.5 K, discharge pressure 0.2 %, fuel
0.5 %, speed 0.0005 pu); a real estimator would take them from data sheets and check them
against the residuals of a known-clean period.

**Steady-state gating and batching.** Every observation goes through the shared
`SteadyStateGate` (defaults: 120 s window, power std ≤ 0.25 MW, exhaust std ≤ 1.5 K,
unchanged setpoint, IGV and ambient). Only observations taken while it is open are used.
They are averaged in batches of 10 s (inputs and readings alike), and each batch mean is
one measurement update with covariance `R / n`. A batch cut short by the gate closing is
used if it covers at least 5 s.

**Unscented Kalman filter.** Written in numpy (`UKFHealthEstimator`): 7 sigma points with
`α = 1, β = 2, κ = 0` (points at ±√3 σ), Cholesky square root with an eigenvalue
fallback, standard UKF update, covariance symmetrised after each update. Steps in health
(a fouling event, a wash) are far faster than any sensible random walk, so a batch whose
normalised innovation squared (NIS, 4 degrees of freedom) exceeds 30 first has its
covariance inflated by 4 (rows and columns scaled back so that no variance exceeds the
prior). With the exact twin the NIS of a batch is χ²(4) (mean 4, 99.9 % point 18.5), so
the inflation fires on steps, rarely on noise.

**API.** `UKFHealthEstimator(settings=None, *, twin=None, gate=None)`;
`update(obs: Observation) -> HealthEstimate | None` returns `None` until the first
measurement update and afterwards the current posterior on every call:
`HealthEstimate(t_s, mean: Health, std: Health, steady: bool)`, frozen, with `t_s` equal to
the observation's time and `steady` true while the gate is open. `std` is the filter's
posterior standard deviation: it covers measurement noise, **not** calibration bias (see
the mismatch section). The estimator never sees `Truth`. `last_nis` and `last_innovation`
expose the latest batch's innovation for a detector.

## Observability

`observability.py` builds a noise-free steady observation of the twin at an operating point
(rated speed, open IGV, fuel flow solved for the requested load, or for the exhaust
temperature-control limit at base load), differentiates the four predictions with respect
to the three health deltas (central differences, ±0.2 point), whitens the Jacobian with the
one-sample residual covariance and reports its singular values, condition number, weakest
direction and the Cramér–Rao bound (CRB). Measured on the clean engine:

Sensitivities at 15 C, 35 MW (change per point of health loss is minus these):

| reading (fuel-input form) | flow capacity | compressor η | turbine η | residual std, 1 sample |
| --- | --- | --- | --- | --- |
| power, MW | +0.018 | +0.507 | +0.739 | 0.221 |
| exhaust T, K | −4.45 | −3.31 | −4.82 | 1.94 |
| discharge T, K | +1.89 | −6.07 | 0 | 0.61 |
| discharge p, kPa | +11.84 | 0 | 0 | 3.42 |

| reading (power-input form) | flow capacity | compressor η | turbine η | residual std, 1 sample |
| --- | --- | --- | --- | --- |
| fuel flow, kg/s | −0.001 | −0.026 | −0.038 | 0.011 |
| exhaust T, K | −4.60 | −7.81 | −11.38 | 0.89 |
| discharge T, K | +1.89 | −6.07 | 0 | 0.61 |
| discharge p, kPa | +11.84 | 0 | 0 | 3.42 |

The structure is triangular: discharge pressure sees only flow capacity (the pressure-rise
scaling of `maps.py`), discharge temperature adds compressor efficiency, and power or fuel
and exhaust temperature add turbine efficiency. The residual std of discharge pressure and
temperature is larger than the instrument noise because speed noise (0.0005 pu) enters the
twin as an input.

Information per steady sample, health in points (9 operating points: 25, 35, 40 MW and
base load at 15 C; 35 MW and base at 5 C; 25, 35 MW and base at 30 C):

| quantity | 15 C, 35 MW | range over the 9 points |
| --- | --- | --- |
| singular values of the whitened Jacobian | 19.3, 8.5, 3.2 | smallest 3.15 to 3.31 |
| condition number | 6.0 | 5.4 to 6.5 |
| weakest direction (flow, ηc, ηt) | (0.87, 0.20, −0.45) | (0.85..0.89, 0.20..0.21, −0.41..−0.50) |
| CRB std, 1 sample (flow, ηc, ηt) | 0.27, 0.11, 0.16 | 0.27, 0.10..0.11, 0.15..0.18 |
| CRB std, 600 samples (10 min) | 0.011, 0.004, 0.007 | same to ±0.001 |
| CRB correlation flow–ηc, flow–ηt, ηc–ηt | 0.46, −0.75, −0.76 | 0.45..0.46, −0.71..−0.79, −0.72..−0.80 |
| std with a diagonal covariance, fuel-input form | 0.29, 0.11, 0.19 | ηt 0.18..0.21 |
| std with a diagonal covariance, power-input form | 0.27, 0.11, 0.16 | ηt 0.15..0.18 |

What this establishes, for this model and these instruments:

- All three parameters are observable at every point checked, with a condition number of
  about 6 (no direction is close to unobservable). The weakest direction is mostly flow
  capacity traded against turbine efficiency: flow capacity is pinned only by discharge
  pressure, the noisiest channel relative to its sensitivity. The fouling signature
  (−1, −0.5, 0)/1.12 lies mostly along that weakest direction (projection 0.87), and is
  still resolved to about 0.01 point by 10 minutes of steady data. Noise is not what limits
  the estimator; model error is (next sections).
- Observability hardly depends on load or ambient (the bounds change by a few percent).
- **Fuel as input or as output.** With the full residual covariance the two forms carry the
  same information: to first order the power-input residual is an invertible linear map of
  the fuel-input residual, so the Fisher information, singular values and bounds agree
  (checked numerically to 1e-4, and asserted in the tests). The forms differ when the
  input-noise correlation is ignored. Fuel noise (0.5 %) enters power and exhaust together,
  so the fuel-input residuals are strongly correlated, and an estimator that keeps only the
  variances loses 18 % (35 MW) to 19 % (base) on turbine efficiency. Power noise (0.2 %) is
  smaller and the power-input residuals are nearly uncorrelated: the same simplification
  costs 1 to 2 %. The power-input form is therefore the default, because its noise model is
  less fragile (a mis-specified correlation, or the input noise being non-Gaussian, matters
  less), not because it is better conditioned; with the full covariance it is not. It also
  makes the filter's input the reading that a revenue-grade meter measures best. The
  tuning sweep below confirms the equivalence on simulated data.

## Tuning

Tuned on scenario seeds 1000, 1001 and 1002 only (the six degradation scenarios and the
five clean ones, 33 runs, exact twin), never on the evaluation seeds. Score: RMS error over
every scored segment from 20 minutes after onset, the worst absolute error, and the longest
time from an onset until the error stays within tolerance. Points of health (flow, ηc, ηt):

| setting | RMS error | worst error |
| --- | --- | --- |
| start: q = (1, 0.5, 0.5), inflation at NIS 30, 10 s batches | 0.044, 0.019, 0.025 | 0.18, 0.08, 0.11 |
| same without inflation, or inflation at NIS 60 | identical | identical |
| q × 3 | 0.066, 0.027, 0.038 | 0.26, 0.11, 0.17 |
| **q × 0.3 (chosen)**, with or without inflation | **0.029, 0.013, 0.015** | **0.15, 0.06, 0.06** |
| q × 0.1 | 0.052, 0.021, 0.022 | 0.19, 0.08, 0.08 |
| start, 30 s batches | 0.039, 0.016, 0.022 | 0.15, 0.07, 0.08 |
| start, one update per sample | 0.045, 0.020, 0.025 | 0.22, 0.11, 0.14 |
| start, diagonal noise covariance | 0.046, 0.017, 0.024 | 0.17, 0.07, 0.10 |
| start, fuel-input form, full covariance | identical to power-input | identical |
| start, fuel-input form, diagonal covariance | 0.048, 0.019, 0.023 | 0.19, 0.08, 0.08 |

- The process noise is the only setting that matters much. Below q × 0.3 the error grows
  again because the filter lags the bank's accelerated fouling (2 to 3 % per hour); above
  it, noise passes through. The chosen value is therefore tied to the bank's accelerated
  rates: real fouling is orders of magnitude slower and would want a much smaller q.
- The covariance inflation never changed a result at q × 0.3 (the random walk alone lets
  the filter follow a 3 % step within a few batches). At q × 0.1 it shortened the slowest
  step response from 9.2 to 8.5 minutes. It is kept as a guard for smaller q.
- Convergence after a step is limited by the steady-state gate, not the filter: the
  slowest onset (the restart after the wash) converged 8.3 minutes after the wash command,
  which is the restart, loading and the gate's 120 s quiet window.
- Batch length, per-sample updates, the diagonal covariance and the fuel-input form change
  the error by a few hundredths of a point at most, consistent with the observability
  result (the full-covariance forms agree to the printed digits).
- The prior (3, 1.5, 1.5 points) and the 10 s batch were not tuned further; the first
  estimate appears when the gate first opens, about 7.5 minutes after a start.

## Results with the exact twin

Evaluation data only: each scenario's bank seed and bank seed + 10000 k (k = 1..4), five
runs per scenario; nothing here was used for tuning. Errors are estimate minus truth in
points. "Mean error" is the mean over the five runs of the error averaged over steady
estimates from 20 minutes after the onset to the end of the segment (clean runs: the whole
run); "worst error" is the largest absolute error over the same samples of all five runs.
Convergence is the time from the onset (clean runs and the fouled start: from the start
command) until the error stays within 0.6 % flow capacity or 0.3 point efficiency for the
rest of the segment; the median over the five runs, all five converged unless stated.

| scenario | mean error (flow, ηc, ηt) | worst error | convergence, min (flow / ηc / ηt) |
| --- | --- | --- | --- |
| fouling_step_part_load | +0.00, -0.00, +0.00 | 0.09, 0.03, 0.04 | 2 / 2 / 0 |
| fouling_progressive_base_load | +0.05, +0.02, -0.02 | 0.12, 0.06, 0.07 | 0 / 0 / 0 |
| fouling_progressive_ambient_swing | +0.03, +0.01, -0.01 | 0.16, 0.06, 0.05 | 0 / 0 / 0 |
| erosion_step_part_load | +0.00, +0.00, -0.00 | 0.11, 0.04, 0.04 | 0 / 0 / 2 |
| fouling_then_erosion (1800–3600 s) | -0.01, -0.00, +0.00 | 0.08, 0.03, 0.04 | 2 / 2 / 0 |
| fouling_then_erosion (3600–7200 s) | +0.00, +0.00, -0.00 | 0.08, 0.04, 0.04 | 0 / 0 / 2 |
| fouled_unit_offline_wash (0–1800 s) | +0.00, +0.00, -0.00 | 0.09, 0.03, 0.03 | 8 / 8 / 8 |
| fouled_unit_offline_wash (3600–9000 s) | -0.00, +0.00, +0.00 | 0.08, 0.03, 0.05 | 8 / 8 / 8 |
| clean_part_load | +0.00, +0.00, +0.00 | 0.09, 0.04, 0.05 | 8 / 8 / 8 |
| clean_base_load | +0.00, +0.00, -0.00 | 0.08, 0.04, 0.05 | 8 / 8 / 8 |
| clean_load_cycling | +0.00, +0.00, -0.00 | 0.11, 0.05, 0.04 | 8 / 8 / 8 |
| clean_ambient_swing | -0.00, +0.00, -0.00 | 0.09, 0.04, 0.05 | 8 / 8 / 8 |
| clean_fast_load_steps | +0.00, -0.00, +0.00 | 0.09, 0.04, 0.06 | 8 / 8 / 8 |

- Every run converges, and after convergence no sample is further than 0.16 % flow capacity
  or 0.07 point efficiency from the truth. The bias on clean runs is below 0.01 point in
  every scenario, including load cycling, fast load steps and ambient steps.
- A fouling or erosion step is tracked within about 2 minutes of the onset: the exhaust
  jump closes the gate for about 125 s (one 120 s window), and the first batches after it
  reopens move the estimate to the new health (the covariance inflation and the random
  walk allow that). Progressive fouling (2 to 3 % per hour) is followed with a lag error
  of 0.02 to 0.05 point.
- The 8 minutes on the clean runs and on the wash are the start-up: synchronisation at about
  4 minutes, loading, then the gate's 120 s quiet window. After the offline wash the
  estimate moves from −3 % fouling to clean with the first steady batch after the restart.
- These numbers are circular: the twin is the plant's own model. They show that the filter,
  the gating and the noise model work, nothing more.

## Twin-plant mismatch

With the default maps the twin is the plant's own model, so the results above are
circular: they show that the filter works, not that the health it reports would be right
on a real unit. `mismatch.py` builds the twin on a perturbed copy of the calibrated engine
(`engine_health_maps(engine, ambient)`, an additive helper in `maps.py` that reproduces
`health_maps` exactly for the calibrated engine) while the plant keeps the calibrated one.
The perturbations are my choice of plausible calibration errors, not values from data:

| name | twin calibration change |
| --- | --- |
| drivetrain | drivetrain efficiency × 0.995 (−0.5 %) |
| inlet_loss | inlet pressure loss 1.0 → 1.5 % (about 5 mbar) |
| exhaust_loss | exhaust pressure loss 1.0 → 1.5 % |
| combustor_loss | combustor pressure loss 4.0 → 4.5 % |
| cooling | cooling flow 8.0 → 8.5 % of compressor flow |
| air_flow | air mass flow × 0.99 |
| barometer | ambient pressure 1 kPa below the site's (and mass flow with it) |
| combined | drivetrain, inlet_loss, combustor_loss and air_flow together |

**Converged bias.** `steady_bias` fits the mismatched twin to noise-free plant readings by
weighted least squares (the point a filter converges to with unlimited steady data).
Points of health, 15 C and 35 MW, with the range over the 9 operating points; "NIS left"
is the normalised residual per sample that no health can explain (what a detector could
see; 10 s batches multiply it by 10):

| mismatch | flow capacity | compressor η | turbine η | ηt range over points | NIS left |
| --- | --- | --- | --- | --- | --- |
| drivetrain | −0.03 | −0.01 | +0.15 | +0.12 to +0.18 | 0.11 |
| inlet_loss | +0.49 | +0.16 | −0.13 | −0.17 to −0.10 | 0.47 |
| exhaust_loss | 0.00 | 0.00 | +0.17 | +0.17 | 0.00 |
| combustor_loss | 0.00 | 0.00 | +0.18 | +0.18 | 0.00 |
| cooling | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| air_flow | +0.11 | +0.02 | +0.22 | +0.17 to +0.28 | 1.43 |
| barometer | +1.07 | +0.33 | −0.39 | −0.40 to −0.39 | 0.03 |
| combined | +0.57 | +0.17 | +0.42 | +0.37 to +0.48 | 0.03 |

Findings:

- A biased twin turns its calibration error into a health error of the same order: a
  0.5-point pressure-loss error is worth 0.13 to 0.18 point of turbine efficiency, a 0.5 %
  inlet-loss error half a percent of flow capacity. Exhaust and combustor pressure losses
  are absorbed entirely by turbine efficiency (no residual is left), so no amount of data
  separates them from erosion.
- The cooling-flow change has **no** effect at all: in this cycle model cooling air bypasses
  the combustor and is mixed back before the turbine, so at a given fuel flow nothing
  downstream changes. That is a property of the model (it only reinterprets the effective
  firing temperature), not evidence that real cooling errors are harmless.
- The barometer case is the largest: 1 kPa (10 mbar, an ordinary weather change) moves the
  flow capacity by 1.07 % and compressor efficiency by 0.33 point, because discharge
  pressure scales with inlet pressure and is the only flow-capacity channel. The
  observation stream has no ambient pressure, so on a real unit this error would follow
  the weather.
- The bias barely depends on the health itself (combined case: +0.57/+0.17/+0.42 point clean,
  +0.55/+0.17/+0.45 at 4.5 % fouling) and only weakly on load and ambient. So a **change**
  measured against a baseline taken on the same twin is far more accurate than the
  absolute value: most of the bias cancels.
- The dangerous mismatches are the ones that leave no residual (barometer, combined, the
  pressure losses): the filter's innovations look healthy and its reported std stays small,
  so neither the estimator nor a residual-based detector can tell. Only air_flow and, a
  little, inlet_loss leave a residual a detector could see.
- If the five independent calibration errors (all but cooling and barometer) are read as
  one-sigma uncertainties with random signs, the root-sum-square bias is about 0.50 % flow
  capacity, 0.16 point compressor efficiency and 0.39 point turbine efficiency; adding a
  1 kPa barometer error brings compressor efficiency to about 0.37 point.

**Filter runs with a mismatched twin.** The same 95 evaluation runs, with the twin built on
the `combined` and the `barometer` engines. "Change error" is the error of the change
since the pre-onset baseline: the mean estimate over the last 10 minutes of the segment
minus the mean over the 10 steady minutes before the onset, compared with the true change
(only for segments with a healthy, steady stretch before the onset).

`combined` (drivetrain −0.5 %, inlet and combustor loss +0.5 point, air flow −1 %):

| scenario | mean error (flow, ηc, ηt) | worst error | change error since baseline (flow, ηc, ηt), mean / worst |
| --- | --- | --- | --- |
| fouling_step_part_load | +0.56, +0.17, +0.44 | 0.64, 0.21, 0.48 | -0.01, -0.01, +0.02 / 0.03, 0.02, 0.03 |
| fouling_progressive_base_load | +0.60, +0.19, +0.46 | 0.68, 0.23, 0.50 | +0.04, +0.02, -0.02 / 0.05, 0.02, 0.02 |
| fouling_progressive_ambient_swing | +0.60, +0.18, +0.42 | 0.72, 0.23, 0.46 | +0.03, +0.01, +0.00 / 0.05, 0.02, 0.01 |
| erosion_step_part_load | +0.57, +0.18, +0.42 | 0.65, 0.21, 0.46 | +0.01, +0.00, -0.01 / 0.03, 0.01, 0.02 |
| fouling_then_erosion (1800–3600 s) | +0.55, +0.17, +0.44 | 0.64, 0.20, 0.47 | -0.01, -0.00, +0.01 / 0.04, 0.01, 0.03 |
| fouling_then_erosion (3600–7200 s) | +0.56, +0.17, +0.43 | 0.64, 0.21, 0.46 | n/a |
| fouled_unit_offline_wash (0–1800 s) | +0.56, +0.17, +0.46 | 0.64, 0.20, 0.49 | n/a |
| fouled_unit_offline_wash (3600–9000 s) | +0.57, +0.17, +0.45 | 0.64, 0.21, 0.49 | n/a |
| clean_part_load | +0.57, +0.18, +0.42 | 0.66, 0.21, 0.47 | n/a |
| clean_base_load | +0.56, +0.17, +0.47 | 0.64, 0.21, 0.52 | n/a |
| clean_load_cycling | +0.57, +0.18, +0.42 | 0.68, 0.21, 0.50 | n/a |
| clean_ambient_swing | +0.57, +0.18, +0.42 | 0.66, 0.21, 0.48 | n/a |
| clean_fast_load_steps | +0.57, +0.17, +0.43 | 0.65, 0.22, 0.49 | n/a |

`barometer` (1 kPa):

| scenario | mean error (flow, ηc, ηt) | worst error | change error since baseline (flow, ηc, ηt), mean / worst |
| --- | --- | --- | --- |
| fouling_step_part_load | +1.04, +0.33, -0.37 | 1.13, 0.36, 0.41 | -0.03, -0.01, +0.03 / 0.04, 0.02, 0.04 |
| fouling_progressive_base_load | +1.09, +0.35, -0.39 | 1.18, 0.38, 0.45 | +0.02, +0.01, +0.01 / 0.03, 0.02, 0.02 |
| fouling_progressive_ambient_swing | +1.09, +0.34, -0.39 | 1.21, 0.39, 0.43 | +0.02, +0.00, +0.01 / 0.04, 0.01, 0.02 |
| erosion_step_part_load | +1.07, +0.33, -0.40 | 1.15, 0.37, 0.44 | +0.01, +0.00, -0.01 / 0.03, 0.01, 0.02 |
| fouling_then_erosion (1800–3600 s) | +1.05, +0.33, -0.37 | 1.13, 0.35, 0.41 | -0.02, -0.01, +0.02 / 0.05, 0.02, 0.03 |
| fouling_then_erosion (3600–7200 s) | +1.05, +0.33, -0.38 | 1.14, 0.37, 0.42 | n/a |
| fouled_unit_offline_wash (0–1800 s) | +1.05, +0.33, -0.37 | 1.12, 0.35, 0.41 | n/a |
| fouled_unit_offline_wash (3600–9000 s) | +1.06, +0.33, -0.39 | 1.14, 0.36, 0.43 | n/a |
| clean_part_load | +1.07, +0.33, -0.39 | 1.16, 0.37, 0.44 | n/a |
| clean_base_load | +1.07, +0.33, -0.40 | 1.14, 0.37, 0.44 | n/a |
| clean_load_cycling | +1.07, +0.33, -0.39 | 1.17, 0.37, 0.44 | n/a |
| clean_ambient_swing | +1.07, +0.33, -0.39 | 1.16, 0.37, 0.43 | n/a |
| clean_fast_load_steps | +1.07, +0.33, -0.39 | 1.15, 0.37, 0.44 | n/a |

- The filter converges to the bias that the steady analysis predicts, on every scenario,
  clean or degraded (combined: +0.57 % flow, +0.17 point ηc, +0.42 to +0.47 point ηt;
  barometer: +1.07 %, +0.33, −0.39). The bias on healthy runs is that same number: a
  mismatched twin reports a clean unit as degraded or improved by it.
- Absolute compressor efficiency stays within 0.3 point with the combined mismatch (worst
  sample 0.23 point) but not with the barometer mismatch (mean 0.33, worst 0.39 point).
  Turbine efficiency is outside 0.3 point with both (combined worst 0.52, barometer 0.45).
- The change since a healthy baseline is accurate to 0.05 % flow capacity and 0.02 point
  efficiency with either mismatch, in every scenario that has a baseline: the bias is
  almost the same before and after the degradation, including across the ambient swing and
  at base load. This is the honest use of such an estimator: trending against a baseline
  taken on the same twin, for example after commissioning or a wash.
- The NIS statistics do not change with these mismatches (the same 0 to 2 % of batches
  above the 99.9 % bound as with the exact twin), confirming that they are invisible in the
  residuals, and the reported std (0.02 to 0.06 point) does not cover the bias.

## Sensor faults

Exact twin, evaluation seeds; the truth is a healthy unit in every case except the two
thermocouple faults at base load, where the plant itself overfires but its health is
unchanged. So every error below is a health change invented from a sensor fault. "NIS >
18.5" is the share of batches after the onset whose innovation exceeds the 99.9 % bound
for 4 degrees of freedom (0 to 2 % on healthy runs).

| scenario | mean error (flow, ηc, ηt) | worst error | final change since onset (flow, ηc, ηt) | batches with NIS > 18.5 |
| --- | --- | --- | --- | --- |
| exhaust_tc_drift_base_load | +0.19, +0.04, +0.63 | 0.54, 0.14, 1.13 | +0.30, +0.06, +0.97 | 64 % |
| exhaust_tc_stuck_load_increase | +2.07, +0.40, +7.89 | 2.29, 0.50, 8.06 | +2.07, +0.40, +7.89 | 89 % |
| exhaust_tc_noise | n/a, n/a, n/a | n/a, n/a, n/a | +0.00, +0.00, -0.00 | 27 % |
| power_transducer_bias | -0.17, -0.03, +0.86 | 0.40, 0.12, 1.00 | -0.18, -0.04, +0.85 | 97 % |
| fuel_meter_drift | +0.42, +0.08, -0.19 | 0.85, 0.19, 0.39 | +0.63, +0.13, -0.30 | 84 % |
| cdt_sensor_bias | -0.00, -0.58, +0.40 | 0.08, 0.61, 0.43 | +0.01, -0.57, +0.39 | 1 % |
| cdp_sensor_bias | -2.65, -0.86, +1.68 | 2.85, 0.95, 1.82 | -2.64, -0.86, +1.67 | 100 % |
| slow_fuel_valve_load_steps | +0.00, +0.00, +0.00 | 0.08, 0.04, 0.05 | -0.00, -0.00, +0.00 | 0 % |

What happens, and why (for the static biases on power, discharge temperature and
discharge pressure, the linear map of a reading error into health from the same weighted
fit as `steady_bias` matches the filter's change to 0.01 point):

- **Power transducer +1 MW.** Power is the model's input, so the twin is asked for 1 MW
  more than the unit makes and finds a unit that needs too little fuel and runs too cool:
  turbine efficiency +0.86 point (an apparent improvement), with a clear residual (97 % of
  batches flagged).
- **Fuel meter drift.** Fuel is a predicted output; the estimate drifts to +0.6 % flow and
  −0.3 point ηt by the end, but most of the error stays in the residual (84 % flagged).
- **Discharge temperature +3.5 K.** Absorbed completely as compressor efficiency −0.57 and
  turbine efficiency +0.39 point, with **no** residual (1 % flagged, the healthy rate). With
  four readings and three parameters there is one redundant direction, and a discharge
  temperature bias is not in it. This fault is indistinguishable from degradation for this
  estimator, and so is any combination of reading errors in the same span.
- **Discharge pressure −35 kPa** (what 3 % fouling does to the true value). Read as −2.6 %
  flow, −0.86 point ηc and +1.7 point ηt (not as fouling, whose ηt is zero), and every batch
  is flagged: the residual makes this one detectable.
- **Thermocouple drift and stuck at base load.** The low reading makes the plant overfire
  and the twin sees a reading lower than the truth: turbine efficiency +1.0 point by the
  end of the drift, +7.9 points with the stuck thermocouple after the load increase, with
  large residuals (64 % and 89 % flagged).
- **Thermocouple noise (3 K).** The exhaust spread keeps the steady-state gate shut from
  18 s after the onset to the end of the run, so the filter holds its last (correct)
  estimate. Safe, but blind (the error columns are empty because no steady estimate
  falls in the scoring window).
- **Slow fuel valve.** No steady-state effect, no change in the estimate.

The estimator does not reject sensor faults itself; separating them is the detectors' job.
What it gives a detector is `last_innovation` and `last_nis`: the faults that leave a
residual are visible there, the discharge-temperature bias is not.

## Verdict on the ±0.3 point target

The target was fouling efficiency loss within ±0.3 efficiency points after convergence.

- **Exact twin (circular): met with a wide margin.** Worst compressor-efficiency error after
  convergence 0.06 point over the six degradation scenarios and five seeds each, converged
  within about 2 minutes of a step.
- **Mismatched twin, absolute value: met for the combined calibration error (worst 0.23
  point), not met for a 1 kPa barometric error (mean 0.33, worst 0.39 point).** For turbine
  efficiency (erosion) the absolute target is missed by both mismatches (0.42 to 0.47 point
  mean). The absolute accuracy is set by the twin's calibration, not by the estimator:
  roughly 1:1 from calibration error to health error, and the root-sum-square budget of
  the stated calibration errors is 0.16 point for ηc and 0.39 point for ηt before any
  barometric error.
- **Mismatched twin, change since a healthy baseline: met with a wide margin** (0.02 point
  on ηc and ηt, 0.05 % on flow capacity in every scenario with a baseline).

So the thesis claim that can be supported is the relative one: degradation since a known
healthy baseline is tracked to well within ±0.3 point despite plausible calibration errors.
An absolute ±0.3 point claim cannot be made on this evidence: it depends on calibration
quality and site conditions (barometric pressure in particular) that the estimator cannot
check from its own residuals.

## Limits and open problems

- **All data is simulated**, and the plant and the twin share their structure (same cycle
  model, same map assumptions, same linear health superposition). The mismatch experiment
  only perturbs parameters inside that structure. Structural error (a real compressor map,
  IGV effects on pressure ratio, load-dependent losses, combustor efficiency, fuel
  composition, humidity, sensor dynamics) is not covered, and is likely larger.
- **Ambient pressure is not in the observation.** A 1 kPa barometric change moves
  compressor efficiency by 0.33 point and flow capacity by 1.07 %. A real deployment needs
  a barometer input (see the request below) or must re-baseline often.
- **Discharge pressure is the only flow-capacity channel**, so anything that biases it
  (inlet pressure loss, barometer, the CDP transducer) goes straight into flow capacity and
  from there into the other two parameters.
- **One redundant direction only.** Four readings for three parameters leave one residual
  direction, so many sensor faults and calibration errors are absorbed into health without
  a trace (the discharge-temperature bias, the pressure-loss errors). More instruments
  (inlet pressure drop, compressor inlet temperature, a second exhaust measurement) would
  add redundancy.
- **The fouling model's 2:1 flow-to-efficiency ratio is not used**, which is right for an
  estimator but means flow capacity and compressor efficiency are estimated separately;
  imposing the ratio would sharpen the fouling estimate if it were known to hold.
- **The process noise is tuned to the bank's accelerated degradation** (2 to 3 % per hour).
  Real fouling is orders of magnitude slower; q would need re-tuning against noise over
  weeks, and the steady gate, sensor drift and ambient seasons would matter far more.
- **Reported std covers noise only.** It is 0.02 to 0.06 point and says nothing about
  calibration bias; a coverage test against the truth fails with any mismatch. An honest
  absolute uncertainty would add a calibration term of the order of the bias budget above.
- **The estimator stops at the gate.** It learns nothing during transients, at low load
  outside the gate's limits or while a noisy thermocouple keeps the gate shut; the
  steady-state twin has no dynamics to do better.
- **Few seeds.** Five evaluation runs per scenario: enough to show the bias and noise level
  (both are much smaller than the tolerances), not enough for tail statistics.

**Requested changes to the shared foundation** (not made here):

1. Add `ambient_pressure_kpa` to `Observation` (and a matching session input and plant
   effect) so that the barometric error above can be measured instead of assumed away.
2. Optionally expose the gate's open/closed reason; the estimator currently cannot tell a
   noisy sensor from a transient when the gate stays shut.

## Reproducing

```bash
PYTHONPATH=src python -m turbineiq.estimation.observability          # observability tables
PYTHONPATH=src python -m turbineiq.estimation.mismatch --bias        # steady bias table
PYTHONPATH=src python -m turbineiq.estimation.mismatch --cache <dir> \
    --mismatch none combined barometer                               # results tables
python -m pytest tests/test_estimation_ukf.py -q
```

The results driver simulates every (scenario, evaluation seed) pair that is not in the
cache directory (95 runs, about 20 s each); `--only <id> ...` restricts it.
