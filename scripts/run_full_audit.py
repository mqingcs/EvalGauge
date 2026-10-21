#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from evalgauge.audit import run_audit
from evalgauge.public_rescore import rescore_public_predictions
from evalgauge.reporting import rebuild_html_report
from evalgauge.rescore import collect_and_rescore


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--public-prediction-root", type=Path)
    parser.add_argument("--frozen-evaluator", type=Path)
    parser.add_argument("--standalone-evaluator", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    frozen = json.loads((output / "frozen/dataset_manifest.json").read_text(encoding="utf-8"))
    expected = {Path(row["path"]).name: row["sha256"] for row in frozen["sources"]}
    for path in [args.real, args.synthetic]:
        observed = sha256_file(path)
        if expected.get(path.name) != observed:
            raise RuntimeError(f"dataset hash mismatch for {path}: {observed}")
    summary = run_audit(real=args.real, synthetic=args.synthetic, output=output)
    if args.source_root:
        collect_and_rescore(
            source_root=args.source_root,
            real=args.real,
            synthetic=args.synthetic,
            output=output,
        )
    subprocess.run(
        [
            sys.executable,
            str(output / "scripts/validate_mr12_source_schema.py"),
            "--real",
            str(args.real),
            "--synthetic",
            str(args.synthetic),
            "--output",
            str(output / "analysis/mr12_source_schema_validation.json"),
        ],
        check=True,
    )
    if args.public_prediction_root:
        rescore_public_predictions(
            root=output,
            prediction_root=args.public_prediction_root,
            real=args.real,
            synthetic=args.synthetic,
            output=output,
        )
        subprocess.run(
            [
                sys.executable,
                str(output / "scripts/classify_public_transitions.py"),
                "--root",
                str(output),
            ],
            check=True,
        )
    if args.source_root and args.public_prediction_root:
        subprocess.run(
            [
                sys.executable,
                str(output / "scripts/analyze_scoring_profiles.py"),
                "--root",
                str(output),
            ],
            check=True,
        )
    if bool(args.frozen_evaluator) != bool(args.standalone_evaluator):
        raise ValueError("--frozen-evaluator and --standalone-evaluator must be supplied together")
    if args.frozen_evaluator and args.standalone_evaluator:
        subprocess.run(
            [
                sys.executable,
                str(output / "scripts/verify_upstream_parity.py"),
                "--root",
                str(output),
                "--frozen-evaluator",
                str(args.frozen_evaluator),
                "--standalone-evaluator",
                str(args.standalone_evaluator),
                "--output",
                str(output / "analysis/upstream_parity.json"),
            ],
            check=True,
        )
    subprocess.run(
        [
            sys.executable,
            str(output / "scripts/build_figures.py"),
            "--root",
            str(output),
            "--real",
            str(args.real),
        ],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(output / "scripts/run_property_fuzz.py"), "--root", str(output)],
        check=True,
    )
    chartqapro_rows = output / "data/chartqapro_contract_rows.parquet"
    if chartqapro_rows.exists():
        subprocess.run(
            [
                sys.executable,
                str(output / "scripts/run_chartqapro_probe.py"),
                "--root",
                str(output),
            ],
            check=True,
        )
    rebuild_html_report(output)
    subprocess.run(
        [sys.executable, str(output / "scripts/build_artifact_manifest.py")],
        check=True,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
