# Cycle model calibration to the published GE 6B.03 point

Status: step 1 of `THESIS_ROADMAP.md`. Code: `src/turbineiq/engineering/real_gas.py`. Evidence: `docs/evidence/calibration/`. Scripts: `export_nasa_coefficients.py`, `calibrate_cycle.py`, `ambient_sweep.py`, `calibration_uncertainty.py`, `crosscheck_cantera.py`, `crosscheck_coolprop.py`, `digitize_ger3567_fig9.py` in `scripts/`.

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
2. **The published set implies about 5.8% of shaft power lost between shaft and net output.** A fixed 0.965 drivetrain (typical for mechanical, gearbox and generator losses) with separate compressor and turbine efficiencies missed every target by about 0.3%, because the targets are tied together by the overall energy balance. The refit gives 0.942. This is robust: across the 45-case grid in `uncertainty.json` (cooling flow, inlet/exhaust loss 0.5 to 2%, fuel LHV 47 to 50 MJ/kg) it stays between 0.942 and 0.946, so it is not an artefact of those assumptions. It is plausible as machine losses of roughly 3.5% plus a few percent of auxiliary power and heat losses in a "net" rating, but the public data cannot separate these, so the single parameter absorbs them and must not be read as a measured drivetrain efficiency.
3. **The cooling-flow fraction is not identifiable.** The fit reproduces the targets exactly for any value from 0 to 16%; only the effective firing temperature changes (1,405 K at 0%, 1,463 K at 8%, 1,530 K at 16%; `calibration.json`). Efficiencies and air flow do not move. Across the full grid in `uncertainty.json` the effective firing temperature spans 1,401 to 1,531 K, about ±65 K. It is **not** an OEM firing temperature.
4. **The compressor/turbine efficiency split is not identifiable**, so one shared value is fitted.
5. Dry air, no humidity, no dissociation, methane as fuel.

## Checks that are not fitting

**Implementation and property data (done).**

- **Cantera cross-check** (`crosscheck_cantera.json`): the same cycle with Cantera thermo objects and equilibrium combustion products (so dissociation is included). Net output differs by +0.02%, exhaust temperature by +0.04 K, exhaust flow by +0.005%, and efficiency by 0.2% relative (fuel flow +0.26%). This checks my mixture, combustion and integration code, not the data, because both use the same GRI-Mech NASA-7 polynomials.
- **CoolProp cross-check** (`crosscheck_coolprop.json`): CoolProp's Helmholtz-energy mixture properties are independent of the NASA polynomials. Specific heat agrees within 0.4% at 300 K and within 0.11% from 500 to 1,400 K for dry air and for a burned-gas composition. Enthalpy differences from 400 K agree within 0.13%. Polytropic compression of air at the fitted efficiency gives a discharge temperature 0.8 K higher and compression work 0.24% higher in CoolProp. Property data are therefore not a significant error source here.
- **Heat rate** 10,778 vs the published 10,779 kJ/kWh follows from output and efficiency and is only a consistency check.
- **Unit tests** (`tests/test_real_gas.py`): fitted point, energy balance, ambient signs, compressor-degradation direction, air cp, input validation.

**Ambient trend against GER-3567H Figure 9 (done, generic family only).** The author supplied the GER-3567H PDF. Figure 9 gives output, heat rate and exhaust flow of a single-shaft **MS7001** against compressor inlet temperature as straight lines normalised to design. I digitized it by pixel colour with the axes calibrated from the plot frame (`scripts/digitize_ger3567_fig9.py`, `ger3567_fig9.json`; reading error about ±0.4 percentage points). The model uses mass flow scaled with inlet density and constant firing temperature (`ambient_sweep.json`). Relative to ISO (15 °C = 100):

| Ambient | Output GER / model | Heat rate GER / model | Exhaust flow GER / model |
| ---: | ---: | ---: | ---: |
| 0 °C | 109.3 / 111.5 | 97.9 / 98.1 | 106.2 / 105.6 |
| 25 °C | 93.8 / 93.0 | 101.4 / 101.4 | 95.8 / 96.6 |
| 35 °C | 87.6 / 86.5 | 102.9 / 102.9 | 91.7 / 93.4 |
| 45 °C | 81.4 / 80.3 | 104.3 / 104.5 | 87.5 / 90.4 |

Over 0 to 45 °C the RMS difference is 1.1 points for output, 0.12 for heat rate and 1.6 for exhaust flow. The largest gaps are output at 0 °C (+2.2 points, the model gains more in the cold) and exhaust flow at 45 °C (+2.9 points, GE's flow falls faster). Heat rate agrees almost exactly; I did not tune toward this, and I would not lean on that coincidence. A 20-case regression test keeps the model within 2.5, 1.0 and 3.5 points on output, heat rate and flow.

How far this goes: it checks the **shape of the ambient response of the model structure** against a published curve for the same machine family. It does not validate the 6B.03: GE states that "each turbine model has its own temperature-effect curve". The refit grid (`uncertainty.json`) moves the 35 °C output change only between -14.1% and -13.1%, so it cannot explain a gap of this size by itself; the remaining difference is most plausibly the model's constant firing temperature and fixed-volume-flow assumptions versus GE's control schedule. The original GER-3567H and its figure are GE's copyright and are not committed; only derived values are.

Exhaust temperature stays almost flat in the model because firing temperature is held constant, whereas real machines follow an exhaust-temperature control curve. Figure 9 does not show exhaust temperature, so this simplification remains unchecked.

## What is still needed

- A 6B-specific ambient curve (GER-3567 Figure 9 is MS7001) and part-load behaviour; Figure 9 gives neither exhaust temperature nor part load.
- Digitizing with a stated error from more than one figure (for example the part-load figures in other GE references) if part-load operation is used.
- Parameter uncertainty carried into every later result as an error band (the grid in `uncertainty.json` is the starting point).

## Reproduce

```sh
pip install -e '.[calibration]'
python scripts/export_nasa_coefficients.py src/turbineiq/engineering/data/nasa7_species.json
export PYTHONPATH=src:scripts
python scripts/calibrate_cycle.py docs/evidence/calibration/calibration.json
python scripts/ambient_sweep.py docs/evidence/calibration/ambient_sweep.json
python scripts/calibration_uncertainty.py docs/evidence/calibration/uncertainty.json
python scripts/crosscheck_cantera.py docs/evidence/calibration/crosscheck_cantera.json
python scripts/crosscheck_coolprop.py docs/evidence/calibration/crosscheck_coolprop.json
# needs the GER-3567H PDF supplied locally: pdftoppm -r 250 -f 12 -l 12 -png GER-3567H.pdf amb
python scripts/digitize_ger3567_fig9.py amb-12.png docs/evidence/calibration/ger3567_fig9.json
```

Only numpy is needed at run time; the `calibration` extra (scipy, Cantera, CoolProp) is needed only for these scripts.
