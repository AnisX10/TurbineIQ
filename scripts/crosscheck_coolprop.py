"""Independent property-data check against CoolProp (Helmholtz-energy equations of state).

Compares the NASA-7 mixture properties used by ``real_gas.py`` with CoolProp's HEOS mixture
for dry air and for burned-gas composition, and repeats the polytropic compression with
CoolProp. CoolProp uses different reference data from the GRI/Burcat polynomials, so
agreement here supports the property data, not only the code.

Usage: python scripts/crosscheck_coolprop.py docs/evidence/calibration/crosscheck_coolprop.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from CoolProp.CoolProp import PropsSI

from turbineiq.engineering import real_gas
from turbineiq.engineering.real_gas import CALIBRATED_6B03

AIR_FLUID = "N2[0.7809]&Oxygen[0.2095]&Argon[0.0096]"
GAS_FLUID = "Nitrogen[0.7451]&Oxygen[0.1349]&Argon[0.0092]&CO2[0.0310]&Water[0.0798]"


def _burned_kmol() -> dict[str, float]:
    return {"N2": 0.7451, "O2": 0.1349, "AR": 0.0092, "CO2": 0.0310, "H2O": 0.0798}


def main(path: Path) -> None:
    air = real_gas._air(real_gas._air_kmol_per_kg())
    gas = real_gas._Mixture(_burned_kmol())
    rows = []
    for name, mix, fluid in (("air", air, AIR_FLUID), ("burned gas", gas, GAS_FLUID)):
        for t in (500.0, 600.0, 900.0, 1200.0, 1400.0):
            cp_cool = PropsSI("CPMASS", "T", t, "P", 101325.0, fluid)
            # Enthalpy difference from 400 K: the burned gas is above its dew point there,
            # whereas at 298 K its water would condense in CoolProp's EOS.
            dh_cool = PropsSI("HMASS", "T", t, "P", 101325.0, fluid) - PropsSI(
                "HMASS", "T", 400.0, "P", 101325.0, fluid
            )
            rows.append(
                {
                    "mixture": name,
                    "temperature_k": t,
                    "cp_nasa_j_kg_k": mix.cp(t),
                    "cp_coolprop_j_kg_k": cp_cool,
                    "cp_difference_percent": (mix.cp(t) / cp_cool - 1) * 100,
                    "dh_nasa_kj_kg": (mix.h(t) - mix.h(400.0)) / 1000,
                    "dh_coolprop_kj_kg": dh_cool / 1000,
                    "dh_difference_percent": ((mix.h(t) - mix.h(400.0)) / dh_cool - 1) * 100
                    if t != 400.0
                    else 0.0,
                }
            )

    # Polytropic compression of air with CoolProp.
    p = CALIBRATED_6B03
    t1 = p.ambient_temperature_c + 273.15
    p1 = p.ambient_pressure_kpa * 1000.0 * (1 - p.inlet_pressure_loss_fraction)
    steps = 60
    ratio = p.pressure_ratio ** (1 / steps)
    t, pr = t1, p1
    h_start = PropsSI("HMASS", "T", t, "P", pr, AIR_FLUID)
    for _ in range(steps):
        h0 = PropsSI("HMASS", "T", t, "P", pr, AIR_FLUID)
        s0 = PropsSI("SMASS", "T", t, "P", pr, AIR_FLUID)
        pr *= ratio
        h_is = PropsSI("HMASS", "P", pr, "SMASS", s0, AIR_FLUID)
        h_new = h0 + (h_is - h0) / p.compressor_polytropic_efficiency
        t = PropsSI("T", "P", pr, "HMASS", h_new, AIR_FLUID)
    work_cool = (PropsSI("HMASS", "T", t, "P", pr, AIR_FLUID) - h_start) / 1000

    t2_mine = real_gas._polytropic_path(
        air, t1, p.pressure_ratio, p.compressor_polytropic_efficiency, compress=True
    )
    work_mine = (air.h(t2_mine) - air.h(t1)) / 1000
    compression = {
        "t2_nasa_k": t2_mine,
        "t2_coolprop_k": t,
        "work_nasa_kj_kg": work_mine,
        "work_coolprop_kj_kg": work_cool,
        "work_difference_percent": (work_mine / work_cool - 1) * 100,
    }
    path.write_text(json.dumps({"properties": rows, "compression": compression}, indent=2) + "\n")
    for r in rows:
        print(
            f"{r['mixture']:10s} {r['temperature_k']:6.0f} K  cp {r['cp_difference_percent']:+.3f}%"
            f"  dh {r['dh_difference_percent']:+.3f}%"
        )
    print(compression)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
