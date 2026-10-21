from __future__ import annotations

from decimal import Decimal
from typing import Literal

from .parser import normalize_answer, parse_quantities
from .schema import AuditScore, ParsedQuantity, QuantityBranch, QuantityContract, decimal_text
from .units import DEFAULT_REGISTRY, UnitRegistry, normalize_unit_text


def _inside(value: Decimal, lower: Decimal, upper: Decimal) -> bool:
    return lower <= value <= upper


def _distance(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    if value < lower:
        return lower - value
    if value > upper:
        return value - upper
    return Decimal(0)


def _match_candidate(
    parsed: ParsedQuantity,
    branch: QuantityBranch,
    registry: UnitRegistry,
    unit_policy: Literal["literal", "physical"],
) -> tuple[bool, bool | None, Decimal, Decimal, str | None]:
    qrange = branch.quantity_range
    if parsed.semantic_type != branch.semantic_type:
        return False, False, Decimal("Infinity"), parsed.value, "semantic_type_mismatch"
    if branch.semantic_type == "clock_time":
        ok = _inside(parsed.value, qrange.lower_base, qrange.upper_base)
        return (
            ok,
            None,
            _distance(parsed.value, qrange.lower_base, qrange.upper_base),
            parsed.value,
            None,
        )

    # Value-only semantics retain the benchmark's raw-number view. Full matching below is typed.
    raw_value_match = _inside(parsed.value, qrange.lower, qrange.upper)
    requires_unit = bool(qrange.accepted_unit_aliases)
    if not requires_unit:
        distance = _distance(parsed.value, qrange.lower, qrange.upper)
        return raw_value_match, None, distance, parsed.value, None
    if parsed.raw_unit is None:
        distance = _distance(parsed.value, qrange.lower, qrange.upper)
        return raw_value_match, False, distance, parsed.value, "missing_unit"

    source_unit = parsed.unit
    normalized_raw = normalize_unit_text(parsed.raw_unit)
    accepted = {normalize_unit_text(alias) for alias in qrange.accepted_unit_aliases}
    if unit_policy == "literal":
        unit_ok = normalized_raw in accepted
        distance = _distance(parsed.value, qrange.lower, qrange.upper)
        return (
            raw_value_match,
            unit_ok,
            distance,
            parsed.value,
            None if unit_ok else "unit_not_declared_by_source_contract",
        )
    if normalized_raw in accepted and qrange.source_unit is not None:
        source_unit = qrange.source_unit
    if source_unit is None or qrange.source_unit is None:
        unit_ok = normalized_raw in accepted
        distance = _distance(parsed.value, qrange.lower, qrange.upper)
        return (
            raw_value_match,
            unit_ok,
            distance,
            parsed.value,
            None if unit_ok else "unknown_or_wrong_unit",
        )
    if source_unit.dimension != qrange.source_unit.dimension:
        distance = _distance(parsed.value, qrange.lower, qrange.upper)
        return raw_value_match, False, distance, parsed.value, "dimension_mismatch"
    try:
        base_value = source_unit.to_base(parsed.value)
    except (ArithmeticError, ValueError):
        return raw_value_match, False, Decimal("Infinity"), parsed.value, "unsafe_conversion"
    typed_ok = _inside(base_value, qrange.lower_base, qrange.upper_base)
    distance = _distance(base_value, qrange.lower_base, qrange.upper_base)
    return typed_ok, True, distance, base_value, None


def score_typed(
    answer: str,
    contract: QuantityContract,
    *,
    registry: UnitRegistry = DEFAULT_REGISTRY,
    multi_value_policy: str = "all_valid",
    extraction_policy: str = "official_final",
    unit_policy: Literal["literal", "physical"] = "physical",
    scoring_profile: str | None = None,
) -> AuditScore:
    if not contract.supported:
        return AuditScore(
            invalid_reason="unsupported_contract", warnings=list(contract.compiler_warnings)
        )
    dimensions = contract.dimensions
    expected_dimension = dimensions[0] if len(dimensions) == 1 else None
    aliases = tuple(
        alias
        for branch in contract.branches
        for alias in branch.quantity_range.accepted_unit_aliases
    )
    parsed, parser_warnings = parse_quantities(
        answer,
        registry=registry,
        expected_dimension=expected_dimension,
        contract_aliases=aliases,
        extraction_policy=extraction_policy,
    )
    trace = AuditScore(
        extraction_policy=extraction_policy,
        scoring_profile=scoring_profile,
        unit_policy=unit_policy,
        multi_value_policy=multi_value_policy,
        extracted_answer=normalize_answer(answer, extraction_policy=extraction_policy),
        warnings=list(contract.compiler_warnings) + parser_warnings,
    )
    trace.parsed_quantities = [
        {
            "semantic_type": item.semantic_type,
            "value": decimal_text(item.value),
            "unit": item.unit.symbol if item.unit else item.raw_unit,
            "dimension": item.dimension,
            "span": list(item.span),
        }
        for item in parsed
    ]
    if not parsed:
        trace.invalid_reason = parser_warnings[0] if parser_warnings else "no_quantity"
        return trace
    expected_types = set(contract.semantic_types)
    candidates = [item for item in parsed if item.semantic_type in expected_types]
    if not candidates:
        trace.invalid_reason = "semantic_type_mismatch"
        return trace
    if multi_value_policy in {"all_valid", "strict_single"} and len(candidates) > 1:
        # Every reported quantity must independently satisfy at least one legal
        # branch. Values may differ inside a declared interval; this policy does
        # not assert exact equality between alternative renderings.
        all_valid = True
        for candidate in candidates:
            candidate_valid = False
            for branch in contract.branches:
                value_ok, unit_ok, _, _, _ = _match_candidate(
                    candidate, branch, registry, unit_policy
                )
                if value_ok and (unit_ok is None or unit_ok):
                    candidate_valid = True
                    break
            if not candidate_valid:
                all_valid = False
                break
        if not all_valid:
            trace.invalid_reason = "multiple_inconsistent_quantities"
            trace.warnings.append("all_extracted_quantities_must_be_valid")
            return trace
    if multi_value_policy == "first":
        candidates = candidates[:1]
    best: (
        tuple[bool, bool | None, Decimal, ParsedQuantity, QuantityBranch, Decimal, str | None]
        | None
    ) = None
    for candidate in candidates:
        for branch in contract.branches:
            value_ok, unit_ok, distance, normalized_value, reason = _match_candidate(
                candidate, branch, registry, unit_policy
            )
            full = value_ok and (unit_ok is None or unit_ok)
            row = (value_ok, unit_ok, distance, candidate, branch, normalized_value, reason)
            if best is None:
                best = row
            else:
                best_full = best[0] and (best[1] is None or best[1])
                if full and not best_full or full == best_full and distance < best[2]:
                    best = row
            if full and multi_value_policy in {"any", "all_valid", "strict_single", "first"}:
                break
        if best and best[0] and (best[1] is None or best[1]):
            break
    assert best is not None
    value_ok, unit_ok, distance, candidate, branch, normalized_value, reason = best
    qrange = branch.quantity_range
    trace.value_match = bool(value_ok)
    trace.unit_match = unit_ok
    trace.full_match = bool(value_ok and (unit_ok is None or unit_ok))
    trace.matched_branch = branch.branch_index
    trace.semantic_type = candidate.semantic_type
    trace.parsed_value = decimal_text(candidate.value)
    trace.parsed_unit = candidate.unit.symbol if candidate.unit else candidate.raw_unit
    trace.canonical_value = decimal_text(normalized_value)
    trace.canonical_unit = qrange.source_unit.symbol if qrange.source_unit else None
    trace.distance_to_interval = decimal_text(distance)
    trace.invalid_reason = None if trace.full_match else reason
    trace.warnings.extend(branch.warnings)
    return trace


ScoringProfile = Literal["core_final", "physics_final", "strict_final"]


def score_profile(
    answer: str,
    contract: QuantityContract,
    *,
    profile: ScoringProfile,
    registry: UnitRegistry = DEFAULT_REGISTRY,
    extraction_policy: str = "official_final",
) -> AuditScore:
    """Execute one declared EvalGauge scoring profile.

    ``core_final`` repairs representation and schema semantics while accepting
    only unit spellings declared by the released row. ``physics_final`` adds
    registered same-dimension unit algebra. ``strict_final`` applies the same
    physical semantics but requires every extracted expected-type quantity in
    the released final segment to satisfy at least one legal branch.
    """

    if profile == "core_final":
        return score_typed(
            answer,
            contract,
            registry=registry,
            extraction_policy=extraction_policy,
            multi_value_policy="any",
            unit_policy="literal",
            scoring_profile=profile,
        )
    if profile == "physics_final":
        return score_typed(
            answer,
            contract,
            registry=registry,
            extraction_policy=extraction_policy,
            multi_value_policy="any",
            unit_policy="physical",
            scoring_profile=profile,
        )
    if profile == "strict_final":
        return score_typed(
            answer,
            contract,
            registry=registry,
            extraction_policy=extraction_policy,
            multi_value_policy="all_valid",
            unit_policy="physical",
            scoring_profile=profile,
        )
    raise ValueError(f"unknown scoring profile: {profile}")
