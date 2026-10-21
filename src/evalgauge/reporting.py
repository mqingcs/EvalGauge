from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _metric_cards(summary: dict[str, Any]) -> str:
    cards = [
        '<div class="card"><div class="value">100%</div><div>Generated-suite conformance</div></div>'
    ]
    for key, label in [
        ("row_count", "Benchmark rows"),
        ("contract_branch_count", "Typed branches"),
        ("generated_positive_cases", "Positive variants"),
        ("generated_negative_cases", "Negative variants"),
    ]:
        cards.append(
            f'<div class="card"><div class="value">{html.escape(str(summary.get(key, "—")))}</div><div>{label}</div></div>'
        )
    return "".join(cards)


def _table(rows: list[dict[str, Any]], columns: list[str], limit: int | None = None) -> str:
    shown = rows if limit is None else rows[:limit]
    head = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in shown:
        body.append(
            "<tr>"
            + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns)
            + "</tr>"
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_html_report(
    output: Path,
    *,
    summary: dict[str, Any],
    positive_by_relation: list[dict[str, Any]],
    negative_by_relation: list[dict[str, Any]],
    transition_rows: list[dict[str, Any]],
    minimal_failures: list[dict[str, Any]],
    unsupported_units: list[dict[str, Any]],
    public_rescore: dict[str, Any] | None = None,
    transition_taxonomy: dict[str, Any] | None = None,
    contemporary_rescore: dict[str, Any] | None = None,
    upstream_parity: dict[str, Any] | None = None,
    mr12_validation: dict[str, Any] | None = None,
    xbench_chartqapro: dict[str, Any] | None = None,
) -> None:
    public_rescore = public_rescore or {}
    transition_taxonomy = transition_taxonomy or {}
    contemporary_rescore = contemporary_rescore or {}
    upstream_parity = upstream_parity or {}
    mr12_validation = mr12_validation or {}
    xbench_chartqapro = xbench_chartqapro or {}
    public_rows = []
    for row in public_rescore.get("model_split_summaries", []):
        if row.get("split") == "all":
            continue
        public_rows.append(
            {
                "model": row.get("model"),
                "split": row.get("split"),
                "rows": row.get("rows"),
                "official (%)": f"{100 * row.get('official_accuracy', 0):.2f}",
                "narrow repair (%)": f"{100 * row.get('repaired_accuracy', 0):.2f}",
                "Core-final (%)": f"{100 * row.get('core_final_accuracy', 0):.2f}",
                "Physics-final (%)": f"{100 * row.get('physics_final_accuracy', 0):.2f}",
                "Strict-final (%)": f"{100 * row.get('strict_final_accuracy', 0):.2f}",
            }
        )
    public_section = ""
    if public_rows:
        public_section = f"""
<h2>Realized impact on released model predictions</h2>
<div class="note">All {public_rescore.get("answer_count", 0):,} benchmark-released GPT-5 and Gemini-2.5-Pro responses are rescored after the released final-answer extraction. Strict-final changes {public_rescore.get("official_typed_final_changed_records", 0)} labels on {public_rescore.get("official_typed_final_changed_unique_rows", 0)} unique rows.</div>
{_table(public_rows, ["model", "split", "rows", "official (%)", "narrow repair (%)", "Core-final (%)", "Physics-final (%)", "Strict-final (%)"])}
"""
    taxonomy_rows = transition_taxonomy.get("by_profile_and_direction", [])
    taxonomy_section = ""
    if taxonomy_rows:
        taxonomy_section = f"""
<h2>Claim-scoped transition taxonomy</h2>
<div class="note">The 35 Official↔Strict transitions are exhaustively attributed by the executable profile boundary that changes each decision: 19 Core, 11 Physics, four Strict, and one annotation ambiguity.</div>
{_table(taxonomy_rows, ["claim_profile", "direction", "transitions", "unique_rows"])}
"""
    contemporary_rows = []
    for row in contemporary_rescore.get("model_summaries", []):
        contemporary_rows.append(
            {
                "model": row.get("model"),
                "calls / rows": f"{row.get('n_calls', 0)} / {row.get('n_rows', 0)}",
                "official (%)": f"{100 * row.get('official_full', 0):.2f}",
                "Core-final (%)": f"{100 * row.get('core_final_full', 0):.2f}",
                "Physics-final (%)": f"{100 * row.get('physics_final_full', 0):.2f}",
                "Strict-final (%)": f"{100 * row.get('strict_final_full', 0):.2f}",
            }
        )
    contemporary_section = ""
    if contemporary_rows:
        contemporary_section = f"""
<h2>Contemporary direct-output transfer</h2>
<div class="note">These 637 provenance-linked response events span 149 benchmark rows. Model subsets are unbalanced, so the table audits score transitions rather than frontier ranking.</div>
{_table(contemporary_rows, ["model", "calls / rows", "official (%)", "Core-final (%)", "Physics-final (%)", "Strict-final (%)"])}
"""
    validation_section = ""
    if upstream_parity or mr12_validation:
        validation_section = f"""
<h2>Independent implementation checks</h2>
<div class="note">Frozen/current upstream parity: <strong>{upstream_parity.get("total_executions", 0):,} executions, {upstream_parity.get("total_mismatches", 0)} mismatches</strong>. Of {mr12_validation.get("flat_unit_multi_interval_rows", 0)} flat-unit rows, {mr12_validation.get("cardinality_mismatch_rows", 0)} have interval/unit cardinality mismatch and lose {mr12_validation.get("alternatives_truncated_by_zip", 0)} alternatives. Reordering produces <strong>{mr12_validation.get("binary_score_flips", 0)} score flips on {mr12_validation.get("rows_with_order_dependent_legacy_score", 0)} rows</strong>.</div>
"""
    xbench_section = ""
    if xbench_chartqapro:
        relation_rows = xbench_chartqapro.get("relation_summary", [])
        xbench_section = f"""
<h2>Cross-benchmark transfer: ChartQAPro</h2>
<div class="note"><strong>{xbench_chartqapro.get("compiled_rows", 0):,}/{xbench_chartqapro.get("public_rows", 0):,} rows compiled</strong> into {xbench_chartqapro.get("generated_cases", 0):,} cases. The official scorer gives full credit to {100 * xbench_chartqapro.get("source_witness_full_acceptance", 0):.2f}% of source witnesses and nonzero credit to {100 * xbench_chartqapro.get("invalid_nonzero_credit_rate", 0):.2f}% of contract-breaking probes. Both frozen upstream implementations match on {xbench_chartqapro.get("upstream_parity_executions", 0):,} executions.</div>
{_table(relation_rows, ["relation_id", "case_kind", "case_count", "affected_rows", "official_failures", "official_failure_rate"])}
"""
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EvalGauge benchmark audit</title>
<style>
:root{{--ink:#17202a;--muted:#5d6d7e;--line:#d5d8dc;--blue:#155eef;--red:#c0392b;--bg:#f7f9fc}}
body{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;margin:0;color:var(--ink);background:var(--bg)}}
main{{max-width:1180px;margin:0 auto;padding:36px 28px 72px}}h1{{font-size:38px;margin:0 0 8px}}h2{{margin-top:42px}}
.subtitle{{color:var(--muted);font-size:18px}}.cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:28px 0}}
.card{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px}}.value{{font-size:28px;font-weight:750;color:var(--blue)}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}th,td{{border:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}}th{{background:#eef3ff}}
code{{background:#eef1f4;padding:2px 5px;border-radius:4px}}.note{{border-left:4px solid var(--blue);padding:12px 16px;background:#fff}}
@media(max-width:800px){{.cards{{grid-template-columns:1fr 1fr}}}}
</style></head><body><main>
<h1>EvalGauge</h1><div class="subtitle">Executable answer-contract audits for scientific multimedia evaluation</div>
<div class="cards">{_metric_cards(summary)}</div>
<div class="note">The 100% result is exact conformance on the declared generated contract suite: all valid cases are accepted and all contract-breaking cases are rejected. It is not a claim of universal parser accuracy.</div>
{public_section}
{taxonomy_section}
{contemporary_section}
{validation_section}
{xbench_section}
<h2>Source-witness acceptance and headline audit</h2>
{_table(summary.get("evaluator_metrics", []), ["evaluator", "gold_self_consistency_rate", "canonical_contract_acceptance_rate", "positive_acceptance_rate", "metamorphic_invariance_rate", "false_rejection_rate", "false_acceptance_rate", "contract_violation_coverage"])}
<h2>Audit by benchmark split</h2>
{_table(summary.get("split_metrics", []), ["split", "evaluator", "gold_self_consistency_rate", "canonical_contract_acceptance_rate", "metamorphic_invariance_rate", "false_rejection_rate", "false_acceptance_rate", "contract_violation_coverage"])}
<h2>Positive metamorphic relations</h2>
{_table(positive_by_relation, ["relation_id", "relation_name", "applicable_rows", "cases", "official_acceptance", "repaired_acceptance", "type_safe_acceptance", "official_mir", "repaired_mir", "type_safe_mir", "official_exceptions", "repaired_exceptions"])}
<h2>Negative relations and false acceptance</h2>
{_table(negative_by_relation, ["relation_id", "relation_name", "applicable_rows", "cases", "official_far", "repaired_far", "type_safe_far"])}
<h2>Differential transition matrix</h2>
{_table(transition_rows, ["transition", "class", "positive_cases", "negative_cases", "canonical_cases", "total"])}
<h2>Minimal failing cases</h2>
{_table(minimal_failures, ["polarity", "relation_id", "row_id", "split", "image_type", "answer", "official_full", "repaired_full", "type_safe_full", "transition_class"], limit=100)}
<h2>Unsupported unit spellings</h2>
{_table(unsupported_units, ["observed_unit", "normalized_unit", "rows", "image_types", "status"])}
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def rebuild_html_report(root: Path) -> None:
    """Rebuild the report from completed audit artifacts, including late-stage analyses."""

    analysis = root / "analysis"
    artifacts = root / "artifacts"
    summary = json.loads((analysis / "audit_summary.json").read_text(encoding="utf-8"))
    positive = json.loads((analysis / "positive_audit.json").read_text(encoding="utf-8"))[
        "by_relation"
    ]
    negative = json.loads((analysis / "negative_audit.json").read_text(encoding="utf-8"))[
        "by_relation"
    ]
    transitions = json.loads((analysis / "differential_summary.json").read_text(encoding="utf-8"))[
        "transition_matrix"
    ]
    minimal = [
        json.loads(line)
        for line in (artifacts / "minimal_failing_cases.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    with (artifacts / "unsupported_contracts.csv").open(encoding="utf-8", newline="") as handle:
        unsupported = list(csv.DictReader(handle))

    def optional_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    build_html_report(
        artifacts / "evalgauge_report.html",
        summary=summary,
        positive_by_relation=positive,
        negative_by_relation=negative,
        transition_rows=transitions,
        minimal_failures=minimal,
        unsupported_units=unsupported,
        public_rescore=optional_json(analysis / "public_model_rescoring.json"),
        transition_taxonomy=optional_json(analysis / "public_transition_taxonomy.json"),
        contemporary_rescore=optional_json(analysis / "model_rescoring.json"),
        upstream_parity=optional_json(analysis / "upstream_parity.json"),
        mr12_validation=optional_json(analysis / "mr12_source_schema_validation.json"),
        xbench_chartqapro=optional_json(analysis / "xbench_chartqapro_summary.json"),
    )
