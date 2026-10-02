"""One-off generator for the architecture diagram used in the TechCon abstract.

Renders the platform's architecture (described in docs/02-architecture.md) as
a single PNG figure in the "system diagram" style common in research papers:
an icon row for entry points, a scheduler-style box, two parallel flow
branches with checkmarked feature lists, a central coordinator, and two
connected execution/output stages at the bottom. Run manually when the
architecture changes:

    .\\.venv\\Scripts\\python.exe scripts\\generate_architecture_diagram.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "reports" / "architecture_diagram.png"

GREY = "#6E6E6E"
GREY_FILL = "#DCDCDC"
DARK = "#1A1A1A"
HPE_GREEN = "#01A982"
LINE = "#333333"


# ---------------------------------------------------------------------------
# Small pictograms (kept intentionally simple/flat, matching the reference
# figure's icon style) drawn directly with matplotlib primitives.
# ---------------------------------------------------------------------------

def icon_excel(ax, cx, cy, s=0.42):
    body = FancyBboxPatch((cx - s, cy - s), 2 * s, 2 * s,
                           boxstyle="round,pad=0.01,rounding_size=0.05",
                           linewidth=1.3, edgecolor=LINE, facecolor="white", zorder=3)
    ax.add_patch(body)
    ax.add_patch(Rectangle((cx - s, cy + s - 0.16), 2 * s, 0.16, facecolor=HPE_GREEN, edgecolor="none", zorder=4))
    for gx in (cx - s / 2.2, cx, cx + s / 2.2):
        ax.plot([gx, gx], [cy - s + 0.06, cy + s - 0.18], color=GREY, linewidth=0.9, zorder=4)
    for gy in (cy - s / 2.2, cy + s / 2.6):
        ax.plot([cx - s + 0.06, cx + s - 0.06], [gy, gy], color=GREY, linewidth=0.9, zorder=4)


def icon_database(ax, cx, cy, s=0.42):
    w, h = s * 1.9, s * 2.0
    top = Ellipse((cx, cy + h / 2 - w * 0.17), w, w * 0.34, facecolor="white", edgecolor=LINE, linewidth=1.3, zorder=4)
    body = Rectangle((cx - w / 2, cy - h / 2), w, h - w * 0.17, facecolor="white", edgecolor=LINE,
                      linewidth=1.3, zorder=2)
    bottom = Ellipse((cx, cy - h / 2), w, w * 0.34, facecolor=GREY_FILL, edgecolor=LINE, linewidth=1.3, zorder=2)
    ax.add_patch(body)
    ax.add_patch(bottom)
    ax.add_patch(top)
    for frac in (0.33, 0.62):
        yy = cy - h / 2 + frac * (h - w * 0.17)
        ax.plot([cx - w / 2, cx + w / 2], [yy, yy], color=GREY, linewidth=0.9, zorder=5)


def icon_notebook(ax, cx, cy, s=0.42):
    body = FancyBboxPatch((cx - s, cy - s), 2 * s, 2 * s,
                           boxstyle="round,pad=0.01,rounding_size=0.05",
                           linewidth=1.3, edgecolor=LINE, facecolor="white", zorder=3)
    ax.add_patch(body)
    ax.text(cx, cy + 0.05, "</>", ha="center", va="center", fontsize=12, fontweight="bold", color=HPE_GREEN, zorder=4)
    ax.plot([cx - s * 0.6, cx + s * 0.6], [cy - s * 0.55, cy - s * 0.55], color=GREY, linewidth=0.9, zorder=4)


def icon_chart(ax, cx, cy, s=0.42):
    body = FancyBboxPatch((cx - s, cy - s), 2 * s, 2 * s,
                           boxstyle="round,pad=0.01,rounding_size=0.05",
                           linewidth=1.3, edgecolor=LINE, facecolor="white", zorder=3)
    ax.add_patch(body)
    bars = [0.25, 0.55, 0.4, 0.7]
    bw = (2 * s * 0.7) / len(bars)
    x0 = cx - s * 0.65
    for i, h in enumerate(bars):
        ax.add_patch(Rectangle((x0 + i * (bw + 0.03), cy - s * 0.6), bw, h * s * 1.1,
                                facecolor=HPE_GREEN if i % 2 == 0 else GREY, edgecolor="none", zorder=4))


def icon_server(ax, cx, cy, s=0.5):
    """A small rack-style icon, echoing the reference figure's compute boxes."""
    w, h = s * 1.5, s * 1.3
    outer = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                            boxstyle="round,pad=0.015,rounding_size=0.04",
                            linewidth=1.3, edgecolor=LINE, facecolor="white", zorder=3)
    ax.add_patch(outer)
    for i in range(3):
        yy = cy - h / 2 + 0.12 + i * (h - 0.24) / 2
        ax.plot([cx - w / 2 + 0.08, cx + w / 2 - 0.08], [yy, yy], color=GREY, linewidth=1.0, zorder=4)
        ax.add_patch(Circle((cx + w / 2 - 0.16, yy), 0.02, facecolor=HPE_GREEN, edgecolor="none", zorder=5))


