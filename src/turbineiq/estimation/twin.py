"""A quasi-steady twin: the plant's steady-state outputs at measured operating inputs.

The twin takes the measured speed and fuel flow, the known IGV position and ambient, and a
health estimate, and predicts electrical power, exhaust temperature and compressor
discharge temperature and pressure from the same calibrated maps the plant uses. It has no
dynamics, so it is only valid at steady state (see :mod:`.steady`), and with the default
maps there is no twin-plant model mismatch: the roadmap's mismatch experiment needs a twin
built on perturbed maps.
"""

from __future__ import annotations

from dataclasses import dataclass

from turbineiq.simulation.maps import Health, HealthMaps, health_maps, igv_air_factor

from .data import Observation


@dataclass(frozen=True)
class Prediction:
    power_mw: float
    exhaust_k: float
    cdt_k: float
    cdp_kpa: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.power_mw, self.exhaust_k, self.cdt_k, self.cdp_kpa)


MEASUREMENTS = ("power_mw", "exhaust_k", "cdt_k", "cdp_kpa")


def measured(obs: Observation) -> tuple[float, float, float, float]:
    """The four twin outputs as measured, in :data:`MEASUREMENTS` order."""

    return (obs.power_mw, obs.exhaust_k, obs.cdt_k, obs.cdp_kpa)


class QuasiSteadyTwin:
    """Steady-state prediction of the instrumented outputs for a given health."""

    def __init__(self, maps_for_ambient=health_maps) -> None:
        # ``maps_for_ambient(ambient_c) -> HealthMaps``; replace it to build a mismatched twin.
        self._maps_for_ambient = maps_for_ambient

    def maps(self, ambient_temperature_c: float) -> HealthMaps:
        return self._maps_for_ambient(ambient_temperature_c)

    def predict(self, health: Health, obs: Observation) -> Prediction:
        maps = self.maps(obs.ambient_temperature_c)
        clean = maps.clean
        g = igv_air_factor(obs.igv_position)
        fuel_pu = obs.fuel_kg_s / clean.rated_fuel_kg_s
        shaft_pu, exhaust_k = maps.lookup(health, obs.speed_pu, g, fuel_pu)
        cdt_k, cdp_kpa = maps.compressor_discharge(health, obs.speed_pu, g)
        return Prediction(clean.electrical_mw(shaft_pu), exhaust_k, cdt_k, cdp_kpa)
