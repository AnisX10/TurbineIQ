"""Export NASA-7 thermodynamic coefficients for the species used by the cycle model.

Source: the GRI-Mech 3.0 mechanism file shipped with Cantera (``gri30.yaml``), which
carries NASA-7 polynomials from the Burcat/GRI thermodynamic database. Run once with
``pip install cantera`` and commit the JSON; the application itself needs only numpy.
"""

import json
import sys
from pathlib import Path

import cantera as ct

SPECIES = ["N2", "O2", "AR", "CO2", "H2O"]


def main(out: Path) -> None:
    gas = ct.Solution("gri30.yaml")
    data = {
        "source": f"Cantera {ct.__version__} gri30.yaml (GRI-Mech 3.0 NASA-7 polynomials)",
        "units": "cp/R = a0 + a1 T + a2 T^2 + a3 T^3 + a4 T^4; h/(R T) = a0 + a1 T/2 + "
        "a2 T^2/3 + a3 T^3/4 + a4 T^4/5 + a5/T; T in K",
        "gas_constant_j_mol_k": ct.gas_constant / 1000.0,
        "species": {},
    }
    for name in SPECIES:
        sp = gas.species(name)
        thermo = sp.thermo
        data["species"][name] = {
            "molar_mass_kg_kmol": sp.molecular_weight,
            "t_low": thermo.min_temp,
            "t_mid": thermo.coeffs[0],
            "t_high": thermo.max_temp,
            "coeffs_high": list(thermo.coeffs[1:8]),
            "coeffs_low": list(thermo.coeffs[8:15]),
        }
    out.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
