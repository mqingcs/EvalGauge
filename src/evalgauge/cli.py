from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import run_audit
from .public_rescore import rescore_public_predictions
from .rescore import collect_and_rescore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalgauge", description="Audit scientific VQA evaluators as typed quantity contracts"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="run the complete benchmark contract audit")
    audit.add_argument("--real", type=Path, required=True)
    audit.add_argument("--synthetic", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    rescore = subparsers.add_parser(
        "rescore", help="collect and rescore traceable historical model answers"
    )
    rescore.add_argument("--source-root", type=Path, required=True)
    rescore.add_argument("--real", type=Path, required=True)
    rescore.add_argument("--synthetic", type=Path, required=True)
    rescore.add_argument("--output", type=Path, required=True)
    public = subparsers.add_parser(
        "public-rescore", help="rescore the frozen public MeasureBench predictions"
    )
    public.add_argument("--root", type=Path, default=Path("."))
    public.add_argument("--prediction-root", type=Path, required=True)
    public.add_argument("--real", type=Path, required=True)
    public.add_argument("--synthetic", type=Path, required=True)
    public.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        summary = run_audit(real=args.real, synthetic=args.synthetic, output=args.output)
    elif args.command == "rescore":
        summary = collect_and_rescore(
            source_root=args.source_root,
            real=args.real,
            synthetic=args.synthetic,
            output=args.output,
        )
    else:
        summary = rescore_public_predictions(
            root=args.root.resolve(),
            prediction_root=args.prediction_root,
            real=args.real,
            synthetic=args.synthetic,
            output=args.output,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
