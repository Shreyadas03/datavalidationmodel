"""Excel/HTML writers for the two-workbook revenue comparison report."""

from __future__ import annotations

import html as html_lib
from pathlib import Path
from typing import Optional

import pandas as pd

from dq_platform.comparison import RevenueComparisonReport


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


def write_revenue_comparison_excel(
    report: RevenueComparisonReport,
    output_path: str | Path,
) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(destination, engine="xlsxwriter") as writer:
        _write_frame(writer, report.summary_frame(), "Summary")
        _write_frame(
            writer,
            pd.DataFrame(
                [
                    {
                        "ZDEL check applied": "Yes" if report.zdel_check_applied else "No",
                        "Selected document type": report.zdel_document_type_value,
                        "Old revenue total for selected type": round(report.zdel_old_sum, 2),
                        "New revenue total for selected type": round(report.zdel_new_sum, 2),
                        "Revenue difference (new - old)": round(report.zdel_delta, 2),
                        "Revenue difference % of old": (
                            round(report.zdel_delta_pct, 2)
                            if report.zdel_delta_pct is not None
                            else "N/A"
                        ),
                        f"Threshold exceeded (>{round(report.zdel_threshold_pct, 2)}%)": (
                            "Yes" if report.zdel_threshold_exceeded else "No"
                        ),
                        "Document type column (old)": report.zdel_document_type_column_old,
                        "Document type column (new)": report.zdel_document_type_column_new,
                        "Revenue column (old)": report.revenue_column_old,
                        "Revenue column (new)": report.revenue_column_new,
                        "Threshold %": round(report.zdel_threshold_pct, 2),
                        "Threshold message": report.zdel_threshold_message,
                    }
                ]
            ),
            "ZDEL_Check",
        )
        _write_frame(
            writer,
            pd.DataFrame(
                [
                    {
                        "Renewal status value": report.renewal_status_value,
                        "Renewal status column (old)": report.renewal_status_column_old,
                        "Renewal status column (new)": report.renewal_status_column_new,
                        "Renewal quote nbr column (old)": report.renewal_quote_number_column_old,
                        "Renewal quote nbr column (new)": report.renewal_quote_number_column_new,
                        "Renewal contract doc nbr column (old)": report.renewal_contract_doc_number_column_old,
                        "Renewal contract doc nbr column (new)": report.renewal_contract_doc_number_column_new,
                        "Rows with selected status (old)": report.renewal_old_filtered_count,
                        "Rows missing required fields (old)": report.renewal_old_missing_count,
                        "Missing % (old)": round(report.renewal_old_missing_pct, 2),
                        "Rows with selected status (new)": report.renewal_new_filtered_count,
                        "Rows missing required fields (new)": report.renewal_new_missing_count,
                        "Missing % (new)": round(report.renewal_new_missing_pct, 2),
                        "Threshold %": round(report.renewal_threshold_pct, 2),
                        f"Threshold exceeded (>{round(report.renewal_threshold_pct, 2)}%)": (
                            "Yes" if report.renewal_threshold_exceeded else "No"
                        ),
                        "Threshold message": report.renewal_threshold_message,
                    }
                ]
            ),
            "Renewal_Check",
        )
        if report.invalid_rows.empty:
            _write_frame(
                writer,
                pd.DataFrame(
                    {
                        "Result": [
                            "No failures: every row with Channel profile = indirect has Tier 2 reseller."
                        ]
                    }
                ),
                "Indirect_Tier2_Check",
            )
        else:
            _write_frame(writer, report.invalid_rows, "Indirect_Tier2_Check")

    return destination


