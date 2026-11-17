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
- Isochronous governor mode, flame-loss trips, compressor surge and bleed behaviour,
  fuel-gas composition changes and fault injection (WP3 injection panel) are not implemented.
- Temperature and acceleration loops use simple PI structures with conditional tracking;
  gains were tuned for stable behaviour in the tests, not identified.

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
`close_breaker`, `set_grid_frequency(hz)`, `set_island_load(mw)`.

Example:

```
curl -X POST localhost:8000/api/sim/sessions -H 'content-type: application/json' -d '{"seed": 1}'
curl -X POST localhost:8000/api/sim/sessions/$ID/commands -d '{"command":"start"}' -H 'content-type: application/json'
curl -X POST localhost:8000/api/sim/sessions/$ID/advance -d '{"seconds":260}' -H 'content-type: application/json'
curl -X POST localhost:8000/api/sim/sessions/$ID/commands -d '{"command":"set_load","params":{"mw":30,"ramp_mw_per_min":20}}' -H 'content-type: application/json'
```

Speed on this container: a session advances about 4,700 steps per second (a step is 50 ms
of simulated time), roughly 235 times real time, so one simulated hour takes about 15 s.

## Next

Step 3 of the roadmap (assistant benchmark before the RAG upgrade) is next. The operator
console UI (the rest of WP3) and fault injection come after the dynamic core is accepted.