def labeled_icon(ax, cx, cy, draw_fn, label, size=0.42, label_dy=-0.68):
    draw_fn(ax, cx, cy, size)
    ax.text(cx, cy + label_dy, label, ha="center", va="top", fontsize=8.3, color=DARK, linespacing=1.25)


def rounded_box(ax, x, y, w, h, text, facecolor="white", edgecolor=LINE, textcolor=DARK,
                 fontsize=10, bold=True, zorder=3, linewidth=1.3):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.015,rounding_size=0.045",
                          linewidth=linewidth, edgecolor=edgecolor, facecolor=facecolor, zorder=zorder)
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize,
            fontweight="bold" if bold else "normal", color=textcolor, linespacing=1.3, zorder=zorder + 1)
    return box


def checklist_box(ax, x, y, w, h, title, items):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.015,rounding_size=0.045",
                          linewidth=1.2, edgecolor=LINE, facecolor="white", zorder=3)
    ax.add_patch(box)
    ax.text(x + w / 2, y + h - 0.16, title, ha="center", va="top", fontsize=9.3,
            fontweight="bold", color=DARK, zorder=4)
    ax.plot([x + 0.12, x + w - 0.12], [y + h - 0.34, y + h - 0.34], color=GREY_FILL, linewidth=1.0, zorder=4)
    n = len(items)
    top = y + h - 0.5
    step = (h - 0.65) / max(n - 1, 1) if n > 1 else 0
    for i, item in enumerate(items):
        yy = top - i * step
        ax.text(x + 0.16, yy, "\u2713", ha="left", va="center", fontsize=9, color=HPE_GREEN,
                fontweight="bold", zorder=4)
        ax.text(x + 0.38, yy, item, ha="left", va="center", fontsize=8.2, color=DARK, zorder=4)


def straight_arrow(ax, p0, p1, color=LINE, lw=1.4, style="-|>", mutation=14, zorder=2):
    arr = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=mutation,
                           linewidth=lw, color=color, zorder=zorder, shrinkA=0, shrinkB=0)
    ax.add_patch(arr)
    return arr


def curved_double_arrow(ax, p0, p1, rad=0.28, color=LINE, lw=1.3, label=None, label_dy=0.18):
    arr = FancyArrowPatch(p0, p1, arrowstyle="<|-|>", mutation_scale=13, linewidth=lw,
                           color=color, zorder=2, connectionstyle=f"arc3,rad={rad}")
    ax.add_patch(arr)
    if label:
        mx, my = (p0[0] + p1[0]) / 2, max(p0[1], p1[1]) + label_dy
        ax.text(mx, my, label, ha="center", va="bottom", fontsize=8.0, color=DARK, style="italic")


