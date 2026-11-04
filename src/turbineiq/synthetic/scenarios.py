"""Generate model-derived demonstration data with explicit synthetic labels."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from turbineiq.engineering import CycleInputs, simulate_cycle


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    description: str
    ambient_shift_c: float = 0.0
    compressor_efficiency_end: float = 0.85
    inject_power_spike: bool = False


SCENARIOS: dict[str, ScenarioSpec] = {
    "baseline": ScenarioSpec(
        name="Baseline",
        description="Model-derived operation with gentle synthetic ambient variation.",
    ),
    "warm_ambient": ScenarioSpec(
        name="Warmer ambient",
        description=(
            "Ambient temperature is shifted upward; inlet mass flow follows a "
            "fixed-volume density assumption."
        ),
        ambient_shift_c=8.0,
    ),
    "compressor_fouling": ScenarioSpec(
        name="Compressor-performance drift",
        description=(
            "A synthetic compressor-efficiency parameter drifts below the fixed "
            "reference-model assumption. The resulting residual is illustrative; "
            "it is not a real fault signature."
        ),
        compressor_efficiency_end=0.80,
    ),
    "sensor_fault": ScenarioSpec(
        name="Power-sensor spike",
        description=(
            "A single synthetic measurement spike is added to observed electrical "
            "power; the model state remains unchanged."
        ),
        inject_power_spike=True,
    ),
}


def generate_scenario(
    scenario_id: str = "baseline",
    *,
    seed: int = 42,
    samples: int = 96,
    base_inputs: CycleInputs | None = None,
) -> pd.DataFrame:
    """Return a seeded, model-derived scenario at 15-minute intervals.

    Mass flow varies with inlet density under a stated fixed-volume assumption.
    Measurement noise and the optional sensor fault are generated from a local
    NumPy random generator; no network or external dataset is used.
    """

    if scenario_id not in SCENARIOS:
        raise ValueError(
            f"unknown scenario_id {scenario_id!r}; choose one of {', '.join(SCENARIOS)}"
        )
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if not isinstance(samples, int) or samples < 8:
        raise ValueError("samples must be an integer of at least 8")

    spec = SCENARIOS[scenario_id]
    base = base_inputs or CycleInputs()
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    ambient_ref_k = base.ambient_temperature_c + 273.15
    ambient_ref_pressure = base.ambient_pressure_kpa
    fault_index = samples // 2

    for index in range(samples):
        phase = 2 * np.pi * index / samples
        ambient_c = base.ambient_temperature_c + spec.ambient_shift_c + 4.0 * np.sin(phase)
        ambient_pressure = ambient_ref_pressure + 0.45 * np.cos(phase)
        ambient_k = ambient_c + 273.15
        air_mass_flow = (
            base.air_mass_flow_kg_s
            * (ambient_pressure / ambient_ref_pressure)
            * (ambient_ref_k / ambient_k)
        )

        drift_fraction = index / max(samples - 1, 1)
        compressor_efficiency = (
            base.compressor_efficiency
            + (spec.compressor_efficiency_end - base.compressor_efficiency) * drift_fraction
        )
        operating_point = replace(
            base,
            ambient_temperature_c=ambient_c,
            ambient_pressure_kpa=ambient_pressure,
            air_mass_flow_kg_s=air_mass_flow,
        )
        reference_inputs = replace(
            operating_point,
            compressor_efficiency=base.compressor_efficiency,
        )
        plant_inputs = replace(operating_point, compressor_efficiency=compressor_efficiency)
        reference_result = simulate_cycle(reference_inputs)
        plant_result = simulate_cycle(plant_inputs)
        modeled_power = reference_result.electrical_power_kw
        plant_power = plant_result.electrical_power_kw
        observed_power = plant_power + float(rng.normal(0, plant_power * 0.002))
        fault_injected = bool(spec.inject_power_spike and index == fault_index)
        if fault_injected:
            observed_power += plant_power * 0.30

        rows.append(
            {
                "timestamp_utc": pd.Timestamp("2025-01-01T00:00:00Z")
                + pd.Timedelta(minutes=15 * index),
                "scenario_id": scenario_id,
                "synthetic_data": True,
                "sensor_fault_injected": fault_injected,
                "sensor_fault_label": "power_sensor_spike" if fault_injected else "none",
                "ambient_temperature_c": ambient_c,
                "ambient_pressure_kpa": ambient_pressure,
                "pressure_ratio": base.pressure_ratio,
                "combustor_pressure_loss_fraction": base.combustor_pressure_loss_fraction,
                "compressor_efficiency_assumption": base.compressor_efficiency,
                "synthetic_true_compressor_efficiency": compressor_efficiency,
                "air_mass_flow_kg_s_assumption": air_mass_flow,
                "compressor_discharge_temperature_k": plant_result.states[1].temperature_k,
                "reference_compressor_discharge_temperature_k": (
                    reference_result.states[1].temperature_k
                ),
                "turbine_inlet_temperature_k": plant_result.states[2].temperature_k,
                "reference_turbine_inlet_temperature_k": reference_result.states[2].temperature_k,
                "exhaust_temperature_k": plant_result.states[3].temperature_k,
                "reference_exhaust_temperature_k": reference_result.states[3].temperature_k,
                "compressor_power_kw": plant_result.compressor_power_kw,
                "reference_compressor_power_kw": reference_result.compressor_power_kw,
                "combustor_heat_input_kw": (
                    plant_result.heat_added_kj_per_kg_air * air_mass_flow
                ),
                "turbine_power_kw": plant_result.turbine_power_kw,
                "reference_turbine_power_kw": reference_result.turbine_power_kw,
                "shaft_power_kw": plant_result.shaft_power_kw,
                "reference_shaft_power_kw": reference_result.shaft_power_kw,
                "model_electrical_power_kw": modeled_power,
                "synthetic_truth_electrical_power_kw": plant_power,
                "observed_electrical_power_kw": observed_power,
                "power_residual_kw": observed_power - modeled_power,
                "fuel_mass_flow_kg_s": plant_result.fuel_mass_flow_kg_s,
                "reference_fuel_mass_flow_kg_s": reference_result.fuel_mass_flow_kg_s,
            }
        )

    frame = pd.DataFrame.from_records(rows)
    frame.attrs["scenario_name"] = spec.name
    frame.attrs["scenario_description"] = spec.description
    frame.attrs["seed"] = seed
    frame.attrs["synthetic_only"] = True
    frame.attrs["model_name"] = "Simplified single-shaft open-cycle Brayton model"
    frame.attrs["mass_flow_assumption"] = (
        "Inlet mass flow scales with ambient density at a fixed inlet-volume assumption."
    )
    return frame
