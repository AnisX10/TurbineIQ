# Seeded scenario bank

The scenario bank is the test set for roadmap WP4 (health estimation and detection) and
WP5 (prescription). Each scenario is a session configuration and a timed command script
run on the simulated plant, so every fault's type, size and onset time is known exactly.
Nothing in it is plant data.

- Definitions: `src/turbineiq/simulation/scenarios.py` (`SCENARIOS`, `run_scenario`,
  `trace_rows`).
- Committed output: `data/scenarios/manifest.json` (scripts, ground-truth fault timeline,
  trace digests, end-state summary) and `data/scenarios/logs/<id>.json` (event logs that
  replay with `turbineiq.simulation.session.replay` or `POST /api/sim/replay`).
- Traces are not committed (about 34 MB for the bank). Regenerate them with
  `PYTHONPATH=src python scripts/build_scenario_bank.py --traces data/scenarios/traces`
  (about six minutes on the development container; `--only <id>` runs one scenario).

## What a trace contains

One row per simulated second. Columns starting `meas_` are what the instruments report
(sensor faults applied, then seeded measurement noise). Columns starting `true_` are
ground truth: true plant values, the injected health deltas (compressor flow capacity,
compressor and turbine polytropic efficiency, as fractions), active sensor faults and the
fuel valve lag. An estimator under test may use the `meas_` columns, the operating inputs
(state, breaker, load setpoint, ambient, IGV) and nothing else.

## Scenarios

All run at 15 C ambient and start from standstill (the unit is loaded at 300 s). Faults
start at 30 minutes (1,800 s) unless stated. Seeds are distinct per scenario.

| Id | Category | Fault (ground truth) |
| --- | --- | --- |
| `clean_part_load` | baseline | None; 35 MW for two hours. Counts false alarms. |
| `clean_base_load` | baseline | None; 47 MW requested, so the unit runs on the exhaust temperature limit (46.1 MW). |
| `clean_load_cycling` | baseline | None; steps between 25 and 45 MW every 20 minutes. |
| `clean_ambient_swing` | baseline | None; ambient steps 15, 20, 25, 18, 10 C at 35 MW (a confounder). |
| `clean_fast_load_steps` | baseline | None; 120 MW/min load steps (reference for the slow valve). |
| `fouling_step_part_load` | degradation | 3 % compressor fouling at 30 min; 35 MW. |
| `fouling_progressive_base_load` | degradation | Fouling growing 3 %/h from 30 min, on the temperature limit; 4.5 % at the end. |
| `fouling_progressive_ambient_swing` | degradation | Fouling growing 2 %/h while the ambient steps; 3 % at the end. |
| `erosion_step_part_load` | degradation | 1.5 points of turbine erosion at 30 min; 35 MW. |
| `fouling_then_erosion` | degradation | 2 % fouling at 30 min, then 1 point of erosion at 60 min. |
| `fouled_unit_offline_wash` | maintenance | 3 % fouling from the start at 40 MW; stop at 30 min, wash at 60 min, restart. 2.5 h. |
| `exhaust_tc_drift_base_load` | sensor | Exhaust thermocouple drifts −10 K/h from 30 min, at 47 MW requested. |
| `exhaust_tc_stuck_load_increase` | sensor | Exhaust thermocouple sticks at 35 MW; load raised to 47 MW 10 minutes later. |
| `exhaust_tc_noise` | sensor | 3 K extra noise (sigma) on the exhaust thermocouple. |
| `power_transducer_bias` | sensor | Power transducer reads +1 MW; the plant is healthy. |
| `fuel_meter_drift` | sensor | Fuel meter drifts +0.06 kg/s per hour (about 3 %/h); the plant is healthy. |
| `cdt_sensor_bias` | sensor | Compressor discharge temperature reads +9 K, about what 3 % fouling does to the true value. |
| `slow_fuel_valve_load_steps` | actuator | Fuel valve lag rises from 0.05 s to 2.5 s; same load steps as `clean_fast_load_steps`. |

Some pairs are built to look alike so that a detector has to tell a sensor fault from a
component fault: `cdt_sensor_bias` against `fouling_step_part_load`, `power_transducer_bias`
against an output loss, and `fuel_meter_drift` against a heat-rate loss.

## Signatures measured in the bank

Differences of the true values against the matching clean scenario, averaged over the last
10 minutes (or the last 100 s at base load). Measured on the committed runs; they are
properties of this model, not of a real 6B.03.

| Scenario | Power | Exhaust T | Fuel flow | Compressor discharge T | Compressor discharge p |
| --- | --- | --- | --- | --- | --- |
| 3 % fouling, 35 MW | held | +21.6 K | +0.029 kg/s (+1.3 %) | +9.1 K | no change (see limits) |
| 1.5 pt erosion, 35 MW | held | +17.3 K | +0.058 kg/s (+2.7 %) | no change | no change |
| 2 % fouling + 1 pt erosion, 35 MW | held | +26.0 K | +0.058 kg/s | +6.1 K | no change |
| 4.5 % fouling, temperature limit | −3.98 MW (−8.6 %) | on the limit | −0.164 kg/s | +13.5 K | no change |
| TC drift −15 K at the end, 47 MW requested | +0.86 MW | +7.6 K over the limit, reading 7.1 K under it | +0.046 kg/s | no change | no change |
| TC stuck, then 47 MW | +0.86 MW | +7.6 K over the limit, reading 98.5 K below the truth | +0.046 kg/s | no change | no change |

The slow fuel valve has no steady-state effect. During the 120 MW/min load steps the true
power lags the healthy run by up to 4.3 MW and the exhaust temperature by up to 30 K (1 s
samples), so it is visible only in transients.

The two thermocouple scenarios show why the exhaust reading matters: the temperature
control and the over-temperature protection use the faulty reading, so the unit overfires
by 7.6 K without an alarm. A real unit votes several thermocouples and monitors their
spread; this model has one reading, which is a stated simplification.

## Reproducibility

Each log in `logs/` replays to the digest in the manifest. That was checked on the machine
that produced them (CPython 3.13, x86_64 Linux) for two full scenarios, and the test suite
replays a 31-minute run of `fouling_step_part_load` against its own digest. Floating-point
results, and so digests, can differ on another platform or Python build; the physics and
the ground truth do not depend on that.

## Limits

- Degradation is accelerated (percent per hour, not per month), so the bank tests whether
  an estimator follows a trend, not whether it follows one through months of noise and
  seasons.
- Compressor discharge pressure carries no fouling or erosion signature: the cycle model
  sets the pressure ratio from speed alone (see `DYNAMIC_MODEL.md`). On a real unit fouling
  lowers the pressure ratio, so a gas-path method that relies on discharge pressure cannot
  be tested on this bank as it stands.
- The fouling model removes flow capacity and compressor efficiency at a fixed 2:1 ratio
  (an assumed ratio, not identified from data); erosion removes turbine efficiency only.
  The degraded maps are a linear superposition of single-parameter maps, checked against
  the directly degraded cycle to within 0.0014 pu power and 1.2 K up to 6 % fouling.
- One seed per scenario. Detection statistics (false-alarm rate, delay) need repeated
  seeds; `run_scenario` on a copy of a scenario with another seed produces them.
- All runs are at 15 C start ambient on an infinite bus.
