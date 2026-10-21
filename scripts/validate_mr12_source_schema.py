#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pandas as pd

from evalgauge.differential import score_legacy


def _clock_midpoint(interval: list[str]) -> str:
    def seconds(value: str) -> int:
        parts = [int(part) for part in value.split(":")]
        if len(parts) == 2:
            parts.append(0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]

    total = (seconds(interval[0]) + seconds(interval[1])) // 2
    return f"{(total // 3600) % 24:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate MR-12 directly from released schemas and legacy behavior"
    )
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidate_rows = 0
    cardinality_mismatch_rows = 0
    cardinality_aligned_rows = 0
    truncated_alternatives = 0
    affected_rows = 0
    score_flips = 0
    patterns: Counter[str] = Counter()
    examples: list[dict] = []
    for split, path in (("real_world", args.real), ("synthetic_test", args.synthetic)):
        frame = pd.read_parquet(path).drop(columns=["image"], errors="ignore")
        for row in frame.itertuples():
            if row.evaluator != "multi_interval_matching":
                continue
            spec = (
                json.loads(row.evaluator_kwargs)
                if isinstance(row.evaluator_kwargs, str)
                else dict(row.evaluator_kwargs)
            )
            intervals = spec.get("intervals", [])
            units = spec.get("units", [])
            if not (
                isinstance(intervals, list)
                and len(intervals) > 1
                and isinstance(units, list)
                and units
                and all(isinstance(unit, str) for unit in units)
            ):
                continue
            candidate_rows += 1
            if len(intervals) == len(units):
                cardinality_aligned_rows += 1
            else:
                cardinality_mismatch_rows += 1
                truncated_alternatives += max(len(intervals) - len(units), 0)
            patterns[f"intervals={len(intervals)},units={len(units)},values={units!r}"] += 1
            reversed_spec = deepcopy(spec)
            reversed_spec["intervals"] = list(reversed(intervals))
            row_flips = 0
            row_examples: list[dict] = []
            for branch_index, interval in enumerate(intervals):
                if not (
                    isinstance(interval, (list, tuple))
                    and len(interval) == 2
                    and all(isinstance(value, str) and ":" in value for value in interval)
                ):
                    continue
                answer = _clock_midpoint(list(interval))
                original = score_legacy(answer, row.evaluator, spec).full
                permuted = score_legacy(answer, row.evaluator, reversed_spec).full
                if original != permuted:
                    row_flips += 1
                    row_examples.append(
                        {
                            "branch_index": branch_index,
                            "answer": answer,
                            "original": original,
                            "permuted": permuted,
                        }
                    )
            if row_flips:
                affected_rows += 1
                score_flips += row_flips
                if len(examples) < 6:
                    examples.append(
                        {
                            "row_id": f"{split}::{row.question_id}",
                            "intervals": intervals,
                            "units": units,
                            "flips": row_examples,
                        }
                    )

    payload = {
        "schema": "evalgauge-mr12-direct-source-validation-v1",
        "method": (
            "Directly read released evaluator_kwargs, reverse only the interval list when "
            "multiple intervals share a flat string-unit list, and execute the legacy scorer. "
            "This check does not call the typed contract compiler."
        ),
        "flat_unit_multi_interval_rows": candidate_rows,
        "cardinality_aligned_rows": cardinality_aligned_rows,
        "cardinality_mismatch_rows": cardinality_mismatch_rows,
        "alternatives_truncated_by_zip": truncated_alternatives,
        "rows_with_order_dependent_legacy_score": affected_rows,
        "binary_score_flips": score_flips,
        "source_schema_patterns": dict(sorted(patterns.items())),
        "examples": examples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
