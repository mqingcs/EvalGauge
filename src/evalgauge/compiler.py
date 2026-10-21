from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .schema import QuantityBranch, QuantityContract, QuantityRange
from .units import DEFAULT_REGISTRY, IMAGE_DIMENSION_HINTS, UnitRegistry, normalize_unit_text

CLOCK_ENDPOINT_RE = re.compile(r"^\s*[+\-]?\d{1,2}:\d{1,2}(?::[+\-]?\d{1,2})?\s*$")


def to_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise InvalidOperation("boolean is not a scientific quantity")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value).strip())


def clock_to_seconds(value: str) -> Decimal:
    parts = [Decimal(part.strip()) for part in value.split(":")]
    if len(parts) == 2:
        hour, minute = parts
        second = Decimal(0)
    elif len(parts) == 3:
        hour, minute, second = parts
    else:
        raise ValueError(f"invalid clock endpoint: {value!r}")
    return hour * Decimal(3600) + minute * Decimal(60) + second


def _interval_kind(interval: Any) -> str:
    if not isinstance(interval, (list, tuple)) or len(interval) != 2:
        return "unknown"
    if all(isinstance(value, str) and CLOCK_ENDPOINT_RE.match(value) for value in interval):
        return "clock_time"
    try:
        for value in interval:
            to_decimal(value)
        return "numeric_quantity"
    except (InvalidOperation, ValueError, TypeError):
        return "unknown"


def _intervals_and_units(
    evaluator: str, spec: dict[str, Any]
) -> tuple[list[Any], list[list[str]], list[str]]:
    warnings: list[str] = []
    if evaluator == "interval_matching":
        intervals = [spec.get("interval")]
        raw_units = spec.get("units", [])
        if raw_units is None:
            raw_units = []
        if isinstance(raw_units, str):
            raw_units = [raw_units]
            warnings.append("scalar_unit_coerced_to_list")
        units = [list(raw_units)]
        return intervals, units, warnings
    if evaluator != "multi_interval_matching":
        return [], [], [f"unsupported_evaluator:{evaluator}"]
    intervals = list(spec.get("intervals") or [])
    raw_units = spec.get("units", [])
    if raw_units is None or raw_units == []:
        return intervals, [[] for _ in intervals], warnings
    if isinstance(raw_units, str):
        raw_units = [raw_units]
    if isinstance(raw_units, (list, tuple)) and all(isinstance(item, str) for item in raw_units):
        warnings.append("flat_unit_list_broadcast_across_alternatives")
        return intervals, [list(raw_units) for _ in intervals], warnings
    units = [list(item) if isinstance(item, (list, tuple)) else [str(item)] for item in raw_units]
    if len(units) != len(intervals):
        warnings.append(f"unit_branch_count_mismatch:{len(units)}!={len(intervals)}")
        if len(units) == 1:
            units = units * len(intervals)
        else:
            units = (units + [[] for _ in intervals])[: len(intervals)]
    return intervals, units, warnings


def _resolve_source_unit(aliases: list[str], image_type: str, registry: UnitRegistry):
    meaningful = [alias for alias in aliases if normalize_unit_text(alias)]
    hint = IMAGE_DIMENSION_HINTS.get(image_type)
    for alias in meaningful:
        unit = registry.resolve(alias, expected_dimension=hint) if hint else None
        if unit:
            return unit
    for alias in meaningful:
        unit = registry.resolve(alias)
        if unit:
            return unit
    return None


def compile_contract(
    *,
    row_id: str,
    split: str,
    evaluator: str,
    evaluator_kwargs: str | dict[str, Any],
    image_type: str = "",
    design: str = "",
    registry: UnitRegistry = DEFAULT_REGISTRY,
) -> QuantityContract:
    spec = json.loads(evaluator_kwargs) if isinstance(evaluator_kwargs, str) else evaluator_kwargs
    spec = dict(spec)
    intervals, units_by_branch, compiler_warnings = _intervals_and_units(evaluator, spec)
    branches: list[QuantityBranch] = []
    supported = bool(intervals)
    for index, (interval, aliases) in enumerate(zip(intervals, units_by_branch)):
        warnings: list[str] = []
        kind = _interval_kind(interval)
        if kind == "unknown":
            supported = False
            warnings.append("unsupported_interval_schema")
            lower = upper = lower_base = upper_base = Decimal("NaN")
            source_unit = None
            dimension = None
        elif kind == "clock_time":
            lower = clock_to_seconds(str(interval[0]))
            upper = clock_to_seconds(str(interval[1]))
            lower_base, upper_base = lower, upper
            source_unit = None
            dimension = "time"
            if any("-" in str(endpoint).split(":")[-1] for endpoint in interval):
                warnings.append("noncanonical_signed_clock_component")
        else:
            lower, upper = to_decimal(interval[0]), to_decimal(interval[1])
            source_unit = _resolve_source_unit(aliases, image_type, registry)
            dimension = source_unit.dimension if source_unit else None
            if source_unit:
                lower_base = source_unit.to_base(lower)
                upper_base = source_unit.to_base(upper)
            else:
                lower_base, upper_base = lower, upper
                if any(normalize_unit_text(alias) for alias in aliases):
                    warnings.append("unrecognized_unit_context")
            if isinstance(interval[0], str) or isinstance(interval[1], str):
                warnings.append("numeric_interval_serialized_as_string")
        if lower > upper:
            warnings.append("reversed_interval_bounds")
            lower, upper = upper, lower
            lower_base, upper_base = upper_base, lower_base
        meaningful_aliases = tuple(alias for alias in aliases if normalize_unit_text(alias))
        qrange = QuantityRange(
            lower=lower,
            upper=upper,
            lower_base=lower_base,
            upper_base=upper_base,
            source_unit=source_unit,
            accepted_unit_aliases=meaningful_aliases,
            source_interval=(interval[0], interval[1])
            if isinstance(interval, (list, tuple)) and len(interval) == 2
            else (None, None),
        )
        branches.append(
            QuantityBranch(
                semantic_type=kind,
                dimension=dimension,
                quantity_range=qrange,
                branch_index=index,
                warnings=tuple(warnings),
            )
        )
    return QuantityContract(
        row_id=str(row_id),
        split=str(split),
        evaluator=evaluator,
        branches=tuple(branches),
        boundary_policy="closed",
        source_schema=spec,
        image_type=image_type,
        design=design,
        compiler_warnings=tuple(compiler_warnings),
        supported=supported and bool(branches),
    )
