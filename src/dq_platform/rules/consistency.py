"""Consistency rules: cross-column relationships and derived durations."""

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


def _to_datetime(series: pd.Series, dayfirst: bool = False) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    return pd.to_datetime(series, errors="coerce", dayfirst=dayfirst)


def date_order(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag rows where the end date precedes the start date."""
    start_col, end_col = require_columns(df, columns, count=2)
    allow_equal = bool(get_param(params, "allow_equal", True))
    dayfirst = bool(get_param(params, "dayfirst", False))

    start = _to_datetime(df[start_col], dayfirst)
    end = _to_datetime(df[end_col], dayfirst)

    both_present = start.notna() & end.notna()
    invalid = (end < start) if allow_equal else (end <= start)
    mask = (invalid & both_present).fillna(False)

    unparsed = int((blank_mask(df[start_col]) | blank_mask(df[end_col])).sum())
    note = f" {unparsed} rows were skipped because a date was missing." if unparsed else ""
    return outcome(
        mask,
        message=f"{int(mask.sum())} rows have '{end_col}' before '{start_col}'.{note}",
    )


def duration_range(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Compute a duration in days between two dates and flag out-of-bound values."""
    start_col, end_col = require_columns(df, columns, count=2)
    min_days = get_param(params, "min_days")
    max_days = get_param(params, "max_days")
    dayfirst = bool(get_param(params, "dayfirst", False))

    start = _to_datetime(df[start_col], dayfirst)
    end = _to_datetime(df[end_col], dayfirst)
    duration = (end - start).dt.days

    below = duration < float(min_days) if min_days not in (None, "") else pd.Series(False, index=df.index)
    above = duration > float(max_days) if max_days not in (None, "") else pd.Series(False, index=df.index)
    mask = (below.fillna(False) | above.fillna(False))

    described = duration.describe()
    detail = pd.DataFrame(
        [
            {
                "Metric": key,
                "Duration_Days": round(float(value), 2) if pd.notna(value) else None,
            }
            for key, value in described.items()
        ]
    )
    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} rows fall outside the allowed contract duration "
            f"({min_days if min_days not in (None, '') else '-inf'} to "
            f"{max_days if max_days not in (None, '') else 'inf'} days)."
        ),
        detail_table=detail,
        derived=duration.rename("Duration_Days"),
    )


def one_to_one(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag keys that map to more than one distinct value, e.g. CE_ID -> Party Name."""
    key_col, value_col = require_columns(df, columns, count=2)
    case_sensitive = bool(get_param(params, "case_sensitive", False))

    key = df[key_col].astype("string").str.strip()
    value = df[value_col].astype("string").str.strip()
    if not case_sensitive:
        value = value.str.upper()

    usable = key.notna() & (key != "") & value.notna() & (value != "")
    frame = pd.DataFrame({"key": key, "value": value})[usable]
    distinct = frame.groupby("key")["value"].nunique()
    conflicting = set(distinct[distinct > 1].index)

    mask = pd.Series(False, index=df.index)
    if conflicting:
        mask = key.isin(conflicting).fillna(False) & usable

    detail = None
    if conflicting:
        rows = (
            frame[frame["key"].isin(conflicting)]
            .drop_duplicates()
            .sort_values(["key", "value"])
            .rename(columns={"key": key_col, "value": value_col})
            .reset_index(drop=True)
        )
        detail = rows

    return outcome(
        mask,
        message=(
            f"{len(conflicting)} value(s) of '{key_col}' map to more than one '{value_col}', "
            f"affecting {int(mask.sum())} rows."
        ),
        detail_table=detail,
    )


def conditional_required(
    df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]
) -> RuleOutcome:
    """When the trigger column holds one of the given values, the target must be filled."""
    trigger_col, target_col = require_columns(df, columns, count=2)
    triggers = split_list_param(get_param(params, "trigger_values"))
    if not triggers:
        raise ValueError("Provide the trigger value(s) that make the target column mandatory.")
    case_sensitive = bool(get_param(params, "case_sensitive", False))

    trigger_text = df[trigger_col].astype("string").str.strip()
    if case_sensitive:
        trigger_set = set(triggers)
    else:
        trigger_text = trigger_text.str.upper()
        trigger_set = {t.upper() for t in triggers}

    triggered = trigger_text.isin(trigger_set).fillna(False)
    mask = triggered & blank_mask(df[target_col])

    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} of {int(triggered.sum())} rows where '{trigger_col}' is "
            f"{', '.join(triggers)} have no '{target_col}'."
        ),
    )
