#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evalgauge.public_rescore import rescore_public_predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Rescore public MeasureBench model predictions")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--prediction-root", type=Path, required=True)
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = rescore_public_predictions(
        root=args.root.resolve(),
        prediction_root=args.prediction_root,
        real=args.real,
        synthetic=args.synthetic,
        output=args.output.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
