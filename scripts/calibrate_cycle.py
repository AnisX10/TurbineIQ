"""Fit the variable-property cycle model to the published GE 6B.03 ISO ratings.

Free parameters: air mass flow, effective firing temperature, one common polytropic
efficiency for compressor and turbine, and the drivetrain efficiency. Four published
targets (net output, LHV efficiency, exhaust temperature, exhaust flow) determine these
four. Pressure ratio is fixed at the published 12.8. An earlier attempt with separate
compressor and turbine efficiencies and a fixed drivetrain loss left residuals of about
0.3 percent on every target: the four targets are tied together by the overall energy
balance, so the published set is only consistent with a drivetrain loss the fit can adjust,
and the compressor/turbine efficiency split is not identifiable. The cooling-flow fraction
is also not identifiable, so it is fixed and varied as a sensitivity study.

Usage: python scripts/calibrate_cycle.py docs/evidence/calibration/calibration.json
(requires scipy; the application itself does not).
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from turbineiq.engineering.real_gas import RealGasInputs, simulate_real_gas_cycle

TARGETS = {
    "net_output_mw": 45.0,
    "lhv_efficiency": 0.334,
    "exhaust_temperature_c": 561.0,
    "exhaust_flow_kg_s": 145.1,
}
BOUNDS = ([100.0, 1200.0, 0.80, 0.94], [200.0, 1700.0, 0.95, 0.99])


def _outputs(base: RealGasInputs, x: np.ndarray) -> dict[str, float]:
    point = replace(
        base,
        air_mass_flow_kg_s=float(x[0]),
        effective_firing_temperature_k=float(x[1]),
        compressor_polytropic_efficiency=float(x[2]),
        turbine_polytropic_efficiency=float(x[2]),
        drivetrain_efficiency=float(x[3]),
    )
    r = simulate_real_gas_cycle(point)
    return {
        "net_output_mw": r.net_electrical_power_mw,
        "lhv_efficiency": r.lhv_efficiency,
        "exhaust_temperature_c": r.exhaust_temperature_k - 273.15,
        "exhaust_flow_kg_s": r.exhaust_mass_flow_kg_s,
    }


def fit(cooling: float) -> dict[str, object]:
    base = RealGasInputs(cooling_flow_fraction=cooling)

    def residuals(x: np.ndarray) -> np.ndarray:
        out = _outputs(base, x)
        return np.array([(out[k] - v) / v for k, v in TARGETS.items()])

    sol = least_squares(
        residuals, x0=[140.0, 1400.0, 0.88, 0.965], bounds=BOUNDS, x_scale=[100, 1000, 0.1, 0.1]
    )
    out = _outputs(base, sol.x)
    return {
        "cooling_flow_fraction": cooling,
        "parameters": {
            "air_mass_flow_kg_s": sol.x[0],
            "effective_firing_temperature_k": sol.x[1],
            "component_polytropic_efficiency": sol.x[2],
            "drivetrain_efficiency": sol.x[3],
        },
        "model": out,
        "relative_residual": {k: (out[k] - v) / v for k, v in TARGETS.items()},
        "at_bound": [
            bool(np.isclose(v, lo) or np.isclose(v, hi))
            for v, lo, hi in zip(sol.x, BOUNDS[0], BOUNDS[1], strict=True)
        ],
    }


def main(path: Path) -> None:
    runs = [fit(c) for c in (0.0, 0.04, 0.08, 0.12, 0.16)]
    path.write_text(json.dumps({"targets": TARGETS, "fits": runs}, indent=2) + "\n")
    for run in runs:
        p = run["parameters"]
        print(
            f"cooling {run['cooling_flow_fraction']:.2f}: m={p['air_mass_flow_kg_s']:.1f} "
            f"Tfire={p['effective_firing_temperature_k']:.0f} "
            f"eta_p={p['component_polytropic_efficiency']:.3f} "
            f"eta_drive={p['drivetrain_efficiency']:.4f} "
            f"max|res|={max(abs(v) for v in run['relative_residual'].values()):.1e} "
            f"bound={run['at_bound']}"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