def write_revenue_comparison_html(
    report: RevenueComparisonReport,
    output_path: str | Path,
    row_limit: Optional[int] = 200,
) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    invalid = report.invalid_rows.head(row_limit) if row_limit is not None else report.invalid_rows
    invalid_html = (
        invalid.to_html(index=False, escape=True, border=0)
        if not invalid.empty
        else "<p>No failures found for the indirect/Tier 2 reseller rule.</p>"
    )
    truncated_note = (
        f"<p><i>Showing first {len(invalid)} of {len(report.invalid_rows)} failing rows.</i></p>"
        if row_limit is not None and len(report.invalid_rows) > len(invalid)
        else ""
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Revenue Validation Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; color: #1f2933; }}
    h1 {{ margin-bottom: 8px; }}
    h2 {{ margin-top: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f7fa; }}
  </style>
</head>
<body>
  <h1>Revenue Validation Report</h1>
  <h2>Summary</h2>
  {report.summary_frame().to_html(index=False, escape=True, border=0)}
  <h2>Document Type Revenue Threshold Check</h2>
  <p><b>Check applied:</b> {"Yes" if report.zdel_check_applied else "No"}</p>
  <p><b>Selected document type:</b> {html_lib.escape(report.zdel_document_type_value)}</p>
  <p><b>Old revenue total:</b> {round(report.zdel_old_sum, 2)} &nbsp;&middot;&nbsp;
     <b>New revenue total:</b> {round(report.zdel_new_sum, 2)} &nbsp;&middot;&nbsp;
     <b>Difference:</b> {round(report.zdel_delta, 2)}</p>
  <p><b>Document type column (old/new):</b> {html_lib.escape(report.zdel_document_type_column_old)} / {html_lib.escape(report.zdel_document_type_column_new)}</p>
  <p><b>Revenue column (old/new):</b> {html_lib.escape(report.revenue_column_old)} / {html_lib.escape(report.revenue_column_new)}</p>
  <p><b>Threshold %:</b> {round(report.zdel_threshold_pct, 2)}</p>
  <p><b>Difference % of old:</b> {round(report.zdel_delta_pct, 2) if report.zdel_delta_pct is not None else "N/A"}</p>
  <p><b>Threshold check (&gt; {round(report.zdel_threshold_pct, 2)}%):</b> {"Exceeded" if report.zdel_threshold_exceeded else "Within limit"}</p>
  <p><b>Message:</b> {html_lib.escape(report.zdel_threshold_message)}</p>
  <h2>Renewal Completeness Check</h2>
  <p><b>Renewal status value:</b> {html_lib.escape(report.renewal_status_value)}</p>
  <p><b>Renewal status column (old/new):</b> {html_lib.escape(report.renewal_status_column_old)} / {html_lib.escape(report.renewal_status_column_new)}</p>
  <p><b>Renewal quote nbr column (old/new):</b> {html_lib.escape(report.renewal_quote_number_column_old)} / {html_lib.escape(report.renewal_quote_number_column_new)}</p>
  <p><b>Renewal contract doc nbr column (old/new):</b> {html_lib.escape(report.renewal_contract_doc_number_column_old)} / {html_lib.escape(report.renewal_contract_doc_number_column_new)}</p>
  <p><b>Old rows with selected status:</b> {report.renewal_old_filtered_count} &nbsp;&middot;&nbsp;
     <b>Old missing rows:</b> {report.renewal_old_missing_count} &nbsp;&middot;&nbsp;
     <b>Old missing %:</b> {round(report.renewal_old_missing_pct, 2)}</p>
  <p><b>New rows with selected status:</b> {report.renewal_new_filtered_count} &nbsp;&middot;&nbsp;
     <b>New missing rows:</b> {report.renewal_new_missing_count} &nbsp;&middot;&nbsp;
     <b>New missing %:</b> {round(report.renewal_new_missing_pct, 2)}</p>
  <p><b>Threshold %:</b> {round(report.renewal_threshold_pct, 2)}</p>
  <p><b>Threshold check (&gt; {round(report.renewal_threshold_pct, 2)}%):</b> {"Exceeded" if report.renewal_threshold_exceeded else "Within limit"}</p>
  <p><b>Message:</b> {html_lib.escape(report.renewal_threshold_message)}</p>
  <h2>Indirect channel profile without Tier 2 reseller</h2>
  {truncated_note}
  {invalid_html}
</body>
</html>"""

    destination.write_text(html, encoding="utf-8")
    return destination
