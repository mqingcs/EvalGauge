from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .compiler import compile_contract
from .differential import score_legacy
from .extraction import extract_official_final
from .matcher import score_profile, score_typed
from .reporting import write_json, write_jsonl


def _spec(value: str | dict[str, Any]) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else dict(value)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_benchmark(real: Path, synthetic: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for split, path in (("real_world", real), ("synthetic_test", synthetic)):
        frame = pd.read_parquet(path).drop(columns=["image"], errors="ignore")
        for record in frame.to_dict("records"):
            key = f"{split}::{record['question_id']}"
            record["source_split"] = split
            record["row_id"] = key
            rows[key] = record
    if len(rows) != 2442:
        raise ValueError(f"expected 2,442 benchmark rows, found {len(rows):,}")
    return rows


def _load_release_manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / "frozen/standalone_release.json").read_text(encoding="utf-8"))


def _summary_row(group: pd.DataFrame, *, model: str, split: str) -> dict[str, Any]:
    official = group.official_full.astype(bool)
    repaired = group.repaired_full.astype(bool)
    core_final = group.core_final_full.astype(bool)
    physics_final = group.physics_final_full.astype(bool)
    strict_final = group.strict_final_full.astype(bool)
    typed_final = group.typed_final_full.astype(bool)
    typed_robust_final = group.typed_robust_final_full.astype(bool)
    typed_global = group.typed_global_full.astype(bool)
    return {
        "model": model,
        "split": split,
        "rows": len(group),
        "official_accuracy": float(official.mean()),
        "repaired_accuracy": float(repaired.mean()),
        "core_final_accuracy": float(core_final.mean()),
        "physics_final_accuracy": float(physics_final.mean()),
        "strict_final_accuracy": float(strict_final.mean()),
        "typed_final_accuracy": float(typed_final.mean()),
        "typed_robust_final_accuracy": float(typed_robust_final.mean()),
        "typed_global_accuracy": float(typed_global.mean()),
        "delta_typed_final_minus_official": float(typed_final.mean() - official.mean()),
        "delta_core_final_minus_official": float(core_final.mean() - official.mean()),
        "delta_physics_final_minus_official": float(physics_final.mean() - official.mean()),
        "delta_strict_final_minus_official": float(strict_final.mean() - official.mean()),
        "delta_typed_global_minus_typed_final": float(typed_global.mean() - typed_final.mean()),
        "official_to_typed_final_changed": int((official != typed_final).sum()),
        "official_to_core_final_changed": int((official != core_final).sum()),
        "official_to_physics_final_changed": int((official != physics_final).sum()),
        "official_to_strict_final_changed": int((official != strict_final).sum()),
        "official_only_accepts": int((official & ~typed_final).sum()),
        "typed_final_only_accepts": int((~official & typed_final).sum()),
        "typed_final_to_global_changed": int((typed_final != typed_global).sum()),
        "typed_final_to_robust_final_changed": int((typed_final != typed_robust_final).sum()),
        "typed_final_only_vs_global": int((typed_final & ~typed_global).sum()),
        "typed_global_only_vs_final": int((~typed_final & typed_global).sum()),
    }


def _ranking_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ["real_world", "synthetic_test", "all"]:
        group = frame if split == "all" else frame[frame.source_split == split]
        policies = {}
        for column in [
            "official_full",
            "repaired_full",
            "core_final_full",
            "physics_final_full",
            "strict_final_full",
            "typed_final_full",
            "typed_robust_final_full",
            "typed_global_full",
        ]:
            means = group.groupby("model")[column].mean().sort_values(ascending=False)
            policies[column.removesuffix("_full")] = {
                "order": list(means.index),
                "accuracy": {str(model): float(value) for model, value in means.items()},
            }
        rows.append({"split": split, "policies": policies})
    return rows


