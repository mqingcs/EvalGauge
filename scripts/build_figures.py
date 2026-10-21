#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

mpl.rcParams.update(
    {
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "font.size": 8.5,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "mathtext.fontset": "stix",
    }
)

INK = "#172A3A"
MUTED = "#667687"
GRID = "#D8E0E8"
PAPER = "#F7F9FB"
RED = "#C44E52"
AMBER = "#A66A00"
TEAL = "#147A78"
BLUE = "#3C6EAD"
COLORS = {"official": RED, "repaired": AMBER, "type-safe": BLUE}
PUBLIC_COLORS = {
    "official": MUTED,
    "repaired": AMBER,
    "core-final": BLUE,
    "physics-final": TEAL,
    "strict-final": INK,
    "typed-final": INK,
    "typed-global": "#8A93A0",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_figure(fig, output: Path, name: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / f"{name}.pdf", bbox_inches="tight", dpi=420)
    fig.savefig(output / f"{name}.png", bbox_inches="tight", dpi=300)
    plt.close(fig)


def extract_teaser_images(real: Path, output: Path) -> None:
    frame = pd.read_parquet(real, columns=["question_id", "image"])
    output.mkdir(parents=True, exist_ok=True)
    for row_id in ["protractor_3", "clock_64", "electricity_meter_5"]:
        matches = frame.loc[frame.question_id == row_id, "image"]
        if len(matches) != 1:
            raise ValueError(f"expected one teaser source row for {row_id}, found {len(matches)}")
        payload = matches.iloc[0]
        image_bytes = payload.get("bytes") if isinstance(payload, dict) else None
        if not image_bytes:
            raise ValueError(f"missing image bytes for teaser row {row_id}")
        (output / f"{row_id}.jpg").write_bytes(image_bytes)


def build_teaser(figures: Path, teaser_images: Path) -> None:
    teaser_font = "Times New Roman"
    fig = plt.figure(figsize=(3.45, 3.44), facecolor="white")
    ax = fig.add_axes([0.012, 0.012, 0.976, 0.976])
    ax.set_axis_off()

    def add_crop(bounds, filename, crop):
        image_ax = ax.inset_axes(bounds)
        image = plt.imread(teaser_images / filename)
        pixel_height, pixel_width = image.shape[:2]
        x0, y0, x1, y1 = crop
        cropped = image[
            int(y0 * pixel_height) : int(y1 * pixel_height),
            int(x0 * pixel_width) : int(x1 * pixel_width),
        ]
        image_ax.imshow(cropped, interpolation="lanczos")
        image_ax.set_xticks([])
        image_ax.set_yticks([])
        for spine in image_ax.spines.values():
            spine.set_color("#7B858E")
            spine.set_linewidth(0.36)
        return image_ax

    # Primary witness: the image dominates; the executable consequence sits beside it.
    add_crop([0.000, 0.596, 0.625, 0.334], "clock_64.jpg", (0.075, 0.01, 0.925, 0.99))
    ax.text(
        0.655,
        0.926,
        "Alternative order",
        transform=ax.transAxes,
        fontsize=8.0,
        fontweight="bold",
        fontfamily=teaser_font,
        color=INK,
        va="top",
    )
    ax.text(
        0.655,
        0.842,
        "Legal readings\n06:45  or  18:45",
        transform=ax.transAxes,
        fontsize=6.95,
        fontfamily=teaser_font,
        color=INK,
        linespacing=1.22,
        va="top",
    )
    ax.text(
        0.655,
        0.724,
        "Response  06:45",
        transform=ax.transAxes,
        fontsize=6.95,
        fontfamily=teaser_font,
        color=INK,
        va="top",
    )
    ax.plot([0.655, 0.998], [0.672, 0.672], transform=ax.transAxes, color=GRID, linewidth=0.48)
    ax.text(
        0.655,
        0.640,
        "same set; reverse list",
        transform=ax.transAxes,
        fontsize=6.55,
        fontstyle="italic",
        fontfamily=teaser_font,
        color=MUTED,
        va="top",
    )
    ax.text(
        0.655,
        0.584,
        "Official score",
        transform=ax.transAxes,
        fontsize=6.6,
        fontfamily=teaser_font,
        color=MUTED,
        va="top",
    )
    ax.text(
        0.860,
        0.584,
        "1  →  0",
        transform=ax.transAxes,
        fontsize=8.15,
        fontweight="bold",
        fontfamily=teaser_font,
        color=AMBER,
        va="top",
    )

    ax.plot([0.000, 0.998], [0.539, 0.539], transform=ax.transAxes, color="#7B858E", linewidth=0.52)

    # Supporting witnesses: same physical size, tightly cropped around the evidence.
    add_crop([0.000, 0.205, 0.472, 0.282], "protractor_3.jpg", (0.02, 0.300, 0.98, 0.702))
    add_crop([0.528, 0.205, 0.472, 0.282], "electricity_meter_5.jpg", (0.03, 0.110, 0.87, 0.462))

    ax.text(
        0.000,
        0.522,
        "Type dispatch",
        transform=ax.transAxes,
        fontsize=7.5,
        fontweight="bold",
        fontfamily=teaser_font,
        color=INK,
        va="top",
    )
    ax.text(
        0.528,
        0.522,
        "Dimension check",
        transform=ax.transAxes,
        fontsize=7.5,
        fontweight="bold",
        fontfamily=teaser_font,
        color=INK,
        va="top",
    )

    ax.text(
        0.000,
        0.168,
        'Gold endpoints  ["60", "60"]\nModel answer  60 degrees',
        transform=ax.transAxes,
        fontsize=6.45,
        fontfamily=teaser_font,
        color=INK,
        linespacing=1.12,
        va="top",
    )
    ax.text(
        0.000,
        0.088,
        "numeric strings dispatched as clock",
        transform=ax.transAxes,
        fontsize=6.5,
        fontfamily=teaser_font,
        color=MUTED,
        va="top",
    )
    ax.text(
        0.000,
        0.027,
        "Official 0",
        transform=ax.transAxes,
        fontsize=6.6,
        fontfamily=teaser_font,
        color=MUTED,
        va="top",
    )
    ax.text(
        0.205,
        0.027,
        "Contract 1",
        transform=ax.transAxes,
        fontsize=6.9,
        fontweight="bold",
        fontfamily=teaser_font,
        color=TEAL,
        va="top",
    )

    ax.text(
        0.528,
        0.168,
        "Expected  kW (power)\nResponse  0.198 kWh (energy)",
        transform=ax.transAxes,
        fontsize=6.45,
        fontfamily=teaser_font,
        color=INK,
        linespacing=1.12,
        va="top",
    )
    ax.text(
        0.528,
        0.088,
        'substring match:  "kW" in "kWh"',
        transform=ax.transAxes,
        fontsize=6.5,
        fontfamily=teaser_font,
        color=MUTED,
        va="top",
    )
    ax.text(
        0.528,
        0.027,
        "Official 1",
        transform=ax.transAxes,
        fontsize=6.6,
        fontfamily=teaser_font,
        color=MUTED,
        va="top",
    )
    ax.text(
        0.735,
        0.027,
        "Contract 0",
        transform=ax.transAxes,
        fontsize=6.9,
        fontweight="bold",
        fontfamily=teaser_font,
        color=TEAL,
        va="top",
    )
    save_figure(fig, figures, "fig0_teaser")


def grouped_bars(ax, labels, series, *, ylabel: str, ylim=(0, 100)) -> None:
    x = np.arange(len(labels))
    width = 0.24
    offsets = np.linspace(-width, width, len(series))
    for offset, (name, values) in zip(offsets, series.items()):
        bars = ax.bar(x + offset, values, width=width, label=name, color=COLORS[name])
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.0,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=7,
            )
    ax.set_xticks(x, labels)
    ax.set_ylabel(ylabel)
    ax.set_ylim(*ylim)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.2)


