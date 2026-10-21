from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Literal

SemanticType = Literal["numeric_quantity", "clock_time", "categorical", "unknown"]


def decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not value.is_finite():
        return str(value)
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class CanonicalUnit:
    symbol: str
    dimension: str
    scale: Decimal = Decimal(1)
    offset: Decimal = Decimal(0)
    aliases: tuple[str, ...] = ()
    conversion: Literal["multiplicative", "affine", "identity"] = "identity"
    conversion_safe: bool = True
    note: str = ""

    def to_base(self, value: Decimal) -> Decimal:
        return self.scale * value + self.offset

    def from_base(self, value: Decimal) -> Decimal:
        return (value - self.offset) / self.scale


@dataclass(frozen=True)
class QuantityRange:
    lower: Decimal
    upper: Decimal
    lower_base: Decimal
    upper_base: Decimal
    source_unit: CanonicalUnit | None
    accepted_unit_aliases: tuple[str, ...]
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    source_interval: tuple[Any, Any] = (None, None)

    @property
    def exact(self) -> bool:
        return self.lower == self.upper


@dataclass(frozen=True)
class QuantityBranch:
    semantic_type: SemanticType
    dimension: str | None
    quantity_range: QuantityRange
    branch_index: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuantityContract:
    row_id: str
    split: str
    evaluator: str
    branches: tuple[QuantityBranch, ...]
    boundary_policy: str
    source_schema: dict[str, Any]
    image_type: str = ""
    design: str = ""
    compiler_warnings: tuple[str, ...] = ()
    supported: bool = True

    @property
    def semantic_types(self) -> tuple[str, ...]:
        return tuple(sorted({branch.semantic_type for branch in self.branches}))

    @property
    def dimensions(self) -> tuple[str, ...]:
        return tuple(sorted({branch.dimension for branch in self.branches if branch.dimension}))


@dataclass(frozen=True)
class ParsedQuantity:
    semantic_type: SemanticType
    value: Decimal
    unit: CanonicalUnit | None
    raw_unit: str | None
    dimension: str | None
    span: tuple[int, int]
    source_text: str
    warnings: tuple[str, ...] = ()


@dataclass
class AuditScore:
    value_match: bool = False
    unit_match: bool | None = False
    full_match: bool = False
    matched_branch: int | None = None
    semantic_type: str | None = None
    parsed_value: str | None = None
    parsed_unit: str | None = None
    canonical_value: str | None = None
    canonical_unit: str | None = None
    distance_to_interval: str | None = None
    invalid_reason: str | None = None
    extraction_policy: str | None = None
    scoring_profile: str | None = None
    unit_policy: str | None = None
    multi_value_policy: str | None = None
    extracted_answer: str | None = None
    warnings: list[str] = field(default_factory=list)
    parsed_quantities: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def contract_to_dict(contract: QuantityContract) -> dict[str, Any]:
    def encode(value: Any) -> Any:
        if isinstance(value, Decimal):
            return decimal_text(value)
        if hasattr(value, "__dataclass_fields__"):
            return {key: encode(val) for key, val in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): encode(val) for key, val in value.items()}
        if isinstance(value, (tuple, list)):
            return [encode(item) for item in value]
        return value

    return encode(contract)
