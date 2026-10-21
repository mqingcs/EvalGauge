from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, DivisionByZero, InvalidOperation

from .extraction import extract_segment
from .schema import ParsedQuantity
from .units import DEFAULT_REGISTRY, UnitRegistry, normalize_unit_text

CLOCK_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(?!\d)")
NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<mixed>[+\-−]?\d+\s+\d+\s*/\s*\d+)"
    r"|(?<![\w.])(?P<fraction>[+\-−]?\d+\s*/\s*[+\-−]?\d+)"
    r"|(?<![\w.])(?P<number>[+\-−]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?))(?![\w])"
)
INVALID_NUMBER_RE = re.compile(r"(?<!\w)(?:nan|[+\-]?inf(?:inity)?)(?!\w)", re.IGNORECASE)


def _unwrap_latex_text_commands(text: str) -> str:
    """Expose unit text without weakening compound-unit boundary checks.

    Public MeasureBench predictions commonly serialize answers as
    ``\boxed{560\text{ A}}``.  The command is only presentation syntax; keeping
    ``\text{`` between the number and unit prevents otherwise ordinary units
    from being detected.  We unwrap a small deterministic set of text commands
    while preserving their contents.  Importantly, ``Pence/kWh`` remains
    ``Pence/kWh`` rather than being collapsed to ``kWh``, so the existing
    proximity/compound-unit checks still reject the wrong dimension.
    """
    command = re.compile(r"\\(?:text|mathrm|textrm|operatorname)\s*\{([^{}]*)\}")
    previous = None
    while previous != text:
        previous = text
        text = command.sub(lambda match: match.group(1), text)
    # The released ``extract_answer`` regex stops at the first closing brace of
    # a nested ``\boxed{...\text{...}}`` expression, leaving the inner command
    # without its final brace. Preserve compatibility with that exact segment.
    text = re.sub(
        r"\\(?:text|mathrm|textrm|operatorname)\s*\{([^{}]*)$",
        lambda match: match.group(1),
        text,
    )
    return text


def normalize_answer(text: str, *, extraction_policy: str = "official_final") -> str:
    raw = extract_segment(str(text).strip(), extraction_policy).strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        structured = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        structured = None
    if isinstance(structured, dict) and structured.get("value") is not None:
        unit = structured.get("unit") or ""
        return f"{structured['value']} {unit}".strip()
    raw = _unwrap_latex_text_commands(raw)
    # Normalize typographic mixed fractions before preserving remaining superscripts as
    # unit powers.  For example, ``3 ³/₈ inches`` must denote one quantity (3.375),
    # rather than the unrelated numeric tokens 3 and 3/8.
    superscript_digits = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    subscript_digits = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

    def replace_mixed_fraction(match: re.Match[str]) -> str:
        numerator = match.group("numerator").translate(superscript_digits)
        denominator = match.group("denominator").translate(subscript_digits)
        return f"{match.group('whole')} {numerator}/{denominator}"

    raw = re.sub(
        r"(?P<whole>[+\-−]?\d+)\s+(?P<numerator>[⁰¹²³⁴⁵⁶⁷⁸⁹]+)\s*[⁄/]\s*"
        r"(?P<denominator>[₀₁₂₃₄₅₆₇₈₉]+)",
        replace_mixed_fraction,
        raw,
    )
    # Preserve powers as explicit unit syntax before NFKC would flatten them to bare digits.
    text = raw.replace("³", "^3").replace("²", "^2")
    text = unicodedata.normalize("NFKC", text)
    replacements = {"−": "-", "–": "-", "‐": "-", " ": " ", "⋅": "·"}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.strip()


def _decimal_from_match(match: re.Match[str]) -> Decimal | None:
    token = match.group(0).replace("−", "-").strip()
    try:
        if match.lastgroup == "mixed":
            whole_text, fraction_text = re.split(r"\s+", token, maxsplit=1)
            numerator, denominator = re.split(r"\s*/\s*", fraction_text, maxsplit=1)
            fraction = Decimal(numerator) / Decimal(denominator)
            whole = Decimal(whole_text)
            return whole - fraction if whole_text.startswith("-") else whole + fraction
        if match.lastgroup == "fraction":
            numerator, denominator = re.split(r"\s*/\s*", token, maxsplit=1)
            return Decimal(numerator) / Decimal(denominator)
        return Decimal(token)
    except (InvalidOperation, DivisionByZero, ZeroDivisionError):
        return None


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    left = r"(?<![\w])" if alias and alias[0].isalnum() else ""
    right = r"(?![\w])" if alias and alias[-1].isalnum() else ""
    return re.compile(left + escaped + right, re.IGNORECASE)


