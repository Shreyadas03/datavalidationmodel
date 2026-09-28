"""Combined report writers for hybrid Data Quality + Revenue Validation runs."""

from __future__ import annotations

import base64
import html as html_lib
import io
from pathlib import Path
from typing import Optional

import pandas as pd

from dq_platform.ai_insights import (
    HistoryStore,
    build_dashboard_summary_section_html,
    collect_dashboard_facts,
    collect_metric_snapshot,
    compare_to_previous,
    generate_dashboard_summary,
    generate_narrative,
)
from dq_platform.ai_insights.trend import build_trend_results
from dq_platform.comparison import RevenueComparisonReport
from dq_platform.models import QualityReport
from dq_platform.report import dashboard
from dq_platform.report.scoring import compute_dashboard_kpis


def _autofit(worksheet, frame: pd.DataFrame, workbook) -> None:
    wrap = workbook.add_format({"valign": "top"})
    for position, column in enumerate(frame.columns):
        values = frame[column].astype("string").fillna("")
        longest = int(values.str.len().max()) if len(values) else 0
        width = min(max(longest, len(str(column))) + 2, 55)
        worksheet.set_column(position, position, width, wrap)


def _write_frame(writer, frame: pd.DataFrame, sheet_name: str) -> None:
    frame.to_excel(writer, sheet_name=sheet_name, index=False)
    worksheet = writer.sheets[sheet_name]
    _autofit(worksheet, frame, writer.book)
    worksheet.freeze_panes(1, 0)


def write_hybrid_combined_excel(
    revenue_report: RevenueComparisonReport,
    output_path: str | Path,
    *,
    quality_report: Optional[QualityReport] = None,
    quality_error: Optional[str] = None,
) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    dq_status = "Completed" if quality_report is not None else "Not completed"
    if quality_error:
        dq_status = "Incomplete"

    with pd.ExcelWriter(destination, engine="xlsxwriter") as writer:
        _write_frame(
            writer,
            pd.DataFrame(
                [
                    {"Flow": "Data Quality", "Status": dq_status, "Details": quality_error or ""},
                    {"Flow": "Revenue Validation", "Status": "Completed", "Details": ""},
                ]
            ),
            "Overview",
        )

        if quality_report is not None:
            _write_frame(writer, quality_report.summary_frame(), "DQ_Summary")
            _write_frame(writer, quality_report.details_frame(), "DQ_Details")
            if quality_report.missing_profile is not None and not quality_report.missing_profile.empty:
                _write_frame(writer, quality_report.missing_profile, "DQ_Missing_Values")
            if quality_report.dtypes_profile is not None and not quality_report.dtypes_profile.empty:
                _write_frame(writer, quality_report.dtypes_profile, "DQ_Column_Profile")
        elif quality_error:
            _write_frame(writer, pd.DataFrame({"Issue": [quality_error]}), "DQ_Status")

        _write_frame(writer, revenue_report.summary_frame(), "Revenue_Summary")
        _write_frame(
            writer,
            pd.DataFrame(
                [
                    {
                        "Selected document type": revenue_report.zdel_document_type_value,
                        "Old revenue total for selected type": round(revenue_report.zdel_old_sum, 2),
                        "New revenue total for selected type": round(revenue_report.zdel_new_sum, 2),
                        "Revenue difference (new - old)": round(revenue_report.zdel_delta, 2),
                        "Revenue difference % of old": (
                            round(revenue_report.zdel_delta_pct, 2)
                            if revenue_report.zdel_delta_pct is not None
                            else "N/A"
                        ),
                        "Threshold %": round(revenue_report.zdel_threshold_pct, 2),
                        f"Threshold exceeded (>{round(revenue_report.zdel_threshold_pct, 2)}%)": (
                            "Yes" if revenue_report.zdel_threshold_exceeded else "No"
                        ),
                        "Message": revenue_report.zdel_threshold_message,
                    }
                ]
            ),
            "Revenue_DocType_Check",
        )
        _write_frame(
            writer,
            pd.DataFrame(
                [
                    {
                        "Renewal status value": revenue_report.renewal_status_value,
                        "Rows with selected status (old)": revenue_report.renewal_old_filtered_count,
                        "Rows missing required fields (old)": revenue_report.renewal_old_missing_count,
                        "Missing % (old)": round(revenue_report.renewal_old_missing_pct, 2),
                        "Rows with selected status (new)": revenue_report.renewal_new_filtered_count,
                        "Rows missing required fields (new)": revenue_report.renewal_new_missing_count,
                        "Missing % (new)": round(revenue_report.renewal_new_missing_pct, 2),
                        "Threshold %": round(revenue_report.renewal_threshold_pct, 2),
                        f"Threshold exceeded (>{round(revenue_report.renewal_threshold_pct, 2)}%)": (
                            "Yes" if revenue_report.renewal_threshold_exceeded else "No"
                        ),
                        "Message": revenue_report.renewal_threshold_message,
                    }
                ]
            ),
            "Revenue_Renewal_Check",
        )
        if revenue_report.invalid_rows.empty:
            _write_frame(
                writer,
                pd.DataFrame(
                    {
                        "Result": [
                            "No failures: every row with Channel profile = indirect has Tier 2 reseller."
                        ]
                    }
                ),
                "Revenue_Details",
            )
        else:
            _write_frame(writer, revenue_report.invalid_rows, "Revenue_Details")

    return destination


