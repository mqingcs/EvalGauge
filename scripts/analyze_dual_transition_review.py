from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

LABELS = ("accept", "reject", "ambiguous")


def load(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row["case_id"]: row for row in payload["reviews"]}


def cohen_kappa(a: list[str], b: list[str]) -> float:
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / len(a)
    ca, cb = Counter(a), Counter(b)
    expected = sum((ca[label] / len(a)) * (cb[label] / len(b)) for label in LABELS)
    return 1.0 if expected == 1.0 else (observed - expected) / (1.0 - expected)


def disagreement_type(a: str, b: str) -> str:
    return "_vs_".join(sorted((a, b)))


def infer_disagreement_category(first: dict, second: dict) -> str:
    notes = " ".join(str(row.get("note", "")) for row in (first, second)).lower()
    if any(token in notes for token in ("模糊", "看不清", "blur", "unreadable")):
        return "visual_readout_uncertainty"
    if first.get("source_issue") or second.get("source_issue") or any(
        token in notes for token in ("原始", "标注", "区间", "interval", "对应")
    ):
        return "source_annotation_or_interval_consistency"
    if any(token in notes for token in ("一半", "两个", "多值", "both", "multiple")):
        return "multi_value_consistency"
    return "response_interpretation"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze dual independent transition reviews")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    review_dir = root / "artifacts/dual_manual_review"
    first = load(review_dir / "reviewer_a.json")
    second = load(review_dir / "reviewer_b.json")
    if set(first) != set(second) or len(first) != 35:
        raise ValueError("reviewer A and B must each contain the same 35 cases")

    ordered = sorted(first)
    verdict_a = [first[case_id]["verdict"] for case_id in ordered]
    verdict_b = [second[case_id]["verdict"] for case_id in ordered]
    returned_path = review_dir / "reviewer_a_returned.json"
    returned_payload = (
        json.loads(returned_path.read_text(encoding="utf-8"))
        if returned_path.exists()
        else {"returned_for_review": []}
    )
    returned = {
        row["case_id"]: row for row in returned_payload.get("returned_for_review", [])
    }
    provisional_a = [
        returned.get(case_id, {}).get("previous_verdict", first[case_id]["verdict"])
        for case_id in ordered
    ]
    disputed = [case_id for case_id in ordered if first[case_id]["verdict"] != second[case_id]["verdict"]]
    adjudication_path = review_dir / "adjudicator.json"
    adjudication = load(adjudication_path) if adjudication_path.exists() else {}
    if adjudication and set(adjudication) != set(disputed):
        raise ValueError("adjudication must cover exactly the reviewer disagreements")

    taxonomy = pd.read_csv(root / "artifacts/public_transition_taxonomy.csv")
    taxonomy.insert(0, "case_id", [f"transition-{index:02d}" for index in range(1, len(taxonomy) + 1)])
    taxonomy = taxonomy.set_index("case_id")
    rows = []
    for case_id in ordered:
        a = first[case_id]["verdict"]
        b = second[case_id]["verdict"]
        category = None
        if a != b:
            category = infer_disagreement_category(first[case_id], second[case_id])
        final = a if a == b else adjudication.get(case_id, {}).get("verdict")
        source_issue = bool(first[case_id]["source_issue"] or second[case_id]["source_issue"])
        if case_id in adjudication:
            source_issue = source_issue or bool(adjudication[case_id]["source_issue"])
        automatic = taxonomy.loc[case_id]
        human_accept = None if final in {None, "ambiguous"} else final == "accept"
        rows.append(
            {
                "case_id": case_id,
                "reviewer_a": a,
                "reviewer_b": b,
                "reviewer_a_note": first[case_id].get("note", ""),
                "reviewer_b_note": second[case_id].get("note", ""),
                "agreed_after_finalized_sop": a == b,
                "disagreement_type": None if a == b else disagreement_type(a, b),
                "disagreement_category": category,
                "adjudicated_verdict": adjudication.get(case_id, {}).get("verdict"),
                "adjudicator_note": adjudication.get(case_id, {}).get("note", ""),
                "final_verdict": final,
                "reviewer_a_source_issue": bool(first[case_id]["source_issue"]),
                "reviewer_b_source_issue": bool(second[case_id]["source_issue"]),
                "source_issue": source_issue,
                "supports_official": None if human_accept is None else human_accept == bool(automatic.official_full),
                "supports_repaired": None if human_accept is None else human_accept == bool(automatic.repaired_full),
                "supports_core": None if human_accept is None else human_accept == bool(automatic.core_final_full),
                "supports_physics": None if human_accept is None else human_accept == bool(automatic.physics_final_full),
                "supports_strict": None if human_accept is None else human_accept == bool(automatic.strict_final_full),
                "official_full": bool(automatic.official_full),
                "repaired_full": bool(automatic.repaired_full),
                "core_final_full": bool(automatic.core_final_full),
                "physics_final_full": bool(automatic.physics_final_full),
                "strict_final_full": bool(automatic.strict_final_full),
                "claim_profile": automatic.claim_profile,
                "direction": automatic.direction,
                "row_id": automatic.row_id,
                "model": automatic.model,
            }
        )

    frame = pd.DataFrame(rows)
    determinate = frame[frame.final_verdict.isin(["accept", "reject"])]
    support_by_profile = {}
    for profile, group in determinate.groupby("claim_profile", sort=True):
        support_by_profile[str(profile)] = {
            "determinate": len(group),
            "supports_official": int(group.supports_official.sum()),
            "supports_repaired": int(group.supports_repaired.sum()),
            "supports_core": int(group.supports_core.sum()),
            "supports_physics": int(group.supports_physics.sum()),
            "supports_strict": int(group.supports_strict.sum()),
        }
    both_source_issue = frame[
        frame.reviewer_a_source_issue & frame.reviewer_b_source_issue
    ]
    summary = {
        "schema": "evalgauge-dual-manual-review-analysis-v1",
        "case_count": len(frame),
        "reviewer_a_verdict_counts": Counter(verdict_a),
        "reviewer_b_verdict_counts": Counter(verdict_b),
        "protocol_return_case_count": len(returned),
        "protocol_return_case_ids": sorted(returned),
        "provisional_first_pass_exact_agreement_count": sum(
            a == b for a, b in zip(provisional_a, verdict_b, strict=True)
        ),
        "provisional_first_pass_exact_agreement_rate": sum(
            a == b for a, b in zip(provisional_a, verdict_b, strict=True)
        )
        / len(ordered),
        "provisional_first_pass_cohen_kappa_three_way": cohen_kappa(
            provisional_a, verdict_b
        ),
        "finalized_sop_pre_adjudication_exact_agreement_count": int(
            frame.agreed_after_finalized_sop.sum()
        ),
        "finalized_sop_pre_adjudication_exact_agreement_rate": float(
            frame.agreed_after_finalized_sop.mean()
        ),
        "finalized_sop_pre_adjudication_cohen_kappa_three_way": cohen_kappa(
            verdict_a, verdict_b
        ),
        "disagreement_count": len(disputed),
        "verdict_pair_disagreement_types": Counter(frame.disagreement_type.dropna()),
        "adjudicated_disagreement_categories": Counter(
            frame.disagreement_category.dropna()
        ),
        "adjudication_complete": bool(adjudication) or not disputed,
        "final_verdict_counts": Counter(frame.final_verdict.dropna()),
        "final_determinate_count": len(determinate),
        "final_policy_alignment": {
            policy: {
                "count": int(determinate[f"supports_{policy}"].sum()),
                "rate": float(determinate[f"supports_{policy}"].mean()),
            }
            for policy in ("official", "repaired", "core", "physics", "strict")
        },
        "final_supports_official": int(determinate.supports_official.sum()),
        "final_supports_strict": int(determinate.supports_strict.sum()),
        "final_support_by_claim_profile": support_by_profile,
        "reviewer_a_source_issue_count": int(frame.reviewer_a_source_issue.sum()),
        "reviewer_b_source_issue_count": int(frame.reviewer_b_source_issue.sum()),
        "source_issue_exact_agreement_count": int(
            (frame.reviewer_a_source_issue == frame.reviewer_b_source_issue).sum()
        ),
        "independently_flagged_source_issue_count": len(both_source_issue),
        "independently_flagged_source_issue_case_ids": both_source_issue.case_id.tolist(),
        "source_issue_count": int(frame.source_issue.sum()),
    }
    analysis_path = root / "analysis/dual_manual_review_analysis.json"
    casebook_path = root / "artifacts/dual_manual_review_casebook.csv"
    analysis_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=dict) + "\n",
        encoding="utf-8",
    )
    frame.to_csv(casebook_path, index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=dict))
    print(casebook_path)


if __name__ == "__main__":
    main()
