# Degradation and performance forecast (WP4, prediction)

Roadmap WP4 asks the twin to forecast the next hours of performance and degradation with
an uncertainty band, scored by forecast error and by the coverage of the band (a 90 % band
should cover about 90 % of outcomes). This page describes the forecaster in
`src/turbineiq/estimation/forecast.py`, how it was tuned and what it scores.

**All results below are from synthetic estimates**: ground-truth health from the scenario
bank plus noise and a random-walk bias (section 3), not from the health estimator, which
was being built at the same time. They show how the forecaster behaves on inputs with that
error model. They do not show how it will do on the estimator's output.

## 1. Method

**Input.** A series of health estimates, each with a time `t_s`, a mean and a standard
deviation per health parameter (compressor flow capacity, compressor and turbine
polytropic efficiency, as fractions of `Health`). An estimator only produces them at
steady state, so the series has gaps at load changes, ambient steps and shutdowns. Any
object with those three attributes is accepted.

**Trend model.** One local-linear-trend Kalman filter per health parameter, with state
(level, rate) and time in hours. The rate follows a small random walk. Estimates closer
than 60 s to the last one used are skipped. A forecast at horizon `h` is normal with mean
`level + rate * h` and variance

    [1 h] P [1 h]^T  +  q h^3 / 3  +  (rho * std_latest)^2

where `P` is the filter covariance, `q` the rate-walk intensity and the last term the part
of the estimator's error that does not average out (below).

Why a Kalman filter rather than weighted least squares on a sliding window: the filter
takes irregular sampling and gaps without special cases (the prediction over a gap widens
the band by the process noise), it gives the covariance of level and rate directly, and its
forecast variance grows with the horizon in a stated way. A window fit needs a window
length, which is the same trade-off as `q` but without an allowance for the rate changing
within the horizon.

**Rate changes.** In the bank a fault starts growing at once (0 to 3 %/h at 30 minutes). A
rate walk large enough to follow that keeps the band several times wider than needed while
the rate is steady (section 4.3). So the rate walk is small (0.005 per hour per
sqrt(hour) for flow capacity, half that for the efficiencies) and the filter watches an
exponentially weighted mean of its normalised innovations (weight 0.2 for the newest).
When that mean leaves 2.0 of its own standard deviations, the rate variance is increased by
its prior variance (prior std 0.02 per hour for flow, 0.01 for the efficiencies) and the rate is re-learned
from the next estimates. A test checks that a 3 %/h onset is detected within 15 minutes and
the rate learned to within 1 %/h within 25 minutes.

**Steps (an offline wash) and outliers.** An estimate whose innovation is beyond 4
standard deviations is held back. If the next estimate is also beyond on the same side,
the level restarts at the first held estimate and the rate is kept (a wash removes the
fouling, not its cause; `faults.py` keeps the growth rate after a wash). If not, the held
estimate is dropped as an outlier. After a long shutdown the predicted spread is wide
enough to hide a 3 % step, and the update would then read the step as a rate (this
happened in the first version: +3.5 %/h after the restart). So the step test counts at most
600 s of process noise. `reset_level()` does the same restart on request, for a logged
wash. The evaluation uses only the automatic detection.

**The cap.** Fouling stops at 10 % flow capacity (5 points of compressor efficiency) and
erosion at 5 points; `HEALTH_LIMITS` equals these maxima (tested). The band edges are
clipped at the cap and the mean is that of the clipped normal distribution. Health is not
clipped at zero ("no better than new"), because that would make a clean parameter covered
by construction.

**Estimator errors.** Successive estimates from a filter are correlated and part of an
estimator's error (model mismatch, a drifting sensor) does not average out. Each estimate
enters the filter with variance `kappa * std^2` (`kappa = 1`), and the forecast adds
`(rho * std)^2` of the latest estimate (`rho = 1`, section 2).

**Performance.** `forecast_performance` draws an ensemble (200 members, Latin hypercube
sampling per parameter, parameters independent) from the health forecast and runs each
member through `QuasiSteadyTwin` at a fixed operating point: rated speed, IGV open (the
auto schedule opens them from 95 % speed), a reference ambient (15 C, so that degradation
is not mixed with an ambient forecast) and a requested load. The fuel flow is found by
false position on the twin: the fuel that gives the requested power, or, if that would
pass the exhaust temperature control limit (rated exhaust + 10 K, as in the plant), the
fuel that puts the exhaust on the limit. The result is power, fuel flow and exhaust
temperature with a central band from the ensemble quantiles. At base load the band is on
the available power; at part load on fuel flow and exhaust temperature.

