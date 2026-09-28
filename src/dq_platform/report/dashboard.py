"""Chart and card builders for the redesigned Hybrid Validation dashboard.

Used exclusively by :mod:`dq_platform.report.hybrid` to render the combined
static HTML report. Charts stay matplotlib PNGs embedded as base64, matching
the rest of the codebase (no JS charting dependency, single self-contained
HTML file).
"""

from __future__ import annotations

import base64
import html as html_lib
import io
import re
from typing import Optional

import pandas as pd

from dq_platform.comparison import RevenueComparisonReport
from dq_platform.io_utils import profile_dtypes
from dq_platform.models import QualityReport

# Shared palette (matches existing report/html.py & report/hybrid.py charts).
GREEN = "#01a982"
RED = "#c8102e"
GREY = "#5f6b6d"
WARN_BROWN = "#8c4223"
ERROR_RED = "#b00020"
NEUTRAL_BG = "#f5f7fa"
NEUTRAL_BORDER = "#d8dee4"


def _figure_to_base64(figure) -> str:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=110, bbox_inches="tight")
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


# --------------------------------------------------------------------------
# Donut charts (Data Quality: completeness & uniqueness)
# --------------------------------------------------------------------------

def _donut_chart(title: str, pct_filled: float, color: str) -> str:
    plt = _mpl()
    pct_filled = max(0.0, min(100.0, pct_filled))
    figure, axes = plt.subplots(figsize=(3.4, 3.4))
    values = [pct_filled, 100 - pct_filled]
    axes.pie(
        values,
        colors=[color, NEUTRAL_BG],
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.38, edgecolor="white"),
    )
    axes.text(0, 0, f"{round(pct_filled, 1)}%", ha="center", va="center", fontsize=18, fontweight="bold")
    axes.set_title(title, fontsize=11)
    axes.set_aspect("equal")
    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


_START_DATE_CANDIDATES = ["Hdr Start Date", "Header Start Date", "Start Date"]
_END_DATE_CANDIDATES = ["Hdr End Date", "Header End Date", "End Date"]
_SALES_DOC_CANDIDATES = ["Sales Doc Nbr", "Sales Document", "Sales Doc Number", "Sales Doc"]
_RENEWAL_DATE_CANDIDATES = ["Renewal Date"]
_RENEWAL_MONTH_CANDIDATES = ["Renewal Month"]
_RENEWAL_QUARTER_CANDIDATES = ["Renewal Quarter"]
_RENEWAL_FISCAL_YEAR_CANDIDATES = ["Renewal Fiscal Year"]
_MONTHS_DURATION_CANDIDATES = ["Months Duration"]
_MULTIYEAR_FLAG_CANDIDATES = ["Multiyear Flag"]
_DATA_COMPLETENESS_FIELDS = [
    "GEOGRAPHY",
    "SUBGEO1",
    "SUBGEO2",
    "SUBGEO3",
    "SUBGEO4",
    "ISO Country Code",
    "Country Name",
    "Sales Organization",
    "Expiring Contract AMP ID",
    "Functional Location",
]


def _find_column(df: pd.DataFrame, candidates: list) -> Optional[str]:
    """Find the first matching column name (case-insensitive) from a candidate list."""
    lookup = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        match = lookup.get(candidate.strip().lower())
        if match is not None:
            return match
    return None


def _completeness_pct(df: pd.DataFrame, candidates: list) -> Optional[tuple]:
    column = _find_column(df, candidates)
    if column is None:
        return None
    series = df[column]
    if len(series) == 0:
        return None
    completeness_pct = max(0.0, 100 - (series.isna().mean() * 100))
    return column, completeness_pct


def start_date_donut(df: Optional[pd.DataFrame]) -> Optional[str]:
    """Non-missing % for the Start Date column."""
    if df is None or df.empty:
        return None
    result = _completeness_pct(df, _START_DATE_CANDIDATES)
    if result is None:
        return None
    _, completeness_pct = result
    return _donut_chart("Completeness (Start Date)", completeness_pct, GREEN)


