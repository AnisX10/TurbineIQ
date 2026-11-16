"""Ambient-temperature sweep of the calibrated model (held-out trend, not fitted)."""

import json
import sys
from pathlib import Path

from turbineiq.engineering.real_gas import CALIBRATED_6B03, at_ambient, simulate_real_gas_cycle

rows = []
for t_c in range(-10, 46, 5):
    r = simulate_real_gas_cycle(at_ambient(CALIBRATED_6B03, float(t_c)))
    rows.append(
        {
            "ambient_c": t_c,
            "net_output_mw": r.net_electrical_power_mw,
            "lhv_efficiency": r.lhv_efficiency,
            "heat_rate_kj_per_kwh": r.heat_rate_kj_per_kwh,
            "exhaust_flow_kg_s": r.exhaust_mass_flow_kg_s,
            "exhaust_temperature_c": r.exhaust_temperature_k - 273.15,
        }
    )
Path(sys.argv[1]).write_text(json.dumps(rows, indent=2) + "\n")
iso = next(r for r in rows if r["ambient_c"] == 15)
for r in rows:
    print(
        f"{r['ambient_c']:>4} C  output {r['net_output_mw']:6.2f} MW "
        f"({r['net_output_mw'] / iso['net_output_mw'] * 100 - 100:+6.1f}%)  "
        f"HR {r['heat_rate_kj_per_kwh']:6.0f} "
        f"({r['heat_rate_kj_per_kwh'] / iso['heat_rate_kj_per_kwh'] * 100 - 100:+5.1f}%)  "
        f"flow {r['exhaust_flow_kg_s']:6.1f}  Texh {r['exhaust_temperature_c']:5.0f}"
    )
