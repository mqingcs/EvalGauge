from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .compiler import compile_contract
from .differential import differential_score
from .metamorphic import (
    RELATION_NAMES,
    canonical_answer,
    positive_cases,
    schema_positive_cases,
    source_witness_answer,
)
from .negatives import negative_cases
from .reporting import build_html_report, write_json, write_jsonl
from .schema import QuantityContract, contract_to_dict
from .suite_analysis import (
    aggregation_sensitivity,
    label_consistency,
    positive_claim_class,
    row_violation_distribution,
)
from .units import DEFAULT_REGISTRY, normalize_unit_text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_frames(real: Path, synthetic: Path) -> pd.DataFrame:
    frames = []
    for expected_split, path in [("real_world", real), ("synthetic_test", synthetic)]:
        frame = pd.read_parquet(path)
        frame = frame.copy()
        frame["source_file"] = path.name
        frame["source_split"] = expected_split
        frame["evalgauge_row_id"] = expected_split + "::" + frame["question_id"].astype(str)
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    if len(result) != 2442:
        raise ValueError(f"expected 2,442 benchmark rows, found {len(result):,}")
    if result["evalgauge_row_id"].duplicated().any():
        duplicates = result.loc[
            result["evalgauge_row_id"].duplicated(), "evalgauge_row_id"
        ].tolist()
        raise ValueError(f"row identifier collision across benchmark: {duplicates[:10]}")
    return result


def _spec(value: str | dict[str, Any]) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else dict(value)


def _raw_intervals(evaluator: str, spec: dict[str, Any]) -> list[Any]:
    return (
        [spec.get("interval")]
        if evaluator == "interval_matching"
        else list(spec.get("intervals") or [])
    )


def _raw_unit_branches(evaluator: str, spec: dict[str, Any]) -> list[list[str]]:
    units = spec.get("units", []) or []
    intervals = _raw_intervals(evaluator, spec)
    if evaluator == "interval_matching":
        return [list(units) if isinstance(units, (list, tuple)) else [str(units)]]
    if isinstance(units, (list, tuple)) and all(isinstance(item, str) for item in units):
        return [list(units) for _ in intervals]
    return [list(item) if isinstance(item, (list, tuple)) else [str(item)] for item in units]


def _census_row(row: Any, contract: QuantityContract) -> dict[str, Any]:
    spec = _spec(row.evaluator_kwargs)
    intervals = _raw_intervals(row.evaluator, spec)
    endpoints = [
        value for interval in intervals if isinstance(interval, (list, tuple)) for value in interval
    ]
    endpoint_types = sorted({type(value).__name__ for value in endpoints})
    units = [unit for branch in _raw_unit_branches(row.evaluator, spec) for unit in branch]
    exact = sum(
        1
        for interval in intervals
        if isinstance(interval, (list, tuple)) and len(interval) == 2 and interval[0] == interval[1]
    )
    clock_endpoints = sum(isinstance(value, str) and ":" in value for value in endpoints)
    numeric_string_endpoints = sum(
        isinstance(value, str) and ":" not in value and _is_decimal(value) for value in endpoints
    )
    warnings = list(contract.compiler_warnings) + [
        warning for branch in contract.branches for warning in branch.warnings
    ]
    return {
        "row_id": str(row.evalgauge_row_id),
        "source_question_id": str(row.question_id),
        "split": str(row.source_split),
        "design": str(row.design),
        "image_type": str(row.image_type),
        "evaluator": str(row.evaluator),
        "interval_python_type": "+".join(endpoint_types),
        "interval_shape": f"{len(intervals)}x2",
        "number_of_alternatives": len(intervals),
        "unit_count": len(units),
        "unit_alias_count": len(set(units)),
        "clock_presence": clock_endpoints > 0,
        "clock_endpoint_count": clock_endpoints,
        "numeric_string_presence": numeric_string_endpoints > 0,
        "numeric_string_endpoint_count": numeric_string_endpoints,
        "multi_interval": len(intervals) > 1,
        "exact_branch_count": exact,
        "range_branch_count": len(intervals) - exact,
        "recognized_dimension": "|".join(contract.dimensions),
        "semantic_type": "|".join(contract.semantic_types),
        "supported_schema": contract.supported,
        "compiler_warnings": "|".join(sorted(set(warnings))),
        "source_schema_json": json.dumps(spec, ensure_ascii=False, sort_keys=True),
    }