def _figure_to_base64(figure) -> str:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=110, bbox_inches="tight")
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _revenue_overview_chart(report: RevenueComparisonReport) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["Old", "New"]
    values = [report.old_revenue_sum, report.new_revenue_sum]
    figure, axes = plt.subplots(figsize=(6.5, 3.5))
    bars = axes.bar(labels, values, color=["#5f6b6d", "#01a982"])
    axes.set_title("Revenue totals (overall)")
    axes.set_ylabel("Revenue")
    for bar, value in zip(bars, values):
        axes.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{round(value, 2)}", ha="center", va="bottom")
    axes.spines[["top", "right"]].set_visible(False)
    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def _revenue_doc_type_chart(report: RevenueComparisonReport) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [f"Old {report.zdel_document_type_value}", f"New {report.zdel_document_type_value}", "Delta"]
    values = [report.zdel_old_sum, report.zdel_new_sum, report.zdel_delta]
    colors = ["#5f6b6d", "#01a982", "#c8102e" if report.zdel_delta < 0 else "#007a5e"]
    figure, axes = plt.subplots(figsize=(7.2, 3.8))
    bars = axes.bar(labels, values, color=colors)
    axes.set_title("Selected document type revenue comparison")
    axes.set_ylabel("Revenue")
    for bar, value in zip(bars, values):
        axes.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{round(value, 2)}", ha="center", va="bottom")
    axes.spines[["top", "right"]].set_visible(False)
    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def _renewal_threshold_chart(report: RevenueComparisonReport) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["Old missing %", "New missing %"]
    values = [report.renewal_old_missing_pct, report.renewal_new_missing_pct]
    threshold = report.renewal_threshold_pct
    colors = [
        "#c8102e" if value > threshold else "#01a982"
        for value in values
    ]
    figure, axes = plt.subplots(figsize=(6.8, 3.5))
    bars = axes.bar(labels, values, color=colors)
    axes.axhline(threshold, color="#5f6b6d", linestyle="--", linewidth=1.2, label=f"Threshold {round(threshold, 2)}%")
    axes.set_title("Renewal missing % vs threshold")
    axes.set_ylabel("Missing %")
    axes.legend(loc="upper right")
    for bar, value in zip(bars, values):
        axes.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{round(value, 2)}%", ha="center", va="bottom")
    axes.spines[["top", "right"]].set_visible(False)
    image = _figure_to_base64(figure)
    plt.close(figure)
    return image


def _revenue_doc_type_details_frame(report: RevenueComparisonReport) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Selected document type": report.zdel_document_type_value,
                "Document type column (old)": report.zdel_document_type_column_old,
                "Document type column (new)": report.zdel_document_type_column_new,
                "Revenue column (old)": report.revenue_column_old,
                "Revenue column (new)": report.revenue_column_new,
                "Old revenue total": round(report.zdel_old_sum, 2),
                "New revenue total": round(report.zdel_new_sum, 2),
                "Difference (new - old)": round(report.zdel_delta, 2),
                "Difference % of old": (
                    round(report.zdel_delta_pct, 2) if report.zdel_delta_pct is not None else "N/A"
                ),
                "Threshold %": round(report.zdel_threshold_pct, 2),
                "Threshold exceeded": "Yes" if report.zdel_threshold_exceeded else "No",
                "Message": report.zdel_threshold_message,
            }
        ]
    )


