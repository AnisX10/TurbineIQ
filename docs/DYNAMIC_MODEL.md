# Dynamic model and operating-session API

Step 2 of the thesis roadmap (`docs/THESIS_ROADMAP.md`, WP2 and the first part of WP3):
a dynamic plant that an operator can start, load, unload, stop and trip, driven by the
calibrated cycle of `docs/CALIBRATION.md`. It is a **simulated** plant. Nothing connects
to a real machine, and the parameters below are illustrative, not identified for a 6B.03.

## Structure

```
 load setpoint ─ramp─► governor (droop, schedule + trim) ┐
 exhaust temperature ─► temperature control (PI)         ├─ min select ─► FSR
 rotor acceleration ──► acceleration control (I)         ┘
 FSR ─► valve lag ─► fuel-system lag ─► combustor lag ─► [maps: shaft power, exhaust T]
 shaft power − load ─► rotor (2H) ─► speed          exhaust T ─► gas lag ─► thermocouple lag
```

This is the block structure of Rowen (1983). Rowen's generic closed-form torque and
exhaust-temperature functions are replaced by `simulation/maps.py`, which tabulates shaft
power and exhaust temperature against speed, IGV position and fuel flow from
`simulate_real_gas_cycle`. At rated speed, open IGV and rated fuel the maps return the
calibrated 45.0 MW, 561 C point exactly.

Off-design assumptions in the maps (illustrative; not validated against 6B.03 data):
air flow scales with speed, IGV factor (0.7 closed to 1.0 open) and inlet density;
pressure ratio follows from compressor work scaling with N^2; polytropic efficiencies,
cooling fraction and losses stay at their calibrated values; the turbine is not choked.

Unit states: standstill, crank, purge, ignition, warm-up, accelerate, full speed no load,
loaded, unloading, cool-down, coast-down, tripped. Start-up timings, the ignition fuel
level and the starter are illustrative.

Protections (thresholds are labelled assumptions, not OEM limits): overspeed 110 percent,
underspeed 90 percent while loaded, exhaust over-temperature 50 K above the calibrated
rated exhaust temperature (the temperature control limit is 10 K above), manual emergency
trip. Flame-loss detection is not modelled.

Grid: `infinite_bus` (speed is the grid frequency while the breaker is closed; droop
responds to frequency events) or `island` (a consumer with load damping; the rotor
integrates and the governor sets the frequency).

## What the tests establish

`tests/test_simulation.py`, `tests/test_simulation_api.py`:

- Maps agree with a direct cycle solution at off-design points (power within 1 percent of
  rated, exhaust temperature within 6 K).
- Steady states at 25, 50, 75 and 100 percent load reproduce the setpoint within 0.2
  percent and agree with the cycle model at the same fuel flow (power within 0.3 percent,
  exhaust temperature within 2 K). 100 percent is 45.0 MW and 561 C.
- Measured with the default parameters: crank to full speed no load in 226 s and
  synchronised at 236 s; a 20 to 40 MW step (120 MW/min ramp limit) reaches 39 MW after
  13.6 s with no overshoot; load rejection from 45 MW peaks at 107.0 percent speed and
  recovers without a trip; an emergency trip from 45 MW peaks at 105.5 percent and the
  rotor is below 3 percent speed after about 12 minutes; a -0.5 Hz grid event gives the
  4 percent droop response (+11.2 MW); an island load step from 20 to 30 MW dips speed to
  98.2 percent and settles at 99.1 percent (droop offset) until the setpoint is raised.
- On a 40 C day the unit is temperature limited at 38.4 MW (14.6 percent below rated),
  with a measured exhaust peak 12 to 18 K above the control limit and no trip. With the
  temperature loop disabled it trips on over-temperature.
- The rotor energy balance d(H N^2)/dt = P_shaft - P_load holds over an island load step.
- Replaying an event log reproduces the run bit-for-bit (SHA-256 of the state trace,
  including seeded measurement noise). That holds on the same machine and Python build;
  floating-point results can differ across platforms.

## What is not established

- **No comparison with Rowen's published responses has been made.** The structure and the
  order of magnitude of the time constants follow Rowen (1983), but I did not have the
  paper's figures to compare against, so "qualitatively matches Rowen" is not yet shown.
  The behaviour above is physically plausible, not validated.