def end_date_donut(df: Optional[pd.DataFrame]) -> Optional[str]:
    """Non-missing % for the End Date column."""
    if df is None or df.empty:
        return None
    result = _completeness_pct(df, _END_DATE_CANDIDATES)
    if result is None:
        return None
    _, completeness_pct = result
    return _donut_chart("Completeness (End Date)", completeness_pct, "#01a982")


def uniqueness_donut(df: Optional[pd.DataFrame]) -> Optional[str]:
    """Unique-value % for the Sales Doc Nbr column specifically. Hidden if column not found."""
    if df is None or df.empty:
        return None
    column = _find_column(df, _SALES_DOC_CANDIDATES)
    if column is None:
        return None
    series = df[column].dropna()
    if len(series) == 0:
        return None
    uniqueness_pct = max(0.0, (series.nunique() / len(series)) * 100)
    return _donut_chart("Uniqueness (Sales Doc Nbr)", uniqueness_pct, "#0b5fff")


def _data_completeness_blank_counts(df: Optional[pd.DataFrame]) -> list[tuple[str, float]]:
    """Blank-row percentage (blank_count / total_rows * 100) per configured field."""
    if df is None or df.empty:
        return []

    total_rows = len(df)
    counts = []
    for field in _DATA_COMPLETENESS_FIELDS:
        column = _find_column(df, [field])
        if column is None:
            continue
        series = df[column]
        blank_count = int((series.isna() | (series.astype(str).str.strip() == "")).sum())
        blank_pct = round((blank_count / total_rows) * 100, 2) if total_rows else 0.0
        counts.append((field, blank_pct))
    return counts


def data_completeness_blank_chart(df: Optional[pd.DataFrame]) -> Optional[str]:
    """Blank-row percentage for selected business fields, hidden when every value is zero."""
    counts = _data_completeness_blank_counts(df)
    if not counts:
        return None

    labels = [label for label, _ in counts][::-1]
    values = [value for _, value in counts][::-1]

    plt = _mpl()
    figure, axes = plt.subplots(figsize=(9, max(3.0, 0.5 * len(labels))))
    bars = axes.barh(labels, values, color=GREEN)
    axes.set_xlabel("Blank Row %")
    axes.set_title("Blank rows by field")
    for bar, value in zip(bars, values):
        axes.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f" {value:.2f}%",
            va="center",
            fontsize=9,
            fontweight="bold",
        )
    axes.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


# --------------------------------------------------------------------------
# Datatype pattern-match table (Data Quality "others")
# --------------------------------------------------------------------------

_DATE_PATTERN_HINTS = re.compile(r"date|dt$|_dt|time", re.IGNORECASE)


def _detect_pattern(series: pd.Series, column_name: str) -> str:
    """Heuristically infer the expected semantic pattern of a column."""
    non_null = series.dropna()
    if non_null.empty:
        return "Unknown"

    sample = non_null.astype(str).str.strip()
    sample = sample[sample != ""]
    if sample.empty:
        return "Unknown"

    numeric_ratio = pd.to_numeric(sample, errors="coerce").notna().mean()
    if numeric_ratio >= 0.9:
        return "Numeric"

    date_ratio = pd.to_datetime(sample, errors="coerce", format="mixed", utc=True).notna().mean()
    if date_ratio >= 0.5 or _DATE_PATTERN_HINTS.search(str(column_name)):
        if date_ratio >= 0.5:
            return "Date"

    return "Text"


