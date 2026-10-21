# Upstream data and evaluator sources

EvalGauge redistributes compact evaluator inputs and derived decisions, not the full upstream multimedia corpora.

## MeasureBench

- Dataset: <https://huggingface.co/datasets/FlagEval/MeasureBench>
- Standalone repository: <https://github.com/flageval-baai/MeasureBench>
- Exact source revisions and file checks are recorded in `frozen/dataset_manifest.json`, `frozen/evaluator_commit.json`, and `frozen/standalone_release.json`.
- The frozen FlagEvalMM evaluator is retrieved from commit `fef27ec696c532d12f0db389bcbbf79eab0e4c41` at <https://github.com/flageval-baai/FlagEvalMM/tree/fef27ec696c532d12f0db389bcbbf79eab0e4c41/tasks/measure_bench>. Its path after checkout is `tasks/measure_bench/measure_bench_evaluator.py`; the upstream file is intentionally not redistributed.
- Fetch the public evaluator and four released prediction files with:

```bash
uv run python scripts/fetch_public_measurebench.py \
  --root . \
  --output external/measurebench-release
```

The full benchmark Parquet files are required only for a complete rebuild. The release already contains compiled contracts, all generated cases, and all derived scores.

## ChartQAPro

- Dataset: <https://huggingface.co/datasets/ahmed-masry/ChartQAPro>
- Benchmark repository: <https://github.com/vis-nlp/ChartQAPro>
- Secondary evaluator: <https://github.com/open-compass/VLMEvalKit>
- Exact revisions and licenses are recorded in `frozen/xbench/chartqapro/source_manifest.json`.

`data/chartqapro_contract_rows.parquet` contains the 1,948 compact question/answer rows required for the evaluator audit. It contains no image column.

## Teaser images

The three modified crops in `artifacts/teaser/` correspond to MeasureBench rows `clock_64`, `protractor_3`, and `electricity_meter_5`. Their source pages and modification record are listed in `THIRD_PARTY_NOTICES.md` and `paper/artifact_statement.md`.
