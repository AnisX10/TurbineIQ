"""Published GE 6B.03 ratings and an honest comparison with the cycle model.

The numbers below come from the GE Vernova 2025 Gas Power catalog (see
``docs/GE_6B03_PUBLIC_DATA_REVIEW.md``). They are net plant ratings at ISO
conditions on natural gas.

The cycle model in :mod:`turbineiq.engineering.core` is a generic
constant-property Brayton model. Its defaults are *not* calibrated to these ratings, and a
calibration was tried and
not adopted: with constant specific heats, no cooling or leakage flows and no
inlet/exhaust losses, a 60,000-sample random search over pressure-ratio-12.8
inputs (air flow, turbine inlet temperature, component efficiencies, combustor
loss) did not find a point matching output, efficiency, exhaust temperature and
exhaust flow together. The best fit left the exhaust about 50 K high and the
efficiency about 2 points high. Matching all four needs temperature-dependent
properties and cooling/loss modelling, which is a larger change.

Instead of hiding the gap, this module reports it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .core import CycleInputs, CycleResult, simulate_cycle
from .real_gas import CALIBRATED_6B03, simulate_real_gas_cycle

PUBLISHED_SOURCE = "GE Vernova 2025 Gas Power catalog, 6B.03 table"

CALIBRATION_STATEMENT = (
    "The cycle model is generic and uncalibrated: its default operating point is "
    "not tuned to the published 6B.03 ratings, and only the trends it produces "
    "(for example the response to ambient temperature or compressor efficiency) "
    "are meant to be meaningful."
)


@dataclass(frozen=True)
class PublishedRating:
    key: str
    label: str
    unit: str
    published: float


PUBLISHED_6B03: tuple[PublishedRating, ...] = (
    PublishedRating("net_output", "Net output", "MW", 45.0),
    PublishedRating("lhv_efficiency", "LHV efficiency", "%", 33.4),
    PublishedRating("pressure_ratio", "Pressure ratio", ":1", 12.8),
    PublishedRating("exhaust_temperature", "Exhaust temperature", "°C", 561.0),
    PublishedRating("exhaust_flow", "Exhaust flow", "kg/s", 145.1),
)


def _model_values(inputs: CycleInputs, result: CycleResult) -> dict[str, float]:
    exhaust_flow = inputs.air_mass_flow_kg_s + result.fuel_mass_flow_kg_s
    return {
        "net_output": result.electrical_power_kw / 1000.0,
        "lhv_efficiency": result.electrical_efficiency * 100.0,
        "pressure_ratio": inputs.pressure_ratio,
        "exhaust_temperature": result.states[3].temperature_k - 273.15,
        "exhaust_flow": exhaust_flow,
    }


def compare_to_published(inputs: CycleInputs | None = None) -> dict[str, object]:
    """Run the model at ``inputs`` (default: the app's reference point) and compare.

    Returns JSON-friendly rows with the published value, the model value, and the
    signed difference, plus the calibration statement. Nothing here is a claim
    that the model reproduces the OEM machine.
    """

    point = inputs or CycleInputs()
    result = simulate_cycle(point)
    model = _model_values(point, result)
    rows = []
    for rating in PUBLISHED_6B03:
        value = model[rating.key]
        rows.append(
            {
                "key": rating.key,
                "label": rating.label,
                "unit": rating.unit,
                "published": rating.published,
                "model": value,
                "difference": value - rating.published,
                "difference_percent": (value - rating.published) / rating.published * 100.0,
            }
        )
    return {
        "source": PUBLISHED_SOURCE,
        "calibrated": False,
        "statement": CALIBRATION_STATEMENT,
        "model_point": "Reference operating point of the synthetic scenarios (ISO ambient)",
        "rows": rows,
    }


def compare_calibrated_to_published() -> dict[str, object]:
    """Compare the variable-property model, fitted to these ratings, with the ratings.

    Agreement at the fitted point is by construction (four parameters, four targets) and is
    not validation; see ``docs/CALIBRATION.md`` for what is and is not established.
    """

    result = simulate_real_gas_cycle(CALIBRATED_6B03)
    model = {
        "net_output": result.net_electrical_power_mw,
        "lhv_efficiency": result.lhv_efficiency * 100.0,
        "pressure_ratio": CALIBRATED_6B03.pressure_ratio,
        "exhaust_temperature": result.exhaust_temperature_k - 273.15,
        "exhaust_flow": result.exhaust_mass_flow_kg_s,
    }
    rows = [
        {
            "key": r.key,
            "label": r.label,
            "unit": r.unit,
            "published": r.published,
            "model": model[r.key],
            "difference": model[r.key] - r.published,
            "difference_percent": (model[r.key] - r.published) / r.published * 100.0,
        }
        for r in PUBLISHED_6B03
    ]
    return {"source": PUBLISHED_SOURCE, "fitted": True, "rows": rows}
