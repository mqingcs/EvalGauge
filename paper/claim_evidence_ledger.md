# EvalGauge claim–evidence ledger

All counts below are machine-generated outputs of the local audit, not manually transcribed source annotations.

| Claim | Exact evidence | Reproduction/filter |
|---|---|---|
| Cross-benchmark total: 4,390 public rows and 90,871 generated cases | `analysis/audit_summary.json`, `analysis/xbench_chartqapro_summary.json` | MeasureBench 2,442/81,778 plus ChartQAPro 1,948/9,093 |
| Natural model outputs total: 5,521 | `analysis/public_model_rescoring.json`, `analysis/model_rescoring.json` | 4,884 released MeasureBench predictions plus 637 contemporary direct responses |
| Reference conformance is 90,871/90,871 over both declared suites | same two summaries | MeasureBench and ChartQAPro reference-suite closure; not universal accuracy |
| Every generated decision has a case-level audit record | `data/metamorphic_cases.parquet`, `data/negative_cases.parquet`, `data/xbench_chartqapro_cases.parquet` | 81,778/81,778 MeasureBench cases contain `type_safe_trace_json`; all 9,093 ChartQAPro cases contain row, relation, expected/reference decision, and upstream score fields |
| Four upstream implementations match on 106,375 executions | `analysis/upstream_parity.json`, `analysis/xbench_chartqapro_summary.json` | 88,189 MeasureBench plus 18,186 ChartQAPro; zero mismatches |
| ChartQAPro compiles all 1,948 rows into 9,093 cases | `analysis/xbench_chartqapro_summary.json` | `compiled_row_coverage=1`, `generated_cases=9093` |
| ChartQAPro rejects full score for 12 source witnesses | `data/xbench_chartqapro_cases.parquet` | `relation_id==XMR-SOURCE` and `official_score<1`; one `nan` token and 11 unquoted bracketed lists |
| 760/3,170 ChartQAPro contract-breaking probes receive nonzero credit | `analysis/xbench_chartqapro_summary.json` | `invalid_nonzero_credit_rate`; relation counts sum to 760 |
| Exact-type suffix leakage affects 292/522 probes; malformed numeric suffix leakage affects 452/657 | `analysis/xbench_chartqapro_summary.json` | `exact_type_suffix_nonzero_credit`, `malformed_numeric_suffix_nonzero_credit` |
| Both ChartQAPro upstream implementations compute but do not forward the exact-match flag | `analysis/xbench_chartqapro_summary.json` | AST-derived `exact_match_control_flow` for both documented source revisions |
| 2,442 rows; 1,272 real and 1,170 synthetic | `analysis/schema_census_summary.json` | `split_counts` |
| 2,887 typed branches | `analysis/audit_summary.json` | `contract_branch_count` |
| 44,566 positive and 37,212 negative cases | `analysis/audit_summary.json` | `generated_positive_cases`, `generated_negative_cases` |
| 2,054 numeric and 388 clock rows | `analysis/schema_census_summary.json` | `semantic_type_counts` |
| 14 numeric-string rows, 28 endpoints | `analysis/schema_census_summary.json` | `numeric_string_rows`, `numeric_string_endpoints` |
| 141 flat-unit multi-alternative rows: 57 cardinality-aligned and 84 mismatched | `analysis/mr12_source_schema_validation.json` | `flat_unit_multi_interval_rows`, `cardinality_aligned_rows`, `cardinality_mismatch_rows` |
| Official SWAR 96.12%; CCA 84.66%; MIR 85.48%; suite-FAR 7.02% | `analysis/audit_summary.json` | official row in `evaluator_metrics`; SWAR was previously named GSCR |
| Repaired SWAR 96.61%; MIR 89.94%; suite-FAR 7.02% | `analysis/audit_summary.json` | repaired row in `evaluator_metrics` |
| 15 of 24 relation families violate official semantics | `analysis/paper_numbers.json` | union of `violating_positive_relations` and `violating_negative_relations` |
| 2,440/2,442 rows have a relation-level official failure | `analysis/row_violation_distribution.json` | `rows_with_any_relation_violation`; two rows have zero |
| Official suite-FRR is 26.03% case-micro, 25.25% row-macro, 29.43% relation-macro | `analysis/aggregation_sensitivity.json` | `valid_case_rejection.official` |
| Official suite-FAR is 7.02% case-micro, 9.71% row-macro, 10.48% relation-macro | `analysis/aggregation_sensitivity.json` | `invalid_case_acceptance.official` |
| No positive/negative label collision | `analysis/label_consistency.json` | exact and normalized row-answer conflicts are both zero |
| MR-10 caused 1,534 official exceptions | `analysis/violation_taxonomy.json` | `legacy_exception_counts.official_positive`; all exception rows are MR-10 in `data/metamorphic_cases.parquet` |
| Released `zip` truncates 86 alternatives; MR-12 changes 168 cases on 84 rows without calling the typed compiler | `analysis/mr12_source_schema_validation.json` | `alternatives_truncated_by_zip`, direct released-schema reversal and legacy execution |
| 2,612 official false accepts | `analysis/differential_summary.json` | transition `110` negative cases; two further repaired-only accepts are transition `010` |
| MR-22 contributes 1,898 accepts | `data/negative_cases.parquet` | `official_full` and `relation_id==MR-22` |
| Released and current standalone upstream evaluators match on 88,189/88,189 executions | `analysis/upstream_parity.json` | `total_mismatches=0`; per-suite counts included |
| 4,884 public GPT-5/Gemini predictions over all 2,442 rows | `analysis/public_model_rescoring.json` | `answer_count`, `unique_benchmark_rows`, and documented source revisions |
| Strict-final changes 35 released labels on 33 rows: 28 strict-only and seven official-only | `analysis/public_model_rescoring.json` | `official_typed_final_changed_records`, unique-row count, and transition fields; `typed_final` is the Strict-final compatibility alias |
| Official→Core changes 68 labels (24 additions/44 removals); Core→Physics adds 53; Physics→Strict removes 12 | `analysis/scoring_profile_analysis.json` | `profile_boundary_transitions` over all 4,884 public responses |
| The final 35 Official↔Strict transitions comprise 19 Core, 11 Physics, four Strict, and one annotation-ambiguity case | `analysis/public_transition_taxonomy.json` | exhaustive executable-profile attribution; all rows in `artifacts/public_transition_taxonomy.csv` |
| Two blinded reviewers cover all 35 released-transition model answers and agree on 32/35 under the finalized SOP (91.43%; three-label Cohen's kappa 0.826) | `artifacts/dual_manual_review/reviewer_a.json`, `artifacts/dual_manual_review/reviewer_b.json`, `analysis/dual_manual_review_analysis.json` | reviewers saw only image, question, raw released annotation, benchmark instruction, and model response; seven returned cases and provisional labels are retained separately |
| A third blinded reviewer independently adjudicates the three disagreements, yielding 20 accepts, 14 rejects, and one ambiguous case; Core-final has the highest policy alignment at 24/34 determinate cases | `artifacts/dual_manual_review/adjudicator.json`, `analysis/dual_manual_review_analysis.json`, `artifacts/dual_manual_review_casebook.csv` | profile counts are descriptive on the selected Official--Strict transition set |
| Both reviewers independently flag two paired-scale source annotations as internally inconsistent | `analysis/dual_manual_review_analysis.json`, `artifacts/dual_manual_review_casebook.csv` | `transition-27` and `transition-34`; source-issue flags were recorded independently |
| Whole-response scoring changes 486 Gemini labels and flips aggregate model order | `analysis/public_model_rescoring.json` | typed-final/global transitions and `ranking_sensitivity` |
| Robust-final versus released-final extraction changes zero public binary scores | `analysis/public_model_rescoring.json` | typed-final/robust-final transition counts |
| Contemporary transfer has 637 direct responses over 149 rows; Strict-final changes nine decisions | `analysis/model_rescoring.json` and `analysis/scoring_profile_analysis.json` | model summaries plus profile boundaries: Official→Core 5/1, Core→Physics 6/0, Physics→Strict 0/5 additions/removals |
| EvalGauge 100% generated-suite conformance | `analysis/audit_summary.json`, `analysis/xbench_chartqapro_summary.json` | 90,871/90,871 cases across both declared suites; not universal evaluator accuracy |

Complete MeasureBench decisions are in `data/metamorphic_cases.parquet` and `data/negative_cases.parquet`; ChartQAPro cases are in `data/xbench_chartqapro_cases.parquet`, with relation summaries under `artifacts/xbench/chartqapro/`. Minimal counterexamples are in `artifacts/minimal_failing_cases.jsonl`; public score changes are in `artifacts/public_model_changed_cases.jsonl`; contemporary responses retain relative provenance paths and raw text in `data/model_answers.parquet`.