**Clock.** In the simulator degradation grows only while air flows. With clock time the
filter assumes it continues through a shutdown, which matters only when the rate is not
zero (in the wash scenario it is zero). Passing operating hours as `t_s` removes this.

## 2. Tuning (seeds 1000-1002)

Settings were chosen on simulation seeds 1000, 1001 and 1002 of the three scenarios, with
10 synthetic-estimate draws per simulation (90 runs). A grid over the rate walk (0.002 to
0.05), `rho` (0 to 1), a level walk (0 or 0.001) and the reopening threshold (2.0 to 3.5,
or off) was scored on coverage and band width of the 90 % band, with the aim of about 90 %
coverage where no fault event is near the forecast and the narrowest band that gives it.
`rho` changes little (the rate-walk term dominates at 60 minutes); `rho = 1` was taken
because in the synthetic input the random-walk bias reaches about the stated std within
two hours. The level walk did not help. On the tuning seeds, 30-minute coverage for flow
capacity in stable periods (defined in section 4) was 0.97 and for compressor efficiency
0.94 (630 forecasts each); at 60 minutes 0.98 and 0.91 (90 each, so roughly ±0.06).

These settings are fitted to the synthetic error model and to the bank's accelerated
rates. They have to be re-tuned on the estimator's output.

## 3. Evaluation set-up

- **Scenarios**: `fouling_progressive_base_load` (fouling grows 3 %/h from 30 min, on the
  exhaust temperature limit), `fouling_progressive_ambient_swing` (2 %/h from 30 min while
  the ambient steps, 35 MW) and `fouled_unit_offline_wash` (3 % fouling, stopped at 30 min,
  washed at 60 min, restarted, 40 MW; 2.5 h).
- **Seeds**: the bank seed and bank seed + 10000 k, k = 1..4, so five simulations per
  scenario. The simulation seed changes the measurement noise and so the steady-state
  windows; the true health path is the same for every seed. Each simulation gets 10
  synthetic-estimate draws (estimate seed = simulation seed x 100 + draw): 150 runs.
- **Synthetic estimates** (`synthetic_estimates`): one estimate every 60 s while the shared
  `SteadyStateGate` is open; mean = true health + random-walk bias + white noise. White
  noise std 0.15 % flow, 0.10 points for each efficiency; the bias walk reaches 0.10 % /
  0.07 points (one std) after one hour and runs through gaps. The stated std is
  `sqrt(noise^2 + walk^2)`: 0.18 % and 0.12 points. No estimator lag, no model mismatch, no
  correlation between parameters.
- **Forecasts**: origins every 5 minutes from 15 minutes after the first estimate, only
  where an estimate arrived in the last 5 minutes (the unit is running steadily); horizons
  30 and 60 minutes; scored against the true health at the target time.
- **Categories** (from the ground-truth event times, used for scoring only): *event in
  horizon* (a fault starts or the wash happens between origin and target: no trend model
  can know), *event 0-10 min ago*, *event 10-30 min ago*, *stable* (no event in the
  30 minutes before the origin nor in the horizon). The fouled unit's initial fouling at
  t = 0 counts as an event; it is long past at every origin.
- **Persistence** is the reference forecast: the latest estimate held constant.

Errors are in percent of flow capacity or in efficiency points (health x 100). Coverage is
given with two standard errors from the spread of per-run coverage (forecasts within a run
are correlated, so runs are the independent units). Reproduce with

    PYTHONPATH=src python -m turbineiq.estimation.forecast --seeds evaluation \
        --traces <folder of <id>.csv and <id>@<seed>.csv> --performance-replicates 2

(missing traces are simulated, about 20 s each; the evaluation takes about ten minutes on
the shared development container). It prints the summaries of 4.1, 4.2 and 4.4 as JSON.
The comparison in 4.3 is `evaluate(config=TrendConfig(rate_walk=Health(0.02, 0.01, 0.01),
rate_change_sigma=math.inf))`, and 4.5 passes `reported_std` or `bias_walk` to
`synthetic_estimates` inside `evaluate_run`.

## 4. Results (synthetic estimates)

### 4.1 Health forecast, three scenarios pooled

Compressor flow capacity (FC) and compressor efficiency (CE). 50 runs per scenario.

