from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from .parser import normalize_answer

PHYSICAL_EQUIVALENCE_RELATIONS = {"MR-07", "MR-08", "MR-09", "MR-23"}


def positive_claim_class(relation_id: str) -> str:
    return (
        "physical_equivalence_extension"
        if relation_id in PHYSICAL_EQUIVALENCE_RELATIONS
        else "specification_invariance"
    )


def _case_row_family_rates(
    frame: pd.DataFrame, *, prefix: str, accepted_is_error: bool
) -> dict[str, float]:
    error = frame[f"{prefix}_full"].astype(bool)
    if not accepted_is_error:
        error = ~error
    case_micro = float(error.mean())
    row_macro = float(
        frame.assign(_error=error).groupby("row_id", sort=False)["_error"].mean().mean()
    )
    family_macro = float(
        frame.assign(_error=error).groupby("relation_id", sort=False)["_error"].mean().mean()
    )
    return {
        "case_micro": case_micro,
        "row_macro": row_macro,
        "relation_family_macro": family_macro,
    }


def aggregation_sensitivity(positive: pd.DataFrame, negative: pd.DataFrame) -> dict[str, Any]:
    result: dict[str, Any] = {
        "definitions": {
            "case_micro": "mean over generated cases",
            "row_macro": "mean of per-row rates over rows with applicable cases",
            "relation_family_macro": "mean of per-relation rates over applicable relation families",
        },
        "valid_case_rejection": {},
        "invalid_case_acceptance": {},
        "by_claim_class": [],
    }
    for prefix in ["official", "repaired", "type_safe"]:
        result["valid_case_rejection"][prefix] = _case_row_family_rates(
            positive, prefix=prefix, accepted_is_error=False
        )
        result["invalid_case_acceptance"][prefix] = _case_row_family_rates(
            negative, prefix=prefix, accepted_is_error=True
        )

    tagged_positive = positive.assign(claim_class=positive.relation_id.map(positive_claim_class))
    tagged_negative = negative.assign(claim_class="invalid_answer_safety")
    for polarity, frame in [("positive", tagged_positive), ("negative", tagged_negative)]:
        for claim_class, group in frame.groupby("claim_class", sort=True):
            row: dict[str, Any] = {
                "polarity": polarity,
                "claim_class": claim_class,
                "cases": len(group),
                "applicable_rows": int(group.row_id.nunique()),
                "relation_families": int(group.relation_id.nunique()),
            }
            for prefix in ["official", "repaired", "type_safe"]:
                if polarity == "positive":
                    row[f"{prefix}_case_error_rate"] = float((~group[f"{prefix}_full"]).mean())
                    row[f"{prefix}_invariance_failure_rate"] = float(
                        (group[f"{prefix}_full"] != group[f"{prefix}_canonical_full"]).mean()
                    )
                else:
                    row[f"{prefix}_case_error_rate"] = float(group[f"{prefix}_full"].mean())
            result["by_claim_class"].append(row)
    return result


def label_consistency(
    positive: pd.DataFrame, negative: pd.DataFrame
) -> tuple[dict[str, Any], pd.DataFrame]:
    positive_keys = positive[["row_id", "answer", "relation_id"]].copy()
    negative_keys = negative[["row_id", "answer", "relation_id"]].copy()
    positive_keys["normalized_answer"] = positive_keys.answer.map(
        lambda value: normalize_answer(str(value), extraction_policy="global").casefold()
    )
    negative_keys["normalized_answer"] = negative_keys.answer.map(
        lambda value: normalize_answer(str(value), extraction_policy="global").casefold()
    )
    conflicts = positive_keys.merge(
        negative_keys,
        on=["row_id", "normalized_answer"],
        suffixes=("_positive", "_negative"),
    )
    payload = {
        "positive_cases": len(positive),
        "negative_cases": len(negative),
        "exact_row_answer_conflicts": int(
            positive[["row_id", "answer"]]
            .drop_duplicates()
            .merge(negative[["row_id", "answer"]].drop_duplicates())
            .shape[0]
        ),
        "normalized_row_answer_conflicts": len(conflicts),
        "interpretation": (
            "A conflict means the same normalized (row_id, answer) was generated as both "
            "semantics-preserving and contract-breaking."
        ),
    }
    return payload, conflicts


def row_violation_distribution(
    census: pd.DataFrame,
    canonical: pd.DataFrame,
    positive: pd.DataFrame,
    negative: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    canonical_groups = {str(key): group for key, group in canonical.groupby("row_id")}
    positive_groups = {str(key): group for key, group in positive.groupby("row_id")}
    negative_groups = {str(key): group for key, group in negative.groupby("row_id")}
    for row_id in census.row_id.astype(str):
        gold = canonical_groups[row_id]
        valid = positive_groups[row_id]
        invalid = negative_groups[row_id]
        base: dict[str, Any] = {"row_id": row_id}
        for prefix in ["official", "repaired", "type_safe"]:
            invariance = set(
                valid.loc[
                    valid[f"{prefix}_full"] != valid[f"{prefix}_canonical_full"],
                    "relation_id",
                ].astype(str)
            )
            over_acceptance = set(invalid.loc[invalid[f"{prefix}_full"], "relation_id"].astype(str))
            base[f"{prefix}_source_witness_failure"] = bool((~gold[f"{prefix}_source_full"]).any())
            base[f"{prefix}_canonical_failure"] = bool((~gold[f"{prefix}_full"]).any())
            base[f"{prefix}_valid_case_rejection"] = bool((~valid[f"{prefix}_full"]).any())
            base[f"{prefix}_invariance_relation_count"] = len(invariance)
            base[f"{prefix}_invalid_accept_relation_count"] = len(over_acceptance)
            base[f"{prefix}_distinct_violated_relation_count"] = len(invariance | over_acceptance)
        rows.append(base)
    frame = pd.DataFrame(rows)
    summary: dict[str, Any] = {"row_count": len(frame), "evaluators": {}}
    for prefix in ["official", "repaired", "type_safe"]:
        count_column = f"{prefix}_distinct_violated_relation_count"
        summary["evaluators"][prefix] = {
            "rows_with_source_witness_failure": int(
                frame[f"{prefix}_source_witness_failure"].sum()
            ),
            "rows_with_canonical_failure": int(frame[f"{prefix}_canonical_failure"].sum()),
            "rows_with_any_valid_case_rejection": int(
                frame[f"{prefix}_valid_case_rejection"].sum()
            ),
            "rows_with_invariance_failure": int(
                (frame[f"{prefix}_invariance_relation_count"] > 0).sum()
            ),
            "rows_with_invalid_acceptance": int(
                (frame[f"{prefix}_invalid_accept_relation_count"] > 0).sum()
            ),
            "rows_with_any_relation_violation": int((frame[count_column] > 0).sum()),
            "distinct_relation_count_distribution": {
                str(key): int(value) for key, value in sorted(Counter(frame[count_column]).items())
            },
        }
    return summary, frame
