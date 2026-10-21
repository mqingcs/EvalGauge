from __future__ import annotations

import ast
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from anls import anls_score

CaseKind = Literal["source", "positive", "negative"]
SemanticType = Literal["scalar_numeric", "ordered_list", "exact", "text_anls"]


@dataclass(frozen=True)
class ChartQAProContract:
    benchmark: str
    row_id: str
    question_type: str
    target: str
    target_items: tuple[str, ...]
    year_flags: tuple[str, ...]
    semantic_type: SemanticType
    tolerance: Decimal
    container_policy: str
    exact_type_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tolerance"] = str(self.tolerance)
        return payload


@dataclass(frozen=True)
class ChartQAProCase:
    benchmark: str
    row_id: str
    relation_id: str
    case_kind: CaseKind
    answer: str
    expected_label: bool
    semantic_type: str
    applicability_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fix_list_format(item: str) -> Any:
    """Faithful copy of the released ChartQAPro list normalization."""
    if not isinstance(item, str):
        return item
    match = re.match(r"^\[(.*)\]$", item.strip())
    if not match:
        return item
    content = match.group(1)
    corrected = re.sub(r"(?<!['\w])(\w[^,]*?)(?!['\w])", r"'\1'", content)
    try:
        return ast.literal_eval(f"[{corrected}]")
    except (SyntaxError, ValueError):
        return item


def parse_to_list(text: str) -> list[str] | None:
    if not isinstance(text, str):
        return None
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None
    if isinstance(parsed, list):
        return [str(value).strip(" '") for value in parsed]
    return None