def datatype_pattern_table(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Column, detected pattern, actual dtype, and whether they agree."""
    if df is None or df.empty:
        return None

    dtypes = profile_dtypes(df)
    rows = []
    for column in df.columns:
        detected = _detect_pattern(df[column], column)
        actual_dtype = str(df[column].dtype)
        is_numeric_dtype = actual_dtype.startswith(("int", "float", "uint"))
        is_datetime_dtype = actual_dtype.startswith("datetime")
        if detected == "Numeric":
            match = is_numeric_dtype
        elif detected == "Date":
            match = is_datetime_dtype
        elif detected == "Text":
            match = not is_numeric_dtype and not is_datetime_dtype
        else:
            match = True
        rows.append(
            {
                "Column": column,
                "Detected Pattern": detected,
                "Actual Dtype": actual_dtype,
                "Match": "Yes" if match else "No",
            }
        )
    result = pd.DataFrame(rows)
    return result.merge(dtypes[["Column", "Null Count"]], on="Column", how="left")


# --------------------------------------------------------------------------
# Missing-by-column bar chart (Data Quality) - thin wrapper re-using html.py
# --------------------------------------------------------------------------

def missing_by_column_chart(report: Optional[QualityReport]) -> Optional[str]:
    from dq_platform.report.html import _missing_chart

    if report is None:
        return None
    return _missing_chart(report)


# --------------------------------------------------------------------------
# Validation-checks failed-record-count bar chart (Data Quality)
# --------------------------------------------------------------------------

_SALES_CHANNEL_ROUTE_CANDIDATES = ["Sales Channel Route Name", "Sales Channel Route", "Channel Route Name"]


def _date_consistency_failed_count(df: pd.DataFrame) -> int:
    """Rows where End Date is before Start Date (both present/parseable)."""
    start_col = _find_column(df, _START_DATE_CANDIDATES)
    end_col = _find_column(df, _END_DATE_CANDIDATES)
    if start_col is None or end_col is None:
        return 0
    start = pd.to_datetime(df[start_col], errors="coerce", utc=True)
    end = pd.to_datetime(df[end_col], errors="coerce", utc=True)
    both_present = start.notna() & end.notna()
    invalid = (end < start) & both_present
    return int(invalid.fillna(False).sum())


def _hygiene_datatype_failed_count(df: pd.DataFrame) -> int:
    """Total cell-level values across all columns that don't match their detected pattern."""
    total = 0
    for column in df.columns:
        series = df[column]
        detected = _detect_pattern(series, column)
        non_null = series.dropna().astype(str).str.strip()
        non_null = non_null[non_null != ""]
        if non_null.empty:
            continue
        if detected == "Numeric":
            total += int(pd.to_numeric(non_null, errors="coerce").isna().sum())
        elif detected == "Date":
            total += int(pd.to_datetime(non_null, errors="coerce", format="mixed", utc=True).isna().sum())
        # Text/Unknown: no per-cell mismatch counted (matches by definition).
    return total


def _uniqueness_duplicate_row_count(df: pd.DataFrame) -> int:
    """Rows that are exact full-row duplicates of another row."""
    return int(df.duplicated(keep=False).sum())


def _start_after_end_check(df: pd.DataFrame) -> tuple[int, int]:
    """(non-blank Start Date count, rows where Start Date > End Date)."""
    start_col = _find_column(df, _START_DATE_CANDIDATES)
    end_col = _find_column(df, _END_DATE_CANDIDATES)
    if start_col is None:
        return 0, 0
    start = pd.to_datetime(df[start_col], errors="coerce", utc=True)
    total = int(start.notna().sum())
    if end_col is None:
        return total, 0
    end = pd.to_datetime(df[end_col], errors="coerce", utc=True)
    both_present = start.notna() & end.notna()
    invalid = (start > end) & both_present
    return total, int(invalid.fillna(False).sum())


def _end_plus_one_renewal_check(df: pd.DataFrame) -> tuple[int, int]:
    """(non-blank End Date count, rows where End Date + 1 day != Renewal Date)."""
    end_col = _find_column(df, _END_DATE_CANDIDATES)
    renewal_col = _find_column(df, _RENEWAL_DATE_CANDIDATES)
    if end_col is None:
        return 0, 0
    end = pd.to_datetime(df[end_col], errors="coerce", utc=True).dt.normalize()
    total = int(end.notna().sum())
    if renewal_col is None:
        return total, 0
    renewal = pd.to_datetime(df[renewal_col], errors="coerce", utc=True).dt.normalize()
    both_present = end.notna() & renewal.notna()
    mismatch = (end + pd.Timedelta(days=1) != renewal) & both_present
    return total, int(mismatch.fillna(False).sum())


def _column_blank_check(df: pd.DataFrame, candidates: list) -> Optional[tuple[int, int]]:
    """(total row count, blank/missing row count) for a column, or None if not found."""
    column = _find_column(df, candidates)
    if column is None:
        return None
    series = df[column]
    blank_count = int((series.isna() | (series.astype(str).str.strip() == "")).sum())
    return len(df), blank_count


def date_renewal_consistency_chart(df: Optional[pd.DataFrame]) -> Optional[str]:
    """Bar chart of failed-row percentage for date-order and renewal-completeness checks."""
    if df is None or df.empty:
        return None

    checks: list[tuple[str, int, int]] = []

    if _find_column(df, _START_DATE_CANDIDATES) is not None:
        total, failed = _start_after_end_check(df)
        checks.append(("Start Date >\nEnd Date", total, failed))

    if _find_column(df, _END_DATE_CANDIDATES) is not None:
        total, failed = _end_plus_one_renewal_check(df)
        checks.append(("End Date+1 !=\nRenewal Date", total, failed))

    for label, candidates in (
        ("Renewal Month\n(Blank)", _RENEWAL_MONTH_CANDIDATES),
        ("Renewal Quarter\n(Blank)", _RENEWAL_QUARTER_CANDIDATES),
        ("Renewal Fiscal Year\n(Blank)", _RENEWAL_FISCAL_YEAR_CANDIDATES),
    ):
        result = _column_blank_check(df, candidates)
        if result is None:
            continue
        total, failed = result
        checks.append((label, total, failed))

    if not checks:
        return None

    import numpy as np

    labels = [label for label, _, _ in checks]
    percentages = [round((failed / total) * 100, 2) if total else 0.0 for _, total, failed in checks]
    x = np.arange(len(labels))

    plt = _mpl()
    figure, axes = plt.subplots(figsize=(max(8.5, 2.3 * len(labels)), 4.8))
    bars = axes.bar(x, percentages, width=0.5, label="Result (Failed %)", color=RED)
    axes.set_xticks(x)
    axes.set_xticklabels(labels, fontsize=9)
    axes.set_ylabel("Failed Row %")
    axes.set_title("Date & Renewal Consistency Checks")
    axes.legend(loc="upper right", fontsize=8)
    for bar in bars:
        axes.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{bar.get_height():.2f}%",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )
    axes.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def _sales_channel_route_blank_count(df: pd.DataFrame) -> int:
    """Rows where Sales Channel Route Name is blank/null."""
    column = _find_column(df, _SALES_CHANNEL_ROUTE_CANDIDATES)
    if column is None:
        return 0
    series = df[column]
    blank = series.isna() | (series.astype(str).str.strip() == "")
    return int(blank.sum())


# --------------------------------------------------------------------------
# Business Case Validation: Direct/Indirect pie chart + Multiyear Flag KPI
# --------------------------------------------------------------------------

def sales_channel_direct_indirect_chart(df: Optional[pd.DataFrame]) -> Optional[str]:
    """Pie chart of Direct vs Indirect counts from Sales Channel Route Name."""
    if df is None or df.empty:
        return None
    column = _find_column(df, _SALES_CHANNEL_ROUTE_CANDIDATES)
    if column is None:
        return None

    channel_text = df[column].astype("string").str.strip().str.upper()
    direct_count = int(channel_text.eq("DIRECT").fillna(False).sum())
    indirect_count = int(channel_text.eq("INDIRECT").fillna(False).sum())
    if direct_count == 0 and indirect_count == 0:
        return None

    plt = _mpl()
    figure, axes = plt.subplots(figsize=(5.2, 5.2))
    axes.pie(
        [direct_count, indirect_count],
        labels=[f"Direct ({direct_count})", f"Indirect ({indirect_count})"],
        colors=[GREEN, RED],
        autopct="%1.1f%%",
        startangle=90,
        counterclock=False,
        wedgeprops=dict(edgecolor="white"),
    )
    axes.set_title("Sales Channel Route Name: Direct vs Indirect")
    axes.set_aspect("equal")
    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def _multiyear_flag_violation_count(df: Optional[pd.DataFrame]) -> Optional[int]:
    """Rows where Months Duration > 12 but Multiyear Flag is not 'X'. None if columns missing."""
    if df is None or df.empty:
        return None
    duration_col = _find_column(df, _MONTHS_DURATION_CANDIDATES)
    flag_col = _find_column(df, _MULTIYEAR_FLAG_CANDIDATES)
    if duration_col is None or flag_col is None:
        return None

    duration = pd.to_numeric(df[duration_col], errors="coerce")
    flag = df[flag_col].astype("string").str.strip().str.upper()
    violation = (duration > 12) & (flag != "X")
    return int(violation.fillna(False).sum())


def business_case_kpi_card(df: Optional[pd.DataFrame]) -> str:
    """Info card for the Months Duration > 12 -> Multiyear Flag = X business rule."""
    violation_count = _multiyear_flag_violation_count(df)
    if violation_count is None:
        return info_card(
            "Multiyear Flag Check",
            {"Months Duration / Multiyear Flag": "N/A - column(s) not found"},
            tone="neutral",
        )
    return info_card(
        "Multiyear Flag Check",
        {"Months Duration > 12, Multiyear Flag = 'X'": f"Unmatched = {violation_count}"},
        tone="good" if violation_count == 0 else "bad",
    )


def validation_checks_bar_chart(df: Optional[pd.DataFrame]) -> Optional[str]:
    """Bar chart: X=Validation Check Name, Y=Failed Record Count, across 4 checks."""
    if df is None or df.empty:
        return None

    checks = [
        ("Date\nConsistency", _date_consistency_failed_count(df)),
        ("Hygiene\n(Datatype)", _hygiene_datatype_failed_count(df)),
        ("Uniqueness\n(Duplicate Rows)", _uniqueness_duplicate_row_count(df)),
        ("Sales Channel\nRoute Name\n(Blank/Null)", _sales_channel_route_blank_count(df)),
    ]
    names = [name for name, _ in checks]
    counts = [count for _, count in checks]

    plt = _mpl()
    figure, axes = plt.subplots(figsize=(8.5, 4.5))
    bars = axes.bar(names, counts, color=[RED, WARN_BROWN, "#0b5fff", GREEN], width=0.55)
    axes.set_xlabel("Validation Check Name")
    axes.set_ylabel("Failed Record Count")
    axes.set_title("Validation checks - failed record count")
    for bar, count in zip(bars, counts):
        axes.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(count),
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
    plt.setp(axes.get_xticklabels(), rotation=0, ha="center", fontsize=9)
    figure.tight_layout()
    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


# --------------------------------------------------------------------------
# KPI / info card HTML builders
# --------------------------------------------------------------------------

def _tone_color(tone: str) -> str:
    return {
        "good": GREEN,
        "bad": RED,
        "warn": WARN_BROWN,
        "neutral": GREY,
    }.get(tone, GREY)


def kpi_card(title: str, value: str, subtitle: str = "", tone: str = "neutral") -> str:
    color = _tone_color(tone)
    subtitle_html = f'<div class="kpi-sub">{html_lib.escape(subtitle)}</div>' if subtitle else ""
    return f"""<div class="kpi-card" style="border-top-color:{color}">
  <div class="kpi-title">{html_lib.escape(title)}</div>
  <div class="kpi-value" style="color:{color}">{html_lib.escape(str(value))}</div>
  {subtitle_html}
</div>"""


def info_card(title: str, rows: dict, tone: str = "neutral") -> str:
    color = _tone_color(tone)
    row_html = "".join(
        f'<div class="info-row"><span class="info-label">{html_lib.escape(str(label))}:</span> '
        f'<span class="info-value">{html_lib.escape(str(value))}</span></div>'
        for label, value in rows.items()
    )
    return f"""<div class="info-card" style="border-left-color:{color}">
  <div class="info-title">{html_lib.escape(title)}</div>
  {row_html}
</div>"""


# --------------------------------------------------------------------------
# Validation section: Tier 2 Reseller geography chart
# --------------------------------------------------------------------------

def tier2_geography_chart(report: RevenueComparisonReport) -> Optional[str]:
    if report.tier2_missing_by_geography is None or report.tier2_missing_by_geography.empty:
        return None

    plt = _mpl()
    data = report.tier2_missing_by_geography.head(15)
    labels = [str(v)[:35] for v in data["Geography"]][::-1]
    values = list(data["Missing Count"])[::-1]

    figure, axes = plt.subplots(figsize=(7.5, max(2.2, 0.42 * len(labels))))
    axes.barh(labels, values, color=RED)
    axes.set_xlabel("Missing Tier 2 Reseller (rows)")
    axes.set_title("Missing Tier 2 Reseller by geography")
    for index, value in enumerate(values):
        axes.text(value, index, f" {value}", va="center", fontsize=8)
    axes.spines[["top", "right"]].set_visible(False)

    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def tier2_severity_tone(severity: str) -> str:
    return {"High": "bad", "Medium": "warn", "Low": "good"}.get(severity, "neutral")


def tier2_info_card(report: RevenueComparisonReport) -> str:
    impact_pct = (
        f"{round(report.tier2_impact_revenue_pct, 2)}%"
        if report.tier2_impact_revenue_pct is not None
        else "N/A"
    )
    rows = {
        "Failed Records": report.indirect_missing_tier2_count,
        "Missing %": f"{round(report.tier2_missing_pct, 2)}%",
        "Impact Revenue (delta %)": impact_pct,
        "Top Geography": report.tier2_top_geography or "N/A",
        "Severity": report.tier2_severity,
    }
    return info_card(
        "Missing Tier 2 Reseller (Indirect Channel)",
        rows,
        tone=tier2_severity_tone(report.tier2_severity),
    )


# --------------------------------------------------------------------------
# Validation section: ZDEL revenue threshold card/chart
# --------------------------------------------------------------------------

def zdel_severity(report: RevenueComparisonReport) -> str:
    if not report.zdel_threshold_exceeded:
        return "Low"
    delta_pct = report.zdel_delta_pct or 0.0
    if delta_pct > report.zdel_threshold_pct * 2:
        return "High"
    return "Medium"


def _format_revenue_millions(value: Optional[float]) -> str:
    """Format a raw revenue amount in millions, e.g. 255567484.68 -> '255.57M'."""
    if value is None:
        return "N/A"
    return f"{value / 1_000_000:.2f}M"


def zdel_info_card(report: RevenueComparisonReport) -> str:
    delta_pct = (
        f"{round(report.zdel_delta_pct, 2)}%" if report.zdel_delta_pct is not None else "N/A"
    )
    severity = zdel_severity(report)
    rows = {
        "Current Revenue": _format_revenue_millions(report.zdel_new_sum),
        "Previous Revenue": _format_revenue_millions(report.zdel_old_sum),
        "Difference %": delta_pct,
        "Threshold": f"{round(report.zdel_threshold_pct, 2)}%",
        "Severity": severity,
    }
    tone = "bad" if severity == "High" else ("warn" if severity == "Medium" else "good")
    return info_card(f"Revenue Threshold Check ({report.zdel_document_type_value})", rows, tone=tone)


def zdel_revenue_chart(report: RevenueComparisonReport) -> str:
    plt = _mpl()
    labels = ["Previous", "Current"]
    values = [report.zdel_old_sum, report.zdel_new_sum]
    colors = [GREY, RED if report.zdel_threshold_exceeded else GREEN]

    figure, axes = plt.subplots(figsize=(6.8, 3.8))
    bars = axes.bar(labels, values, color=colors, width=0.5)
    threshold_line = report.zdel_old_sum * (1 + report.zdel_threshold_pct / 100)
    axes.axhline(
        threshold_line,
        color=GREY,
        linestyle="--",
        linewidth=1.2,
        label=f"Threshold (+{round(report.zdel_threshold_pct, 2)}%)",
    )
    axes.set_title(f"{report.zdel_document_type_value} revenue: previous vs current")
    axes.set_ylabel("Revenue")
    axes.legend(loc="upper left", fontsize=8)
    for bar, value in zip(bars, values):
        axes.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            _format_revenue_millions(value),
            ha="center",
            va="bottom",
        )
    axes.spines[["top", "right"]].set_visible(False)

    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def zdel_warning_html(report: RevenueComparisonReport) -> str:
    if not report.zdel_threshold_exceeded:
        return ""
    return (
        f'<div class="alert-banner">⚠ Threshold crossed: '
        f'{html_lib.escape(report.zdel_threshold_message)} — issue needs to be checked.</div>'
    )