def rescore_public_predictions(
    *,
    root: Path,
    prediction_root: Path,
    real: Path,
    synthetic: Path,
    output: Path,
) -> dict[str, Any]:
    manifest = _load_release_manifest(root)
    benchmark = _load_benchmark(real, synthetic)
    output_rows: list[dict[str, Any]] = []
    source_rows = [record for record in manifest["files"] if record.get("model")]
    for source in source_rows:
        path = prediction_root / source["path"]
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if len(payload) != source["rows"]:
            raise ValueError(f"{path} has {len(payload)} rows; expected {source['rows']}")
        seen: set[str] = set()
        for prediction in payload:
            row_id = f"{source['split']}::{prediction['question_id']}"
            if row_id in seen:
                raise ValueError(f"duplicate public prediction: {row_id} in {path}")
            seen.add(row_id)
            if row_id not in benchmark:
                raise KeyError(f"public prediction cannot be linked: {row_id}")
            row = benchmark[row_id]
            evaluator_kwargs = _spec(row["evaluator_kwargs"])
            answer = str(prediction.get("answer") or "")
            official = score_legacy(answer, row["evaluator"], evaluator_kwargs)
            repaired = score_legacy(answer, row["evaluator"], evaluator_kwargs, repair=True)
            contract = compile_contract(
                row_id=row_id,
                split=row["source_split"],
                evaluator=row["evaluator"],
                evaluator_kwargs=evaluator_kwargs,
                image_type=row["image_type"],
                design=row["design"],
            )
            core_final = score_profile(
                answer,
                contract,
                profile="core_final",
                extraction_policy="official_final",
            )
            physics_final = score_profile(
                answer,
                contract,
                profile="physics_final",
                extraction_policy="official_final",
            )
            strict_final = score_profile(
                answer,
                contract,
                profile="strict_final",
                extraction_policy="official_final",
            )
            # Backward-compatible alias for the previously published Contract-final condition.
            typed_final = strict_final
            typed_robust_final = score_typed(
                answer,
                contract,
                extraction_policy="typed_final",
                multi_value_policy="all_valid",
            )
            typed_global = score_typed(
                answer,
                contract,
                extraction_policy="global",
                multi_value_policy="all_valid",
            )
            output_rows.append(
                {
                    "row_id": row_id,
                    "source_question_id": str(row["question_id"]),
                    "source_split": row["source_split"],
                    "image_type": row["image_type"],
                    "design": row["design"],
                    "model": source["model"],
                    "source_path": source["path"],
                    "source_file_sha256": source["sha256"],
                    "answer_sha256": _sha256_text(answer),
                    "official_final_segment": extract_official_final(answer),
                    "official_value": official.value,
                    "official_unit": official.unit,
                    "official_full": official.full,
                    "official_exception": official.exception,
                    "repaired_value": repaired.value,
                    "repaired_unit": repaired.unit,
                    "repaired_full": repaired.full,
                    "repaired_exception": repaired.exception,
                    "core_final_value": core_final.value_match,
                    "core_final_unit": core_final.unit_match,
                    "core_final_full": core_final.full_match,
                    "physics_final_value": physics_final.value_match,
                    "physics_final_unit": physics_final.unit_match,
                    "physics_final_full": physics_final.full_match,
                    "strict_final_value": strict_final.value_match,
                    "strict_final_unit": strict_final.unit_match,
                    "strict_final_full": strict_final.full_match,
                    "typed_final_value": typed_final.value_match,
                    "typed_final_unit": typed_final.unit_match,
                    "typed_final_full": typed_final.full_match,
                    "typed_robust_final_value": typed_robust_final.value_match,
                    "typed_robust_final_unit": typed_robust_final.unit_match,
                    "typed_robust_final_full": typed_robust_final.full_match,
                    "typed_global_value": typed_global.value_match,
                    "typed_global_unit": typed_global.unit_match,
                    "typed_global_full": typed_global.full_match,
                    "official_typed_final_transition": f"{int(official.full)}{int(typed_final.full_match)}",
                    "typed_final_global_transition": f"{int(typed_final.full_match)}{int(typed_global.full_match)}",
                    "typed_final_robust_final_transition": (
                        f"{int(typed_final.full_match)}{int(typed_robust_final.full_match)}"
                    ),
                    "typed_final_trace": json.dumps(
                        typed_final.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                    "core_final_trace": json.dumps(
                        core_final.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                    "physics_final_trace": json.dumps(
                        physics_final.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                    "strict_final_trace": json.dumps(
                        strict_final.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                    "typed_global_trace": json.dumps(
                        typed_global.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                    "typed_robust_final_trace": json.dumps(
                        typed_robust_final.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                }
            )
        expected = {
            f"{source['split']}::{row_id.split('::', 1)[1]}"
            for row_id in benchmark
            if row_id.startswith(source["split"] + "::")
        }
        if seen != expected:
            raise ValueError(
                f"public prediction coverage mismatch for {path}: "
                f"missing={len(expected - seen)}, extra={len(seen - expected)}"
            )

    frame = pd.DataFrame(output_rows)
    if len(frame) != 4884:
        raise ValueError(f"expected 4,884 public predictions, found {len(frame):,}")
    data_dir = output / "data"
    analysis_dir = output / "analysis"
    artifacts_dir = output / "artifacts"
    data_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(data_dir / "public_model_scores.parquet", index=False)

    summaries: list[dict[str, Any]] = []
    for (model, split), group in frame.groupby(["model", "source_split"], sort=True):
        summaries.append(_summary_row(group, model=str(model), split=str(split)))
    for model, group in frame.groupby("model", sort=True):
        summaries.append(_summary_row(group, model=str(model), split="all"))

    breakdown = (
        frame.groupby(["model", "source_split", "design", "image_type"])[
            [
                "official_full",
                "repaired_full",
                "core_final_full",
                "physics_final_full",
                "strict_final_full",
                "typed_final_full",
                "typed_robust_final_full",
                "typed_global_full",
            ]
        ]
        .agg(["count", "mean"])
        .reset_index()
    )
    breakdown.columns = [
        "_".join(str(part) for part in column if part).rstrip("_")
        if isinstance(column, tuple)
        else str(column)
        for column in breakdown.columns
    ]
    breakdown.to_csv(artifacts_dir / "public_model_breakdown.csv", index=False)

    changed = frame[
        (frame.official_full != frame.typed_final_full)
        | (frame.typed_final_full != frame.typed_robust_final_full)
        | (frame.typed_final_full != frame.typed_global_full)
    ]
    changed_rows = (
        changed[
            [
                "row_id",
                "model",
                "source_split",
                "image_type",
                "design",
                "official_final_segment",
                "official_full",
                "repaired_full",
                "core_final_full",
                "physics_final_full",
                "strict_final_full",
                "typed_final_full",
                "typed_robust_final_full",
                "typed_global_full",
                "official_typed_final_transition",
                "core_final_trace",
                "physics_final_trace",
                "strict_final_trace",
                "typed_final_global_transition",
                "typed_final_robust_final_transition",
                "typed_final_trace",
                "typed_global_trace",
                "typed_robust_final_trace",
            ]
        ]
        .where(pd.notna(changed), None)
        .to_dict("records")
    )
    write_jsonl(artifacts_dir / "public_model_changed_cases.jsonl", changed_rows)

    official_changed = frame[frame.official_full != frame.typed_final_full]
    final_global_changed = frame[frame.typed_final_full != frame.typed_global_full]
    official_only = official_changed[
        official_changed.official_full & ~official_changed.typed_final_full
    ]
    typed_only = official_changed[
        ~official_changed.official_full & official_changed.typed_final_full
    ]
    official_only_reasons = (
        official_only.typed_final_trace.map(
            lambda value: json.loads(value).get("invalid_reason") or "unspecified"
        )
        .value_counts()
        .sort_index()
        .to_dict()
    )

    payload = {
        "release_commit": manifest["commit"],
        "answer_count": len(frame),
        "unique_benchmark_rows": int(frame.row_id.nunique()),
        "models": sorted(frame.model.unique()),
        "source_files": source_rows,
        "policy_definitions": {
            "official": "released final-segment extraction plus first-clock/last-numeric legacy matching",
            "repaired": "official policy plus numeric-string endpoint repair only",
            "core_final": "released final-segment extraction, typed unordered alternatives, closed intervals, token-safe matching, and only source-declared unit spellings; any valid extracted quantity suffices",
            "physics_final": "Core-final plus registered same-dimension unit aliases and multiplicative or affine conversion; any valid extracted quantity suffices",
            "strict_final": "Physics-final plus all-extracted-expected-type-quantities-valid aggregation",
            "typed_final": "backward-compatible alias of Strict-final",
            "typed_robust_final": "extended deterministic Answer/Reading/boxed extraction followed by typed all-extracted-quantities-valid matching",
            "typed_global": "whole-response typed all-extracted-quantities-valid matching; sensitivity analysis only",
        },
        "model_split_summaries": summaries,
        "ranking_sensitivity": _ranking_summary(frame),
        "official_typed_final_transition_counts": frame["official_typed_final_transition"]
        .value_counts()
        .sort_index()
        .to_dict(),
        "typed_final_global_transition_counts": frame["typed_final_global_transition"]
        .value_counts()
        .sort_index()
        .to_dict(),
        "typed_final_robust_final_transition_counts": frame["typed_final_robust_final_transition"]
        .value_counts()
        .sort_index()
        .to_dict(),
        "official_typed_final_changed_records": len(official_changed),
        "official_typed_final_changed_unique_rows": int(official_changed.row_id.nunique()),
        "typed_final_only_records": len(typed_only),
        "typed_final_only_already_fixed_by_narrow_repair": int(typed_only.repaired_full.sum()),
        "typed_final_only_beyond_narrow_repair": int((~typed_only.repaired_full).sum()),
        "official_only_records": len(official_only),
        "official_only_typed_rejection_reasons": official_only_reasons,
        "typed_final_global_changed_records": len(final_global_changed),
        "typed_final_global_changed_unique_rows": int(final_global_changed.row_id.nunique()),
        "changed_records": len(changed),
        "changed_unique_rows": int(changed.row_id.nunique()),
    }
    write_json(analysis_dir / "public_model_rescoring.json", payload)
    return payload