- Part-load fuel, heat rate and exhaust temperature are consequences of the off-design
  assumptions above. No-load losses are not modelled, so full-speed-no-load fuel is 16
  percent of rated and exhaust temperature there is only 163 C; real machines are higher.
  The calibrated drivetrain efficiency (0.942) also absorbs losses that would be load
  dependent.
- Exhaust thermal inertia of the casing is not modelled (only the gas and thermocouple
  lags), so cool-down temperatures fall faster than a real machine's.
- Isochronous governor mode, flame-loss trips, compressor surge and bleed behaviour and
  fuel-gas composition changes are not implemented.
- Temperature and acceleration loops use simple PI structures with conditional tracking;
  gains were tuned for stable behaviour in the tests, not identified.

## Fault and degradation injection

`simulation/faults.py` adds the WP3 fault-injection layer; it creates the ground truth that
WP4 estimators are scored against. All faults are commands, so they are logged and replay
with the rest of the session.

- **Gas-path degradation** changes the plant through three health deltas: compressor flow
  capacity, compressor polytropic efficiency and turbine polytropic efficiency. Compressor
  fouling of `s` percent removes `s` % of flow capacity and `s/2` points of compressor
  efficiency (an assumed 2:1 ratio). With less flow through the same turbine nozzle the
  compressor pressure rise (`PR - 1`) also falls by `s` %, close to a choked nozzle's
  proportional drop near design. Turbine erosion of `s` removes `s` points of turbine
  efficiency (the flow-capacity increase of real erosion is not modelled). Limits: 10 %
  fouling, 5 points erosion, growth up to 10 %/h, and degradation grows only while air
  flows (speed above 0.5 pu). An offline wash at standstill removes the fouling but keeps
  its growth rate.
- **Degraded maps.** The step-1 cycle is run once per ambient with each health parameter
  moved by a reference amount (flow −4 %, each efficiency −2 points); the degraded maps are
  the clean maps plus the scaled sum of those single-parameter changes. Per-unit bases stay
  those of the clean engine, so a degraded unit shows a real loss. Checked against the
  directly degraded cycle: within 0.0021 pu power and 1.1 K exhaust up to 6 % fouling
  (0.0045 pu and 6.4 K at the 10 % maximum), compressor discharge temperature within 0.5 K
  and pressure exact; the temperature-limited output of a 3 % fouled unit matches the direct
  cycle within 0.5 %. The clean maps are unchanged bit for bit.
- **Sensor faults** on six channels (electrical power, exhaust temperature, speed,
  compressor discharge temperature and pressure, fuel flow): bias, drift (per hour), stuck
  (frozen at the reading when it started) and extra noise. They change the reading, not the
  plant, except that the exhaust thermocouple reading is what the temperature control and
  over-temperature protection use, so a fault there acts on the plant through the control.
  The governor and overspeed protection use the true speed (real units vote redundant
  pickups). Noise faults draw from their own seeded stream.
- **Fuel valve lag** from 0.05 to 5 s (healthy 0.05 s), for a sticky or degraded valve.
- A fault acts from the next simulation step; a snapshot taken between steps still shows the
  previous reading.

Measured signatures (steady state, against the same clean run): 3 % fouling at 35 MW holds
power, raises exhaust temperature by 25.8 K, fuel by 2.0 % and compressor discharge
temperature by 3.4 K, and lowers discharge pressure by 2.8 %; 1.5 points of erosion raises
exhaust temperature by 17.3 K and fuel by 2.7 % with no change at the compressor; on the
temperature limit, 4.5 % fouling costs 10.4 % of output. A low-reading exhaust thermocouple lets the unit overfire without an
alarm. `SCENARIO_BANK.md` has the full table and the seeded scenario bank.

