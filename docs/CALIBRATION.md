# Cycle model calibration to the published GE 6B.03 point

Status: step 1 of `THESIS_ROADMAP.md`. Code: `src/turbineiq/engineering/real_gas.py`. Evidence: `docs/evidence/calibration/`. Scripts: `export_nasa_coefficients.py`, `calibrate_cycle.py`, `ambient_sweep.py`, `calibration_uncertainty.py`, `crosscheck_cantera.py`, `crosscheck_coolprop.py` in `scripts/`.

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

**Ambient trend (signs checked, sizes not).** With mass flow scaled with inlet density and firing temperature held constant (`ambient_sweep.json`), output is 3.6% lower at 20 °C and 13.5% lower at 35 °C than at ISO, and 11.5% higher at 0 °C; heat rate is 2.9% higher at 35 °C. Refitting under all 45 assumption combinations moves the 35 °C output change only between -14.1% and -13.1%, and the 0 °C change between +11.1% and +11.9%, so the trend is insensitive to what the targets cannot pin down. The signs match what GER-3567 and Brun and Kurz (Turbomachinery International, 2019) describe qualitatively: higher ambient temperature lowers output and raises heat rate, with a smaller effect on heat rate. **No numeric public source for the magnitude was found.** GER-3567H (10/00) gives the ambient effect only in Figure 9, and the two Turbomachinery International articles checked contain no numbers. Exhaust temperature stays almost flat here because firing temperature is held constant, whereas real machines follow an exhaust-temperature control curve; that is a known simplification.

## What is still needed to validate the ambient trend

A numeric ambient correction curve for a heavy-duty single-shaft machine. The most direct source is GER-3567 Figure 9 (an MS7001 curve, so a generic-family check, not a 6B.03 check), read from the PDF with a stated reading error. The PDF could not be downloaded from this environment (the host was blocked), so this needs the PDF supplied locally, or another public numeric source. Until then the model should be used for ambient trends with the stated sign-only validation.

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
```

Only numpy is needed at run time; the `calibration` extra (scipy, Cantera, CoolProp) is needed only for these scripts.
