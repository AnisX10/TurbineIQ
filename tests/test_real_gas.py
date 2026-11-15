import json
from importlib import resources

import pytest

from turbineiq.engineering import (
    CALIBRATED_6B03,
    RealGasInputs,
    at_ambient,
    compare_calibrated_to_published,
    simulate_real_gas_cycle,
)


def _rows():
    return {r["key"]: r for r in compare_calibrated_to_published()["rows"]}  # type: ignore[union-attr]


def test_fitted_point_matches_published_ratings():
    rows = _rows()
    for key in ("net_output", "lhv_efficiency", "exhaust_temperature", "exhaust_flow"):
        assert abs(rows[key]["difference_percent"]) < 0.05, key
    assert rows["pressure_ratio"]["model"] == 12.8


def test_heat_rate_matches_published_10779_kj_per_kwh():
    result = simulate_real_gas_cycle(CALIBRATED_6B03)
    assert result.heat_rate_kj_per_kwh == pytest.approx(10779, rel=0.002)


def test_energy_balance_closes():
    r = simulate_real_gas_cycle(CALIBRATED_6B03)
    assert r.turbine_power_mw > r.compressor_power_mw > 0
    assert r.net_electrical_power_mw < r.turbine_power_mw - r.compressor_power_mw
    assert 0.0 < r.lhv_efficiency < 0.5
    assert r.exhaust_mass_flow_kg_s == pytest.approx(
        CALIBRATED_6B03.air_mass_flow_kg_s * (1 + r.fuel_to_air_ratio)
    )


def test_ambient_trends_have_the_expected_sign():
    cold = simulate_real_gas_cycle(at_ambient(CALIBRATED_6B03, 0.0))
    iso = simulate_real_gas_cycle(CALIBRATED_6B03)
    hot = simulate_real_gas_cycle(at_ambient(CALIBRATED_6B03, 35.0))
    assert cold.net_electrical_power_mw > iso.net_electrical_power_mw > hot.net_electrical_power_mw
    assert cold.heat_rate_kj_per_kwh < iso.heat_rate_kj_per_kwh < hot.heat_rate_kj_per_kwh
    assert cold.exhaust_mass_flow_kg_s > iso.exhaust_mass_flow_kg_s > hot.exhaust_mass_flow_kg_s


def test_compressor_degradation_lowers_output_and_efficiency():
    from dataclasses import replace

    base = simulate_real_gas_cycle(CALIBRATED_6B03)
    worse = simulate_real_gas_cycle(replace(CALIBRATED_6B03, compressor_polytropic_efficiency=0.85))
    assert worse.net_electrical_power_mw < base.net_electrical_power_mw
    assert worse.lhv_efficiency < base.lhv_efficiency


def test_species_data_reproduces_air_cp_at_300k_and_1000k():
    from turbineiq.engineering import real_gas

    air = real_gas._air(real_gas._air_kmol_per_kg())
    assert air.cp(300.0) == pytest.approx(1005, rel=0.01)
    assert air.cp(1000.0) == pytest.approx(1141, rel=0.01)


def test_species_file_has_provenance():
    path = resources.files("turbineiq.engineering").joinpath("data/nasa7_species.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "GRI-Mech" in data["source"]
    assert set(data["species"]) == {"N2", "O2", "AR", "CO2", "H2O"}


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        RealGasInputs(pressure_ratio=0.9)
    with pytest.raises(ValueError):
        RealGasInputs(cooling_flow_fraction=0.7)
