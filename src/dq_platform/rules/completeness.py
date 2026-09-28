"""Completeness rules: nulls, blanks and empty strings."""

from __future__ import annotations

from typing import Any, Dict, Sequence

import pandas as pd

from dq_platform.rules.base import (
    RuleOutcome,
    blank_mask,
    get_param,
    outcome,
    require_columns,
    split_list_param,
)


def null_blank(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag rows where the selected column is null, empty or whitespace only."""
    column = require_columns(df, columns, count=1)[0]
    series = df[column]

    if get_param(params, "treat_whitespace_as_blank", True):
        mask = blank_mask(series)
    else:
        mask = series.isna()

    return outcome(
        mask,
        message=f"{int(mask.sum())} of {len(df)} rows have no value in '{column}'.",
    )


def missing_summary(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Dataset-wide missing value profile; flags every row with at least one gap."""
    subset = [c for c in split_list_param(columns) if c in df.columns] or list(df.columns)
    total = len(df)

    blanks = pd.DataFrame({c: blank_mask(df[c]) for c in subset}, index=df.index)
    counts = blanks.sum().astype(int)

    detail = pd.DataFrame(
        {
            "Column": counts.index,
            "Missing_Count": counts.values,
            "Missing_Pct": (counts.values / total * 100).round(2) if total else 0.0,
        }
    ).sort_values("Missing_Count", ascending=False).reset_index(drop=True)

    mask = blanks.any(axis=1) if len(subset) else pd.Series(False, index=df.index)
    incomplete_columns = int((counts > 0).sum())

    return outcome(
        mask,
        message=(
            f"{incomplete_columns} of {len(subset)} columns contain missing values; "
            f"{int(mask.sum())} rows are affected."
        ),
        detail_table=detail,
    )


def completeness_threshold(
    df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]
) -> RuleOutcome:
    """Flag rows in which fewer than ``min_filled_pct`` of the selected columns are filled."""
    subset = require_columns(df, columns)
    threshold = float(get_param(params, "min_filled_pct", 100))

    filled = pd.DataFrame({c: ~blank_mask(df[c]) for c in subset}, index=df.index)
    filled_pct = filled.sum(axis=1) / len(subset) * 100
    mask = filled_pct < threshold

    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} rows have less than {threshold}% of the "
            f"{len(subset)} selected columns populated."
        ),
    )