Not established: the 2:1 fouling ratio and the fault magnitudes are assumptions, not OEM or
fleet data. The pressure-ratio response to flow is applied to the health change only: IGV
position and firing temperature still do not change the pressure ratio of the clean engine
(a real unit's discharge pressure falls at part load), and erosion leaves the discharge
pressure unchanged because its flow-capacity increase is not modelled. A single exhaust
reading stands for the thermocouple array (no spread monitoring or voting), and an
open-circuit thermocouple is represented only by a large bias or a stuck reading.

**Trace format 2.** The trace digest now also hashes the four added measured channels, the
controller's thermocouple reading, the health deltas and the valve lag. Runs without faults
have the same physics and the same power and exhaust noise as before (checked bit for bit
against the previous core), but logs recorded before this change do not replay to their old
digest. Logs carry `"trace_format": 2`.

## API

All endpoints are under `/api/sim` and act on an in-memory simulated session (at most 16;
least recently used is evicted). `GET /api/sim/commands` lists commands and parameter types.

| Method and path | Purpose |
| --- | --- |
| `POST /sessions` | Create a session: `seed`, `ambient_temperature_c`, `grid`, `grid_frequency_hz`, `island_load_mw`, `measurement_noise`, `record_interval_s`. |
| `GET /sessions/{id}` | Current state snapshot, including `available_commands`. |
| `POST /sessions/{id}/commands` | `{"command": "...", "params": {...}}`. 422 for a malformed command, 409 when the state does not allow it. Accepted commands are logged at the current step. |
| `POST /sessions/{id}/advance` | `{"seconds": n}` (up to 3600): run faster than real time and return recent samples. |
| `GET /sessions/{id}/stream` | Server-sent events, one snapshot per `interval_s` of simulated time, paced by `speed` (simulated seconds per wall second). Commands can be posted while it runs. |
| `GET /sessions/{id}/history` | Recent samples (recorded at `record_interval_s`). |
| `GET /sessions/{id}/log` | Config, event log, step count and trace digest. |
| `POST /replay` | Re-run a log and report whether its digest matches. |

Commands: `start`, `stop`, `trip`, `reset`, `set_load(mw, ramp_mw_per_min)`,
`set_igv(mode, position)`, `set_ambient(temperature_c)`, `open_breaker` (load rejection),
`close_breaker`, `set_grid_frequency(hz)`, `set_island_load(mw)`, and the fault commands
`inject_degradation(kind, severity_pct, rate_pct_per_h)`, `inject_sensor_fault(channel,
mode, magnitude)`, `set_fuel_valve_lag(tau_s)`, `clear_fault(target)` and
`wash_compressor` (standstill only). Fault commands are accepted in every unit state.
Snapshots carry `measured` (the six instrument readings) and `injected_faults` (ground
truth, which an estimator under test must not read).

Example:

```
curl -X POST localhost:8000/api/sim/sessions -H 'content-type: application/json' -d '{"seed": 1}'
curl -X POST localhost:8000/api/sim/sessions/$ID/commands -d '{"command":"start"}' -H 'content-type: application/json'
curl -X POST localhost:8000/api/sim/sessions/$ID/advance -d '{"seconds":260}' -H 'content-type: application/json'
curl -X POST localhost:8000/api/sim/sessions/$ID/commands -d '{"command":"set_load","params":{"mw":30,"ramp_mw_per_min":20}}' -H 'content-type: application/json'
```

Speed on this container: a session advances about 4,700 steps per second (a step is 50 ms
of simulated time), roughly 235 times real time, so one simulated hour takes about 15 s.

## Operator console

`#/operate` in the web app drives a session through the API above. It creates a unit (seed,
ambient, grid), then offers Start, Normal stop, Reject load (open breaker), Close breaker,
Reset trip and Emergency trip, a load setpoint with ramp, IGV auto/manual, ambient, and grid
frequency (infinite bus) or island load. Buttons are enabled only for commands the server
lists in `available_commands`, which follows the unit state, the breaker and the grid type.
While running, the page polls `advance` every 0.5 s at 1x, 10x or 60x simulated time and
plots power, speed, exhaust temperature (with the limit) and fuel flow. It is labelled
"Simulated plant" throughout; the page, the API and the model are not connected to a real
machine. The page keeps its own short log of commands and alarms; the authoritative event
log with the replay digest is `GET /sessions/{id}/log`.

The fault-injection panel injects degradation (fouling or erosion, with an optional growth
rate), sensor faults (channel, mode, magnitude) and a slow fuel valve, offers an offline
compressor wash at standstill, lists the active faults with a Clear button each, and shows
every instrument's true value next to its reading.

Limits: one session per page load (a reload creates a new unit), no stored sessions, and
the console does not yet show the replay digest.

## Next

Section 10 of the roadmap defines steps 1 to 3. Fault injection and the scenario bank are
step 4 here: the WP3 injection prerequisite of WP4 in the roadmap's timeline. WP4
(health-parameter estimation scored against the bank) follows. Showing the replay digest in
the console is still open.
