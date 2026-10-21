#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def key(model: str, row_id: str) -> tuple[str, str]:
    return model, row_id


AMBIGUOUS_REMOVALS = {
    key("Gemini-2.5-Pro", "real_world::electricity_meter_23"),
}


def classify(row: pd.Series) -> tuple[str, str, str]:
    identity = key(str(row.model), str(row.row_id))
    if identity in AMBIGUOUS_REMOVALS:
        return (
            "annotation_ambiguity",
            "official_accept_to_strict_reject",
            "The response reports a price-rate unit while the released contract declares an energy unit; the row is retained as annotation/protocol ambiguity, not claimed as a correction.",
        )
    if bool(row.official_full) == bool(row.physics_final_full) and (
        bool(row.physics_final_full) != bool(row.strict_final_full)
    ):
        return (
            "safety_strict_policy",
            "physics_accept_to_strict_reject",
            "The final segment contains at least one legal and one illegal expected-type quantity; only Strict-final applies the all-quantities-valid aggregation rule.",
        )
    if bool(row.official_full) != bool(row.core_final_full):
        direction = (
            "official_reject_to_core_accept"
            if bool(row.core_final_full)
            else "official_accept_to_core_reject"
        )
        return (
            "source_declared_core",
            direction,
            "Core-final alone changes the decision using typed schema, unordered alternatives, closed intervals, exact source-declared unit tokens, and official final-segment extraction.",
        )
    if bool(row.core_final_full) != bool(row.physics_final_full) and (
        bool(row.official_full) != bool(row.physics_final_full)
    ):
        return (
            "physics_equivalent_extension",
            "core_reject_to_physics_accept",
            "Physics-final changes the Core-final decision only after registered same-dimension alias normalization or multiplicative/affine conversion.",
        )
    raise AssertionError(
        f"unclassified transition: {identity}; "
        f"official/core/physics/strict={int(row.official_full)}/"
        f"{int(row.core_final_full)}/{int(row.physics_final_full)}/"
        f"{int(row.strict_final_full)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    frame = pd.read_parquet(root / "data/public_model_scores.parquet")
    changed = frame[frame.official_full != frame.typed_final_full].copy()
    if len(changed) != 35:
        raise AssertionError(f"expected 35 official/contract transitions, found {len(changed)}")

    labels = changed.apply(classify, axis=1, result_type="expand")
    labels.columns = ["claim_profile", "direction", "rationale"]
    changed = pd.concat([changed.reset_index(drop=True), labels.reset_index(drop=True)], axis=1)
    keep = [
        "row_id",
        "model",
        "source_split",
        "image_type",
        "design",
        "official_final_segment",
        "official_full",
        "repaired_full",
        "typed_final_full",
        "core_final_full",
        "physics_final_full",
        "strict_final_full",
        "claim_profile",
        "direction",
        "rationale",
        "source_file_sha256",
        "answer_sha256",
    ]
    output = changed[keep].sort_values(["claim_profile", "direction", "model", "row_id"])
    artifacts = root / "artifacts"
    analysis = root / "analysis"
    artifacts.mkdir(parents=True, exist_ok=True)
    analysis.mkdir(parents=True, exist_ok=True)
    output.to_csv(artifacts / "public_transition_taxonomy.csv", index=False)

    by_profile = []
    for (profile, direction), group in output.groupby(["claim_profile", "direction"], sort=True):
        by_profile.append(
            {
                "claim_profile": profile,
                "direction": direction,
                "transitions": len(group),
                "unique_rows": int(group.row_id.nunique()),
            }
        )
    payload = {
        "schema": "evalgauge-public-transition-taxonomy-v1",
        "method": (
            "Exhaustive executable-profile audit of the 35 official/Strict-final transitions. "
            "Each transition is assigned by the first profile boundary that changes its score: "
            "source-declared Core-final, declared Physics-final, or Strict-final aggregation. "
            "One known annotation/protocol ambiguity is isolated and not claimed as a correction. "
            "This is a complete decision-scope audit, not an independent human accuracy estimate."
        ),
        "transition_count": len(output),
        "unique_rows": int(output.row_id.nunique()),
        "by_profile_and_direction": by_profile,
        "profile_totals": {
            str(profile): int(count)
            for profile, count in output.claim_profile.value_counts().sort_index().items()
        },
    }
    (analysis / "public_transition_taxonomy.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
