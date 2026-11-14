"""Check that numbers in an assistant answer come from something it was given.

Language models can state plausible numbers that no tool produced. This module
extracts the numbers in an answer and looks for each one in the data the
assistant actually had: the user's question, the server-recomputed context, and
the results of the tools that ran. A number it cannot find is reported as
*unverified*; it is not necessarily wrong (it may be a derived value), but the
reader is told it was not traced to a tool result.

The check is deliberately conservative about what it ignores (citations, list
numbering, small counts and "sample N" labels) and tolerant about how a value is
shown (rounding, kW/MW, kelvin/Celsius, fraction/percent).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Optional sign, digits with optional thousands separators, optional decimals.
_NUMBER = re.compile(r"(?<![\w.])([-−+]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\w])")
_CITATION = re.compile(r"\[[^\]\n]*\]")
_CODE_SPAN = re.compile(r"`[^`\n]*`")
_LIST_MARKER = re.compile(r"(?m)^\s*\d{1,2}[.)]\s")
_LABEL_NUMBER = re.compile(
    r"(?i)\b(sample|samples|round|rounds|step|figure|table|page|pages)\s+\d+"
)
_SMALL_INTEGER_LIMIT = 10
_MAX_REPORTED = 12


@dataclass(frozen=True)
class NumberMention:
    text: str
    value: float
    decimals: int


@dataclass(frozen=True)
class Grounding:
    checked: int
    verified: int
    unverified: tuple[str, ...]

    @property
    def all_verified(self) -> bool:
        return not self.unverified

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "verified": self.verified,
            "unverified": list(self.unverified),
            "method": "number-match against question, context and tool results",
        }


def extract_numbers(text: str) -> list[NumberMention]:
    """Return the numbers in ``text`` that the check should account for."""

    cleaned = _CITATION.sub(" ", text)
    cleaned = _CODE_SPAN.sub(" ", cleaned)
    cleaned = _LIST_MARKER.sub(" ", cleaned)
    cleaned = _LABEL_NUMBER.sub(" ", cleaned)
    mentions: list[NumberMention] = []
    for match in _NUMBER.finditer(cleaned):
        sign, whole, fraction = match.groups()
        digits = whole.replace(",", "")
        decimals = len(fraction) if fraction else 0
        value = float(f"{digits}.{fraction}" if fraction else digits)
        if sign in {"-", "−"}:
            value = -value
        if decimals == 0 and abs(value) <= _SMALL_INTEGER_LIMIT:
            continue
        mentions.append(NumberMention(match.group(0).lstrip("+"), value, decimals))
    return mentions


def _walk_numbers(value: Any, found: list[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        found.append(float(value))
    elif isinstance(value, str):
        found.extend(mention.value for mention in extract_numbers(value))
    elif isinstance(value, dict):
        for item in value.values():
            _walk_numbers(item, found)
    elif isinstance(value, list | tuple):
        for item in value:
            _walk_numbers(item, found)


def collect_source_numbers(*sources: Any) -> list[float]:
    """Gather every number from the given JSON-like values and plain strings."""

    found: list[float] = []
    for source in sources:
        _walk_numbers(source, found)
    return found


def _candidates(value: float) -> Iterable[float]:
    """Ways a source value is commonly shown: as is, kW to MW, K and Celsius, fraction to %."""

    yield value
    yield value / 1000.0
    yield value - 273.15
    yield value + 273.15
    yield value * 100.0


def _matches(mention: NumberMention, sources: list[float]) -> bool:
    # Sign is ignored: "residual of -1,000.9 kW" is often written as "1,000.9 kW below".
    target = abs(mention.value)
    tolerance = 0.5 * 10 ** (-mention.decimals) + 1e-9
    for source in sources:
        for candidate in _candidates(source):
            if abs(abs(candidate) - target) <= tolerance:
                return True
    return False


def check_numbers(answer: str, *sources: Any) -> Grounding:
    """Compare the numbers in ``answer`` with the numbers found in ``sources``."""

    mentions = extract_numbers(answer)
    source_numbers = collect_source_numbers(*sources)
    unverified: list[str] = []
    verified = 0
    for mention in mentions:
        if _matches(mention, source_numbers):
            verified += 1
        elif mention.text not in unverified:
            unverified.append(mention.text)
    return Grounding(
        checked=len(mentions),
        verified=verified,
        unverified=tuple(unverified[:_MAX_REPORTED]),
    )
