from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figures" / "fig1_pipeline.pdf"
CLOCK = ROOT / "assets" / "clock_64.jpg"

plt.rcParams.update(
    {
        "font.family": "Times New Roman",
        "mathtext.fontset": "stix",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

INK = "#172A3A"
MUTED = "#667687"
RULE = "#AEB9C5"
BLUE = "#3C6EAD"
VALID = "#147A78"
INVALID = "#C44E52"


def arrow(ax, start, end):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=8,
            linewidth=0.8,
            color=RULE,
        )
    )


fig, ax = plt.subplots(figsize=(7.15, 2.55), facecolor="white")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

# Three scientific objects replace a numbered or card-based workflow.
ax.text(0.155, 0.955, "Released row", ha="center", va="top", fontsize=11.2, weight="bold", color=INK)
ax.text(0.500, 0.955, "Typed contract", ha="center", va="top", fontsize=11.2, weight="bold", color=INK)
ax.text(0.835, 0.955, "Paired scorer test", ha="center", va="top", fontsize=11.2, weight="bold", color=INK)

# Left: one real multimedia row plus the relevant released annotation.
image_ax = ax.inset_axes([0.025, 0.500, 0.255, 0.345])
image = plt.imread(CLOCK)
h, w = image.shape[:2]
image_ax.imshow(
    image[int(0.01 * h) : int(0.99 * h), int(0.075 * w) : int(0.925 * w)],
    interpolation="lanczos",
)
image_ax.set_xticks([])
image_ax.set_yticks([])
for spine in image_ax.spines.values():
    spine.set_color("#7B858E")
    spine.set_linewidth(0.45)

ax.text(0.025, 0.438, "MeasureBench · clock_64", fontsize=9.1, weight="bold", color=INK)
ax.text(0.025, 0.367, "released annotation", fontsize=8.6, color=MUTED, style="italic")
ax.text(
    0.025,
    0.292,
    "intervals = [6:45:12–14,\n             18:45:12–14]\nunits = [\"\"]",
    fontsize=8.8,
    family="DejaVu Sans Mono",
    color=INK,
    va="top",
    linespacing=1.25,
)

# Center: the scientific object implied by that row.
ax.text(0.500, 0.815, "ClockTime", ha="center", fontsize=11.5, weight="bold", color=BLUE)
ax.text(0.500, 0.710, "dimension = time", ha="center", fontsize=9.2, color=INK)
ax.text(0.500, 0.610, "legal alternatives", ha="center", fontsize=8.8, style="italic", color=MUTED)
ax.text(0.500, 0.515, "{ 06:45:12–14,", ha="center", fontsize=9.1, family="DejaVu Sans Mono", color=INK)
ax.text(0.500, 0.435, "  18:45:12–14 }", ha="center", fontsize=9.1, family="DejaVu Sans Mono", color=INK)
ax.text(0.500, 0.320, "order = unordered", ha="center", fontsize=9.2, color=INK)

# Right: paired probes use one visual grammar and expose the trace.
ax.text(0.695, 0.830, "Valid reformulation", fontsize=8.9, weight="bold", color=VALID)
ax.text(0.695, 0.745, "response   18:45:13", fontsize=9.0, family="DejaVu Sans Mono", color=INK)
ax.text(0.695, 0.660, "official 0   contract 1", fontsize=9.1, color=INK)
ax.text(0.695, 0.582, "alternative pairing", fontsize=8.6, color=MUTED, style="italic")
ax.plot([0.695, 0.975], [0.525, 0.525], color=RULE, linewidth=0.7)

ax.text(0.695, 0.445, "Invalid response", fontsize=8.9, weight="bold", color=INVALID)
ax.text(0.695, 0.360, "06:45:13 or 23:59:59", fontsize=8.7, family="DejaVu Sans Mono", color=INK)
ax.text(0.695, 0.275, "official 1   contract 0", fontsize=9.1, color=INK)
ax.text(0.695, 0.197, "conflicting values", fontsize=8.6, color=MUTED, style="italic")

arrow(ax, (0.292, 0.585), (0.368, 0.585))
arrow(ax, (0.628, 0.585), (0.688, 0.585))

OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, bbox_inches="tight", pad_inches=0.025, dpi=300)
plt.close(fig)
print(OUT)
