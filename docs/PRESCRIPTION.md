# Prescriptive and autonomous layer (WP5)

This page describes how the layer in `src/turbineiq/prescription/` works and which choices
it rests on. Results are in [WP5_RESULTS.md](WP5_RESULTS.md). Everything runs against the
simulated plant; nothing here is connected to a real machine, and the limits are labelled
assumptions, not OEM values.

## What the layer may see

The layer reads a session snapshot once per simulated second but passes on only the
instrument readings (`measured`, with sensor faults and noise) and the operating inputs a
control system knows: unit state, breaker, load setpoint, IGV position and mode, ambient.
The injected ground truth in the snapshot (`injected_faults`, true temperatures) is never
read. It is used only by the scoring in `runner.py`.

## The twin and its mismatch

The twin is built on a perturbed copy of the calibrated engine: the WP4 `combined` mismatch
(drivetrain efficiency 0.5 % lower, inlet and combustor pressure losses 0.5 point higher,
air flow 1 % lower). So the twin is wrong in a known way, and the plant and twin are not the
same model with the same parameters (roadmap section 3.2). `SupervisorConfig(twin_engine=None)`
gives the exact twin, which is useful only as a circular reference.

`monitor.py` keeps four things on top of it:

- **Health estimate.** This is the WP4 unscented Kalman filter (power input), with the exhaust
  temperature taken out of its measurements. Health then comes from fuel flow and compressor
  discharge temperature and pressure, so a failed exhaust thermocouple cannot drag the
  estimate along. On the bank with the mismatched twin, the estimate with and without the
  exhaust channel agrees within 0.001 on the fouling and erosion steps. On the
  thermocouple-drift scenario, the exhaust-free estimate moves about a third as far
  (turbine efficiency +0.004 against +0.014).
- **Degradation forecaster.** This is the WP4 trend model on the estimates. It gives the
  fouling growth rate used by the wash decision.
- **Steady residuals** of each channel against the quasi-steady twin at the estimated
  health, averaged over 120 s of steady operation. Two quantities come from them:
  - the *model mismatch index*: the largest mean residual of the power, compressor discharge
    temperature and pressure channels, in units of one reading's noise;
  - the *thermocouple check*: the mean exhaust residual. The thermocouple is distrusted when
    the mean exhaust residual exceeds 12 K, or its scatter exceeds 2 K (instrument noise is
    0.5 K), for 30 steady seconds while the mismatch index stays below 4. That last
    condition is what keeps a twin that has drifted as a whole from being blamed on the
    sensor.
- **Model exhaust temperature.** This is the twin's exhaust prediction from measured fuel
  flow, speed, IGV and ambient at the estimated health, passed through a 3 s lag standing in
  for the thermocouple's.

## The forward twin

`twin.predictive_twin` builds a dynamic `TwinPlant` for what-if runs. It uses only:

- **Control-system state** copied from the plant: unit state, breaker, setpoints, ramp rate,
  IGV mode and position, controller integrators and limits.
- **The twin's engine model** at the estimated health.
- **Measured fuel flow and speed.** The exhaust temperature is the twin's own value at that
  fuel flow.

Injected degradation, sensor faults and a slow fuel valve are not copied. The twin settles
for 30 s on its own engine before a candidate is applied. `forward_run` applies the
candidate commands to a copy and simulates the horizon at the plant's 50 ms step.

## Decision problems

**(a) Load setpoint and IGV (`load_setpoint`).** The dispatcher gives a demand *d*, and the
band is *d* ± 2 MW. Candidates are the loads {*d* − 2, *d*, *d* + 2} (those above minimum
load) crossed with the IGV settings {auto, 80, 60, 40, 20, 0 % open}. Each candidate is first
evaluated on the steady twin (fuel, exhaust and heat rate at rated speed). Candidates whose
steady exhaust would be within the control margin, the twin's exhaust uncertainty and a
further 3 K of the temperature control limit are screened out.

The default objective (`track_demand`) holds the demand and picks the IGV setting with the
lowest heat rate. It uses the rest of the band only when the demand cannot be reached. The
alternative (`heat_rate`) takes the lowest heat rate anywhere in the band, which tends to
sit at one edge.

A recommendation is made when the best candidate improves heat rate by at least 0.15 % or
moves the setpoint towards the demand. No recommendation is made when the unit already runs
on the exhaust temperature limit while delivering inside the band, because that is normal
base-load operation.

When no candidate passes the screen while the IGV is in a position the layer set, the layer
proposes returning the IGV to its auto schedule at the present setpoint (the fixed policy)
instead of proposing nothing. Without this, a stuck thermocouple and a 3× mismatched twin
left the unit overfiring at IGV 40 % until it tripped (see `docs/WP5_RESULTS.md`, section 5.2).