# --------------------------------------------------------------------------
# Validation section: Renewal status card/chart
# --------------------------------------------------------------------------

def renewal_severity(report: RevenueComparisonReport) -> str:
    if not report.renewal_threshold_exceeded:
        return "Low"
    worst = max(report.renewal_old_missing_pct, report.renewal_new_missing_pct)
    if worst > report.renewal_threshold_pct * 2:
        return "High"
    return "Medium"


def renewal_info_card(report: RevenueComparisonReport) -> str:
    severity = renewal_severity(report)
    rows = {
        "Old Missing %": f"{round(report.renewal_old_missing_pct, 2)}%",
        "New Missing %": f"{round(report.renewal_new_missing_pct, 2)}%",
        "Threshold": f"{round(report.renewal_threshold_pct, 2)}%",
        "Severity": severity,
    }
    tone = "bad" if severity == "High" else ("warn" if severity == "Medium" else "good")
    return info_card("Renewal Quote Completeness Check", rows, tone=tone)


def renewal_chart(report: RevenueComparisonReport) -> str:
    plt = _mpl()
    labels = ["Old missing %", "New missing %"]
    values = [report.renewal_old_missing_pct, report.renewal_new_missing_pct]
    threshold = report.renewal_threshold_pct
    colors = [RED if value > threshold else GREEN for value in values]

    figure, axes = plt.subplots(figsize=(6.8, 3.5))
    bars = axes.bar(labels, values, color=colors, width=0.5)
    axes.axhline(threshold, color=GREY, linestyle="--", linewidth=1.2, label=f"Threshold {round(threshold, 2)}%")
    axes.set_title("Renewal Quote/Contract missing % vs threshold")
    axes.set_ylabel("Missing %")
    axes.legend(loc="upper right", fontsize=8)
    for bar, value in zip(bars, values):
        axes.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{round(value, 2)}%", ha="center", va="bottom")
    axes.spines[["top", "right"]].set_visible(False)

    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def renewal_warning_html(report: RevenueComparisonReport) -> str:
    if not report.renewal_threshold_exceeded:
        return ""
    return (
        f'<div class="alert-banner">⚠ Threshold crossed: '
        f'{html_lib.escape(report.renewal_threshold_message)} — issue needs to be checked.</div>'
    )


