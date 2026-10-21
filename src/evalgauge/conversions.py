from __future__ import annotations

from decimal import Decimal

from .schema import CanonicalUnit
from .units import DEFAULT_REGISTRY


def convert(value: Decimal | str | float, source: str, target: str) -> Decimal:
    source_unit = DEFAULT_REGISTRY.resolve(source)
    target_unit = DEFAULT_REGISTRY.resolve(target)
    if source_unit is None or target_unit is None:
        raise ValueError(f"unknown unit conversion: {source!r} -> {target!r}")
    return DEFAULT_REGISTRY.convert(Decimal(str(value)), source_unit, target_unit)


def to_base(value: Decimal | str | float, unit: CanonicalUnit) -> Decimal:
    return unit.to_base(Decimal(str(value)))