Reviews happen every 300 s, on a demand change and on an ambient change. Closing the IGV at
part load lowers heat rate in this model: at 25 MW from 11,937 to 11,125 kJ/kWh with the
IGV fully closed. That is a property of the simulated maps, not a measured 6B.03 figure.

**(b) Offline compressor wash (`compressor_wash`).** The excess fuel cost rate *c* is the
twin's extra fuel at the present power and IGV with the estimated health, against the same
health with the compressor clean. Its growth *a* comes from the forecaster's fouling rate.
For a loss rate growing linearly between washes, the average cost per hour of the best wash
cycle is √(2*Wa*), at an interval of √(2*W*/*a*), where *W* is the cost of one wash. The
layer recommends a wash when *c* ≥ max(√(2*Wa*), *W*/*H*), with *H* a planning horizon, so a
fouling level that does not grow is still washed if it pays back within *H*. The fouling
estimate must also exceed 0.5 % flow-capacity loss, which is beyond the mismatch bias.

The bank's degradation runs about 720 times faster than in service (percent per hour, not
per month). So *W* and *H* are divided by that factor (`Economics.time_compression`), which
scales the optimal interval by the same factor. The default prices (8 $/GJ fuel, 30,000 $
per wash including the outage) are illustrative.

**(c) Exhaust feedback (`exhaust_feedback`).** When the thermocouple is distrusted, the
layer proposes switching the temperature control and over-temperature protection to the
model exhaust temperature. This uses the plant command `set_exhaust_feedback`. Once switched,
the value is refreshed every 5 s. `Supervisor.trust_thermocouple()` returns control to the
thermocouple after a repair.

## The guard

`guard.py` is deterministic and does not optimise. Each verdict lists named checks with the
value found, the limit and the result:

| Group | Checks |
| --- | --- |
| Twin trust | unit loaded; health estimate has had steady updates; health standard deviation ≤ (0.006, 0.003, 0.003); model mismatch index ≤ 3 |
| Rate limits | setpoint step ≤ 6 MW; ramp ≤ 10 MW/min; at least 120 s since the last automatic load action |
| Forward run (load and IGV) | no trip; peak exhaust ≥ 25 K below the trip threshold; transient peak ≤ control limit + 3 K; settled exhaust ≥ 5 K plus the twin's exhaust uncertainty below the control limit; speed within 0.98–1.02 pu; settled power within 0.6 MW of the target and inside the band; the temperature control acts on a trusted or substituted exhaust value |
| Fallback to IGV auto | no trip; settled exhaust no hotter than a forward run of holding (or under the limit); speed within 0.98–1.02 pu. The start state is already outside the screen, so the full forward set would reject every corrective move. |
| Exhaust substitute | twin trust, and a model exhaust value in range |
| Wash | twin trust, and `autonomous_wash` (off by default: a shutdown changes availability, so it stays with the operator) |

Only the candidate the layer proposes is run forward, with up to three in ranked order until
one passes. The lower-ranked candidates are screened on the steady twin only, which keeps a
review to about a second. This departs from the roadmap's wording, which has every
candidate run forward.

## Modes and the decision log

- **Manual**: the layer estimates and monitors but proposes nothing.
- **Advisory** (level 4): every proposal waits for the operator (`accept` or `reject`). One
  the guard rejected is marked `escalated` with the failed checks.
- **Autonomous** (level 5): a guard-approved proposal is applied at once (`applied`). One the
  guard rejects is `escalated` and waits for the operator.

Each `Decision` records:
- the time, problem, mode and summary;
- the commands;
- the objective values, including the candidates checked forward;
- the full guard verdict, including the forward-run summary;
- the status (`applied`, `pending`, `escalated`, `accepted`, `rejected`, `expired` or
  `superseded`), the reason, and who resolved it.

An open load recommendation is replaced only when a newer one differs in its actions or its
verdict. A load recommendation accepted after the demand changed expires instead of being
applied.

## The simulated operator

`runner.OperatorModel` is an assumption, not a human-factors model. It handles each open
recommendation after a fixed delay (300 s by default). It accepts the ones the guard
approved and declines the ones it escalated, except the wash, which the guard always
escalates because it is a shutdown. The dispatcher's load requests in a scenario script
are applied as the operator would apply them in every mode, and they also become the
layer's demand.

## No language model in the loop

No part of this layer calls a language model. The roadmap's assistant tool
`recommend_action` (WP6) should call `Supervisor` and report its verdict. It should not
generate commands of its own.