def write_table(frame: pd.DataFrame, tables: Path, name: str) -> None:
    tables.mkdir(parents=True, exist_ok=True)
    frame.to_csv(tables / f"{name}.csv", index=False)
    (tables / f"{name}.tex").write_text(
        frame.to_latex(index=False, escape=True, float_format=lambda value: f"{value:.4f}"),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--real", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    analysis, figures, tables = (
        root / "analysis",
        root / "artifacts/figures",
        root / "artifacts/tables",
    )
    teaser_images = root / "artifacts/teaser"
    if args.real:
        extract_teaser_images(args.real, teaser_images)
    if all(
        (teaser_images / f"{row_id}.jpg").exists()
        for row_id in ["protractor_3", "clock_64", "electricity_meter_5"]
    ):
        build_teaser(figures, teaser_images)

    audit = load_json(analysis / "audit_summary.json")
    positive = pd.DataFrame(load_json(analysis / "positive_audit.json")["by_relation"])
    negative = pd.DataFrame(load_json(analysis / "negative_audit.json")["by_relation"])
    differential = load_json(analysis / "differential_summary.json")
    models = pd.DataFrame(
        load_json(analysis / "model_rescoring.json")["model_experiment_summaries"]
    )
    public_payload = load_json(analysis / "public_model_rescoring.json")
    public = pd.DataFrame(public_payload["model_split_summaries"])
    aggregation = load_json(analysis / "aggregation_sensitivity.json")
    parity = load_json(analysis / "upstream_parity.json")
    census = load_json(analysis / "schema_census_summary.json")
    profiles = load_json(analysis / "scoring_profile_analysis.json")
    mr12 = load_json(analysis / "mr12_source_schema_validation.json")

    metrics = pd.DataFrame(audit["evaluator_metrics"])
    metric_labels = {
        "gold_self_consistency_rate": "Source-witness\nacceptance",
        "canonical_contract_acceptance_rate": "Canonical-contract\nacceptance",
        "metamorphic_invariance_rate": "Metamorphic\ninvariance",
        "invalid_rejection_rate": "Invalid-case\nrejection",
    }
    fig, ax = plt.subplots(figsize=(8.2, 3.7))
    grouped_bars(
        ax,
        list(metric_labels.values()),
        {
            evaluator: [
                100
                * (
                    1
                    - float(
                        metrics.loc[metrics.evaluator == evaluator, "false_acceptance_rate"].iloc[0]
                    )
                    if key == "invalid_rejection_rate"
                    else float(metrics.loc[metrics.evaluator == evaluator, key].iloc[0])
                )
                for key in metric_labels
            ]
            for evaluator in ["official", "repaired", "type-safe"]
        },
        ylabel="Rate (%)",
    )
    ax.legend(frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    save_figure(fig, figures, "fig1_headline_metrics")

    selected_positive = positive[
        positive.relation_id.isin(["MR-02", "MR-08", "MR-09", "MR-10", "MR-12"])
    ]
    fig, ax = plt.subplots(figsize=(8.2, 3.7))
    grouped_bars(
        ax,
        selected_positive.relation_id.tolist(),
        {
            name: (100 * selected_positive[f"{name.replace('-', '_')}_acceptance"]).tolist()
            for name in ["official", "repaired", "type-safe"]
        },
        ylabel="Equivalent-answer acceptance (%)",
    )
    ax.legend(frameon=False, ncol=3, loc="upper center")
    save_figure(fig, figures, "fig2_positive_relations")

    negative_cases = pd.read_parquet(root / "data/negative_cases.parquet")
    selected_negative = negative[negative.relation_id.isin(["MR-22", "MR-18", "MR-16"])].copy()
    selected_negative["accepted_invalid"] = (
        (selected_negative.cases * selected_negative.official_far).round().astype(int)
    )
    selected_negative["affected_rows"] = selected_negative.relation_id.map(
        negative_cases.loc[negative_cases.official_full]
        .groupby("relation_id")
        .row_id.nunique()
        .to_dict()
    )
    selected_negative = selected_negative.sort_values("official_far", ascending=False)
    short_names = {
        "MR-22": "UNIT TOKEN",
        "MR-18": "MULTI-VALUE",
        "MR-16": "CONVERSION",
    }
    selected_negative["label"] = selected_negative.apply(
        lambda row: (
            f"{row['relation_id']}  {short_names[row['relation_id']]}\n"
            f"{row['accepted_invalid']:,}/{row['cases']:,}; {int(row['affected_rows']):,} rows"
        ),
        axis=1,
    )
    fig, ax = plt.subplots(figsize=(3.55, 1.84))
    rates = 100 * selected_negative.official_far
    bars = ax.barh(np.arange(len(selected_negative)), rates, height=0.42, color=RED)
    ax.set_yticks(np.arange(len(selected_negative)), selected_negative.label)
    ax.invert_yaxis()
    for bar, rate in zip(bars, rates):
        inside = rate > 24
        ax.text(
            rate - 1.7 if inside else rate + 1.7,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.1f}%",
            fontsize=6.7,
            color="white" if inside else INK,
            ha="right" if inside else "left",
            va="center",
            fontweight="bold",
        )
    ax.set_xlim(0, 100)
    ax.set_xlabel("Generated invalid cases accepted (%)")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=6.3)
    ax.grid(axis="x", color=GRID, linewidth=0.55)
    ax.set_axisbelow(True)
    save_figure(fig, figures, "fig3_false_acceptance_relations")

    schema_labels = [
        "Numeric rows",
        "Clock rows",
        "Multi-interval",
        "Flat-unit alternatives",
        "Numeric strings",
    ]
    schema_values = [
        census["semantic_type_counts"]["numeric_quantity"],
        census["semantic_type_counts"]["clock_time"],
        census["multi_interval_rows"],
        census["compiler_warning_counts"]["flat_unit_list_broadcast_across_alternatives"],
        census["numeric_string_rows"],
    ]
    fig, ax = plt.subplots(figsize=(7.3, 3.7))
    bars = ax.bar(schema_labels, schema_values, color="#5470C6")
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.set_ylabel("Benchmark rows")
    ax.tick_params(axis="x", labelrotation=22)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.2)
    save_figure(fig, figures, "fig4_schema_census")

    model_labels = []
    for row in models.itertuples(index=False):
        model = (
            "Doubao"
            if "doubao" in row.model.casefold()
            else ("Gemini" if "gemini" in row.model.casefold() else "Qwen")
        )
        suffix = "65" if row.n_rows == 65 else str(row.n_rows)
        model_labels.append(f"{model}-{suffix}")
    fig, ax = plt.subplots(figsize=(8.2, 3.7))
    grouped_bars(
        ax,
        model_labels,
        {
            "official": (100 * models.official_full).tolist(),
            "repaired": (100 * models.repaired_full).tolist(),
            "type-safe": (100 * models.type_safe_full).tolist(),
        },
        ylabel="Historical response accuracy (%)",
        ylim=(0, 60),
    )
    ax.legend(frameon=False, ncol=3, loc="upper center")
    save_figure(fig, figures, "fig5_model_rescoring")

    public_splits = public[public.split != "all"].copy()
    public_splits["label"] = public_splits.apply(
        lambda row: (
            f"{row['model'].replace('-2.5-Pro', '')}\n{'Real' if row['split'] == 'real_world' else 'Synthetic'}"
        ),
        axis=1,
    )
    for profile in ["core_final", "physics_final", "strict_final"]:
        public_splits[f"{profile}_delta_pp"] = 100 * (
            public_splits[f"{profile}_accuracy"] - public_splits.official_accuracy
        )
    public_splits = public_splits.sort_values("strict_final_delta_pp", ascending=True)
    fig, ax = plt.subplots(figsize=(3.55, 2.24))
    y = np.arange(len(public_splits))
    profile_style = [
        ("core_final", "o", PUBLIC_COLORS["core-final"], "Core"),
        ("physics_final", "D", PUBLIC_COLORS["physics-final"], "Physics"),
        ("strict_final", "s", PUBLIC_COLORS["strict-final"], "Strict"),
    ]
    for ypos, row in zip(y, public_splits.itertuples(index=False)):
        values = [
            row.core_final_delta_pp,
            row.physics_final_delta_pp,
            row.strict_final_delta_pp,
        ]
        ax.plot(values, [ypos] * 3, color="#AEB9C5", linewidth=1.0, zorder=1)
    for profile, marker, color, label in profile_style:
        ax.scatter(
            public_splits[f"{profile}_delta_pp"],
            y,
            s=27,
            marker=marker,
            color=color,
            edgecolor="white",
            linewidth=0.45,
            zorder=3,
            label=label,
        )
    ax.set_yticks(y, public_splits.label.str.replace("\n", " · "))
    ax.set_xlabel("Score change from released evaluator (pp)")
    ax.set_xlim(-1.1, 1.5)
    ax.axvline(0, color="#7C8794", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.55)
    ax.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker=marker,
                color="none",
                markerfacecolor=color,
                markeredgecolor="white",
                markersize=5.5,
                label=label,
            )
            for _, marker, color, label in profile_style
        ],
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        columnspacing=1.1,
        handletextpad=0.35,
    )
    save_figure(fig, figures, "fig6_public_rescoring")

    all_public = public[public.split == "all"].copy()
    fig, ax = plt.subplots(figsize=(6.8, 3.5))
    x = np.arange(len(all_public))
    final_values = 100 * all_public.typed_final_accuracy
    global_values = 100 * all_public.typed_global_accuracy
    bars_final = ax.bar(
        x - 0.16, final_values, width=0.32, label="Typed-final", color=PUBLIC_COLORS["typed-final"]
    )
    bars_global = ax.bar(
        x + 0.16,
        global_values,
        width=0.32,
        label="Whole-response",
        color=PUBLIC_COLORS["typed-global"],
    )
    ax.bar_label(
        bars_final, labels=[f"{value:.2f}" for value in final_values], padding=2, fontsize=8
    )
    ax.bar_label(
        bars_global, labels=[f"{value:.2f}" for value in global_values], padding=2, fontsize=8
    )
    ax.set_xticks(x, all_public.model.str.replace("-2.5-Pro", "", regex=False))
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(0, max(35, final_values.max() + 4))
    ax.legend(frameon=False, ncol=2, loc="upper center")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.2)
    save_figure(fig, figures, "fig7_extraction_sensitivity")

    transition = pd.DataFrame(differential["transition_matrix"])
    write_table(metrics, tables, "table1_evaluator_metrics")
    write_table(pd.DataFrame(audit["split_metrics"]), tables, "table2_split_metrics")
    write_table(positive, tables, "table3_positive_relations")
    write_table(negative, tables, "table4_negative_relations")
    write_table(models, tables, "table5_model_rescoring")
    write_table(transition, tables, "table6_transition_matrix")
    write_table(public, tables, "table7_public_model_rescoring")

    violating_positive = set(positive.loc[positive.official_mir < 1, "relation_id"])
    violating_negative = set(negative.loc[negative.official_far > 0, "relation_id"])
    paper_numbers = {
        "benchmark_rows": audit["row_count"],
        "contract_branches": audit["contract_branch_count"],
        "positive_cases": audit["generated_positive_cases"],
        "negative_cases": audit["generated_negative_cases"],
        "official_affected_rows": audit["affected_row_count_official"],
        "relation_families_with_official_violation": len(violating_positive | violating_negative),
        "violating_positive_relations": sorted(violating_positive),
        "violating_negative_relations": sorted(violating_negative),
        "historical_answers": int(load_json(analysis / "model_rescoring.json")["answer_count"]),
        "historical_unique_rows": int(load_json(analysis / "model_rescoring.json")["unique_rows"]),
        "max_model_score_shift_pp": float(100 * models.delta_type_safe_minus_official.max()),
        "ranking_groups": int(load_json(analysis / "ranking_analysis.json")["ranking_groups"]),
        "ranking_order_changes": int(
            load_json(analysis / "ranking_analysis.json")["order_changed_groups"]
        ),
        "public_answers": int(public_payload["answer_count"]),
        "public_official_typed_changed": int(
            public_payload["official_typed_final_changed_records"]
        ),
        "public_typed_only": int(public_payload["typed_final_only_records"]),
        "public_official_only": int(public_payload["official_only_records"]),
        "public_whole_response_policy_changes": int(
            public_payload["typed_final_global_changed_records"]
        ),
        "public_profile_boundary_transitions": profiles["profile_boundary_transitions"],
        "mr12_flat_unit_rows": int(mr12["flat_unit_multi_interval_rows"]),
        "mr12_aligned_flat_unit_rows": int(mr12["cardinality_aligned_rows"]),
        "mr12_mismatched_flat_unit_rows": int(mr12["cardinality_mismatch_rows"]),
        "mr12_alternatives_truncated_by_legacy_zip": int(
            mr12["alternatives_truncated_by_zip"]
        ),
        "mr12_binary_score_flips": int(mr12["binary_score_flips"]),
        "upstream_parity_executions": int(parity["total_executions"]),
        "upstream_parity_mismatches": int(parity["total_mismatches"]),
        "official_valid_rejection_case_micro": float(
            aggregation["valid_case_rejection"]["official"]["case_micro"]
        ),
        "official_valid_rejection_row_macro": float(
            aggregation["valid_case_rejection"]["official"]["row_macro"]
        ),
        "official_valid_rejection_relation_macro": float(
            aggregation["valid_case_rejection"]["official"]["relation_family_macro"]
        ),
        "official_invalid_acceptance_case_micro": float(
            aggregation["invalid_case_acceptance"]["official"]["case_micro"]
        ),
        "official_invalid_acceptance_row_macro": float(
            aggregation["invalid_case_acceptance"]["official"]["row_macro"]
        ),
        "official_invalid_acceptance_relation_macro": float(
            aggregation["invalid_case_acceptance"]["official"]["relation_family_macro"]
        ),
    }
    (analysis / "paper_numbers.json").write_text(
        json.dumps(paper_numbers, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