def _is_decimal(value: Any) -> bool:
    try:
        from decimal import Decimal

        Decimal(str(value))
        return True
    except (ArithmeticError, TypeError, ValueError):
        return False


def _score_case(row: Any, answer: str) -> dict[str, Any]:
    spec = _spec(row.evaluator_kwargs)
    return differential_score(
        answer=answer,
        row_id=str(row.evalgauge_row_id),
        split=str(row.source_split),
        evaluator=str(row.evaluator),
        evaluator_kwargs=spec,
        image_type=str(row.image_type),
        design=str(row.design),
    )


def _score_schema_case(row: Any, answer: str, spec: dict[str, Any]) -> dict[str, Any]:
    return differential_score(
        answer=answer,
        row_id=str(row.evalgauge_row_id),
        split=str(row.source_split),
        evaluator=str(row.evaluator),
        evaluator_kwargs=spec,
        image_type=str(row.image_type),
        design=str(row.design),
    )


def _flatten_score(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "official_value": result["official"]["value"],
        "official_unit": result["official"]["unit"],
        "official_full": result["official"]["full"],
        "official_exception": result["official"].get("exception"),
        "repaired_value": result["repaired"]["value"],
        "repaired_unit": result["repaired"]["unit"],
        "repaired_full": result["repaired"]["full"],
        "repaired_exception": result["repaired"].get("exception"),
        "type_safe_value": result["type_safe"]["value_match"],
        "type_safe_unit": result["type_safe"]["unit_match"],
        "type_safe_full": result["type_safe"]["full_match"],
        "score_transition": result["score_transition"],
        "transition_class": result["transition_class"],
        "type_safe_trace_json": json.dumps(result["type_safe"], ensure_ascii=False, sort_keys=True),
    }


