from __future__ import annotations

from decimal import Decimal

from .metamorphic import RELATION_NAMES, MetamorphicCase, canonical_answer
from .schema import QuantityBranch, QuantityContract, decimal_text
from .units import DEFAULT_REGISTRY


def _text(value: Decimal) -> str:
    return decimal_text(value) or "0"


def _epsilon(branch: QuantityBranch) -> Decimal:
    qrange = branch.quantity_range
    width = abs(qrange.upper - qrange.lower)
    magnitude = max(abs(qrange.lower), abs(qrange.upper), Decimal(1))
    return max(width / Decimal(1000), magnitude * Decimal("0.000001"), Decimal("0.000000001"))


def _unit(branch: QuantityBranch) -> str:
    if branch.quantity_range.source_unit:
        return branch.quantity_range.source_unit.symbol
    return (
        branch.quantity_range.accepted_unit_aliases[0]
        if branch.quantity_range.accepted_unit_aliases
        else ""
    )


def _case(
    relation: str, answer: str, canonical: str, branch: QuantityBranch, note: str
) -> MetamorphicCase:
    return MetamorphicCase(
        relation,
        RELATION_NAMES[relation],
        "negative",
        answer,
        canonical,
        False,
        branch.branch_index,
        note,
    )


def negative_cases(contract: QuantityContract) -> list[MetamorphicCase]:
    cases: list[MetamorphicCase] = []
    for branch in contract.branches:
        canonical = canonical_answer(branch)
        qrange = branch.quantity_range
        if branch.semantic_type == "clock_time":
            cases.extend(
                [
                    _case(
                        "MR-14",
                        "60",
                        canonical,
                        branch,
                        "numeric-looking answer for clock contract",
                    ),
                    _case("MR-20", "cannot determine", canonical, branch, "abstention"),
                    _case(
                        "MR-18",
                        f"{canonical} or 23:59:59",
                        canonical,
                        branch,
                        "contradictory multiple times",
                    ),
                ]
            )
            continue
        unit = _unit(branch)
        suffix = f" {unit}" if unit else ""
        midpoint = (qrange.lower + qrange.upper) / Decimal(2)
        epsilon = _epsilon(branch)
        cases.extend(
            [
                _case(
                    "MR-13",
                    f"{_text(qrange.lower - epsilon)}{suffix}",
                    canonical,
                    branch,
                    "below lower boundary",
                ),
                _case(
                    "MR-13",
                    f"{_text(qrange.upper + epsilon)}{suffix}",
                    canonical,
                    branch,
                    "above upper boundary",
                ),
                _case(
                    "MR-17",
                    f"{_text(midpoint * 10)}{suffix}",
                    canonical,
                    branch,
                    "factor-10 numeric error",
                ),
                _case(
                    "MR-17",
                    f"{_text(midpoint / 10)}{suffix}",
                    canonical,
                    branch,
                    "decimal-point shift",
                ),
                _case("MR-20", "unknown", canonical, branch, "parse failure"),
                _case("MR-20", "N/A", canonical, branch, "abstention"),
                _case("MR-20", "NaN", canonical, branch, "NaN"),
                _case("MR-20", "Inf", canonical, branch, "infinity"),
                _case("MR-20", f"{'9' * 256}{suffix}", canonical, branch, "extremely long number"),
                _case(
                    "MR-18",
                    f"{canonical} or {_text(qrange.upper + epsilon)}{suffix}",
                    canonical,
                    branch,
                    "one correct and one wrong value",
                ),
                _case("MR-14", "01:00", canonical, branch, "clock-looking numeric"),
                _case(
                    "MR-21",
                    f"{_text(midpoint).replace('.', ',')}{suffix}",
                    canonical,
                    branch,
                    "undeclared decimal comma",
                ),
            ]
        )
        if qrange.accepted_unit_aliases:
            wrong_dimension = "mm" if branch.dimension != "length" else "°C"
            cases.extend(
                [
                    _case(
                        "MR-15",
                        f"{_text(midpoint)} {wrong_dimension}",
                        canonical,
                        branch,
                        "same number wrong dimension",
                    ),
                    _case("MR-19", _text(midpoint), canonical, branch, "missing required unit"),
                    _case(
                        "MR-22",
                        f"{_text(midpoint)} {unit}m",
                        canonical,
                        branch,
                        "unit substring extension",
                    ),
                ]
            )
        source = qrange.source_unit
        if source:
            alternatives = [
                candidate
                for candidate in DEFAULT_REGISTRY.compatible_units(source.dimension)
                if candidate.symbol != source.symbol and candidate.conversion_safe
            ]
            if alternatives:
                target = alternatives[0]
                cases.append(
                    _case(
                        "MR-16",
                        f"{_text(midpoint)} {target.symbol}",
                        canonical,
                        branch,
                        "unit changed without converting value",
                    )
                )
        if midpoint < 0:
            cases.append(
                _case(
                    "MR-03",
                    f"{_text(abs(midpoint))}{suffix}",
                    canonical,
                    branch,
                    "negative sign removed",
                )
            )
    unique: dict[tuple[str, int, str, str], MetamorphicCase] = {}
    for case in cases:
        unique[(case.relation_id, case.branch_index, case.answer, case.note)] = case
    # Include only candidates that are outside the complete union of legal branches.
    # This prevents a near miss for one unit branch from being a valid alternative branch.
    from .matcher import score_typed

    return [case for case in unique.values() if not score_typed(case.answer, contract).full_match]
