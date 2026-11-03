# TurbineIQ synthetic demonstration notes

This locally authored note exists only to demonstrate source retrieval. It is an educational summary of the prototype's own formulas. It is not an OEM manual and contains no manufacturer data, operating limits, or FieldCore material.

## Simplified cycle

The model follows four states in an open Brayton cycle. State 1 is ambient air at the compressor inlet. State 2 is compressor discharge. State 3 is the turbine inlet after approximate heat addition and combustor pressure loss. State 4 is exhaust at ambient pressure.

For a constant specific heat ratio gamma, the ideal compressor temperature is T2s = T1 * pressure_ratio^((gamma - 1)/gamma). The actual compressor temperature is T2 = T1 + (T2s - T1)/compressor_efficiency. Compressor specific work is cp_air * (T2 - T1).

The ideal turbine exhaust temperature is T4s = T3 * (P4/P3)^((gamma_gas - 1)/gamma_gas). Actual exhaust temperature is T4 = T3 - turbine_efficiency * (T3 - T4s). Turbine specific work is approximated as (1 + fuel_to_air_ratio) * cp_gas * (T3 - T4).

## Performance estimates

Net cycle work is turbine specific work minus compressor specific work. Net cycle power is net specific work multiplied by air mass flow. Mechanical efficiency is applied to obtain shaft power, and generator efficiency is then applied to estimate electrical power.

Heat added per unit air mass is approximated as cp_air * (T3 - T2). Fuel-to-air ratio is estimated as heat added divided by combustor efficiency and fuel lower heating value. Fuel energy input is fuel mass flow multiplied by lower heating value. Electrical efficiency and heat rate are derived from these estimates.

## Interpretation boundary

All numeric inputs are illustrative assumptions. The constant-property cycle omits detailed cooling flows, variable geometry, maps, control schedules, emissions, transient dynamics, and machine-specific behavior. Its results cannot establish an OEM rating, safe limit, root cause, maintenance action, or performance guarantee.