| Horizon | Category | Forecasts | MAE FC | MAE CE | Persistence MAE FC | 90 % band width FC | Coverage FC | Coverage CE |
|---|---|---|---|---|---|---|---|---|
| 30 min | stable | 1050 | 0.22 | 0.15 | 0.92 | 1.23 | 0.96 ± 0.02 | 0.94 ± 0.02 |
| 30 min | event 10-30 min ago | 650 | 0.41 | 0.26 | 0.85 | 1.82 | 0.92 ± 0.03 | 0.84 ± 0.04 |
| 30 min | event 0-10 min ago | 200 | 1.26 | 0.62 | 1.27 | 1.34 | 0.12 ± 0.05 | 0.14 ± 0.06 |
| 30 min | event in horizon | 150 | 0.78 | 0.38 | 0.74 | 1.31 | 0.41 ± 0.08 | 0.56 ± 0.08 |
| 30 min | all but event in horizon | 1900 | 0.40 | 0.24 | 0.93 | 1.44 | 0.86 ± 0.02 | 0.82 ± 0.03 |
| 30 min | all | 2050 | 0.42 | 0.25 | 0.92 | 1.43 | 0.82 ± 0.02 | 0.80 ± 0.03 |
| 60 min | stable | 150 | 0.40 | 0.28 | 1.75 | 2.14 | 0.93 ± 0.04 | 0.93 ± 0.04 |
| 60 min | event 10-30 min ago | 600 | 0.77 | 0.47 | 1.74 | 3.40 | 0.90 ± 0.03 | 0.81 ± 0.04 |
| 60 min | event 0-10 min ago | 200 | 2.45 | 1.21 | 2.52 | 2.36 | 0.12 ± 0.05 | 0.08 ± 0.04 |
| 60 min | event in horizon | 200 | 2.66 | 1.31 | 2.64 | 2.29 | 0.04 ± 0.04 | 0.09 ± 0.05 |
| 60 min | all but event in horizon | 950 | 1.06 | 0.60 | 1.91 | 2.98 | 0.74 ± 0.03 | 0.68 ± 0.04 |
| 60 min | all | 1150 | 1.34 | 0.72 | 2.03 | 2.86 | 0.62 ± 0.02 | 0.57 ± 0.03 |

Only one origin per run is "stable" at 60 minutes (the runs are two hours long and the
event is at 30 or 60 minutes), hence 150 forecasts.

Calibration curve, flow and compressor efficiency together (nominal 0.50 / 0.80 / 0.90 /
0.95):

| Horizon | Category | 50 % | 80 % | 90 % | 95 % |
|---|---|---|---|---|---|
| 30 min | stable | 0.58 | 0.88 | 0.95 | 0.98 |
| 60 min | stable | 0.60 | 0.86 | 0.93 | 0.97 |
| 30 min | event 10-30 min ago | 0.52 | 0.80 | 0.88 | 0.91 |
| 60 min | event 10-30 min ago | 0.52 | 0.80 | 0.86 | 0.89 |

Turbine efficiency is zero throughout these scenarios. Its 90 % band (0.7 points wide at
30 minutes, 1.1 at 60) covered 0.96-0.99, and its MAE (0.12-0.18 points) is a little worse
than persistence (0.09-0.10), because the rate term adds noise to a constant.

### 4.2 By scenario (all forecasts without an event in the horizon)

| Scenario | Horizon | MAE FC | Persistence MAE FC | Coverage FC | Coverage CE |
|---|---|---|---|---|---|
| progressive, base load | 30 min | 0.52 | 1.56 | 0.81 ± 0.03 | 0.77 ± 0.03 |
| progressive, base load | 60 min | 1.48 | 3.05 | 0.67 ± 0.04 | 0.61 ± 0.04 |
| progressive, ambient swing | 30 min | 0.43 | 1.02 | 0.78 ± 0.04 | 0.75 ± 0.04 |
| progressive, ambient swing | 60 min | 1.14 | 2.02 | 0.63 ± 0.04 | 0.51 ± 0.05 |
| offline wash | 30 min | 0.22 | 0.16 | 0.98 ± 0.02 | 0.96 ± 0.03 |
| offline wash | 60 min | 0.37 | 0.15 | 1.00 ± 0.01 | 1.00 ± 0.00 |

In the progressive scenarios almost all misses come from the first 10 minutes after the
fault starts: at the origins 30 and 35 minutes into the run the trend has not shown yet
(flow coverage 0.04 and 0.20 at 30 minutes in the base-load runs), at 40 minutes 0.74, and
from 45 minutes on 0.90-1.00. The wash was found as a step in all 50 runs, for both
compressor parameters and at the first estimates after the restart, with no other step and
no outlier in any of the 150 runs. Rate reopenings also fire without cause: about 0.6 to 0.8
per run on turbine efficiency, which never changes; each one widens that band for a few
minutes. After the restart the bands covered; the wash scenario has no trend to
forecast, so persistence is better there, and the bands are wider than needed because the
rate uncertainty grows over the shutdown.

