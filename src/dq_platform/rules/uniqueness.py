"""Uniqueness rules: exact duplicate rows and duplicate business keys."""

from __future__ import annotations

from typing import Any, Dict, Sequence

import pandas as pd

from dq_platform.rules.base import RuleOutcome, blank_mask, get_param, outcome, require_columns


def duplicate_rows(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag every row that is an exact copy of another row."""
    subset = [c for c in (columns or []) if c in df.columns] or None
    mask = df.duplicated(subset=subset, keep=False)
    extra_copies = int(df.duplicated(subset=subset, keep="first").sum())
    groups = int(mask.sum()) - extra_copies

    scope = f"across {len(subset)} selected column(s)" if subset else "across all columns"
    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} rows belong to {groups} duplicate group(s) {scope} "
            f"({extra_copies} redundant copies)."
        ),
    )


def duplicate_key(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag rows whose key column(s) repeat, e.g. duplicate Sales Doc Nbr."""
    subset = require_columns(df, columns)
    ignore_blanks = get_param(params, "ignore_blanks", True)

    frame = df[subset]
    mask = frame.duplicated(keep=False)

    if ignore_blanks:
        any_blank = pd.DataFrame(
            {c: blank_mask(df[c]) for c in subset}, index=df.index
        ).any(axis=1)
        mask = mask & ~any_blank

    duplicated_keys = int(frame[mask.fillna(False)].drop_duplicates().shape[0])
    return outcome(
        mask,
        message=(
            f"{int(mask.fillna(False).sum())} rows share {duplicated_keys} repeated "
            f"value(s) of '{', '.join(subset)}'."
        ),
    )


def unique_ratio(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Informational: report the distinct-value ratio of a column."""
    column = require_columns(df, columns, count=1)[0]
    total = len(df)
    distinct = int(df[column].nunique(dropna=True))
    min_ratio = float(get_param(params, "min_distinct_pct", 0))
    ratio = round(distinct / total * 100, 2) if total else 0.0

    detail = pd.DataFrame(
        [{"Column": column, "Distinct Values": distinct, "Distinct %": ratio}]
    )
    return outcome(
        None,
        message=f"'{column}' has {distinct} distinct values ({ratio}% of {total} rows).",
        detail_table=detail,
        rule_failed=bool(min_ratio > 0 and total and ratio < min_ratio),
    )
