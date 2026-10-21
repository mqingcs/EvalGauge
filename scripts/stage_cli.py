from __future__ import annotations

import argparse
import json
from pathlib import Path

from evalgauge.audit import run_audit
from evalgauge.rescore import collect_and_rescore


def audit_stage(label: str, artifact: str) -> None:
    parser = argparse.ArgumentParser(description=f"Rebuild EvalGauge stage: {label}")
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run_audit(real=args.real, synthetic=args.synthetic, output=args.output)
    print(json.dumps({"stage": label, "artifact": artifact, "audit": summary}, indent=2))


def rescore_stage(label: str) -> None:
    parser = argparse.ArgumentParser(description=f"Rebuild EvalGauge stage: {label}")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = collect_and_rescore(
        source_root=args.source_root,
        real=args.real,
        synthetic=args.synthetic,
        output=args.output,
    )
    print(json.dumps({"stage": label, "rescoring": summary}, indent=2))


def analysis_stage(label: str, relative_path: str) -> None:
    parser = argparse.ArgumentParser(description=f"Read EvalGauge stage: {label}")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    path = args.root.resolve() / relative_path
    if not path.exists():
        raise SystemExit(f"missing {path}; run the full audit first")
    print(path.read_text(encoding="utf-8"))