def _revenue_renewal_details_frame(report: RevenueComparisonReport) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Renewal status value": report.renewal_status_value,
                "Status column (old)": report.renewal_status_column_old,
                "Status column (new)": report.renewal_status_column_new,
                "Quote column (old)": report.renewal_quote_number_column_old,
                "Quote column (new)": report.renewal_quote_number_column_new,
                "Contract doc column (old)": report.renewal_contract_doc_number_column_old,
                "Contract doc column (new)": report.renewal_contract_doc_number_column_new,
                "Rows with selected status (old)": report.renewal_old_filtered_count,
                "Rows missing required fields (old)": report.renewal_old_missing_count,
                "Missing % (old)": round(report.renewal_old_missing_pct, 2),
                "Rows with selected status (new)": report.renewal_new_filtered_count,
                "Rows missing required fields (new)": report.renewal_new_missing_count,
                "Missing % (new)": round(report.renewal_new_missing_pct, 2),
                "Threshold %": round(report.renewal_threshold_pct, 2),
                "Threshold exceeded": "Yes" if report.renewal_threshold_exceeded else "No",
                "Message": report.renewal_threshold_message,
            }
        ]
    )


def _table_html(frame: pd.DataFrame) -> str:
    return frame.to_html(index=False, escape=True, border=0)