def _unit_census(frame: pd.DataFrame) -> pd.DataFrame:
    records: dict[str, dict[str, Any]] = {}
    for row in frame.itertuples(index=False):
        spec = _spec(row.evaluator_kwargs)
        for branch in _raw_unit_branches(row.evaluator, spec):
            for raw in branch:
                key = str(raw)
                record = records.setdefault(
                    key,
                    {
                        "observed_unit": key,
                        "normalized_unit": normalize_unit_text(key),
                        "rows": set(),
                        "splits": set(),
                        "image_types": set(),
                        "canonical_units": set(),
                        "dimensions": set(),
                    },
                )
                record["rows"].add(str(row.evalgauge_row_id))
                record["splits"].add(str(row.source_split))
                record["image_types"].add(str(row.image_type))
                candidates = DEFAULT_REGISTRY.resolve_all(key)
                record["canonical_units"].update(unit.symbol for unit in candidates)
                record["dimensions"].update(unit.dimension for unit in candidates)
    rows = []
    for record in records.values():
        rows.append(
            {
                "observed_unit": record["observed_unit"],
                "normalized_unit": record["normalized_unit"],
                "rows": len(record["rows"]),
                "splits": "|".join(sorted(record["splits"])),
                "image_types": "|".join(sorted(record["image_types"])),
                "canonical_units": "|".join(sorted(record["canonical_units"])),
                "dimensions": "|".join(sorted(record["dimensions"])),
                "status": "recognized"
                if record["canonical_units"] or not record["normalized_unit"]
                else "context_only_or_unsupported",
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["status", "rows", "observed_unit"], ascending=[True, False, True]
    )


def _relation_summary(results: pd.DataFrame, *, positive: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relation_id, group in results.groupby("relation_id", sort=True):
        row = {
            "relation_id": relation_id,
            "relation_name": RELATION_NAMES.get(relation_id, ""),
            "claim_class": (
                positive_claim_class(str(relation_id)) if positive else "invalid_answer_safety"
            ),
            "applicable_rows": int(group["row_id"].nunique()),
            "cases": len(group),
        }
        if positive:
            for prefix in ["official", "repaired", "type_safe"]:
                acceptance = float(group[f"{prefix}_full"].mean())
                invariant = float(
                    (group[f"{prefix}_full"] == group[f"{prefix}_canonical_full"]).mean()
                )
                row[f"{prefix}_acceptance"] = acceptance
                row[f"{prefix}_mir"] = invariant
            row["official_exceptions"] = int(group["official_exception"].notna().sum())
            row["repaired_exceptions"] = int(group["repaired_exception"].notna().sum())
        else:
            for prefix in ["official", "repaired", "type_safe"]:
                row[f"{prefix}_far"] = float(group[f"{prefix}_full"].mean())
        rows.append(row)
    return rows


def _metrics(
    census: pd.DataFrame,
    canonical: pd.DataFrame,
    positive: pd.DataFrame,
    negative: pd.DataFrame,
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    metrics = []
    affected: dict[str, set[str]] = {key: set() for key in ["official", "repaired", "type_safe"]}
    for prefix, label in [
        ("official", "official"),
        ("repaired", "repaired"),
        ("type_safe", "type-safe"),
    ]:
        gold = float(canonical[f"{prefix}_source_full"].mean())
        canonical_acceptance = float(canonical[f"{prefix}_full"].mean())
        pos_accept = float(positive[f"{prefix}_full"].mean())
        mir = float((positive[f"{prefix}_full"] == positive[f"{prefix}_canonical_full"]).mean())
        frr = 1.0 - pos_accept
        far = float(negative[f"{prefix}_full"].mean())
        bad_positive = positive.loc[~positive[f"{prefix}_full"], "row_id"]
        bad_negative = negative.loc[negative[f"{prefix}_full"], "row_id"]
        bad_gold = canonical.loc[~canonical[f"{prefix}_source_full"], "row_id"]
        bad_canonical = canonical.loc[~canonical[f"{prefix}_full"], "row_id"]
        affected[prefix].update(map(str, bad_positive))
        affected[prefix].update(map(str, bad_negative))
        affected[prefix].update(map(str, bad_gold))
        affected[prefix].update(map(str, bad_canonical))
        metrics.append(
            {
                "evaluator": label,
                "gold_self_consistency_rate": gold,
                "canonical_contract_acceptance_rate": canonical_acceptance,
                "positive_acceptance_rate": pos_accept,
                "metamorphic_invariance_rate": mir,
                "false_rejection_rate": frr,
                "false_acceptance_rate": far,
                "contract_violation_coverage": len(affected[prefix]) / len(census),
                "affected_rows": len(affected[prefix]),
            }
        )
    return metrics, affected


def run_audit(*, real: Path, synthetic: Path, output: Path) -> dict[str, Any]:
    data_dir = output / "data"
    analysis_dir = output / "analysis"
    artifacts_dir = output / "artifacts"
    frozen_dir = output / "frozen"
    for directory in [data_dir, analysis_dir, artifacts_dir, frozen_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    frame = _load_frames(real, synthetic)
    census_rows: list[dict[str, Any]] = []
    contract_rows: list[dict[str, Any]] = []
    canonical_rows: list[dict[str, Any]] = []
    positive_rows: list[dict[str, Any]] = []
    negative_rows: list[dict[str, Any]] = []

    for row in frame.itertuples(index=False):
        spec = _spec(row.evaluator_kwargs)
        contract = compile_contract(
            row_id=str(row.evalgauge_row_id),
            split=str(row.source_split),
            evaluator=str(row.evaluator),
            evaluator_kwargs=spec,
            image_type=str(row.image_type),
            design=str(row.design),
        )
        census_rows.append(_census_row(row, contract))
        contract_rows.append(contract_to_dict(contract))
        canonical_cache: dict[int, dict[str, Any]] = {}
        for branch in contract.branches:
            answer = canonical_answer(branch)
            scored = _score_case(row, answer)
            flattened = _flatten_score(scored)
            source_answer = source_witness_answer(branch)
            source_scored = _flatten_score(_score_case(row, source_answer))
            canonical_cache[branch.branch_index] = flattened
            canonical_rows.append(
                {
                    "row_id": str(row.evalgauge_row_id),
                    "source_question_id": str(row.question_id),
                    "split": str(row.source_split),
                    "image_type": str(row.image_type),
                    "design": str(row.design),
                    "branch_index": branch.branch_index,
                    "semantic_type": branch.semantic_type,
                    "dimension": branch.dimension,
                    "canonical_answer": answer,
                    "source_witness_answer": source_answer,
                    "official_source_full": source_scored["official_full"],
                    "repaired_source_full": source_scored["repaired_full"],
                    "type_safe_source_full": source_scored["type_safe_full"],
                    **flattened,
                }
            )
        for case in positive_cases(contract):
            scored = _score_case(row, case.answer)
            flattened = _flatten_score(scored)
            baseline = canonical_cache[case.branch_index]
            positive_rows.append(
                {
                    "row_id": str(row.evalgauge_row_id),
                    "source_question_id": str(row.question_id),
                    "split": str(row.source_split),
                    "image_type": str(row.image_type),
                    "design": str(row.design),
                    **asdict(case),
                    **flattened,
                    "official_canonical_full": baseline["official_full"],
                    "repaired_canonical_full": baseline["repaired_full"],
                    "type_safe_canonical_full": baseline["type_safe_full"],
                }
            )
        for case in schema_positive_cases(contract):
            scored = _score_schema_case(row, case.answer, case.evaluator_kwargs)
            flattened = _flatten_score(scored)
            baseline = canonical_cache[case.branch_index]
            positive_rows.append(
                {
                    "row_id": str(row.evalgauge_row_id),
                    "source_question_id": str(row.question_id),
                    "split": str(row.source_split),
                    "image_type": str(row.image_type),
                    "design": str(row.design),
                    "relation_id": case.relation_id,
                    "relation_name": case.relation_name,
                    "polarity": "positive",
                    "answer": case.answer,
                    "canonical_answer": case.canonical_answer,
                    "expected_full": case.expected_full,
                    "branch_index": case.branch_index,
                    "note": case.note,
                    "variant_name": case.variant_name,
                    "schema_variant_repr": repr(case.evaluator_kwargs),
                    "schema_variant_json": json.dumps(
                        case.evaluator_kwargs, ensure_ascii=False, sort_keys=True
                    ),
                    **flattened,
                    "official_canonical_full": baseline["official_full"],
                    "repaired_canonical_full": baseline["repaired_full"],
                    "type_safe_canonical_full": baseline["type_safe_full"],
                }
            )
        for case in negative_cases(contract):
            scored = _score_case(row, case.answer)
            negative_rows.append(
                {
                    "row_id": str(row.evalgauge_row_id),
                    "source_question_id": str(row.question_id),
                    "split": str(row.source_split),
                    "image_type": str(row.image_type),
                    "design": str(row.design),
                    **asdict(case),
                    **_flatten_score(scored),
                }
            )

    census = pd.DataFrame(census_rows)
    canonical = pd.DataFrame(canonical_rows)
    positive = pd.DataFrame(positive_rows)
    negative = pd.DataFrame(negative_rows)
    units = _unit_census(frame)
    census.to_parquet(data_dir / "schema_census.parquet", index=False)
    units.to_parquet(data_dir / "unit_census.parquet", index=False)
    canonical.to_parquet(data_dir / "canonical_gold_answers.parquet", index=False)
    positive.to_parquet(data_dir / "metamorphic_cases.parquet", index=False)
    negative.to_parquet(data_dir / "negative_cases.parquet", index=False)
    write_jsonl(data_dir / "compiled_contracts.jsonl", contract_rows)

    metrics, affected = _metrics(census, canonical, positive, negative)
    split_metrics = []
    for split in sorted(census.split.unique()):
        split_census = census[census.split == split]
        split_rows = set(split_census.row_id)
        local_metrics, _ = _metrics(
            split_census,
            canonical[canonical.row_id.isin(split_rows)],
            positive[positive.row_id.isin(split_rows)],
            negative[negative.row_id.isin(split_rows)],
        )
        for metric in local_metrics:
            split_metrics.append({"split": split, **metric})
    positive_by_relation = _relation_summary(positive, positive=True)
    negative_by_relation = _relation_summary(negative, positive=False)
    all_cases = pd.concat(
        [
            canonical.assign(polarity="canonical", relation_id="GOLD"),
            positive,
            negative,
        ],
        ignore_index=True,
        sort=False,
    )
    transition_rows = []
    for transition, group in all_cases.groupby("score_transition"):
        transition_rows.append(
            {
                "transition": transition,
                "class": group["transition_class"].iloc[0],
                "positive_cases": int((group["polarity"] == "positive").sum()),
                "negative_cases": int((group["polarity"] == "negative").sum()),
                "canonical_cases": int((group["polarity"] == "canonical").sum()),
                "total": len(group),
            }
        )
    violations = pd.concat(
        [
            positive.loc[
                (~positive.official_full) | (~positive.repaired_full) | (~positive.type_safe_full)
            ],
            negative.loc[negative.official_full | negative.repaired_full | negative.type_safe_full],
        ],
        ignore_index=True,
        sort=False,
    )
    minimal = (
        violations.sort_values(
            ["relation_id", "answer"],
            key=lambda col: col.astype(str).str.len() if col.name == "answer" else col,
        )
        .groupby(["polarity", "relation_id", "score_transition"], as_index=False)
        .first()
    )
    violation_rows = violations.where(pd.notna(violations), None).to_dict("records")
    minimal_rows = minimal.where(pd.notna(minimal), None).to_dict("records")
    write_jsonl(artifacts_dir / "violations.jsonl", violation_rows)
    write_jsonl(artifacts_dir / "minimal_failing_cases.jsonl", minimal_rows)
    all_cases.to_csv(artifacts_dir / "official_vs_typesafe.csv", index=False)
    unsupported = units.loc[units.status != "recognized"]
    unsupported.to_csv(artifacts_dir / "unsupported_contracts.csv", index=False)

    schema_summary = {
        "row_count": len(census),
        "split_counts": census.split.value_counts().to_dict(),
        "evaluator_counts": census.evaluator.value_counts().to_dict(),
        "semantic_type_counts": census.semantic_type.value_counts().to_dict(),
        "numeric_string_rows": int(census.numeric_string_presence.sum()),
        "numeric_string_endpoints": int(census.numeric_string_endpoint_count.sum()),
        "clock_rows": int(census.clock_presence.sum()),
        "clock_endpoints": int(census.clock_endpoint_count.sum()),
        "multi_interval_rows": int(census.multi_interval.sum()),
        "supported_rows": int(census.supported_schema.sum()),
        "unsupported_rows": int((~census.supported_schema).sum()),
        "compiler_warning_counts": Counter(
            warning
            for packed in census.compiler_warnings
            for warning in str(packed).split("|")
            if warning
        ),
        "by_split": census.groupby("split")
        .agg(
            rows=("row_id", "count"),
            clock_rows=("clock_presence", "sum"),
            numeric_string_rows=("numeric_string_presence", "sum"),
            multi_interval_rows=("multi_interval", "sum"),
        )
        .reset_index()
        .to_dict("records"),
    }
    write_json(analysis_dir / "schema_census_summary.json", schema_summary)
    write_json(
        analysis_dir / "gold_self_test.json",
        {
            "branch_count": len(canonical),
            "metrics": [
                {
                    "evaluator": row["evaluator"],
                    "source_witness_rate": row["gold_self_consistency_rate"],
                    "canonical_contract_acceptance_rate": row["canonical_contract_acceptance_rate"],
                }
                for row in metrics
            ],
            "source_witness_failures_by_evaluator": {
                key: int((~canonical[f"{key}_source_full"]).sum()) for key in affected
            },
            "canonical_failures_by_evaluator": {
                key: int((~canonical[f"{key}_full"]).sum()) for key in affected
            },
        },
    )
    write_json(
        analysis_dir / "positive_audit.json",
        {"case_count": len(positive), "by_relation": positive_by_relation},
    )
    write_json(
        analysis_dir / "negative_audit.json",
        {"case_count": len(negative), "by_relation": negative_by_relation},
    )
    write_json(
        analysis_dir / "differential_summary.json",
        {"transition_matrix": transition_rows, "evaluator_metrics": metrics},
    )
    violation_taxonomy = {
        "by_transition": transition_rows,
        "by_positive_relation": positive_by_relation,
        "by_negative_relation": negative_by_relation,
        "by_split": split_metrics,
        "legacy_exception_counts": {
            "official_canonical": int(canonical.official_exception.notna().sum()),
            "official_positive": int(positive.official_exception.notna().sum()),
            "official_negative": int(negative.official_exception.notna().sum()),
            "repaired_canonical": int(canonical.repaired_exception.notna().sum()),
            "repaired_positive": int(positive.repaired_exception.notna().sum()),
            "repaired_negative": int(negative.repaired_exception.notna().sum()),
        },
        "negative_generation_policy": (
            "Algebraically generated near misses are retained only when the complete "
            "typed contract rejects them, preventing another legal branch from turning a "
            "branch-local near miss into a valid answer."
        ),
    }
    write_json(analysis_dir / "violation_taxonomy.json", violation_taxonomy)
    write_json(
        analysis_dir / "aggregation_sensitivity.json",
        aggregation_sensitivity(positive, negative),
    )
    consistency, conflicts = label_consistency(positive, negative)
    write_json(analysis_dir / "label_consistency.json", consistency)
    conflicts.to_csv(artifacts_dir / "positive_negative_label_conflicts.csv", index=False)
    row_summary, row_frame = row_violation_distribution(census, canonical, positive, negative)
    write_json(analysis_dir / "row_violation_distribution.json", row_summary)
    row_frame.to_parquet(data_dir / "row_violation_distribution.parquet", index=False)

    summary = {
        "row_count": len(census),
        "contract_branch_count": len(canonical),
        "generated_positive_cases": len(positive),
        "generated_negative_cases": len(negative),
        "affected_row_count_official": len(affected["official"]),
        "affected_row_count_repaired": len(affected["repaired"]),
        "affected_row_count_type_safe": len(affected["type_safe"]),
        "evaluator_metrics": metrics,
        "split_metrics": split_metrics,
        "schema": schema_summary,
    }
    write_json(analysis_dir / "audit_summary.json", summary)
    build_html_report(
        artifacts_dir / "evalgauge_report.html",
        summary=summary,
        positive_by_relation=positive_by_relation,
        negative_by_relation=negative_by_relation,
        transition_rows=transition_rows,
        minimal_failures=minimal_rows,
        unsupported_units=unsupported.to_dict("records"),
    )
    manifest = {
        "schema": "evalgauge-dataset-manifest-v1",
        "row_count": len(census),
        "sources": [
            {"path": real.name, "rows": 1272, "sha256": sha256_file(real)},
            {"path": synthetic.name, "rows": 1170, "sha256": sha256_file(synthetic)},
        ],
    }
    write_json(frozen_dir / "dataset_manifest.json", manifest)
    write_json(
        frozen_dir / "unit_registry.json",
        {
            symbol: {
                "dimension": unit.dimension,
                "scale": str(unit.scale),
                "offset": str(unit.offset),
                "aliases": list(unit.aliases),
                "conversion_safe": unit.conversion_safe,
                "note": unit.note,
            }
            for symbol, unit in DEFAULT_REGISTRY.units.items()
        },
    )
    return summary