# --------------------------------------------------------------------------
# Root cause & recommended solutions
# --------------------------------------------------------------------------

_PCT_PATTERN = re.compile(r"\s*\(?\d+(?:\.\d+)?%\)?")


def _strip_pct(text: str) -> str:
    """Remove percentage figures (e.g. "12.3%" or "(12.3%)") from a message,
    tidying up any leftover double spaces/punctuation left behind."""
    cleaned = _PCT_PATTERN.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip()


def root_causes(
    quality_report: Optional[QualityReport],
    revenue_report: RevenueComparisonReport,
) -> list[str]:
    causes: list[str] = []

    if quality_report is not None:
        failing = [r for r in quality_report.results if r.status == "FAIL"]
        for result in sorted(failing, key=lambda r: r.failed_pct, reverse=True)[:5]:
            causes.append(
                f"<b>{html_lib.escape(result.label)}</b> ({html_lib.escape(result.column_label)}): "
                f"{result.failed_count} rows failed — {html_lib.escape(_strip_pct(result.message))}"
            )
        for result in quality_report.results:
            if result.status == "ERROR":
                causes.append(
                    f"<b>{html_lib.escape(result.label)}</b> could not run: {html_lib.escape(result.error or '')}"
                )

    if revenue_report.indirect_missing_tier2_count:
        top_geo = (
            f" concentrated in {html_lib.escape(revenue_report.tier2_top_geography)}"
            if revenue_report.tier2_top_geography
            else ""
        )
        causes.append(
            f"<b>Missing Tier 2 Reseller:</b> {revenue_report.indirect_missing_tier2_count} of "
            f"{revenue_report.indirect_row_count} indirect-channel rows have no Tier 2 Reseller Id"
            f"{top_geo}, likely a data-entry gap at order creation for indirect deals."
        )

    if revenue_report.zdel_threshold_exceeded:
        causes.append(
            f"<b>{html_lib.escape(revenue_report.zdel_document_type_value)} revenue swing:</b> "
            f"{html_lib.escape(_strip_pct(revenue_report.zdel_threshold_message))} — "
            "likely driven by volume changes, late postings, or reclassifications between periods."
        )

    if revenue_report.renewal_threshold_exceeded:
        causes.append(
            f"<b>Renewal completeness:</b> exceeds the allowed threshold — "
            f"old: {revenue_report.renewal_old_missing_count} of "
            f"{revenue_report.renewal_old_filtered_count} rows missing, "
            f"new: {revenue_report.renewal_new_missing_count} of "
            f"{revenue_report.renewal_new_filtered_count} rows missing — "
            "likely renewal quotes/contracts not yet linked at time of extract, or missing entry during "
            "renewal processing."
        )

    if not causes:
        causes.append("No failing checks or threshold breaches detected in this run.")

    return causes


