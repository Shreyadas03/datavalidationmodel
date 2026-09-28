"""Standalone HTML dashboard writer.

The output is a single self-contained file: charts are embedded as base64 PNGs
and all cell values pass through Jinja/pandas escaping.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from dq_platform.models import QualityReport

TEMPLATE_DIR = Path(__file__).parent / "templates"

# HTML previews stay small so the file opens quickly in a browser.
DEFAULT_HTML_ROW_LIMIT = 200


def _figure_to_base64(figure) -> str:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=110, bbox_inches="tight")
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _failure_chart(report: QualityReport) -> Optional[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    failing = [r for r in report.results if r.status == "FAIL" and r.failed_count]
    if not failing:
        return None

    failing = sorted(failing, key=lambda r: r.failed_pct, reverse=True)[:15]
    labels = [f"{r.label} ({r.column_label})"[:55] for r in failing][::-1]
    values = [r.failed_pct for r in failing][::-1]

    figure, axes = plt.subplots(figsize=(9, max(2.2, 0.42 * len(labels))))
    axes.barh(labels, values, color="#c8102e")
    axes.set_xlabel("Rows failed (%)")
    axes.set_title("Failing checks by share of rows")
    for index, value in enumerate(values):
        axes.text(value, index, f" {value}%", va="center", fontsize=8)
    axes.spines[["top", "right"]].set_visible(False)

    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def _missing_chart(report: QualityReport) -> Optional[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    profile = report.missing_profile
    if profile is None or profile.empty:
        return None

    data = profile[profile["Missing_Count"] > 0].head(15)
    if data.empty:
        return None

    labels = [str(v)[:45] for v in data["Column"]][::-1]
    values = list(data["Missing_Pct"])[::-1]

    figure, axes = plt.subplots(figsize=(9, max(2.2, 0.42 * len(labels))))
    axes.barh(labels, values, color="#01a982")
    axes.set_xlabel("Missing (%)")
    axes.set_title("Columns with missing values")
    for index, value in enumerate(values):
        axes.text(value, index, f" {value}%", va="center", fontsize=8)
    axes.spines[["top", "right"]].set_visible(False)

    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def _table_html(frame: Optional[pd.DataFrame], limit: Optional[int] = None) -> Optional[Markup]:
    """Render a DataFrame as escaped HTML."""
    if frame is None or frame.empty:
        return None
    view = frame.head(limit) if limit else frame
    html = view.to_html(index=False, escape=True, border=0, classes="dq-table", na_rep="")
    return Markup(html)


def build_context(
    report: QualityReport,
    df: pd.DataFrame,
    row_limit: int = DEFAULT_HTML_ROW_LIMIT,
) -> Dict[str, Any]:
    cards: List[Dict[str, Any]] = []
    for result in report.results:
        flagged = result.failed_rows(df, limit=row_limit)
        if not flagged.empty and result.derived is not None:
            flagged = flagged.copy()
            derived = result.derived.reindex(flagged.index)
            flagged[str(derived.name or "Derived")] = derived.values

        cards.append(
            {
                "rule_id": result.rule_id,
                "label": result.label,
                "dimension": result.dimension,
                "columns": result.column_label,
                "status": result.status,
                "failed_count": result.failed_count,
                "failed_pct": result.failed_pct,
                "total_rows": result.total_rows,
                "message": result.error or result.message,
                "detail_table": _table_html(result.detail_table, limit=row_limit),
                "flagged_table": _table_html(flagged),
                "flagged_truncated": result.failed_count > len(flagged),
                "shown_rows": len(flagged),
            }
        )

    return {
        "report": report,
        "cards": cards,
        "failure_chart": _failure_chart(report),
        "missing_chart": _missing_chart(report),
        "missing_table": _table_html(
            report.missing_profile[report.missing_profile["Missing_Count"] > 0]
            if report.missing_profile is not None
            else None
        ),
        "profile_table": _table_html(report.dtypes_profile),
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def write_html_report(
    report: QualityReport,
    df: pd.DataFrame,
    output_path: str | Path,
    row_limit: int = DEFAULT_HTML_ROW_LIMIT,
) -> Path:
    """Render the dashboard to a single self-contained HTML file."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml", "j2"], default_for_string=True),
    )
    template = environment.get_template("report.html.j2")
    html = template.render(**build_context(report, df, row_limit=row_limit))

    destination.write_text(html, encoding="utf-8")
    return destination
