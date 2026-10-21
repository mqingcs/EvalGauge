from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    included_roots = ["analysis", "artifacts", "data", "frozen", "paper", "src", "tests", "scripts"]
    included_files = ["README.md", "pyproject.toml", "uv.lock"]
    excluded_suffixes = {".aux", ".bbl", ".blg", ".log"}
    excluded_names = {".DS_Store", "artifact_manifest.json", "main.extracted.txt"}
    excluded_directories = {".git", "__pycache__"}
    records = []
    for directory in included_roots:
        for path in sorted((root / directory).rglob("*")):
            if not path.is_file() or excluded_directories.intersection(path.parts):
                continue
            if path.name in excluded_names or path.suffix in excluded_suffixes:
                continue
            records.append(
                {
                    "path": str(path.relative_to(root)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    for filename in included_files:
        path = root / filename
        if path.is_file():
            records.append(
                {
                    "path": filename,
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    records.sort(key=lambda record: record["path"])
    payload = {
        "schema": "evalgauge-artifact-manifest-v1",
        "file_count": len(records),
        "files": records,
    }
    destination = root / "frozen/artifact_manifest.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
