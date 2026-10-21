#!/usr/bin/env python3
"""Verify the frozen headline claims in an EvalGauge release.

This check is intentionally lightweight: it uses only Python's standard library
and the machine-readable analysis files already distributed with the artifact.
It performs no network access, model inference, or data regeneration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def changed_count(transitions: dict[str, int]) -> int:
    return int(transitions.get("01", 0)) + int(transitions.get("10", 0))


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, dict):
        return {prefix: value}
    result: dict[str, Any] = {}
    for key, child in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else key
        result.update(flatten(child, child_prefix))
    return result


def main() -> int:
    verification = load_json("analysis/verification_summary.json")
    expected = verification["quick_verification"]
    audit = load_json("analysis/audit_summary.json")
    chart = load_json("analysis/xbench_chartqapro_summary.json")
    parity = load_json("analysis/upstream_parity.json")
    mr12 = load_json("analysis/mr12_source_schema_validation.json")
    differential = load_json("analysis/differential_summary.json")
    public = load_json("analysis/public_model_rescoring.json")
    profiles = load_json("analysis/scoring_profile_analysis.json")
    dual = load_json("analysis/dual_manual_review_analysis.json")
    contemporary = load_json("analysis/model_rescoring.json")

    measurebench_cases = audit["generated_positive_cases"] + audit["generated_negative_cases"]
    official_invalid = next(
        row["negative_cases"]
        for row in differential["transition_matrix"]
        if row["transition"] == "110"
    )
    chart_invalid = round(chart["invalid_nonzero_credit_rate"] * chart["negative_cases"])

    public_transitions = profiles["profile_boundary_transitions"]
    support = dual["final_support_by_claim_profile"]
    all_ranking = next(row for row in public["ranking_sensitivity"] if row["split"] == "all")
    ranking_reversal = (
        all_ranking["policies"]["official"]["order"]
        != all_ranking["policies"]["typed_global"]["order"]
    )
    type_safe = next(
        row for row in audit["evaluator_metrics"] if row["evaluator"] == "type-safe"
    )
    reference_closed = (
        type_safe["positive_acceptance_rate"] == 1.0
        and type_safe["false_acceptance_rate"] == 0.0
        and chart["reference_suite_conformance"] == 1.0
    )

    actual = {
        "generated_cases": {
            "measurebench": measurebench_cases,
            "chartqapro": chart["generated_cases"],
            "combined": measurebench_cases + chart["generated_cases"],
            "reference_conformance": (
                f"{measurebench_cases + chart['generated_cases']}/"
                f"{measurebench_cases + chart['generated_cases']}"
                if reference_closed
                else "failed"
            ),
        },
        "upstream_parity": {
            "measurebench": parity["total_executions"],
            "chartqapro": chart["upstream_parity_executions"],
            "combined": parity["total_executions"] + chart["upstream_parity_executions"],
            "mismatches": parity["total_mismatches"] + chart["upstream_parity_mismatches"],
        },
        "mr12": {
            "flips": mr12["binary_score_flips"],
            "rows": mr12["rows_with_order_dependent_legacy_score"],
            "truncated_alternatives": mr12["alternatives_truncated_by_zip"],
        },
        "invalid_credit": {
            "measurebench": f"{official_invalid}/{audit['generated_negative_cases']}",
            "chartqapro": f"{chart_invalid}/{chart['negative_cases']}",
        },
        "released_predictions": {
            "answers": public["answer_count"],
            "changed_labels": public["official_typed_final_changed_records"],
            "changed_rows": public["official_typed_final_changed_unique_rows"],
        },
        "profile_ladder": {
            "official_to_core": changed_count(public_transitions["public_official_to_core"]),
            "core_to_physics": changed_count(public_transitions["public_core_to_physics"]),
            "physics_to_strict": changed_count(public_transitions["public_physics_to_strict"]),
        },
        "dual_review": {
            "agreement": (
                f"{dual['finalized_sop_pre_adjudication_exact_agreement_count']}/"
                f"{dual['case_count']}"
            ),
            "kappa": round(dual["finalized_sop_pre_adjudication_cohen_kappa_three_way"], 3),
            "core_alignment": (
                f"{dual['final_policy_alignment']['core']['count']}/"
                f"{dual['final_determinate_count']}"
            ),
            "source_core": (
                f"{support['source_declared_core']['supports_core']}/"
                f"{support['source_declared_core']['determinate']}"
            ),
            "safety_strict": (
                f"{support['safety_strict_policy']['supports_strict']}/"
                f"{support['safety_strict_policy']['determinate']}"
            ),
            "physics_extension": (
                f"{support['physics_equivalent_extension']['supports_physics']}/"
                f"{support['physics_equivalent_extension']['determinate']}"
            ),
            "source_issues": dual["independently_flagged_source_issue_count"],
            "sop_returned": dual["protocol_return_case_count"],
            "verdicts": (
                f"{dual['final_verdict_counts']['accept']}/"
                f"{dual['final_verdict_counts']['reject']}/"
                f"{dual['final_verdict_counts']['ambiguous']}"
            ),
        },
        "contemporary_transfer": {
            "answers": contemporary["answer_count"],
            "changed_labels": changed_count(
                public_transitions["contemporary_official_to_strict"]
            ),
        },
        "extraction_sensitivity": {
            "changed_labels": public["typed_final_global_changed_records"],
            "ranking_reversal": ranking_reversal,
        },
    }

    expected_flat = flatten(expected)
    actual_flat = flatten(actual)
    failures = []
    for key, expected_value in expected_flat.items():
        actual_value = actual_flat.get(key, "<missing>")
        if actual_value != expected_value:
            failures.append((key, expected_value, actual_value))

    if failures:
        print("EvalGauge release verification: FAIL")
        for key, expected_value, actual_value in failures:
            print(f"  {key}: expected {expected_value!r}, found {actual_value!r}")
        return 1

    print("EvalGauge offline release verification")
    print(
        "[PASS] generated cases: "
        f"{actual['generated_cases']['measurebench']:,} + "
        f"{actual['generated_cases']['chartqapro']:,} = "
        f"{actual['generated_cases']['combined']:,}"
    )
    print(
        "[PASS] upstream parity: "
        f"{actual['upstream_parity']['combined']:,} executions, "
        f"{actual['upstream_parity']['mismatches']} mismatches"
    )
    print(
        "[PASS] MR-12: "
        f"{actual['mr12']['flips']} flips / {actual['mr12']['rows']} rows; "
        f"{actual['mr12']['truncated_alternatives']} alternatives truncated"
    )
    print(
        "[PASS] invalid credit: MeasureBench "
        f"{actual['invalid_credit']['measurebench']}; ChartQAPro "
        f"{actual['invalid_credit']['chartqapro']}"
    )
    print(
        "[PASS] released predictions: "
        f"{actual['released_predictions']['answers']:,} answers; "
        f"{actual['released_predictions']['changed_labels']} labels / "
        f"{actual['released_predictions']['changed_rows']} rows changed"
    )
    print(
        "[PASS] profile ladder: "
        f"{actual['profile_ladder']['official_to_core']} / "
        f"{actual['profile_ladder']['core_to_physics']} / "
        f"{actual['profile_ladder']['physics_to_strict']} boundary changes"
    )
    print(
        "[PASS] dual review: "
        f"agreement {actual['dual_review']['agreement']}, "
        f"kappa {actual['dual_review']['kappa']:.3f}, "
        "Core alignment on selected transitions "
        f"{actual['dual_review']['core_alignment']}"
    )
    print(
        "[PASS] contemporary transfer: "
        f"{actual['contemporary_transfer']['answers']} answers, "
        f"{actual['contemporary_transfer']['changed_labels']} changed labels"
    )
    print(
        "[PASS] extraction sensitivity: "
        f"{actual['extraction_sensitivity']['changed_labels']} changes, "
        "aggregate order reversed"
    )
    print("PASS: all frozen headline claims match the distributed evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