def parse_source_list(text: str) -> list[str] | None:
    """Parse the list syntax used by ChartQAPro annotations, including unquoted items."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    try:
        parsed = ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        content = stripped[1:-1]
        if not content.strip():
            return []
        return [item.strip().strip("'\"") for item in content.split(",")]
    if isinstance(parsed, list):
        return [str(value).strip(" '\"") for value in parsed]
    return None


def to_float(text: str) -> float | None:
    try:
        return float(text.strip().strip("%"))
    except (TypeError, ValueError):
        return None


def _decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().strip("%"))
    except (InvalidOperation, AttributeError):
        return None
    return value if value.is_finite() else None


def _final_target(row: Mapping[str, Any]) -> str:
    answers = list(row["Answer"])
    return str(answers[-1]).strip(".").strip("\n")


def _effective_year_flags(row: Mapping[str, Any], item_count: int) -> tuple[str, ...]:
    flags = [str(flag) for flag in row["Year"]]
    if row["Question Type"] == "Conversational":
        flags = flags[-1:]
    if len(flags) < item_count:
        flags = flags * item_count
    return tuple(flags[:item_count])


def compile_chartqapro_contract(
    row: Mapping[str, Any], row_id: str | int
) -> ChartQAProContract:
    target = _final_target(row)
    parsed_items = parse_source_list(target)
    items = tuple(parsed_items or [target])
    flags = _effective_year_flags(row, len(items))
    question_type = str(row["Question Type"])
    exact_reason: str | None = None
    if question_type in {"Fact Checking", "Multi Choice"}:
        semantic_type: SemanticType = "exact"
        exact_reason = "question_type"
    elif any(flag.upper() == "YES" for flag in flags):
        semantic_type = "exact" if len(items) == 1 else "ordered_list"
        exact_reason = "year_flag"
    elif len(items) > 1:
        semantic_type = "ordered_list"
    elif _decimal(items[0]) is not None:
        semantic_type = "scalar_numeric"
    else:
        semantic_type = "text_anls"
    return ChartQAProContract(
        benchmark="ChartQAPro",
        row_id=str(row_id),
        question_type=question_type,
        target=target,
        target_items=items,
        year_flags=flags,
        semantic_type=semantic_type,
        tolerance=Decimal("0.05"),
        container_policy="ordered" if len(items) > 1 else "scalar",
        exact_type_reason=exact_reason,
    )


def _official_element_score(target: str, prediction: str, tolerance: float) -> float:
    target_text = target.strip().strip("%").strip()
    prediction_text = prediction.strip().strip("%").strip()
    target_float = to_float(target_text)
    prediction_float = to_float(prediction_text)
    if target_float is not None and prediction_float is not None:
        if target_float == 0.0:
            return 1.0 if prediction_float == 0.0 else 0.0
        change = abs(prediction_float - target_float) / abs(target_float)
        return 1.0 if change <= tolerance else 0.0
    return float(
        anls_score(
            prediction=prediction_text.lower(),
            gold_labels=[target_text.lower()],
            threshold=0.5,
        )
    )


def official_chartqapro_score(contract: ChartQAProContract, prediction: str) -> float:
    """Execute the released/current ChartQAPro scorer, including observed routing."""
    prediction = str(prediction).strip(".").strip("\n")
    target = contract.target
    target_list = parse_to_list(str(fix_list_format(target))) or [target]
    prediction_list = parse_to_list(prediction) or [prediction]
    flags = list(contract.year_flags)
    scores: list[float] = []
    for index in range(max(len(target_list), len(prediction_list))):
        if index >= len(target_list) or index >= len(prediction_list):
            scores.append(0.0)
            continue
        target_item = target_list[index]
        prediction_item = prediction_list[index]
        flag = flags[index] if index < len(flags) else "NO"
        if flag.upper() == "YES":
            scores.append(
                1.0
                if target_item.strip().lower() == prediction_item.strip().lower()
                else 0.0
            )
        else:
            scores.append(
                _official_element_score(
                    target_item, prediction_item, float(contract.tolerance)
                )
            )
    return sum(scores) / len(scores) if scores else 0.0


def _reference_element_match(
    target: str,
    prediction: str,
    *,
    exact: bool,
    tolerance: Decimal,
) -> bool:
    target_text = target.strip().strip("%").strip()
    prediction_text = prediction.strip().strip("%").strip()
    if exact:
        return target_text.lower() == prediction_text.lower()
    target_decimal = _decimal(target_text)
    prediction_decimal = _decimal(prediction_text)
    if target_decimal is not None:
        if prediction_decimal is None:
            return False
        if target_decimal == 0:
            return prediction_decimal == 0
        return abs(prediction_decimal - target_decimal) / abs(target_decimal) <= tolerance
    return (
        anls_score(
            prediction=prediction_text.lower(),
            gold_labels=[target_text.lower()],
            threshold=0.5,
        )
        > 0
    )


def reference_chartqapro_score(contract: ChartQAProContract, prediction: str) -> bool:
    """Execute the source-declared contract, including intended exact answer types."""
    prediction = str(prediction).strip(".").strip("\n")
    prediction_items = parse_source_list(prediction) or [prediction]
    if len(prediction_items) != len(contract.target_items):
        return False
    for index, (target, candidate) in enumerate(
        zip(contract.target_items, prediction_items, strict=True)
    ):
        flag_exact = contract.year_flags[index].upper() == "YES"
        type_exact = contract.question_type in {"Fact Checking", "Multi Choice"}
        if not _reference_element_match(
            target,
            candidate,
            exact=flag_exact or type_exact,
            tolerance=contract.tolerance,
        ):
            return False
    return True


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _add_case(
    cases: list[ChartQAProCase],
    contract: ChartQAProContract,
    relation_id: str,
    case_kind: CaseKind,
    answer: str,
    expected_label: bool,
    reason: str,
) -> None:
    if any(
        case.relation_id == relation_id and case.answer == answer and case.row_id == contract.row_id
        for case in cases[-12:]
    ):
        return
    cases.append(
        ChartQAProCase(
            benchmark=contract.benchmark,
            row_id=contract.row_id,
            relation_id=relation_id,
            case_kind=case_kind,
            answer=answer,
            expected_label=expected_label,
            semantic_type=contract.semantic_type,
            applicability_reason=reason,
        )
    )


def generate_chartqapro_cases(contract: ChartQAProContract) -> list[ChartQAProCase]:
    cases: list[ChartQAProCase] = []
    _add_case(
        cases,
        contract,
        "XMR-SOURCE",
        "source",
        contract.target,
        True,
        "source final-answer witness",
    )
    _add_case(
        cases,
        contract,
        "XMR-P-PUNCT",
        "positive",
        f"{contract.target}.",
        True,
        "released scorer removes terminal periods",
    )
    if any(character.isalpha() for character in contract.target):
        _add_case(
            cases,
            contract,
            "XMR-P-CASE",
            "positive",
            contract.target.swapcase(),
            True,
            "declared answer matching is case-insensitive",
        )
    if contract.semantic_type == "scalar_numeric":
        value = _decimal(contract.target)
        if value is not None:
            _add_case(
                cases,
                contract,
                "XMR-P-NUMERIC-FORM",
                "positive",
                f"{_decimal_text(value)}.0" if value == value.to_integral() else format(value, "e"),
                True,
                "equivalent finite numeric serialization",
            )
            if contract.target.strip().endswith("%"):
                _add_case(
                    cases,
                    contract,
                    "XMR-P-PERCENT-POLICY",
                    "positive",
                    contract.target.strip().rstrip("%"),
                    True,
                    "ChartQAPro source policy treats a terminal percent sign as optional",
                )
            if value != 0:
                _add_case(
                    cases,
                    contract,
                    "XMR-N-TOLERANCE",
                    "negative",
                    _decimal_text(value * Decimal("1.051")),
                    False,
                    "candidate lies beyond the declared five-percent tolerance",
                )
                _add_case(
                    cases,
                    contract,
                    "XMR-N-FACTOR10",
                    "negative",
                    _decimal_text(value * Decimal(10)),
                    False,
                    "factor-ten value error",
                )
            _add_case(
                cases,
                contract,
                "XMR-N-NUMERIC-SUFFIX",
                "negative",
                f"{contract.target}x",
                False,
                "malformed numeric must not receive text-similarity credit",
            )
            _add_case(
                cases,
                contract,
                "XMR-N-NONFINITE",
                "negative",
                "NaN",
                False,
                "non-finite numeric",
            )
    if contract.semantic_type == "exact":
        _add_case(
            cases,
            contract,
            "XMR-N-EXACT-SUFFIX",
            "negative",
            f"{contract.target}x",
            False,
            "exact answer type with an extra token",
        )
    if contract.container_policy == "ordered":
        serialized = "[" + ", ".join(repr(item) for item in contract.target_items) + "]"
        _add_case(
            cases,
            contract,
            "XMR-P-LIST-SERIALIZATION",
            "positive",
            serialized,
            True,
            "equivalent ordered-list serialization",
        )
        if len(set(contract.target_items)) > 1:
            reverse = "[" + ", ".join(repr(item) for item in reversed(contract.target_items)) + "]"
            if not reference_chartqapro_score(contract, reverse):
                _add_case(
                    cases,
                    contract,
                    "XMR-N-LIST-PERMUTATION",
                    "negative",
                    reverse,
                    False,
                    "contract-distinct ordered-list permutation",
                )
        extra = "[" + ", ".join(
            [*(repr(item) for item in contract.target_items), repr("__extra__")]
        ) + "]"
        _add_case(
            cases,
            contract,
            "XMR-N-LIST-EXTRA",
            "negative",
            extra,
            False,
            "extra ordered-list element",
        )
    return cases


def summarize_relation_rows(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record["relation_id"]), []).append(record)
    summary: list[dict[str, Any]] = []
    for relation_id, rows in sorted(grouped.items()):
        kind = str(rows[0]["case_kind"])
        positive = kind != "negative"
        official_failures = sum(
            (float(row["official_score"]) < 1.0) if positive else (float(row["official_score"]) > 0.0)
            for row in rows
        )
        full_invalid_accepts = sum(
            (not positive) and math.isclose(float(row["official_score"]), 1.0)
            for row in rows
        )
        summary.append(
            {
                "relation_id": relation_id,
                "case_kind": kind,
                "case_count": len(rows),
                "affected_rows": len({str(row["row_id"]) for row in rows}),
                "official_failures": official_failures,
                "official_failure_rate": official_failures / len(rows),
                "full_invalid_accepts": full_invalid_accepts,
            }
        )
    return summary
