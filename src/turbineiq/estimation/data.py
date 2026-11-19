"""Observation and ground-truth streams from scenario runs.

An :class:`Observation` is what a twin may use: the operating inputs it knows (unit state,
breaker, load setpoint, ambient temperature, IGV position) and the six instrument readings,
which include sensor faults and measurement noise. A :class:`Truth` row is the plant's
internal state for the same instant and is only for scoring.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from turbineiq.simulation.maps import Health
from turbineiq.simulation.scenarios import Scenario, run_scenario, trace_rows


@dataclass(frozen=True)
class Observation:
    t_s: float
    state: str
    breaker_closed: bool
    load_setpoint_mw: float
    ambient_temperature_c: float
    igv_position: float  # 0 closed .. 1 open; the commanded position is known to the twin
    power_mw: float
    exhaust_k: float
    speed_pu: float
    cdt_k: float  # compressor discharge temperature
    cdp_kpa: float  # compressor discharge pressure
    fuel_kg_s: float


@dataclass(frozen=True)
class Truth:
    t_s: float
    health: Health
    sensor_faults: str  # "channel:mode;..." or ""
    fuel_valve_lag_s: float
    power_mw: float
    exhaust_k: float
    fuel_kg_s: float
    cdt_k: float


def _obs(row: Mapping[str, Any]) -> Observation:
    return Observation(
        t_s=float(row["t_s"]),
        state=str(row["state"]),
        breaker_closed=row["breaker_closed"] in (True, "True", "true", 1, "1"),
        load_setpoint_mw=float(row["load_setpoint_mw"]),
        ambient_temperature_c=float(row["ambient_temperature_c"]),
        igv_position=float(row["igv_position"]),
        power_mw=float(row["meas_electrical_power_mw"]),
        exhaust_k=float(row["meas_exhaust_temperature_k"]),
        speed_pu=float(row["meas_speed_pu"]),
        cdt_k=float(row["meas_compressor_discharge_temperature_k"]),
        cdp_kpa=float(row["meas_compressor_discharge_pressure_kpa"]),
        fuel_kg_s=float(row["meas_fuel_flow_kg_s"]),
    )


def _truth(row: Mapping[str, Any]) -> Truth:
    return Truth(
        t_s=float(row["t_s"]),
        health=Health(
            float(row["true_compressor_flow_capacity_delta"]),
            float(row["true_compressor_efficiency_delta"]),
            float(row["true_turbine_efficiency_delta"]),
        ),
        sensor_faults=str(row["true_sensor_faults"] or ""),
        fuel_valve_lag_s=float(row["true_fuel_valve_lag_s"]),
        power_mw=float(row["true_electrical_power_mw"]),
        exhaust_k=float(row["true_exhaust_temperature_k"]),
        fuel_kg_s=float(row["true_fuel_flow_kg_s"]),
        cdt_k=float(row["true_compressor_discharge_temperature_k"]),
    )


def split_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[list[Observation], list[Truth]]:
    """Split trace rows (from ``trace_rows`` or a CSV trace) into observations and truth."""

    observations: list[Observation] = []
    truths: list[Truth] = []
    for row in rows:
        observations.append(_obs(row))
        truths.append(_truth(row))
    return observations, truths


def scenario_with_seed(item: Scenario, seed: int) -> Scenario:
    """The same scenario with another noise seed (for repeated trials)."""

    return replace(item, id=f"{item.id}@{seed}", seed=seed)


def run_streams(
    item: Scenario, seed: int | None = None, until_s: float | None = None
) -> tuple[list[Observation], list[Truth]]:
    """Run a scenario (optionally with another seed) and return its two streams."""

    chosen = item if seed is None else scenario_with_seed(item, seed)
    return split_rows(trace_rows(run_scenario(chosen, until_s=until_s)))
