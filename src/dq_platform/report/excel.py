"""Multi-sheet Excel report writer."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from dq_platform.models import QualityReport, RuleResult

# Cap exported rows per sheet so a huge file cannot blow up memory or Excel.
DEFAULT_ROW_LIMIT = 5000

_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def _safe_sheet_name(name: str, used: Dict[str, int]) -> str:
    cleaned = _INVALID_SHEET_CHARS.sub("_", str(name)).strip() or "Sheet"
    cleaned = cleaned[:31]
    if cleaned not in used:
        used[cleaned] = 1
        return cleaned
    used[cleaned] += 1
    suffix = f"_{used[cleaned]}"
    return cleaned[: 31 - len(suffix)] + suffix


def _autofit(worksheet, frame: pd.DataFrame, workbook) -> None:
    wrap = workbook.add_format({"valign": "top"})
    for position, column in enumerate(frame.columns):
        values = frame[column].astype("string").fillna("")
        longest = int(values.str.len().max()) if len(values) else 0
        width = min(max(longest, len(str(column))) + 2, 55)
        worksheet.set_column(position, position, width, wrap)


def _write_frame(writer, frame: pd.DataFrame, sheet_name: str) -> None:
    frame.to_excel(writer, sheet_name=sheet_name, index=False)
    _autofit(writer.sheets[sheet_name], frame, writer.book)
    writer.sheets[sheet_name].freeze_panes(1, 0)


def write_excel_report(
    report: QualityReport,
    df: pd.DataFrame,
    output_path: str | Path,
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> Path:
    """Write the full quality report as a multi-sheet workbook."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    used: Dict[str, int] = {}
    details = report.details_frame()
    sheet_links: List[str] = []

    with pd.ExcelWriter(destination, engine="xlsxwriter") as writer:
        workbook = writer.book

        summary_sheet = _safe_sheet_name("Summary", used)
        _write_frame(writer, report.summary_frame(), summary_sheet)

        if report.notes:
            notes_sheet = _safe_sheet_name("Notes", used)
            _write_frame(writer, pd.DataFrame({"Note": report.notes}), notes_sheet)

        # Reserve the details sheet name now so per-rule sheets can reference it.
        details_sheet = _safe_sheet_name("Rule_Details", used)

        detail_targets: Dict[int, str] = {}
        flagged_targets: Dict[int, str] = {}

        for position, result in enumerate(report.results):
            if result.detail_table is not None and not result.detail_table.empty:
                name = _safe_sheet_name(f"D{position + 1}_{result.label}", used)
                detail_targets[position] = name

            if result.status == "FAIL" and result.failed_count:
                name = _safe_sheet_name(f"F{position + 1}_{result.label}", used)
                flagged_targets[position] = name

        for position in range(len(report.results)):
            links = []
            if position in flagged_targets:
                links.append(f"Rows: {flagged_targets[position]}")
            if position in detail_targets:
                links.append(f"Detail: {detail_targets[position]}")
            sheet_links.append(" | ".join(links))

        if not details.empty:
            details = details.copy()
            details["Report Sheet"] = sheet_links
        _write_frame(writer, details, details_sheet)

        if not details.empty:
            worksheet = writer.sheets[details_sheet]
            status_col = list(details.columns).index("Status")
            fail_format = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
            pass_format = workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
            error_format = workbook.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"})
            cell_range = (0, status_col, len(details), status_col)
            for text, fmt in (("FAIL", fail_format), ("PASS", pass_format), ("ERROR", error_format)):
                worksheet.conditional_format(
                    *cell_range,
                    {"type": "cell", "criteria": "==", "value": f'"{text}"', "format": fmt},
                )

        if report.missing_profile is not None and not report.missing_profile.empty:
            _write_frame(writer, report.missing_profile, _safe_sheet_name("Missing_Values", used))

        if report.dtypes_profile is not None and not report.dtypes_profile.empty:
            _write_frame(writer, report.dtypes_profile, _safe_sheet_name("Column_Profile", used))

        for position, result in enumerate(report.results):
            if position in detail_targets:
                _write_frame(writer, result.detail_table, detail_targets[position])

            if position in flagged_targets:
                rows = _flagged_frame(result, df, row_limit)
                _write_frame(writer, rows, flagged_targets[position])

    return destination


def _flagged_frame(result: RuleResult, df: pd.DataFrame, row_limit: Optional[int]) -> pd.DataFrame:
    """Offending rows with the source row number and any derived column attached."""
    rows = result.failed_rows(df, limit=row_limit)
    if rows.empty:
        return rows

    output = rows.copy()
    # Excel row number of the original record (header is row 1).
    output.insert(0, "Source Row", [df.index.get_loc(idx) + 2 for idx in rows.index])

    if result.derived is not None:
        derived = result.derived.reindex(rows.index)
        output[str(derived.name or "Derived")] = derived.values

    return output.reset_index(drop=True)
