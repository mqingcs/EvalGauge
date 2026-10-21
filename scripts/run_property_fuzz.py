#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--seed", type=int, default=20260815)
    args = parser.parse_args()
    root = args.root.resolve()
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--hypothesis-seed={args.seed}",
        "tests/test_property_based.py",
    ]
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    payload = {
        "command": ["python", *command[1:]],
        "exit_code": completed.returncode,
        "fuzz_examples": 550,
        "property_tests": 3,
        "seed": args.seed,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
    destination = root / "analysis/property_fuzz_summary.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if completed.returncode:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
