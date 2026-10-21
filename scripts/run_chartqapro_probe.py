#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pandas as pd

from evalgauge.xbench.chartqapro import (
    compile_chartqapro_contract,
    generate_chartqapro_cases,
    official_chartqapro_score,
    reference_chartqapro_score,
    summarize_relation_rows,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_upstream(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import frozen upstream source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upstream_row_score(module: Any, row: dict[str, Any], answer: str) -> float:
    payload = {
        "Answer": list(row["Answer"]),
        "Question Type": str(row["Question Type"]),
        "Year": list(row["Year"]),
        "prediction": answer,
    }
    return float(module.evaluate_predictions_chartqapro([payload])["Overall"])


def exact_flag_flow(path: Path) -> dict[str, bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate_predictions_chartqapro"
    )
    computed = any(
        isinstance(node, ast.Name) and node.id == "always_use_exact_match"
        for node in ast.walk(function)
    )
    forwarded = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "relaxed_correctness_chartqapro"
        and any(keyword.arg == "always_use_exact_match" for keyword in node.keywords)
        for node in ast.walk(function)
    )
    return {"computed": computed, "forwarded": forwarded}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-parquet", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    compact_path = root / "data/chartqapro_contract_rows.parquet"
    if args.source_parquet:
        source = pd.read_parquet(
            args.source_parquet,
            columns=["Question", "Answer", "Question Type", "Year"],
        )
        source.to_parquet(compact_path, index=False)
    if not compact_path.exists():
        raise FileNotFoundError(
            "missing compact ChartQAPro metadata; supply --source-parquet on the first run"
        )
    rows = pd.read_parquet(compact_path)
    source_repo_path = root / "frozen/xbench/chartqapro/repository_evaluator.py"
    toolkit_path = root / "frozen/xbench/chartqapro/vlmevalkit_chartqapro_utils.py"
    source_repo = load_upstream(source_repo_path, "chartqapro_repository_frozen")
    toolkit = load_upstream(toolkit_path, "chartqapro_vlmevalkit_frozen")

    contract_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    upstream_mismatches: list[dict[str, Any]] = []
    for row_index, series in rows.iterrows():
        row = series.to_dict()
        contract = compile_chartqapro_contract(row, row_index)
        contract_rows.append(contract.to_dict())
        for case in generate_chartqapro_cases(contract):
            official_score = official_chartqapro_score(contract, case.answer)
            reference_label = reference_chartqapro_score(contract, case.answer)
            repository_score = upstream_row_score(source_repo, row, case.answer)
            toolkit_score = upstream_row_score(toolkit, row, case.answer)
            if not (
                abs(official_score - repository_score) < 1e-12
                and abs(official_score - toolkit_score) < 1e-12
            ):
                upstream_mismatches.append(
                    {
                        "row_id": str(row_index),
                        "relation_id": case.relation_id,
                        "answer": case.answer,
                        "local": official_score,
                        "repository": repository_score,
                        "vlmevalkit": toolkit_score,
                    }
                )
            record = case.to_dict()
            record.update(
                {
                    "official_score": official_score,
                    "reference_label": reference_label,
                    "repository_score": repository_score,
                    "vlmevalkit_score": toolkit_score,
                    "contract_hash": hashlib.sha256(
                        json.dumps(contract.to_dict(), sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                }
            )
            case_rows.append(record)

    reference_mismatches = [
        record
        for record in case_rows
        if bool(record["reference_label"]) != bool(record["expected_label"])
    ]
    relation_summary = summarize_relation_rows(case_rows)
    positives = [row for row in case_rows if row["case_kind"] != "negative"]
    negatives = [row for row in case_rows if row["case_kind"] == "negative"]
    positive_failures = [row for row in positives if float(row["official_score"]) < 1.0]
    invalid_credits = [row for row in negatives if float(row["official_score"]) > 0.0]
    full_invalid_credits = [row for row in negatives if float(row["official_score"]) == 1.0]
    exact_routing = [
        row for row in case_rows if row["relation_id"] == "XMR-N-EXACT-SUFFIX"
    ]
    numeric_fallback = [
        row for row in case_rows if row["relation_id"] == "XMR-N-NUMERIC-SUFFIX"
    ]
    semantic_counts = pd.Series(
        [row["semantic_type"] for row in contract_rows], dtype="string"
    ).value_counts()
    question_counts = rows["Question Type"].value_counts()
    summary = {
        "schema": "evalgauge-xbench-chartqapro-v1",
        "benchmark": "ChartQAPro",
        "public_rows": len(rows),
        "compiled_rows": len(contract_rows),
        "compiled_row_coverage": len(contract_rows) / len(rows),
        "semantic_type_counts": {str(key): int(value) for key, value in semantic_counts.items()},
        "question_type_counts": {str(key): int(value) for key, value in question_counts.items()},
        "generated_cases": len(case_rows),
        "positive_cases": len(positives),
        "negative_cases": len(negatives),
        "source_witness_full_acceptance": sum(
            row["relation_id"] == "XMR-SOURCE" and float(row["official_score"]) == 1.0
            for row in case_rows
        )
        / len(rows),
        "positive_full_conformance": 1 - len(positive_failures) / len(positives),
        "invalid_nonzero_credit_rate": len(invalid_credits) / len(negatives),
        "invalid_full_credit_rate": len(full_invalid_credits) / len(negatives),
        "exact_type_rows": len(exact_routing),
        "exact_type_suffix_nonzero_credit": sum(
            float(row["official_score"]) > 0 for row in exact_routing
        ),
        "numeric_rows": len(numeric_fallback),
        "malformed_numeric_suffix_nonzero_credit": sum(
            float(row["official_score"]) > 0 for row in numeric_fallback
        ),
        "reference_suite_conformance": 1 - len(reference_mismatches) / len(case_rows),
        "upstream_parity_executions": len(case_rows) * 2,
        "upstream_parity_mismatches": len(upstream_mismatches),
        "exact_match_control_flow": {
            "repository": exact_flag_flow(source_repo_path),
            "vlmevalkit": exact_flag_flow(toolkit_path),
        },
        "relation_summary": relation_summary,
        "frozen_sources": {
            "chartqapro_repository_commit": "4b422c658270aff1d3105fd0fb39b1dd5de9f08c",
            "vlmevalkit_commit": "fd09032341aed9f1e85b761745154299e13f50c0",
            "dataset_commit": "e27c2874825874d6767d2bbc538ed4f0dc2c64c2",
            "full_parquet_sha256": "feb03a5579e49114b45350b75aed7f674e285f795a425c83e22f400095c91489",
            "compact_metadata_sha256": sha256(compact_path),
            "repository_evaluator_sha256": sha256(source_repo_path),
            "vlmevalkit_evaluator_sha256": sha256(toolkit_path),
        },
    }
    artifacts = root / "artifacts/xbench/chartqapro"
    artifacts.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(contract_rows).to_parquet(
        root / "data/xbench_chartqapro_contracts.parquet", index=False
    )
    pd.DataFrame(case_rows).to_parquet(
        root / "data/xbench_chartqapro_cases.parquet", index=False
    )
    pd.DataFrame(relation_summary).to_csv(artifacts / "relation_summary.csv", index=False)
    (artifacts / "upstream_mismatches.json").write_text(
        json.dumps(upstream_mismatches, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (artifacts / "reference_mismatches.json").write_text(
        json.dumps(reference_mismatches, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "analysis/xbench_chartqapro_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_manifest = {
        "schema": "evalgauge-xbench-frozen-source-v1",
        "benchmark": "ChartQAPro",
        "dataset": {
            "repository": "https://huggingface.co/datasets/ahmed-masry/ChartQAPro",
            "commit": summary["frozen_sources"]["dataset_commit"],
            "full_parquet_sha256": summary["frozen_sources"]["full_parquet_sha256"],
            "compact_metadata_sha256": summary["frozen_sources"]["compact_metadata_sha256"],
            "license": "MIT",
        },
        "evaluators": [
            {
                "repository": "https://github.com/vis-nlp/ChartQAPro",
                "commit": summary["frozen_sources"]["chartqapro_repository_commit"],
                "path": "frozen/xbench/chartqapro/repository_evaluator.py",
                "sha256": summary["frozen_sources"]["repository_evaluator_sha256"],
                "license": "MIT",
            },
            {
                "repository": "https://github.com/open-compass/VLMEvalKit",
                "commit": summary["frozen_sources"]["vlmevalkit_commit"],
                "path": "frozen/xbench/chartqapro/vlmevalkit_chartqapro_utils.py",
                "sha256": summary["frozen_sources"]["vlmevalkit_evaluator_sha256"],
                "license": "Apache-2.0",
            },
        ],
    }
    (root / "frozen/xbench/chartqapro/source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