### 4.3 The same filter without rate reopening

A fixed, larger rate walk (0.02 per hour per sqrt(hour), no reopening) was the other
candidate. Same evaluation set:

| Horizon | Category | Width FC (default / fixed) | Coverage FC (default / fixed) | Coverage CE (default / fixed) |
|---|---|---|---|---|
| 30 min | stable | 1.23 / 2.13 | 0.96 / 1.00 | 0.94 / 1.00 |
| 30 min | event 10-30 min ago | 1.82 / 2.33 | 0.92 / 0.98 | 0.84 / 0.97 |
| 30 min | event 0-10 min ago | 1.34 / 2.11 | 0.12 / 0.34 | 0.14 / 0.46 |
| 30 min | all but event in horizon | 1.44 / 2.20 | 0.86 / 0.92 | 0.82 / 0.93 |
| 60 min | stable | 2.14 / 4.79 | 0.93 / 1.00 | 0.93 / 1.00 |
| 60 min | all but event in horizon | 2.98 / 5.02 | 0.74 / 0.90 | 0.68 / 0.90 |

The fixed walk reaches about 90 % pooled coverage, but by being far too wide while the rate
is steady (its 90 % band covers 100 % there, its 50 % band 84 % at 30 minutes and 96 % at
60) while still missing most forecasts made just after an onset. The pooled number then
depends on how often faults start in the test set, which in the bank is unrealistically
often. The default was chosen for calibration where the model holds and a sharper band;
its pooled coverage is below nominal for the reason in 4.2.

### 4.4 Performance forecast

Two of the ten draws per simulation, 200-member ensembles, at 15 C: base load (47 MW
requested, on the exhaust temperature limit) for the base-load scenario, 35 MW and 40 MW
for the others. "Truth" is the twin at the true health at the target time, so this scores
the propagation of the health forecast, not the plant's transients.

| Scenario | Quantity | Horizon | Category | Forecasts | MAE | 90 % width | Coverage |
|---|---|---|---|---|---|---|---|
| base load | available power, MW | 30 min | stable | 70 | 0.23 | 1.19 | 0.97 ± 0.04 |
| base load | available power, MW | 30 min | all but event in horizon | 130 | 0.56 | 1.47 | 0.76 ± 0.05 |
| base load | available power, MW | 60 min | all but event in horizon | 70 | 1.56 | 2.87 | 0.56 ± 0.09 |
| ambient swing | fuel at 35 MW, kg/s | 30 min | all but event in horizon | 130 | 0.008 | 0.036 | 0.95 ± 0.05 |
| ambient swing | fuel at 35 MW, kg/s | 60 min | all but event in horizon | 70 | 0.020 | 0.066 | 0.76 ± 0.10 |
| ambient swing | exhaust at 35 MW, K | 30 min | all but event in horizon | 130 | 3.1 | 12.3 | 0.85 ± 0.07 |
| ambient swing | exhaust at 35 MW, K | 60 min | all but event in horizon | 70 | 9.0 | 24.4 | 0.70 ± 0.11 |
| offline wash | fuel at 40 MW, kg/s | 30 min | all but event in horizon | 120 | 0.005 | 0.036 | 0.97 ± 0.05 |
| offline wash | exhaust at 40 MW, K | 30 min | all but event in horizon | 120 | 1.8 | 11.4 | 0.95 ± 0.08 |
| offline wash | exhaust at 40 MW, K | 60 min | all but event in horizon | 50 | 2.6 | 18.1 | 0.98 ± 0.04 |

The performance bands inherit the health bands: well covered where the health forecast is,
under-covered after an onset. With 10-70 forecasts per row these coverages are rough.

### 4.5 Sensitivity to the estimator's stated uncertainty

The same evaluation with three draws per simulation (45 runs per case), flow capacity and
compressor efficiency pooled, default settings (not re-tuned):

| Synthetic input | Horizon | Coverage, stable | MAE, stable | Coverage, all but event in horizon |
|---|---|---|---|---|
| as in section 3 | 30 min | 0.96 | 0.18 | 0.84 |
| as in section 3 | 60 min | 0.93 | 0.33 | 0.72 |
| stated std half the actual error | 30 min | 0.82 | 0.33 | 0.77 |
| stated std half the actual error | 60 min | 0.86 | 0.63 | 0.74 |
| stated std twice the actual error | 30 min | 0.99 | 0.19 | 0.84 |
| stated std twice the actual error | 60 min | 0.91 | 0.39 | 0.58 |
| bias walk doubled (and stated) | 30 min | 0.89 | 0.27 | 0.80 |
| bias walk doubled (and stated) | 60 min | 0.93 | 0.45 | 0.68 |

