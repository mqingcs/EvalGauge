#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch the frozen public MeasureBench release")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "frozen/standalone_release.json").read_text())
    commit = manifest["commit"]
    base = f"https://raw.githubusercontent.com/flageval-baai/MeasureBench/{commit}"
    for record in manifest["files"]:
        destination = args.output / record["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or sha256_file(destination) != record["sha256"]:
            with urllib.request.urlopen(f"{base}/{record['path']}") as response:
                destination.write_bytes(response.read())
        observed = sha256_file(destination)
        if destination.stat().st_size != record["bytes"] or observed != record["sha256"]:
            raise RuntimeError(f"source verification failed for {destination}: {observed}")
        print(f"verified {record['path']} {observed}")


if __name__ == "__main__":
    main()
