"""Independent cross-check of the variable-property model using Cantera objects.

Same cycle structure and parameters as ``real_gas.py`` (CALIBRATED_6B03), but properties,
isentropic steps and the combustion product composition come from Cantera's thermo objects
(GRI-Mech 3.0 gas, equilibrium products at the firing temperature so dissociation is
included). Differences from ``real_gas.py`` therefore show the effect of my own mixture and
integration code and of ignoring dissociation, not of the data. The NASA-7 coefficients are
shared, so this does not test the property data themselves.

Usage: python scripts/crosscheck_cantera.py docs/evidence/calibration/crosscheck_cantera.json
(requires cantera).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cantera as ct
from scipy.optimize import brentq

from turbineiq.engineering.real_gas import CALIBRATED_6B03, simulate_real_gas_cycle

AIR = "N2:0.7809,O2:0.2095,AR:0.0096"
N = 400


def _step_path(gas: ct.Solution, p_ratio: float, eta: float, compress: bool) -> None:
    step = p_ratio ** (1.0 / N)
    for _ in range(N):
        h0, s0, p0 = gas.h, gas.s, gas.P
        gas.SP = s0, p0 * step if compress else p0 / step
        dh_is = gas.h - h0
        dh = dh_is / eta if compress else dh_is * eta
        gas.HP = h0 + dh, gas.P


def run() -> dict[str, float]:
    p = CALIBRATED_6B03
    t1 = p.ambient_temperature_c + 273.15
    p1 = p.ambient_pressure_kpa * 1000.0 * (1 - p.inlet_pressure_loss_fraction)
    p2 = p1 * p.pressure_ratio
    p3 = p2 * (1 - p.combustor_pressure_loss_fraction)
    p4 = p.ambient_pressure_kpa * 1000.0 * (1 + p.exhaust_pressure_loss_fraction)
    xc = p.cooling_flow_fraction

    air = ct.Solution("gri30.yaml")
    air.TPX = t1, p1, AIR
    h1 = air.h  # J/kg
    _step_path(air, p.pressure_ratio, p.compressor_polytropic_efficiency, True)
    t2, h2 = air.T, air.h
    compressor_work = h2 - h1

    fuel_gas = ct.Solution("gri30.yaml")
    fuel_gas.TPX = 298.15, p3, "CH4:1"
    h_fuel = fuel_gas.h
    lhv = p.fuel_lhv_kj_kg * 1000.0

    def burn(f: float) -> ct.Solution:
        g = ct.Solution("gri30.yaml")
        y_air = ct.Solution("gri30.yaml")
        y_air.TPX = t2, p3, AIR
        mass = {s: 0.0 for s in g.species_names}
        for s, y in zip(y_air.species_names, y_air.Y, strict=True):
            mass[s] += (1 - xc) * y
        mass["CH4"] += f
        total = sum(mass.values())
        g.Y = {k: v / total for k, v in mass.items()}
        h_in = (1 - xc) * h2 + f * h_fuel - (1 - p.combustor_efficiency) * f * lhv
        g.TP = 1500.0, p3
        g.HP = h_in / total, p3
        g.equilibrate("HP")
        return g

    f = brentq(lambda x: burn(x).T - p.effective_firing_temperature_k, 0.005, 0.035, xtol=1e-12)
    burned = burn(f)

    # Mix cooling air (at T2) into the burned gas, frozen composition.
    mix = ct.Solution("gri30.yaml")
    y_c = ct.Solution("gri30.yaml")
    y_c.TPX = t2, p3, AIR
    mass_b = 1 - xc + f
    y = {s: 0.0 for s in mix.species_names}
    for s, yb in zip(burned.species_names, burned.Y, strict=True):
        y[s] += mass_b * yb
    for s, yc in zip(y_c.species_names, y_c.Y, strict=True):
        y[s] += xc * yc
    total = sum(y.values())
    mix.Y = {k: v / total for k, v in y.items()}
    mix.TP = 1400.0, p3
    mix.HP = (mass_b * burned.h + xc * h2) / total, p3
    t3, h3 = mix.T, mix.h
    _step_path(mix, p3 / p4, p.turbine_polytropic_efficiency, False)
    t4, h4 = mix.T, mix.h

    turbine_work = total * (h3 - h4)
    net = (turbine_work - compressor_work) * p.drivetrain_efficiency
    mdot = p.air_mass_flow_kg_s
    return {
        "net_output_mw": net * mdot / 1e6,
        "lhv_efficiency": net * mdot / 1e6 / (f * mdot * lhv / 1e6),
        "exhaust_temperature_c": t4 - 273.15,
        "exhaust_flow_kg_s": mdot * (1 + f),
        "compressor_discharge_k": t2,
        "mixed_turbine_inlet_k": t3,
        "fuel_to_air_ratio": f,
    }


def main(path: Path) -> None:
    ref = simulate_real_gas_cycle(CALIBRATED_6B03)
    mine = {
        "net_output_mw": ref.net_electrical_power_mw,
        "lhv_efficiency": ref.lhv_efficiency,
        "exhaust_temperature_c": ref.exhaust_temperature_k - 273.15,
        "exhaust_flow_kg_s": ref.exhaust_mass_flow_kg_s,
        "compressor_discharge_k": ref.compressor_discharge_temperature_k,
        "mixed_turbine_inlet_k": ref.mixed_turbine_inlet_temperature_k,
        "fuel_to_air_ratio": ref.fuel_to_air_ratio,
    }
    other = run()
    rows = {
        k: {"real_gas": mine[k], "cantera": other[k], "difference": other[k] - mine[k]}
        for k in mine
    }
    path.write_text(json.dumps(rows, indent=2) + "\n")
    for k, v in rows.items():
        print(
            f"{k:26s} real_gas {v['real_gas']:12.5f}  cantera {v['cantera']:12.5f}"
            f"  d {v['difference']:+.5f}"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
