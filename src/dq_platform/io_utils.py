"""Safe Excel loading helpers.

Header rows are read without materialising the whole workbook so the column
dropdowns populate instantly even for large files.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pandas as pd

ALLOWED_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}


def resolve_path(path: str | Path) -> Path:
    """Validate a user supplied workbook path and return it as a ``Path``."""
    if path is None or str(path).strip() == "":
        raise ValueError("No file path provided.")

    # Users often paste Windows paths wrapped in quotes.
    cleaned = str(path).strip().strip('"').strip("'")
    resolved = Path(cleaned).expanduser()

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"Path is not a file: {resolved}")
    if resolved.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(
            f"Unsupported file type '{resolved.suffix}'. "
            f"Expected one of: {', '.join(sorted(ALLOWED_SUFFIXES))}"
        )
    return resolved


def list_sheets(path: str | Path) -> List[str]:
    """Return the sheet names of a workbook."""
    resolved = resolve_path(path)
    if resolved.suffix.lower() == ".xls":
        return pd.ExcelFile(resolved).sheet_names

    from openpyxl import load_workbook

    workbook = load_workbook(resolved, read_only=True, data_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def read_header_columns(path: str | Path, sheet_name: Optional[str] = None) -> List[str]:
    """Read only the first row of a sheet and return its column names."""
    resolved = resolve_path(path)
    if resolved.suffix.lower() == ".xls":
        frame = pd.read_excel(resolved, sheet_name=sheet_name or 0, nrows=0)
        return [str(c) for c in frame.columns]

    from openpyxl import load_workbook

    workbook = load_workbook(resolved, read_only=True, data_only=True)
    try:
        sheet = workbook[sheet_name] if sheet_name else workbook[workbook.sheetnames[0]]
        header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
    finally:
        workbook.close()

    columns: List[str] = []
    for position, value in enumerate(header_row):
        name = str(value).strip() if value is not None else ""
        columns.append(name or f"Unnamed: {position}")
    return columns


def load_dataframe(path: str | Path, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Load a worksheet into a DataFrame."""
    resolved = resolve_path(path)
    frame = pd.read_excel(resolved, sheet_name=sheet_name if sheet_name else 0)
    if isinstance(frame, dict):  # defensive: sheet_name=None returns a dict
        frame = next(iter(frame.values()))
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def profile_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """A compact ``df.info()`` equivalent as a DataFrame."""
    return pd.DataFrame(
        {
            "Column": df.columns,
            "Dtype": [str(df[c].dtype) for c in df.columns],
            "Non-Null Count": [int(df[c].notna().sum()) for c in df.columns],
            "Null Count": [int(df[c].isna().sum()) for c in df.columns],
            "Unique Values": [int(df[c].nunique(dropna=True)) for c in df.columns],
        }
    )


def profile_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Missing value counts and percentages, sorted worst-first."""
    total = len(df)
    profile = pd.DataFrame(
        {
            "Column": df.columns,
            "Missing_Count": [int(df[c].isna().sum()) for c in df.columns],
        }
    )
    profile["Missing_Pct"] = (
        (profile["Missing_Count"] / total * 100).round(2) if total else 0.0
    )
    return profile.sort_values("Missing_Count", ascending=False).reset_index(drop=True)
