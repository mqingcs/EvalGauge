from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal

from .schema import QuantityBranch, QuantityContract, decimal_text
from .units import DEFAULT_REGISTRY


@dataclass(frozen=True)
class MetamorphicCase:
    relation_id: str
    relation_name: str
    polarity: str
    answer: str
    canonical_answer: str
    expected_full: bool
    branch_index: int
    note: str = ""


@dataclass(frozen=True)
class SchemaMetamorphicCase:
    relation_id: str
    relation_name: str
    answer: str
    canonical_answer: str
    expected_full: bool
    branch_index: int
    variant_name: str
    evaluator_kwargs: dict
    note: str = ""


def _midpoint(branch: QuantityBranch) -> Decimal:
    return (branch.quantity_range.lower + branch.quantity_range.upper) / Decimal(2)


def _number(value: Decimal) -> str:
    return decimal_text(value) or "0"


def _clock(seconds: Decimal, *, short: bool = False) -> str:
    total = int(seconds)
    hour = (total // 3600) % 24
    minute = (total % 3600) // 60
    second = total % 60
    if short and second == 0:
        return f"{hour}:{minute:02d}"
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def canonical_answer(branch: QuantityBranch) -> str:
    if branch.semantic_type == "clock_time":
        return _clock(_midpoint(branch))
    value = _number(_midpoint(branch))
    unit = (
        branch.quantity_range.source_unit.symbol
        if branch.quantity_range.source_unit
        else (
            branch.quantity_range.accepted_unit_aliases[0]
            if branch.quantity_range.accepted_unit_aliases
            else ""
        )
    )
    return f"{value} {unit}".strip()


def source_witness_answer(branch: QuantityBranch) -> str:
    """Render a valid midpoint using the annotation's own first unit spelling."""
    if branch.semantic_type == "clock_time":
        return _clock(_midpoint(branch))
    value = _number(_midpoint(branch))
    unit = (
        branch.quantity_range.accepted_unit_aliases[0]
        if branch.quantity_range.accepted_unit_aliases
        else ""
    )
    return f"{value} {unit}".strip()


def _case(
    relation_id: str,
    name: str,
    answer: str,
    canonical: str,
    expected: bool,
    branch: QuantityBranch,
    note: str = "",
) -> MetamorphicCase:
    return MetamorphicCase(
        relation_id,
        name,
        "positive" if expected else "negative",
        answer,
        canonical,
        expected,
        branch.branch_index,
        note,
    )


RELATION_NAMES = {
    "MR-01": "numeric representation",
    "MR-02": "scientific notation",
    "MR-03": "zeros and explicit sign",
    "MR-04": "natural-language wrapper",
    "MR-05": "whitespace and punctuation",
    "MR-06": "Unicode symbols",
    "MR-07": "registered unit aliases",
    "MR-08": "multiplicative unit conversion",
    "MR-09": "affine temperature conversion",
    "MR-10": "interval container schema",
    "MR-11": "singleton and exact interval",
    "MR-12": "alternative permutation",
    "MR-13": "inclusive boundaries",
    "MR-14": "clock-number separation",
    "MR-15": "right number wrong dimension",
    "MR-16": "wrong same-dimension conversion",
    "MR-17": "SI-prefix factor error",
    "MR-18": "multi-value injection",
    "MR-19": "unit presence contract",
    "MR-20": "parse failure and abstention",
    "MR-21": "locale ambiguity",
    "MR-22": "unit token boundaries",
    "MR-23": "compound units",
    "MR-24": "approximation wrappers",
}


def positive_cases(contract: QuantityContract) -> list[MetamorphicCase]:
    cases: list[MetamorphicCase] = []
    for branch in contract.branches:
        canonical = canonical_answer(branch)
        if branch.semantic_type == "clock_time":
            midpoint = _midpoint(branch)
            for value in [_clock(midpoint), _clock(midpoint, short=True)]:
                cases.append(
                    _case("MR-14", RELATION_NAMES["MR-14"], value, canonical, True, branch)
                )
            cases.append(
                _case(
                    "MR-04",
                    RELATION_NAMES["MR-04"],
                    f"The time is {canonical}.",
                    canonical,
                    True,
                    branch,
                )
            )
            cases.append(
                _case("MR-05", RELATION_NAMES["MR-05"], f"({canonical})", canonical, True, branch)
            )
            continue
        value = _midpoint(branch)
        number = _number(value)
        unit = (
            branch.quantity_range.source_unit.symbol
            if branch.quantity_range.source_unit
            else (
                branch.quantity_range.accepted_unit_aliases[0]
                if branch.quantity_range.accepted_unit_aliases
                else ""
            )
        )
        suffix = f" {unit}" if unit else ""
        for variant in [number, f"{number}.0" if "." not in number else f"{number}0"]:
            cases.append(
                _case(
                    "MR-01", RELATION_NAMES["MR-01"], f"{variant}{suffix}", canonical, True, branch
                )
            )
        if value != 0:
            cases.append(
                _case(
                    "MR-02",
                    RELATION_NAMES["MR-02"],
                    f"{value.normalize():E}{suffix}",
                    canonical,
                    True,
                    branch,
                )
            )
        cases.extend(
            [
                _case(
                    "MR-03", RELATION_NAMES["MR-03"], f"+{number}{suffix}", canonical, True, branch
                ),
                _case(
                    "MR-04",
                    RELATION_NAMES["MR-04"],
                    f"The reading is {canonical}.",
                    canonical,
                    True,
                    branch,
                ),
                _case(
                    "MR-04",
                    RELATION_NAMES["MR-04"],
                    f"Answer: {canonical}",
                    canonical,
                    True,
                    branch,
                ),
                _case("MR-05", RELATION_NAMES["MR-05"], f"({canonical})", canonical, True, branch),
                _case(
                    "MR-05",
                    RELATION_NAMES["MR-05"],
                    f"{number}  {unit}.".strip(),
                    canonical,
                    True,
                    branch,
                ),
                _case(
                    "MR-24",
                    RELATION_NAMES["MR-24"],
                    f"approximately {canonical}",
                    canonical,
                    True,
                    branch,
                ),
            ]
        )
        qrange = branch.quantity_range
        if qrange.lower != qrange.upper:
            cases.extend(
                [
                    _case(
                        "MR-13",
                        RELATION_NAMES["MR-13"],
                        f"{_number(qrange.lower)}{suffix}",
                        canonical,
                        True,
                        branch,
                        "lower boundary",
                    ),
                    _case(
                        "MR-13",
                        RELATION_NAMES["MR-13"],
                        f"{_number(qrange.upper)}{suffix}",
                        canonical,
                        True,
                        branch,
                        "upper boundary",
                    ),
                ]
            )
        if qrange.exact:
            cases.append(
                _case(
                    "MR-11",
                    RELATION_NAMES["MR-11"],
                    canonical,
                    canonical,
                    True,
                    branch,
                    "exact point as singleton",
                )
            )
        for alias in qrange.accepted_unit_aliases[:3]:
            cases.append(
                _case(
                    "MR-07", RELATION_NAMES["MR-07"], f"{number} {alias}", canonical, True, branch
                )
            )
        source = qrange.source_unit
        if source and source.dimension not in {"temperature"}:
            alternatives = [
                unit
                for unit in DEFAULT_REGISTRY.compatible_units(source.dimension)
                if unit.symbol != source.symbol and unit.conversion_safe
            ]
            if alternatives:
                target = alternatives[0]
                converted = target.from_base(source.to_base(value))
                cases.append(
                    _case(
                        "MR-08",
                        RELATION_NAMES["MR-08"],
                        f"{_number(converted)} {target.symbol}",
                        canonical,
                        True,
                        branch,
                    )
                )
        if source and source.dimension == "temperature":
            target = DEFAULT_REGISTRY.units["°F" if source.symbol == "°C" else "°C"]
            converted = target.from_base(source.to_base(value))
            cases.append(
                _case(
                    "MR-09",
                    RELATION_NAMES["MR-09"],
                    f"{_number(converted)} {target.symbol}",
                    canonical,
                    True,
                    branch,
                )
            )
        if unit:
            unicode_unit = unit.replace("cm^3", "cm³").replace("kgf/cm^2", "kgf/cm²")
            cases.append(
                _case(
                    "MR-06",
                    RELATION_NAMES["MR-06"],
                    f"{number} {unicode_unit}",
                    canonical,
                    True,
                    branch,
                )
            )
        if unit and "/" in unit:
            cases.append(
                _case("MR-23", RELATION_NAMES["MR-23"], canonical, canonical, True, branch)
            )
    # Deduplicate exact witnesses within relation/branch while retaining coverage.
    unique: dict[tuple[str, int, str], MetamorphicCase] = {}
    for case in cases:
        unique[(case.relation_id, case.branch_index, case.answer)] = case
    return list(unique.values())


def _map_interval_container(value, transform, *, tuple_container: bool = False):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return value
    mapped = [transform(value[0]), transform(value[1])]
    if tuple_container or isinstance(value, tuple):
        return tuple(mapped)
    return mapped


def schema_positive_cases(contract: QuantityContract) -> list[SchemaMetamorphicCase]:
    """Generate schema-side equivalents while holding the candidate answer fixed."""
    source = contract.source_schema
    variants: list[tuple[str, str, dict, str]] = []

    def transform_intervals(transform, *, tuple_container: bool = False) -> dict:
        spec = deepcopy(source)
        if contract.evaluator == "interval_matching":
            spec["interval"] = _map_interval_container(
                spec.get("interval"), transform, tuple_container=tuple_container
            )
        else:
            mapped = [
                _map_interval_container(interval, transform, tuple_container=tuple_container)
                for interval in spec.get("intervals", [])
            ]
            spec["intervals"] = tuple(mapped) if tuple_container else mapped
        return spec

    numeric_present = any(
        branch.semantic_type == "numeric_quantity" for branch in contract.branches
    )
    if numeric_present:
        as_strings = transform_intervals(
            lambda value: str(value) if not (isinstance(value, str) and ":" in value) else value
        )
        variants.append(
            (
                "MR-10",
                "numeric_endpoints_as_strings",
                as_strings,
                "numeric endpoints serialized as strings",
            )
        )
        as_floats = transform_intervals(
            lambda value: float(value) if not (isinstance(value, str) and ":" in value) else value
        )
        variants.append(
            (
                "MR-10",
                "numeric_endpoints_as_floats",
                as_floats,
                "numeric endpoints serialized as floats",
            )
        )
    tuple_spec = transform_intervals(lambda value: value, tuple_container=True)
    variants.append(
        ("MR-10", "tuple_interval_container", tuple_spec, "list/tuple container equivalence")
    )

    if contract.evaluator == "multi_interval_matching" and len(contract.branches) > 1:
        permuted = deepcopy(source)
        permuted["intervals"] = list(reversed(permuted.get("intervals", [])))
        raw_units = permuted.get("units", [])
        if (
            isinstance(raw_units, (list, tuple))
            and raw_units
            and not all(isinstance(item, str) for item in raw_units)
        ):
            permuted["units"] = list(reversed(raw_units))
        variants.append(
            ("MR-12", "reverse_alternative_order", permuted, "interval-unit pairs reversed")
        )

    cases: list[SchemaMetamorphicCase] = []
    for relation_id, variant_name, spec, note in variants:
        for branch in contract.branches:
            canonical = canonical_answer(branch)
            cases.append(
                SchemaMetamorphicCase(
                    relation_id=relation_id,
                    relation_name=RELATION_NAMES[relation_id],
                    answer=canonical,
                    canonical_answer=canonical,
                    expected_full=True,
                    branch_index=branch.branch_index,
                    variant_name=variant_name,
                    evaluator_kwargs=spec,
                    note=note,
                )
            )
    return cases
