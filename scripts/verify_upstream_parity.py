#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pandas as pd


class _Registry:
    def register_module(self):
        return lambda cls: cls


def _load(path: Path, name: str, *, stub_flageval: bool):
    if stub_flageval:
        evaluator = types.ModuleType("flagevalmm.evaluator")
        evaluator.BaseEvaluator = object
        registry = types.ModuleType("flagevalmm.registry")
        registry.EVALUATORS = _Registry()
        sys.modules["flagevalmm"] = types.ModuleType("flagevalmm")
        sys.modules["flagevalmm.evaluator"] = evaluator
        sys.modules["flagevalmm.registry"] = registry
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _score(module, answer: str, evaluator: str, kwargs: dict[str, Any]):
    pred = {"answer": str(answer)}
    pred["raw_answer"] = pred["answer"]
    pred["answer"] = module.normalize_string(module.extract_answer(pred))
    try:
        function = (
            module.interval_matching
            if evaluator == "interval_matching"
            else module.multi_interval_matching
        )
        result = function(pred, **kwargs)
        return {
            "value": bool(result["number_correct"]),
            "unit": None if result["unit_correct"] is None else bool(result["unit_correct"]),
            "full": bool(result["all_correct"]),
            "exception": None,
        }
    except Exception as exc:  # noqa: BLE001 - upstream exceptions are audit outputs
        return {
            "value": False,
            "unit": False,
            "full": False,
            "exception": type(exc).__name__,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify frozen/current MeasureBench parity")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--frozen-evaluator", type=Path, required=True)
    parser.add_argument("--standalone-evaluator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    frozen = _load(args.frozen_evaluator, "measurebench_frozen", stub_flageval=True)
    standalone = _load(args.standalone_evaluator, "measurebench_standalone", stub_flageval=False)
    census = pd.read_parquet(root / "data/schema_census.parquet")
    metadata = {
        row.row_id: (row.evaluator, json.loads(row.source_schema_json))
        for row in census.itertuples()
    }
    suites = [
        ("canonical", root / "data/canonical_gold_answers.parquet", "canonical_answer"),
        ("source_witness", root / "data/canonical_gold_answers.parquet", "source_witness_answer"),
        ("positive", root / "data/metamorphic_cases.parquet", "answer"),
        ("negative", root / "data/negative_cases.parquet", "answer"),
        ("historical_model", root / "data/model_answers.parquet", "raw_answer"),
    ]
    summaries: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for name, path, answer_column in suites:
        frame = pd.read_parquet(path)
        mismatch_count = 0
        for row in frame.itertuples():
            evaluator, kwargs = metadata[row.row_id]
            if hasattr(row, "schema_variant_json") and not pd.isna(row.schema_variant_json):
                kwargs = json.loads(row.schema_variant_json)
            answer = getattr(row, answer_column)
            left = _score(frozen, answer, evaluator, kwargs)
            right = _score(standalone, answer, evaluator, kwargs)
            if left != right:
                mismatch_count += 1
                if len(mismatches) < 100:
                    mismatches.append(
                        {
                            "suite": name,
                            "row_id": row.row_id,
                            "answer": str(answer),
                            "frozen": left,
                            "standalone": right,
                        }
                    )
        summaries.append({"suite": name, "executions": len(frame), "mismatches": mismatch_count})
    payload = {
        "schema": "evalgauge-upstream-parity-v1",
        "frozen_evaluator_file": args.frozen_evaluator.name,
        "standalone_evaluator_file": args.standalone_evaluator.name,
        "frozen_release": json.loads(
            (root / "frozen/evaluator_commit.json").read_text(encoding="utf-8")
        )["official"],
        "standalone_release": {
            "repository": json.loads(
                (root / "frozen/standalone_release.json").read_text(encoding="utf-8")
            )["repository"],
            "commit": json.loads(
                (root / "frozen/standalone_release.json").read_text(encoding="utf-8")
            )["commit"],
            "sha256": json.loads(
                (root / "frozen/standalone_release.json").read_text(encoding="utf-8")
            )["files"][1]["sha256"],
        },
        "suite_summaries": summaries,
        "total_executions": sum(row["executions"] for row in summaries),
        "total_mismatches": sum(row["mismatches"] for row in summaries),
        "mismatch_examples": mismatches,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if payload["total_mismatches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