def main():
    fig_w, fig_h = 10.6, 12.4
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    # ---- Row 1: entry-point icons -----------------------------------
    icon_y = fig_h - 0.85
    labeled_icon(ax, 2.1, icon_y, icon_excel, "Excel\nworkbook", label_dy=-0.58)
    labeled_icon(ax, 5.3, icon_y, icon_database, "SQL Server\n(S/4HANA renewal data)", label_dy=-0.58)
    labeled_icon(ax, 8.5, icon_y, icon_notebook, "Analyst\n(Jupyter notebook)", label_dy=-0.58)

    sched_y = icon_y - 2.05
    for cx in (2.1, 5.3, 8.5):
        straight_arrow(ax, (cx, icon_y - 1.1), (cx, sched_y + 0.78))

    # ---- Request scheduler: Notebook UI ------------------------------
    sched_x, sched_w, sched_h = 1.1, 8.4, 0.78
    rounded_box(ax, sched_x, sched_y, sched_w, sched_h,
                "Notebook UI  \u2014  request scheduler\n(ui/widgets.py: DataQualityApp)",
                facecolor=GREY_FILL, fontsize=10.2)

    # ---- Two parallel flows -------------------------------------------
    flow_y = sched_y - 2.55
    flow_h = 2.15
    flow_w = 3.95
    gap = 0.5
    left_x = sched_x
    right_x = sched_x + flow_w + gap

    ax.text(left_x + flow_w / 2, flow_y + flow_h + 0.28, "Flow A \u2014 Data Quality", ha="center",
            fontsize=9.3, fontweight="bold", color=HPE_GREEN, style="italic")
    ax.text(right_x + flow_w / 2, flow_y + flow_h + 0.28, "Flow B \u2014 Revenue Validation", ha="center",
            fontsize=9.3, fontweight="bold", color=HPE_GREEN, style="italic")

    checklist_box(ax, left_x, flow_y, flow_w, flow_h, "Registry-driven checks",
                  ["Completeness", "Uniqueness", "Validity", "Consistency",
                   "Hygiene", "Distribution"])
    checklist_box(ax, right_x, flow_y, flow_w, flow_h, "Old-vs-new renewal rules",
                  ["Revenue delta vs. threshold", "Renewal doc. completeness",
                   "Channel profile / Tier 2", "Document-type filter"])

    straight_arrow(ax, (left_x + flow_w / 2, sched_y), (left_x + flow_w / 2, flow_y + flow_h + 0.05))
    straight_arrow(ax, (right_x + flow_w / 2, sched_y), (right_x + flow_w / 2, flow_y + flow_h + 0.05))

    # ---- Central coordinator -------------------------------------------
    coord_y = flow_y - 1.35
    coord_x, coord_w, coord_h = 1.6, 7.4, 0.78
    rounded_box(ax, coord_x, coord_y, coord_w, coord_h,
                "Central coordinator  \u2014  Rule Registry + Engine\n(registry.py \u00b7 presets.py \u00b7 engine.run_checks())",
                facecolor=GREY_FILL, fontsize=10.2)
    straight_arrow(ax, (left_x + flow_w / 2, flow_y), (coord_x + coord_w * 0.3, coord_y + coord_h))
    straight_arrow(ax, (right_x + flow_w / 2, flow_y), (coord_x + coord_w * 0.7, coord_y + coord_h))

    # ---- Bottom stage: execution + output, with curved link -----------
    bottom_y = coord_y - 2.55
    bottom_h = 2.0
    bottom_w = 3.95
    straight_arrow(ax, (coord_x + coord_w * 0.3, coord_y), (left_x + flow_w / 2, bottom_y + bottom_h))
    straight_arrow(ax, (coord_x + coord_w * 0.7, coord_y), (right_x + flow_w / 2, bottom_y + bottom_h))

    rounded_box(ax, left_x, bottom_y, bottom_w, bottom_h,
                "Rule runners\n(rules/*.py \u2014 25 runners,\nerror isolation per rule)",
                facecolor="white", fontsize=9.6)
    rounded_box(ax, right_x, bottom_y, bottom_w, bottom_h,
                "Report writers\n(report/excel.py \u00b7 report/html.py)\n+ decision-tree root cause analysis\n(rule-based + learned tree)",
                facecolor="white", fontsize=9.6)

    curved_double_arrow(ax, (left_x + bottom_w, bottom_y + bottom_h * 0.55),
                         (right_x, bottom_y + bottom_h * 0.55),
                         rad=0.35, label="QualityReport (results, counts, status)")

    # ---- Final outputs row ---------------------------------------------
    out_y = bottom_y - 1.3
    labeled_icon(ax, left_x + bottom_w / 2, out_y, icon_server, "Data access layer\n(io_utils.py \u00b7 SQL connector)",
                 size=0.5, label_dy=-0.78)
    labeled_icon(ax, right_x + 0.95, out_y, icon_excel, "Excel workbook")
    labeled_icon(ax, right_x + bottom_w - 0.95, out_y, icon_chart, "HTML dashboard\n+ root cause insights")

    straight_arrow(ax, (left_x + bottom_w / 2, bottom_y), (left_x + bottom_w / 2, out_y + 0.72))
    straight_arrow(ax, (right_x + 0.95, bottom_y), (right_x + 0.95, out_y + 0.72))
    straight_arrow(ax, (right_x + bottom_w - 0.95, bottom_y), (right_x + bottom_w - 0.95, out_y + 0.72))

    ax.text(fig_w / 2, 0.25,
            "Figure 1 \u2014 Architecture of the Data Quality and Revenue Validation platform.\n"
            "Dependencies flow one way: presentation \u2192 configuration \u2192 execution \u2192 data access \u2192 output.",
            fontsize=9.3, ha="center", va="bottom", color=DARK, style="italic")

    fig.tight_layout(pad=0.4)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=220, facecolor="white")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