def _find_unit(
    text: str,
    number_span: tuple[int, int],
    registry: UnitRegistry,
    expected_dimension: str | None,
    contract_aliases: tuple[str, ...],
):
    start, end = number_span
    following = text[end : min(len(text), end + 80)]
    preceding = text[max(0, start - 24) : start]
    candidates: list[tuple[int, str, object]] = []
    aliases = set(contract_aliases)
    aliases.update(alias for unit in registry.units.values() for alias in unit.aliases)
    for alias in aliases:
        if not normalize_unit_text(alias):
            continue
        for zone_priority, zone in [(0, following), (1, preceding)]:
            match = _alias_pattern(alias).search(zone)
            if not match:
                continue
            if zone_priority == 0 and match.start() > 5:
                continue
            if zone_priority == 1 and len(zone) - match.end() > 3:
                continue
            unit = registry.resolve(alias, expected_dimension=expected_dimension)
            if unit is None and alias in contract_aliases:
                # The caller later treats exact contract aliases as the branch source unit.
                unit = registry.resolve(alias)
            candidates.append((zone_priority * 1000 + match.start(), alias, unit))
    if not candidates:
        return None, None
    candidates.sort(
        key=lambda item: (
            item[0],
            -len(item[1]),
            normalize_unit_text(item[1]),
            item[1],
        )
    )
    _, alias, unit = candidates[0]
    return alias, unit


def _find_declared_unit(
    text: str,
    registry: UnitRegistry,
    expected_dimension: str | None,
    contract_aliases: tuple[str, ...],
):
    """Read a standalone ``Unit: ...`` field used by historical structured answers."""
    declarations = re.findall(r"(?im)\bunit\b[^:\n]{0,8}[:：]\s*([^\n]+)", text)
    if not declarations:
        return None, None
    aliases = set(contract_aliases)
    aliases.update(alias for unit in registry.units.values() for alias in unit.aliases)
    for declaration in reversed(declarations):
        matches: list[tuple[int, int, str, object]] = []
        for alias in aliases:
            if not normalize_unit_text(alias):
                continue
            match = _alias_pattern(alias).search(declaration)
            if not match:
                continue
            unit = registry.resolve(alias, expected_dimension=expected_dimension)
            if unit is None and alias in contract_aliases:
                unit = registry.resolve(alias)
            matches.append((match.start(), -len(alias), alias, unit))
        if matches:
            _, _, alias, unit = min(matches)
            return alias, unit
    return None, None


def parse_quantities(
    answer: str,
    *,
    registry: UnitRegistry = DEFAULT_REGISTRY,
    expected_dimension: str | None = None,
    contract_aliases: tuple[str, ...] = (),
    extraction_policy: str = "official_final",
) -> tuple[list[ParsedQuantity], list[str]]:
    text = normalize_answer(answer, extraction_policy=extraction_policy)
    warnings: list[str] = []
    if INVALID_NUMBER_RE.search(text):
        return [], ["nonfinite_numeric_token"]
    parsed: list[ParsedQuantity] = []
    declared_raw_unit, declared_unit = _find_declared_unit(
        text, registry, expected_dimension, contract_aliases
    )
    occupied: list[tuple[int, int]] = []
    for match in CLOCK_RE.finditer(text):
        hour, minute, second = match.groups()
        seconds = Decimal(hour) * 3600 + Decimal(minute) * 60 + Decimal(second or 0)
        parsed.append(
            ParsedQuantity(
                semantic_type="clock_time",
                value=seconds,
                unit=None,
                raw_unit=None,
                dimension="time",
                span=match.span(),
                source_text=match.group(0),
            )
        )
        occupied.append(match.span())
    for match in NUMBER_RE.finditer(text):
        if any(match.start() >= left and match.end() <= right for left, right in occupied):
            continue
        if match.start() > 0 and text[match.start() - 1] == "^":
            continue
        value = _decimal_from_match(match)
        if value is None or not value.is_finite():
            warnings.append("invalid_numeric_token")
            continue
        raw_unit, unit = _find_unit(
            text,
            match.span(),
            registry,
            expected_dimension,
            contract_aliases,
        )
        if raw_unit is None and declared_raw_unit is not None:
            raw_unit, unit = declared_raw_unit, declared_unit
        parsed.append(
            ParsedQuantity(
                semantic_type="numeric_quantity",
                value=value,
                unit=unit,
                raw_unit=raw_unit,
                dimension=unit.dimension if unit else None,
                span=match.span(),
                source_text=match.group(0),
            )
        )
    parsed.sort(key=lambda item: item.span)
    return parsed, warnings
