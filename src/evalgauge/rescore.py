from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from .compiler import compile_contract
from .differential import differential_score
from .matcher import score_profile
from .reporting import write_json, write_jsonl

ID_KEYS = {
    "opaque_id",
    "source_opaque_id",
    "question_id",
    "source_question_id",
    "original_question_id",
    "round2_id",
    "round3_id",
    "round4_id",
    "holdout_id",
    "blind_id",
    "benchmark_id",
    "real200_id",
}
EXCLUDE_DIRECT_MARKERS = {
    "candidate",
    "coverage",
    "local_search",
    "interface",
    "physical",
    "calibrated",
    "marker",
    "verifier",
    "preannotation",
    "geometry",
    "anchor",
}


def _load_rows(real: Path, synthetic: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    rows: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    for split, path in [("real_world", real), ("synthetic_test", synthetic)]:
        frame = pd.read_parquet(path)
        for record in frame.drop(columns=["image"], errors="ignore").to_dict("records"):
            row_id = f"{split}::{record['question_id']}"
            record["row_id"] = row_id
            record["source_split"] = split
            rows[row_id] = record
            aliases[row_id] = row_id
    return rows, aliases


def _iter_json_records(path: Path) -> Iterable[dict[str, Any]]:
    try:
        if path.suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        yield value
            return
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if isinstance(value, dict):
        if "response_text" in value:
            yield value
        for key in ["records", "responses", "rows", "calls", "items"]:
            nested = value.get(key)
            if isinstance(nested, list):
                yield from (record for record in nested if isinstance(record, dict))
    elif isinstance(value, list):
        yield from (record for record in value if isinstance(record, dict))


def _record_ids(record: dict[str, Any]) -> list[str]:
    return [
        str(record[key])
        for key in ID_KEYS
        if record.get(key) is not None and not isinstance(record[key], (dict, list))
    ]


def _resolve_row(record: dict[str, Any], aliases: dict[str, str]) -> str | None:
    source_split = str(record.get("source_split") or "")
    for key in ["source_question_id", "original_question_id", "question_id"]:
        value = record.get(key)
        if value is not None:
            if source_split and f"{source_split}::{value}" in aliases:
                return aliases[f"{source_split}::{value}"]
            if f"real_world::{value}" in aliases:
                return aliases[f"real_world::{value}"]
    for identifier in _record_ids(record):
        if identifier in aliases:
            return aliases[identifier]
    return None


def _build_alias_map(
    source_root: Path, aliases: dict[str, str]
) -> tuple[dict[str, str], dict[str, int]]:
    manifest = source_root / "data/manifests/evaluation.parquet"
    if manifest.exists():
        for record in pd.read_parquet(manifest).to_dict("records"):
            row_id = f"{record.get('source_split', 'real_world')}::{record['original_question_id']}"
            if row_id in aliases:
                aliases[str(record["opaque_id"])] = row_id
                aliases[str(record["original_question_id"])] = row_id
    files = sorted(
        {
            *source_root.glob("round2/**/evaluation.jsonl"),
            *source_root.glob("round2/**/inference.jsonl"),
            *source_root.glob("round3/**/evaluation.jsonl"),
            *source_root.glob("round3/**/inference.jsonl"),
        }
    )
    stats = Counter(files_scanned=len(files), alias_source_records_scanned=0, aliases_added=0)
    pending: list[dict[str, Any]] = []
    for path in files:
        for record in _iter_json_records(path):
            stats["alias_source_records_scanned"] += 1
            pending.append(record)
    for _ in range(4):
        changed = 0
        for record in pending:
            row_id = _resolve_row(record, aliases)
            if not row_id:
                continue
            for identifier in _record_ids(record):
                if identifier not in aliases:
                    aliases[identifier] = row_id
                    stats["aliases_added"] += 1
                    changed += 1
        if not changed:
            break
    stats["alias_source_records_linked"] = sum(
        _resolve_row(record, aliases) is not None for record in pending
    )
    return aliases, dict(stats)


def _preferred_request_paths(source_root: Path) -> tuple[list[Path], dict[str, int]]:
    index = source_root / "round3/frozen/process_data_inventory_2026-08-14/request_index.jsonl"
    selected: set[Path] = set()
    stats = Counter(request_index_rows=0)
    if index.exists():
        with index.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                stats["request_index_rows"] += 1
                candidates = [source_root / path for path in record.get("paths", [])]
                candidates = [
                    path
                    for path in candidates
                    if path.suffix in {".json", ".jsonl"} and path.exists()
                ]
                if not candidates:
                    continue
                candidates.sort(
                    key=lambda path: (
                        "/responses/" in str(path),
                        path.suffix != ".jsonl",
                        not any(
                            token in path.name
                            for token in ["responses", "records", "calls", "ledger"]
                        ),
                        len(str(path)),
                    )
                )
                selected.add(candidates[0])
    ledger = source_root / "artifacts/logs/call_ledger.jsonl"
    if ledger.exists():
        selected.add(ledger)
    stats["selected_unique_files"] = len(selected)
    return sorted(selected), dict(stats)


def _looks_direct(record: dict[str, Any], path: Path) -> bool:
    if not isinstance(record.get("response_text"), str) or not record["response_text"].strip():
        return False
    mode = str(record.get("mode") or "").casefold()
    component = str(record.get("component") or "").casefold()
    prompt = str(record.get("prompt_version") or "").casefold()
    path_text = str(path).casefold()
    direct_signal = (
        mode == "direct"
        or component in {"direct", "direct_measurement", "measurement_readout"}
        or "direct" in prompt
        or "direct" in path_text
    )
    if not direct_signal:
        return False
    descriptor = f"{component} {prompt} {path_text}"
    if any(marker in descriptor for marker in EXCLUDE_DIRECT_MARKERS):
        return component in {"direct", "direct_measurement", "measurement_readout"}
    return True


def _experiment_name(source_root: Path, path: Path, record: dict[str, Any]) -> str:
    parts = path.relative_to(source_root).parts
    if parts[:2] == ("artifacts", "logs"):
        base = "round1_gate"
    elif len(parts) >= 3 and parts[1] in {"generated", "archive", "frozen"}:
        base = "/".join(parts[:3])
    else:
        base = "/".join(parts[:2])
    component = str(record.get("component") or record.get("mode") or "direct")
    prompt = str(record.get("prompt_version") or "")
    return "::".join(part for part in [base, component, prompt] if part)


def _dedup_key(record: dict[str, Any], row_id: str) -> str:
    for key in ["request_id", "message_id"]:
        if record.get(key):
            return f"{key}:{record[key]}"
    payload = "\n".join(
        [
            row_id,
            str(record.get("requested_model") or record.get("returned_model") or ""),
            str(record.get("mode") or record.get("component") or ""),
            str(record.get("prompt_sha256") or ""),
            str(record.get("response_text") or ""),
        ]
    )
    return "content:" + hashlib.sha256(payload.encode()).hexdigest()


def _ranking_analysis(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"groups": [], "ranking_groups": 0, "order_changed_groups": 0}
    groups = []
    for experiment, group in frame.groupby("experiment"):
        models = sorted(group.requested_model.dropna().unique())
        if len(models) < 2:
            continue
        shared: set[str] | None = None
        for model in models:
            ids = set(group.loc[group.requested_model == model, "row_id"])
            shared = ids if shared is None else shared & ids
        if not shared:
            continue
        model_rows = []
        for model in models:
            subset = group[(group.requested_model == model) & group.row_id.isin(shared)]
            per_row = subset.groupby("row_id")[
                ["official_full", "repaired_full", "type_safe_full"]
            ].mean()
            model_rows.append(
                {
                    "model": model,
                    "shared_rows": len(shared),
                    "official": float(per_row.official_full.mean()),
                    "repaired": float(per_row.repaired_full.mean()),
                    "type_safe": float(per_row.type_safe_full.mean()),
                }
            )
        official_order = [
            row["model"]
            for row in sorted(model_rows, key=lambda row: (-row["official"], row["model"]))
        ]
        typed_order = [
            row["model"]
            for row in sorted(model_rows, key=lambda row: (-row["type_safe"], row["model"]))
        ]
        groups.append(
            {
                "experiment": experiment,
                "models": model_rows,
                "official_order": official_order,
                "type_safe_order": typed_order,
                "order_changed": official_order != typed_order,
            }
        )
    return {
        "groups": groups,
        "ranking_groups": len(groups),
        "order_changed_groups": sum(group["order_changed"] for group in groups),
    }


def collect_and_rescore(*, source_root: Path, real: Path, synthetic: Path, output: Path):
    rows, aliases = _load_rows(real, synthetic)
    aliases, alias_stats = _build_alias_map(source_root, aliases)
    paths, request_stats = _preferred_request_paths(source_root)
    stats = Counter(
        files_scanned=0,
        records_scanned=0,
        response_records=0,
        direct_records=0,
        linked_records=0,
        duplicate_records=0,
        scored_records=0,
    )
    output_rows: list[dict[str, Any]] = []
    unlinked_rows: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    included_counts: Counter[str] = Counter()
    seen: set[str] = set()
    for path in paths:
        stats["files_scanned"] += 1
        for record in _iter_json_records(path):
            stats["records_scanned"] += 1
            if isinstance(record.get("response_text"), str):
                stats["response_records"] += 1
            if not _looks_direct(record, path):
                continue
            stats["direct_records"] += 1
            source_counts[str(path.relative_to(source_root))] += 1
            row_id = _resolve_row(record, aliases)
            if not row_id or row_id not in rows:
                unlinked_rows.append(
                    {
                        "source_path": str(path.relative_to(source_root)),
                        "record_ids": _record_ids(record),
                        "requested_model": record.get("requested_model"),
                        "returned_model": record.get("returned_model"),
                        "component": record.get("component") or record.get("mode"),
                        "prompt_version": record.get("prompt_version"),
                        "response_text": record.get("response_text"),
                    }
                )
                continue
            stats["linked_records"] += 1
            key = _dedup_key(record, row_id)
            if key in seen:
                stats["duplicate_records"] += 1
                continue
            seen.add(key)
            benchmark = rows[row_id]
            spec = (
                json.loads(benchmark["evaluator_kwargs"])
                if isinstance(benchmark["evaluator_kwargs"], str)
                else benchmark["evaluator_kwargs"]
            )
            scored = differential_score(
                answer=record["response_text"],
                row_id=row_id,
                split=benchmark["source_split"],
                evaluator=benchmark["evaluator"],
                evaluator_kwargs=spec,
                image_type=benchmark["image_type"],
                design=benchmark["design"],
            )
            contract = compile_contract(
                row_id=row_id,
                split=benchmark["source_split"],
                evaluator=benchmark["evaluator"],
                evaluator_kwargs=spec,
                image_type=benchmark["image_type"],
                design=benchmark["design"],
            )
            core_final = score_profile(
                record["response_text"], contract, profile="core_final"
            )
            physics_final = score_profile(
                record["response_text"], contract, profile="physics_final"
            )
            strict_final = score_profile(
                record["response_text"], contract, profile="strict_final"
            )
            if strict_final.full_match != bool(scored["type_safe"]["full_match"]):
                raise AssertionError(f"strict/type-safe compatibility mismatch: {row_id}")
            output_rows.append(
                {
                    "row_id": row_id,
                    "source_split": benchmark["source_split"],
                    "source_question_id": benchmark["question_id"],
                    "image_type": benchmark["image_type"],
                    "design": benchmark["design"],
                    "model_requested": record.get("requested_model"),
                    "model_returned": record.get("returned_model"),
                    "requested_model": record.get("requested_model")
                    or record.get("returned_model")
                    or "unknown",
                    "experiment": _experiment_name(source_root, path, record),
                    "request_id": record.get("request_id") or record.get("message_id"),
                    "prompt_version": record.get("prompt_version"),
                    "component": record.get("component") or record.get("mode"),
                    "raw_answer": record["response_text"],
                    "source_path": str(path.relative_to(source_root)),
                    "official_value": scored["official"]["value"],
                    "official_unit": scored["official"]["unit"],
                    "official_full": scored["official"]["full"],
                    "repaired_value": scored["repaired"]["value"],
                    "official_exception": scored["official"].get("exception"),
                    "repaired_unit": scored["repaired"]["unit"],
                    "repaired_full": scored["repaired"]["full"],
                    "repaired_exception": scored["repaired"].get("exception"),
                    "core_final_full": core_final.full_match,
                    "physics_final_full": physics_final.full_match,
                    "strict_final_full": strict_final.full_match,
                    "core_final_trace": json.dumps(
                        core_final.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                    "physics_final_trace": json.dumps(
                        physics_final.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                    "strict_final_trace": json.dumps(
                        strict_final.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                    "type_safe_value": scored["type_safe"]["value_match"],
                    "type_safe_unit": scored["type_safe"]["unit_match"],
                    "type_safe_full": scored["type_safe"]["full_match"],
                    "score_transition": scored["score_transition"],
                    "transition_class": scored["transition_class"],
                    "parsed_quantities": json.dumps(
                        scored["type_safe"]["parsed_quantities"], ensure_ascii=False, sort_keys=True
                    ),
                    "type_safe_trace": json.dumps(
                        scored["type_safe"], ensure_ascii=False, sort_keys=True
                    ),
                }
            )
            included_counts[str(path.relative_to(source_root))] += 1
            stats["scored_records"] += 1
    result = pd.DataFrame(output_rows)
    data_dir, analysis_dir = output / "data", output / "analysis"
    data_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    if result.empty:
        result = pd.DataFrame(
            columns=[
                "row_id",
                "requested_model",
                "experiment",
                "raw_answer",
                "official_full",
                "repaired_full",
                "type_safe_full",
                "score_transition",
            ]
        )
    result.to_parquet(data_dir / "model_answers.parquet", index=False)
    artifacts_dir = output / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(artifacts_dir / "unlinked_direct_records.jsonl", unlinked_rows)
    pd.DataFrame(
        [
            {
                "source_path": source_path,
                "direct_records": count,
                "included_records": included_counts[source_path],
            }
            for source_path, count in sorted(source_counts.items())
        ]
    ).to_csv(artifacts_dir / "model_response_sources.csv", index=False)
    summaries = []
    model_summaries = []
    if len(result):
        for (model, experiment), group in result.groupby(
            ["requested_model", "experiment"], dropna=False
        ):
            official_errors = ~group.official_full
            summaries.append(
                {
                    "model": model,
                    "experiment": experiment,
                    "n_calls": len(group),
                    "n_rows": int(group.row_id.nunique()),
                    "official_full": float(group.official_full.mean()),
                    "repaired_full": float(group.repaired_full.mean()),
                    "core_final_full": float(group.core_final_full.mean()),
                    "physics_final_full": float(group.physics_final_full.mean()),
                    "strict_final_full": float(group.strict_final_full.mean()),
                    "type_safe_full": float(group.type_safe_full.mean()),
                    "delta_type_safe_minus_official": float(
                        group.type_safe_full.mean() - group.official_full.mean()
                    ),
                    "official_errors": int(official_errors.sum()),
                    "official_errors_corrected": int(
                        (official_errors & group.type_safe_full).sum()
                    ),
                    "official_false_credits": int(
                        (group.official_full & (~group.type_safe_full)).sum()
                    ),
                    "error_pool_contamination": float(
                        (official_errors & group.type_safe_full).sum()
                        / max(official_errors.sum(), 1)
                    ),
                }
            )
        for model, group in result.groupby("requested_model", dropna=False):
            typed_only = (~group.official_full) & group.type_safe_full
            official_only = group.official_full & (~group.type_safe_full)
            model_summaries.append(
                {
                    "model": model,
                    "n_calls": len(group),
                    "n_rows": int(group.row_id.nunique()),
                    "official_full": float(group.official_full.mean()),
                    "core_final_full": float(group.core_final_full.mean()),
                    "physics_final_full": float(group.physics_final_full.mean()),
                    "strict_final_full": float(group.strict_final_full.mean()),
                    "contract_full": float(group.type_safe_full.mean()),
                    "delta_contract_minus_official": float(
                        group.type_safe_full.mean() - group.official_full.mean()
                    ),
                    "contract_only_accepts": int(typed_only.sum()),
                    "official_only_accepts": int(official_only.sum()),
                }
            )
    ranking = _ranking_analysis(result)
    payload = {
        "collection_stats": {**alias_stats, **request_stats, **dict(stats)},
        "answer_count": len(result),
        "unique_rows": int(result.row_id.nunique()) if len(result) else 0,
        "model_count": int(result.requested_model.nunique()) if len(result) else 0,
        "transition_counts": result.score_transition.value_counts().sort_index().to_dict()
        if len(result)
        else {},
        "model_experiment_summaries": summaries,
        "model_summaries": model_summaries,
    }
    write_json(analysis_dir / "model_rescoring.json", payload)
    write_json(analysis_dir / "ranking_analysis.json", ranking)
    official_errors = ~result.official_full if len(result) else pd.Series(dtype=bool)
    error_payload = {
        "official_errors": int(official_errors.sum()) if len(result) else 0,
        "official_errors_corrected": int((official_errors & result.type_safe_full).sum())
        if len(result)
        else 0,
        "official_false_credits": int((result.official_full & (~result.type_safe_full)).sum())
        if len(result)
        else 0,
        "error_pool_contamination": float(
            (official_errors & result.type_safe_full).sum() / max(official_errors.sum(), 1)
        )
        if len(result)
        else 0.0,
        "by_model_experiment": summaries,
    }
    write_json(analysis_dir / "error_pool_analysis.json", error_payload)
    return payload
