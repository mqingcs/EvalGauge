from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PROFILE_COLUMNS = [
    ("official", "official_full"),
    ("numeric_patch", "repaired_full"),
    ("core_final", "core_final_full"),
    ("physics_final", "physics_final_full"),
    ("strict_final", "strict_final_full"),
]


def transition_counts(frame: pd.DataFrame, left: str, right: str) -> dict[str, int]:
    labels = frame[left].astype(int).astype(str) + frame[right].astype(int).astype(str)
    counts = labels.value_counts().sort_index().to_dict()
    return {label: int(counts.get(label, 0)) for label in ["00", "01", "10", "11"]}


def summarize_group(group: pd.DataFrame, *, source: str, model: str, split: str) -> dict:
    row = {
        "source": source,
        "model": model,
        "split": split,
        "responses": len(group),
        "unique_rows": int(group.row_id.nunique()),
    }
    for label, column in PROFILE_COLUMNS:
        row[f"{label}_accuracy"] = float(group[column].mean())
    row["official_to_core_changed"] = int(
        (group.official_full != group.core_final_full).sum()
    )
    row["core_to_physics_changed"] = int(
        (group.core_final_full != group.physics_final_full).sum()
    )
    row["physics_to_strict_changed"] = int(
        (group.physics_final_full != group.strict_final_full).sum()
    )
    row["official_to_strict_changed"] = int(
        (group.official_full != group.strict_final_full).sum()
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize executable scoring profiles")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()

    public = pd.read_parquet(root / "data/public_model_scores.parquet")
    contemporary = pd.read_parquet(root / "data/model_answers.parquet")
    rows: list[dict] = []
    for (model, split), group in public.groupby(["model", "source_split"], sort=True):
        rows.append(
            summarize_group(
                group,
                source="benchmark_released",
                model=str(model),
                split=str(split),
            )
        )
    for model, group in contemporary.groupby("requested_model", sort=True):
        rows.append(
            summarize_group(
                group,
                source="contemporary_transfer",
                model=str(model),
                split="linked_subset",
            )
        )

    matrix = pd.DataFrame(rows)
    matrix.to_csv(root / "artifacts/scoring_profile_matrix.csv", index=False)
    boundaries = {
        "public_official_to_core": transition_counts(
            public, "official_full", "core_final_full"
        ),
        "public_core_to_physics": transition_counts(
            public, "core_final_full", "physics_final_full"
        ),
        "public_physics_to_strict": transition_counts(
            public, "physics_final_full", "strict_final_full"
        ),
        "public_official_to_strict": transition_counts(
            public, "official_full", "strict_final_full"
        ),
        "contemporary_official_to_core": transition_counts(
            contemporary, "official_full", "core_final_full"
        ),
        "contemporary_core_to_physics": transition_counts(
            contemporary, "core_final_full", "physics_final_full"
        ),
        "contemporary_physics_to_strict": transition_counts(
            contemporary, "physics_final_full", "strict_final_full"
        ),
        "contemporary_official_to_strict": transition_counts(
            contemporary, "official_full", "strict_final_full"
        ),
    }
    payload = {
        "schema": "evalgauge-executable-profile-analysis-v1",
        "profile_definitions": {
            "core_final": (
                "Released final extraction; typed endpoints; unordered alternatives; closed "
                "intervals; token-safe matching against source-declared unit spellings; any "
                "valid expected-type quantity suffices."
            ),
            "physics_final": (
                "Core-final plus registered same-dimension aliases and multiplicative or affine "
                "conversion."
            ),
            "strict_final": (
                "Physics-final plus all-extracted-expected-type-quantities-valid aggregation."
            ),
        },
        "public_responses": len(public),
        "contemporary_responses": len(contemporary),
        "matrix": matrix.to_dict("records"),
        "profile_boundary_transitions": boundaries,
    }
    (root / "analysis/scoring_profile_analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