An overconfident estimator (std too small) makes the band too narrow and the error larger,
because the filter then follows noise. An underconfident one keeps the stable band
covering but makes the filter slower to notice an onset, so the 60-minute coverage after
events falls further (0.58). A larger persistent bias, honestly stated, costs accuracy but
little coverage.

## 5. What the accelerated degradation means

The bank grows fouling at 2-3 % per hour; its own documentation says real rates are of the
order of percent per month, about 700 times slower. For these results that means:

- The trend is large against the estimate noise: flow capacity changes 1.5 % in 30 minutes
  against a stated std of 0.18 %. That is why the trend model beats persistence by a factor
  of two to three in the progressive scenarios. At a real rate the change in an hour is a
  few thousandths of a percent, far below the noise; a 30-60 minute forecast is then
  persistence, and its band is set by the estimator's error (the `rho` term), not by the
  trend.
- The same filter applies to the real case only with time scaled: rate walk, rate prior,
  reopening and step settings are per hour and were fitted to hourly rates. Forecasting
  days or weeks ahead from weeks of data is the realistic counterpart of these runs, and
  over weeks the estimator error would include ambient seasons, load patterns and sensor
  drift that a two-hour run does not have.
- Fault events are frequent relative to the run length (one per two hours), so the
  forecasts close to an event are a large share of the total and pull pooled coverage
  down. The stable-period numbers are the ones that transfer.
- The true paths are piecewise linear, which is exactly the local-linear-trend model.
  Fouling on a real unit tends to level off; a linear forecast would then overshoot.

## 6. When the estimator's output replaces the synthetic estimates

- **Stated std**: the band is only as good as the estimator's std. The forecaster uses it
  twice (filter noise and the persistent term); section 4.5 shows the effect of a std that
  is too small. Check the estimator's calibration first (its own normalised errors against
  truth on the tuning seeds).
- **Correlated errors**: a UKF's output is correlated over its own time constant. Re-tune
  `min_interval_s`, `variance_inflation` and `persistent_fraction` from the autocorrelation
  of the estimator's error against truth on the tuning seeds, not from this page.
- **Estimator lag after a step**: the synthetic estimates jump at a wash; a UKF converges
  over some minutes, which the step test may read as a rate. If so, feed the logged wash
  through `reset_level()`, or raise `shift_confirm`.
- **Correlation between parameters**: the forecaster treats the three parameters as
  independent and so does the performance ensemble. A UKF gives a full covariance, and flow
  capacity and compressor efficiency are hard to separate (fouling moves both at 2:1), so
  their errors will be correlated. The performance band could then be too wide or too
  narrow; a joint trend model or sampling from the estimator's covariance would fix it.
- **Ambient-dependent bias**: model mismatch that changes with ambient appears as steps at
  ambient changes, which may trigger step or rate-change detection. The ambient-swing
  scenario is the check.
- **Time base**: pass operating hours if shutdowns are long and the rate is not zero.

## 7. Limits

- All numbers are on synthetic estimates whose error model (white noise plus a random-walk
  bias, honest stated std, no lag) was chosen, not measured.
- The defaults were tuned on the same synthetic error model they are evaluated on (other
  seeds), so the evaluation shows generalisation across noise draws, not across error
  models.
- Forecasts made in the first 10 minutes after a fault starts, or across a fault onset or a
  wash, miss. A trend model cannot do better; a forecast that needs to cover them has to
  include a prior on events (maintenance plans, fault rates), which this one does not.
- Turbine efficiency never changes in these scenarios, so its coverage says little.
- Performance is forecast at fixed reference conditions (15 C, rated speed, IGV open). The
  ambient, load and the plant's response to them are not forecast, and the twin has no
  mismatch to the plant here.
- Coverage intervals assume the runs are independent; the five simulations per scenario
  share the true health path.

## 8. Code and tests

- `src/turbineiq/estimation/forecast.py`: `DegradationForecaster` (`update`, `forecast`,
  `reset_level`), `HealthForecast`, `TrendConfig`, `forecast_performance`,
  `steady_performance`, `OperatingPoint`, `synthetic_estimates` and the evaluation
  (`evaluate_run`, `evaluate`, `summarize_health`, `summarize_performance`, `main`).
- `tests/test_estimation_forecast.py`: trend recovery, skipping, gaps, wash and outliers,
  logged wash, the cap, calibration when the error model holds, rate reopening, the
  synthetic generator, evaluation labels and the performance propagation (about 5 s).
