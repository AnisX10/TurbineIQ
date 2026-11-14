"""Small rule-based question parsing for the deterministic local assistant.

Local mode has no language model, so it maps a question onto the existing tools
with explicit, readable rules: numbers named next to a cycle input become a
what-if calculation, scenario names select scenario summaries, and wording about
the current selection selects the replay snapshot. Nothing here guesses a value
that the question did not state.
"""

from __future__ import annotations

import re

from turbineiq.synthetic import SCENARIOS

_NUM = r"(-?\d+(?:\.\d+)?)"
_LINK = r"(?:\s+(?:of|at|to|=|is|be|was|:|by))?\s*"

# Aliases beyond the scenario id and display name, in lower case.
_SCENARIO_ALIASES: dict[str, tuple[str, ...]] = {
    "baseline": ("baseline", "base case"),
    "warm_ambient": ("warm ambient", "warmer ambient", "warmer", "hot ambient"),
    "compressor_fouling": (
        "compressor fouling",
        "fouling",
        "compressor drift",
        "compressor performance drift",
        "compressor-performance drift",
        "compressor degradation",
    ),
    "sensor_fault": ("sensor fault", "power sensor", "sensor spike", "power spike"),
}

_SELECTION_RE = re.compile(
    r"\b(this|selected|current|chosen)\b|\bsamples?\b|\bresidual\b|\bflagged\b|\bmetrics?\b",
    re.IGNORECASE,
)
_COMPONENT_RE = re.compile(
    r"\b(inlet|compressor|combustor|turbine|shaft|generator)\b", re.IGNORECASE
)
_RUN_RE = re.compile(
    r"\b(this|the|whole|entire|full)\s+(run|scenario|replay|timeline)\b|\bhow\s+many\b"
    r"|\bflagged\s+samples\b",
    re.IGNORECASE,
)
_STRONG_SELECTION_RE = re.compile(
    r"\b(this|selected|current|chosen)\s+(sample|component|part|point|snapshot|step|row)\b"
    r"|\bsample\s+\d+\b|\bat\s+sample\b",
    re.IGNORECASE,
)

CYCLE_LABELS = {
    "pressure_ratio": "pressure ratio",
    "ambient_temperature_c": "ambient temperature (°C)",
    "ambient_pressure_kpa": "ambient pressure (kPa)",
    "air_mass_flow_kg_s": "air mass flow (kg/s)",
    "turbine_inlet_temperature_k": "turbine inlet temperature (K)",
    "compressor_efficiency": "compressor efficiency",
    "turbine_efficiency": "turbine efficiency",
    "mechanical_efficiency": "mechanical efficiency",
    "generator_efficiency": "generator efficiency",
}


def _take(pattern: str, text: str) -> tuple[re.Match[str] | None, str]:
    """Return the first match and the text with that span blanked out."""

    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return None, text
    blanked = text[: match.start()] + " " * (match.end() - match.start()) + text[match.end() :]
    return match, blanked


def parse_cycle_overrides(question: str) -> dict[str, float]:
    """Extract cycle inputs that the question states with an explicit number.

    Returns only the stated inputs, converted to the model's units (°C, kPa, K,
    kg/s, fractions). Unstated inputs are left to the caller's defaults.
    """

    text = question.replace("°", " ° ")
    found: dict[str, float] = {}

    for name in ("compressor", "turbine", "mechanical", "generator"):
        match, text = _take(rf"\b{name}\s+efficiency{_LINK}{_NUM}\s*(%|percent)?", text)
        if match:
            value = float(match.group(1))
            found[f"{name}_efficiency"] = value / 100 if match.group(2) or value > 1 else value

    match, text = _take(
        rf"(?:turbine[ -]inlet(?:\s+temperature)?|\btit\b|firing\s+temperature){_LINK}{_NUM}"
        r"\s*(?:°\s*)?(k|kelvin|c|celsius)?\b",
        text,
    )
    if match:
        value = float(match.group(1))
        unit = (match.group(2) or "k").lower()
        found["turbine_inlet_temperature_k"] = value + 273.15 if unit in {"c", "celsius"} else value

    match, text = _take(rf"\bambient\s+pressure{_LINK}{_NUM}\s*(kpa|bar|psi)?", text)
    if match:
        value = float(match.group(1))
        unit = (match.group(2) or "kpa").lower()
        found["ambient_pressure_kpa"] = value * {"kpa": 1.0, "bar": 100.0, "psi": 6.894757}[unit]

    ambient: tuple[float, str] | None = None
    match, text = _take(
        rf"\bambient(?:\s+air)?(?:\s+temperature)?{_LINK}{_NUM}\s*(?:°\s*)?"
        r"(c|f|k|celsius|fahrenheit|kelvin)?\b",
        text,
    )
    if match:
        ambient = (float(match.group(1)), (match.group(2) or "c").lower())
    else:
        match, text = _take(
            rf"{_NUM}\s*°\s*(c|f)\b|{_NUM}\s*(celsius)\b|{_NUM}\s*(c|f|k)\s+ambient\b", text
        )
        if match:
            ambient = (
                float(match.group(1) or match.group(3) or match.group(5)),
                (match.group(2) or match.group(4) or match.group(6)).lower(),
            )
    if ambient:
        value, unit = ambient[0], ambient[1][0]
        if unit == "f":
            value = (value - 32) * 5 / 9
        elif unit == "k":
            value -= 273.15
        found["ambient_temperature_c"] = value

    match, text = _take(
        rf"\bpressure[ -]ratio{_LINK}{_NUM}|{_NUM}\s*(?::\s*1)?\s+pressure[ -]ratio", text
    )
    if match:
        found["pressure_ratio"] = float(match.group(1) or match.group(2))

    match, text = _take(
        rf"\b(?:air\s+)?(?:mass\s+)?flow(?:\s+rate)?{_LINK}{_NUM}|{_NUM}\s*kg\s*/\s*s\b", text
    )
    if match:
        found["air_mass_flow_kg_s"] = float(match.group(1) or match.group(2))

    return found


def find_scenarios(question: str) -> list[str]:
    """Return scenario ids named in the question, in the order they appear."""

    text = question.casefold()
    hits: list[tuple[int, str]] = []
    for scenario_id, spec in SCENARIOS.items():
        names = {scenario_id.replace("_", " "), spec.name.casefold()}
        names.update(_SCENARIO_ALIASES.get(scenario_id, ()))
        positions = [text.find(name) for name in names if name in text]
        if positions:
            hits.append((min(positions), scenario_id))
    return [scenario_id for _, scenario_id in sorted(hits)]


def parse_seed(question: str, default: int = 42) -> int:
    match = re.search(r"\bseed\s*(?:of|=|:)?\s*(\d{1,10})\b", question, flags=re.IGNORECASE)
    if match and int(match.group(1)) <= 2_147_483_647:
        return int(match.group(1))
    return default


def refers_to_selection(question: str) -> bool:
    """True when the wording points at the selected sample ("this", "residual", ...)."""

    return _SELECTION_RE.search(question) is not None


def mentions_component(question: str) -> bool:
    return _COMPONENT_RE.search(question) is not None


def refers_to_whole_run(question: str) -> bool:
    """True for run-level questions such as "how many samples are flagged in this run"."""

    return _RUN_RE.search(question) is not None


def refers_explicitly_to_selection(question: str) -> bool:
    """True for "this sample", "selected component", "sample 48" and similar."""

    return _STRONG_SELECTION_RE.search(question) is not None