def write_hybrid_combined_html(
    revenue_report: RevenueComparisonReport,
    output_path: str | Path,
    *,
    quality_report: Optional[QualityReport] = None,
    quality_error: Optional[str] = None,
    quality_df: Optional[pd.DataFrame] = None,
    enable_ai_insights: bool = True,
) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    kpis = compute_dashboard_kpis(
        quality_report, revenue_report, quality_df=quality_df, quality_error=quality_error
    )

    dashboard_summary_html = ""
    if enable_ai_insights:
        history_store = HistoryStore(destination.parent / "dq_history.json")
        current_snapshot = collect_metric_snapshot(
            quality_report, revenue_report, kpis, quality_df
        )
        prior_snapshots = history_store.recent(months=3, before=current_snapshot.timestamp)
        previous_snapshot = prior_snapshots[-1] if prior_snapshots else None
        changes = compare_to_previous(current_snapshot, previous_snapshot)
        trends = build_trend_results(prior_snapshots, current_snapshot)
        narrative = generate_narrative(changes, trends, current_snapshot)
        history_store.append(current_snapshot)

        dashboard_facts = collect_dashboard_facts(quality_report, revenue_report, kpis, quality_df)
        dashboard_summary = generate_dashboard_summary(dashboard_facts)
        dashboard_summary_html = build_dashboard_summary_section_html(dashboard_summary, narrative)

    completeness_chart = dashboard.data_completeness_blank_chart(quality_df)
    date_renewal_chart = dashboard.date_renewal_consistency_chart(quality_df)
    channel_pie_chart = dashboard.sales_channel_direct_indirect_chart(quality_df)
    business_case_kpi = dashboard.business_case_kpi_card(quality_df)

    tier2_chart = dashboard.tier2_geography_chart(revenue_report)
    zdel_chart = dashboard.zdel_revenue_chart(revenue_report)
    renewal_chart_img = dashboard.renewal_chart(revenue_report)

    solutions = dashboard.recommended_solutions(quality_report, revenue_report)

    quality_status_html = (
        f"<p><b>Status:</b> Incomplete - {html_lib.escape(quality_error)}</p>"
        if quality_error
        else (
            "<p><b>Status:</b> Data Completeness Validation</p>"
            if quality_report is not None
            else "<p><b>Status:</b> Not completed</p>"
        )
    )
    revenue_invalid_html = (
        revenue_report.invalid_rows.to_html(index=False, escape=True, border=0)
        if not revenue_report.invalid_rows.empty
        else "<p>No failures found for the indirect/Tier 2 reseller rule.</p>"
    )

    kpi_row = "".join(
        [
            dashboard.kpi_card(
                "Total Test Cases",
                f"{kpis.total_test_cases} Tests",
                f"100% Checked \u2022 {kpis.total_test_cases_passed}/{kpis.total_test_cases} passed",
                tone=(
                    "good"
                    if kpis.total_test_cases and kpis.total_test_cases_passed == kpis.total_test_cases
                    else ("warn" if kpis.total_test_cases_passed else "bad")
                ),
            ),
            dashboard.kpi_card(
                "Data Quality Score",
                f"{kpis.dq_subset_passed}/{kpis.dq_subset_total}",
                "Business Case, Date & Renewal Consistency, Completeness",
                tone=(
                    "good"
                    if kpis.dq_subset_total and kpis.dq_subset_passed == kpis.dq_subset_total
                    else ("warn" if kpis.dq_subset_passed else "bad")
                ),
            ),
            dashboard.kpi_card(
                "Validation Score",
                f"{kpis.validation_subset_passed}/{kpis.validation_subset_total}",
                "Renewal Quote, ZDEL Revenue, Tier 2 Reseller",
                tone=(
                    "good"
                    if kpis.validation_subset_total
                    and kpis.validation_subset_passed == kpis.validation_subset_total
                    else ("warn" if kpis.validation_subset_passed else "bad")
                ),
            ),
            dashboard.kpi_card(
                "Critical",
                str(kpis.critical_count),
                "Checks crossing threshold - need urgent attention",
                tone="bad" if kpis.critical_count else "good",
            ),
        ]
    )

    dq_completeness_html = (
        '<h3>Blank rows by field</h3>'
        f'<div class="chart wide"><img src="{completeness_chart}" alt="Blank row count by field chart"></div>'
        if completeness_chart
        else ""
    )
    dq_pattern_html = (
        f'<div class="chart wide"><img src="{date_renewal_chart}" alt="Date and renewal consistency checks chart"></div>'
        if date_renewal_chart
        else '<p class="subtle">No date/renewal consistency checks available for this dataset.</p>'
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Data Quality Validation Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; color: #1f2933; background:#fafbfc; }}
    h1 {{ margin-bottom: 8px; }}
    h2 {{ margin-top: 32px; border-left: 4px solid #01a982; padding-left: 10px; }}
    h3 {{ margin-top: 16px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f7fa; }}
    .chart {{ max-width:100%; border:1px solid #d8dee4; border-radius:8px; padding:8px; background:#fff; margin:8px 0 14px; display:inline-block; }}
    .chart img {{ max-width:100%; }}
    .chart.wide {{ display:block; }}
    .chart-row {{ display:flex; flex-wrap:nowrap; gap:16px; align-items:flex-start; overflow-x:auto; }}
    .chart-row .chart {{ margin:8px 0; flex:0 0 auto; }}
    .subtle {{ color:#5f6b6d; }}
    .kpi-row {{ display:flex; flex-wrap:wrap; gap:14px; margin:16px 0 8px; }}
    .kpi-card {{ flex:1 1 200px; background:#fff; border:1px solid #d8dee4; border-top:4px solid #5f6b6d; border-radius:8px; padding:14px 16px; box-shadow:0 1px 3px rgba(0,0,0,0.06); }}
    .kpi-title {{ font-size:13px; color:#5f6b6d; text-transform:uppercase; letter-spacing:0.03em; }}
    .kpi-value {{ font-size:28px; font-weight:700; margin-top:4px; }}
    .kpi-sub {{ font-size:12px; color:#5f6b6d; margin-top:4px; }}
    .info-card {{ background:#fff; border:1px solid #d8dee4; border-left:5px solid #5f6b6d; border-radius:8px; padding:12px 16px; margin:10px 0; max-width:480px; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
    .info-title {{ font-weight:700; margin-bottom:6px; }}
    .info-row {{ font-size:13px; padding:2px 0; }}
    .info-label {{ color:#5f6b6d; }}
    .info-value {{ font-weight:600; }}
    .alert-banner {{ background:#fdecea; color:#8c1d18; border:1px solid #f5c6cb; border-radius:6px; padding:10px 14px; margin:8px 0; font-weight:600; }}
    .cause-list li, .solution-list li {{ margin-bottom:8px; }}
    .validation-block {{ display:flex; flex-wrap:wrap; gap:20px; align-items:flex-start; margin-bottom:12px; }}
    .dash-summary-card {{ background:#fff; border:1px solid #d8dee4; border-left:5px solid #0074c2; border-radius:8px; padding:14px 18px; margin:10px 0 16px; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
    .dash-summary-grid {{ display:flex; flex-wrap:wrap; gap:16px; margin-bottom:16px; }}
    .dash-summary-block {{ flex:1 1 260px; background:#fff; border:1px solid #d8dee4; border-top:4px solid #0074c2; border-radius:8px; padding:12px 16px; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
    .dash-summary-title {{ font-weight:700; margin-bottom:6px; color:#1f2933; }}
    .dash-summary-block ul, .dash-summary-card ul {{ margin:4px 0 0 18px; padding:0; font-size:13px; }}
    .risk-chip-row {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; }}
    .risk-chip {{ background:#fdecea; color:#8c1d18; border:1px solid #f5c6cb; border-radius:14px; padding:4px 12px; font-size:12px; font-weight:600; }}
    .risk-chip-ok {{ background:#eaf7f0; color:#0b6b3a; border:1px solid #b7e4c7; }}
  </style>
</head>
<body>
  <h1>Data Quality Validation Report</h1>
  <p class="subtle">Generated at {revenue_report.generated_at.strftime("%Y-%m-%d %H:%M:%S")}</p>

  <div class="kpi-row">
    {kpi_row}
  </div>

  <h2>1. Data Quality</h2>
  {quality_status_html}
  {dq_completeness_html}
  <h3>Date &amp; Renewal Consistency Check</h3>
  {dq_pattern_html}

  <h3>Business Case Validation</h3>
  <div class="validation-block">
    {business_case_kpi}
    {f'<div class="chart"><img src="{channel_pie_chart}" alt="Direct vs Indirect sales channel pie chart"></div>' if channel_pie_chart else '<p class="subtle">No Sales Channel Route Name data available.</p>'}
  </div>

  <h2>2. Validation</h2>
  <h3>Missing Tier 2 Reseller (Indirect Channel)</h3>
  <div class="validation-block">
    {dashboard.tier2_info_card(revenue_report)}
    {f'<div class="chart"><img src="{tier2_chart}" alt="Missing Tier 2 Reseller by geography chart"></div>' if tier2_chart else '<p class="subtle">Provide a Subregion column to see the geography breakdown.</p>'}
  </div>

  <h3>Revenue Validation ({html_lib.escape(revenue_report.zdel_document_type_value)})</h3>
  <div class="validation-block">
    {dashboard.zdel_info_card(revenue_report)}
    <div class="chart"><img src="{zdel_chart}" alt="ZDEL revenue previous vs current chart"></div>
  </div>
  {dashboard.zdel_warning_html(revenue_report)}

  <h3>Renewal Quote Check</h3>
  <div class="validation-block">
    {dashboard.renewal_info_card(revenue_report)}
    <div class="chart"><img src="{renewal_chart_img}" alt="Renewal missing percent vs threshold chart"></div>
  </div>
  {dashboard.renewal_warning_html(revenue_report)}

  {dashboard_summary_html}

  <h2>4. Recommended Solutions</h2>
  <ul class="solution-list">
    {''.join(f'<li>{solution}</li>' for solution in solutions)}
  </ul>

  <h2>5. Details</h2>
  <h3>Data Quality rule details</h3>
  {_table_html(quality_report.details_frame()) if quality_report is not None else '<p class="subtle">No Data Quality rule details available.</p>'}
  <h3>Revenue document type threshold details</h3>
  {_table_html(_revenue_doc_type_details_frame(revenue_report))}
  <h3>Revenue renewal completeness details</h3>
  {_table_html(_revenue_renewal_details_frame(revenue_report))}
  <h3>Revenue indirect Tier 2 details</h3>
  {revenue_invalid_html}
</body>
</html>"""

    destination.write_text(html, encoding="utf-8")
    return destination
