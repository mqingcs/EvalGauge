# Artifact statement

EvalGauge is a deterministic Python 3.11–3.12 artifact. It contains the answer-contract adapters, typed quantity compiler, answer parser, unit registry, matcher, relation generators, differential evaluators, historical-response collector, reports, figures, and tests.

The frozen inputs are recorded in:

- `frozen/dataset_manifest.json` — source paths, row counts, and SHA-256 hashes;
- `frozen/evaluator_commit.json` — official commit and evaluator hashes;
- `frozen/standalone_release.json` — current standalone commit plus evaluator/public-prediction hashes;
- `frozen/unit_registry.json` — executable unit definitions;
- `frozen/audit_config.json` — boundary, locale, conversion, multi-value, negative-generation, and fuzz policies.
- `frozen/xbench/chartqapro/source_manifest.json` — ChartQAPro dataset/evaluator commits, hashes, and licenses.

Reproduce the public-data audits and primary paper claims from the release root:

```bash
uv sync --extra dev
uv run python scripts/run_full_audit.py \
  --real /path/to/real_world.parquet \
  --synthetic /path/to/synthetic_test.parquet \
  --public-prediction-root external/measurebench-d5bb865 \
  --frozen-evaluator /path/to/frozen/measure_bench_evaluator.py \
  --standalone-evaluator external/measurebench-d5bb865/evaluation/measure_bench_evaluator.py \
  --output .
uv run python scripts/run_chartqapro_probe.py --root .
uv run ruff check src tests scripts
uv run pytest -q --hypothesis-seed=20260815
```

The optional `--source-root` argument is needed only to regenerate the secondary
637-response contemporary provenance case study. Its response-level scores and
relative provenance records are already included in `data/model_answers.parquet`.

The audit is population-based and deterministic. Property fuzzing uses seed `20260815` and 550 generated examples. Combined upstream parity comprises 106,375 executions across four frozen/current implementations with zero mismatches. The generated contract suites contain 90,871 case-level decisions over all 4,390 public rows. Public rescoring covers four immutable MeasureBench prediction files, 4,884 responses, and all 2,442 rows. `analysis/scoring_profile_analysis.json` and `artifacts/scoring_profile_matrix.csv` contain independently executed Core-final, Physics-final, and Strict-final decisions. Historical rescoring is a secondary provenance-bounded case study: `artifacts/model_response_sources.csv` lists the aggregate files contributing the 637 linked responses, and no unlinked response enters score claims. Unlinked exploratory outputs and raw provider call ledgers are not redistributed.

Every one of the 35 Official--Strict transition model answers has two blinded human reviews. The browser exposed only the image, question, raw released annotation, benchmark instruction, and model response. A third blinded reviewer independently adjudicated the three disagreements from the same materials. `analysis/dual_manual_review_analysis.json` and `artifacts/dual_manual_review_casebook.csv` contain finalized-SOP agreement, provisional-label sensitivity, final verdicts, policy alignment, note-derived disagreement categories, and source-issue flags; the underlying review JSON files remain under `artifacts/dual_manual_review/`.

The Qwen transfer snapshot is the local 4-bit MLX release `mlx-community/Qwen3-VL-8B-Instruct-4bit@defcdea7cc7a4b0858fea563cbbce171d328e457`; its full identifier is retained in the response ledger and derived score table.

Generated tables contain row identifiers, contract metadata, variants, scores, and traces. Three source-identified MeasureBench thumbnails are retained solely for the paper teaser; the ChartQAPro probe retains compact answer metadata but no image column. Two context-only unit spellings are matched exactly but never converted.

## Figure 1 attribution

Figure 1 uses cropped images from the MeasureBench rows `clock_64`, `protractor_3`, and `electricity_meter_5`. The MeasureBench dataset card declares CC BY-SA 4.0: <https://huggingface.co/datasets/FlagEval/MeasureBench>; the license text is at <https://creativecommons.org/licenses/by-sa/4.0/>. The dataset metadata identifies the original source pages as `https://www.youtube.com/watch?v=aaBWF9XxrP0`, `https://www.youtube.com/watch?v=LGO9Bq7usSo`, and `https://www.youtube.com/watch?v=01B1MlxauI0`, respectively. Modifications comprise cropping, resizing, composition, and typographic annotations.