def recommended_solutions(
    quality_report: Optional[QualityReport],
    revenue_report: RevenueComparisonReport,
) -> list[str]:
    solutions: list[str] = []

    if quality_report is not None and quality_report.failed_checks:
        solutions.append(
            "Review and correct the flagged rows for each failing Data Quality check, then re-run "
            "validation; consider adding upstream field-level validation to prevent recurrence."
        )
    if quality_report is not None and quality_report.errored_checks:
        solutions.append(
            "Investigate errored checks (missing columns / bad configuration) and re-run once corrected."
        )

    if revenue_report.indirect_missing_tier2_count:
        top_geo = (
            f" starting with {html_lib.escape(revenue_report.tier2_top_geography)}"
            if revenue_report.tier2_top_geography
            else ""
        )
        solutions.append(
            f"Enforce a mandatory Tier 2 Reseller Id field for indirect-channel orders at entry"
            f"{top_geo}; backfill the {revenue_report.indirect_missing_tier2_count} flagged rows with "
            "the sales/partner team."
        )

    if revenue_report.zdel_threshold_exceeded:
        solutions.append(
            f"Reconcile the {html_lib.escape(revenue_report.zdel_document_type_value)} revenue delta with "
            "finance/billing to confirm whether the change is expected (volume/price) or an error "
            "(duplicate postings, wrong document type mapping)."
        )

    if revenue_report.renewal_threshold_exceeded:
        solutions.append(
            "Follow up with the renewals team to close out quotes/contracts missing a Renewal Quote Nbr "
            "or Renewal Contract Doc Nbr before the next extract, and tighten the renewal workflow to "
            "require these fields at status change."
        )

    if not solutions:
        solutions.append("No action required — all checks passed within thresholds.")

    return solutions
