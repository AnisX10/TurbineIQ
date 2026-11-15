# Cycle model calibration to the published GE 6B.03 point

Status: step 1 of `THESIS_ROADMAP.md`. Code: `src/turbineiq/engineering/real_gas.py`. Evidence: `docs/evidence/calibration/`. Scripts: `scripts/export_nasa_coefficients.py`, `scripts/calibrate_cycle.py`, `scripts/ambient_sweep.py`.

## What changed

The constant-property model in `core.py` gives about 25.5 MW against the published 45 MW and cannot be tuned to match (see `GE_6B03_PUBLIC_DATA_REVIEW.md`). The new `real_gas.py` model adds what that review listed as missing:

- temperature-dependent ideal-gas properties (NASA-7 polynomials for N2, O2, Ar, CO2, H2O, exported from the GRI-Mech 3.0 data in Cantera into `data/nasa7_species.json`);
- a combustor energy balance on sensible enthalpy and fuel lower heating value (methane, 50 MJ/kg), with burned-gas composition computed from the fuel flow;
- a cooling-flow fraction that bypasses the combustor and is mixed in before the turbine;
- fixed inlet (1%), combustor (4%) and exhaust (1%) pressure losses;
- compression and expansion integrated in 60 small steps with a polytropic efficiency.

The old model is unchanged and still feeds the API and the synthetic twin. Switching the twin to the new model is a separate step.

## The fit

Targets (GE Vernova 2025 catalog, ISO, natural gas): 45 MW net, 33.4% LHV efficiency, 561 °C exhaust, 145.1 kg/s exhaust flow; pressure ratio fixed at 12.8.

Free parameters: air mass flow, effective firing temperature, one polytropic efficiency shared by compressor and turbine, and drivetrain efficiency. Four parameters, four targets.

| Parameter | Fitted value (8% cooling flow) |
| --- | ---: |
| Air mass flow | 142.4 kg/s |
| Effective firing temperature | 1,463 K |
| Polytropic efficiency (compressor and turbine) | 0.874 |
| Drivetrain efficiency (mechanical, gearbox, generator, auxiliaries) | 0.942 |

At the fitted point the model gives 45.00 MW, 33.40%, 561.0 °C, 145.1 kg/s and a heat rate of 10,778 kJ/kWh (published 10,779). **That agreement is by construction, not validation.**

## What the fit does not establish

1. **Four targets fix four parameters, so a good fit says nothing about model correctness.** Only the checks below can.
2. **The published set forced an unusually low drivetrain efficiency.** With a fixed 0.965 (typical for mechanical, gearbox and generator losses) and separate compressor and turbine efficiencies, every target missed by about 0.3% and no parameter choice closed the gap, because the targets are tied together by the overall energy balance. The fit needs about 2.4 points of extra loss. Plausible explanations: auxiliary load in the "net" rating, larger inlet/exhaust losses, a lower real fuel LHV than pure methane, or catalog rounding. The data cannot tell them apart, so the single parameter absorbs them. It must not be read as a measured drivetrain efficiency.
3. **The cooling-flow fraction is not identifiable.** The fit reproduces the targets exactly for any value from 0 to 16%; only the effective firing temperature changes (1,405 K at 0%, 1,463 K at 8%, 1,530 K at 16%; `calibration.json`). Efficiencies and air flow do not move. So the effective firing temperature is uncertain by roughly ±60 K and is **not** an OEM firing temperature.
4. **The compressor/turbine efficiency split is not identifiable**, so one shared value is fitted.
5. Dry air, no humidity, no dissociation, methane as fuel.

## Checks that are not fitting

- **Heat rate**: 10,778 vs the published 10,779 kJ/kWh. This is only a consistency check, because it follows from output and efficiency.
- **Ambient trend** (`ambient_sweep.json`, mass flow scaled with inlet density, firing temperature held constant): output about 3.6% lower at 20 °C and 13.5% lower at 35 °C than at ISO; heat rate 0.7% and 2.9% higher; exhaust flow falls. The signs match the behaviour GER-3567 describes for a single-shaft machine (output and exhaust flow fall, heat rate rises as compressor inlet temperature rises). **The magnitudes are not checked**: in the text of GER-3567H (10/00) the ambient effect appears only in Figure 9, with no numbers, and this review could not read values from the figure. Exhaust temperature stays almost flat here because firing temperature is held constant, whereas real machines run an exhaust-temperature control curve; that is a known simplification.
- **Unit tests** (`tests/test_real_gas.py`) cover the fitted point, energy balance, ambient signs, compressor-degradation direction, and air cp at 300 K and 1000 K.

## What is needed to turn this into validation

- Numeric ambient and part-load correction curves for a 6B-class machine, read from the GER-3567 figures with a digitizer and stated with their reading error, or from another public source.
- An independent cross-check of one point in pyCycle or TESPy.
- Parameter uncertainty (for example a profile over cooling flow, losses and LHV) carried into later results as error bands.

## Reproduce

```sh
pip install cantera scipy
python scripts/export_nasa_coefficients.py src/turbineiq/engineering/data/nasa7_species.json
PYTHONPATH=src python scripts/calibrate_cycle.py docs/evidence/calibration/calibration.json
PYTHONPATH=src python scripts/ambient_sweep.py docs/evidence/calibration/ambient_sweep.json
```

Only numpy is needed at run time; scipy is an optional `calibration` extra and Cantera is needed only to regenerate the species file.
