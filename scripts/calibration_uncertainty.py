"""Refit the model over the assumptions the published targets cannot pin down.

Grid: cooling-flow fraction, inlet and exhaust pressure loss, fuel LHV. For every
combination the four free parameters are refitted to the four published targets, and the
predicted ambient sensitivity is recorded. The spread across the grid is the part of the
calibration uncertainty that comes from those assumptions; it does not include model-form
error. Usage:
    python scripts/calibration_uncertainty.py docs/evidence/calibration/uncertainty.json
(requires scipy)
"""

from __future__ import annotations

import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from calibrate_cycle import BOUNDS, TARGETS, _outputs
from scipy.optimize import least_squares

from turbineiq.engineering.real_gas import RealGasInputs, at_ambient, simulate_real_gas_cycle

COOLING = (0.0, 0.04, 0.08, 0.12, 0.16)
LOSSES = (0.005, 0.01, 0.02)
LHV_KJ_KG = (47_000.0, 48_500.0, 50_000.0)


def fit(base: RealGasInputs) -> tuple[RealGasInputs, float]:
    def residuals(x: np.ndarray) -> np.ndarray:
        out = _outputs(base, x)
        return np.array([(out[k] - v) / v for k, v in TARGETS.items()])

    sol = least_squares(
        residuals, x0=[142.0, 1450.0, 0.87, 0.95], bounds=BOUNDS, x_scale=[100, 1000, 0.1, 0.1]
    )
    x = sol.x
    fitted = replace(
        base,
        air_mass_flow_kg_s=float(x[0]),
        effective_firing_temperature_k=float(x[1]),
        compressor_polytropic_efficiency=float(x[2]),
        turbine_polytropic_efficiency=float(x[2]),
        drivetrain_efficiency=float(x[3]),
    )
    return fitted, float(np.max(np.abs(sol.fun)))


def main(path: Path) -> None:
    rows = []
    for cooling, loss, lhv in itertools.product(COOLING, LOSSES, LHV_KJ_KG):
        base = RealGasInputs(
            cooling_flow_fraction=cooling,
            inlet_pressure_loss_fraction=loss,
            exhaust_pressure_loss_fraction=loss,
            fuel_lhv_kj_kg=lhv,
        )
        fitted, worst = fit(base)
        iso = simulate_real_gas_cycle(fitted)
        hot = simulate_real_gas_cycle(at_ambient(fitted, 35.0))
        cold = simulate_real_gas_cycle(at_ambient(fitted, 0.0))
        rows.append(
            {
                "cooling_flow_fraction": cooling,
                "inlet_exhaust_loss_fraction": loss,
                "fuel_lhv_kj_kg": lhv,
                "max_target_residual": worst,
                "air_mass_flow_kg_s": fitted.air_mass_flow_kg_s,
                "effective_firing_temperature_k": fitted.effective_firing_temperature_k,
                "polytropic_efficiency": fitted.compressor_polytropic_efficiency,
                "drivetrain_efficiency": fitted.drivetrain_efficiency,
                "output_change_35c_percent": (
                    hot.net_electrical_power_mw / iso.net_electrical_power_mw - 1
                )
                * 100,
                "output_change_0c_percent": (
                    cold.net_electrical_power_mw / iso.net_electrical_power_mw - 1
                )
                * 100,
                "heat_rate_change_35c_percent": (
                    hot.heat_rate_kj_per_kwh / iso.heat_rate_kj_per_kwh - 1
                )
                * 100,
            }
        )
    path.write_text(json.dumps(rows, indent=2) + "\n")
    keys = (
        "effective_firing_temperature_k",
        "polytropic_efficiency",
        "drivetrain_efficiency",
        "air_mass_flow_kg_s",
        "output_change_35c_percent",
        "output_change_0c_percent",
        "heat_rate_change_35c_percent",
        "max_target_residual",
    )
    for k in keys:
        vals = [r[k] for r in rows]
        print(f"{k:32s} min {min(vals):10.4f}  max {max(vals):10.4f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
