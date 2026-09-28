"""Hygiene rules: whitespace, casing and unexpected characters."""

from __future__ import annotations

import re
from typing import Any, Dict, Sequence

import pandas as pd

from dq_platform.rules.base import RuleOutcome, blank_mask, get_param, outcome, require_columns

DEFAULT_SPECIAL_CHARS = r"[^A-Za-z0-9 .,\-_/&()@:'#+]"


def whitespace(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag leading/trailing whitespace and, optionally, doubled inner spaces."""
    column = require_columns(df, columns, count=1)[0]
    check_inner = bool(get_param(params, "check_inner_spaces", True))

    raw = df[column].astype("string")
    has_edge = (raw != raw.str.strip()).fillna(False)
    mask = has_edge
    if check_inner:
        has_inner = raw.str.contains(r"\s{2,}", regex=True, na=False)
        mask = mask | has_inner

    return outcome(
        mask,
        message=f"{int(mask.sum())} rows in '{column}' have stray whitespace.",
    )


def casing(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag values that do not follow the expected casing convention."""
    column = require_columns(df, columns, count=1)[0]
    expected = str(get_param(params, "expected_case", "consistent")).lower()

    blanks = blank_mask(df[column])
    text = df[column].astype("string").str.strip()

    if expected == "upper":
        ok = (text == text.str.upper()).fillna(False)
    elif expected == "lower":
        ok = (text == text.str.lower()).fillna(False)
    elif expected == "title":
        ok = (text == text.str.title()).fillna(False)
    else:
        # "consistent": flag values that only differ from another value by case.
        upper = text.str.upper()
        variants = pd.DataFrame({"upper": upper, "text": text}).dropna()
        counts = variants.groupby("upper")["text"].nunique()
        inconsistent = set(counts[counts > 1].index)
        ok = ~upper.isin(inconsistent).fillna(False)

    mask = (~ok) & (~blanks)
    return outcome(
        mask,
        message=f"{int(mask.sum())} rows in '{column}' break the '{expected}' casing rule.",
    )


def special_characters(
    df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]
) -> RuleOutcome:
    """Flag values containing characters outside the accepted character set."""
    column = require_columns(df, columns, count=1)[0]
    pattern = str(get_param(params, "disallowed_pattern", DEFAULT_SPECIAL_CHARS))

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid character pattern: {exc}") from exc

    blanks = blank_mask(df[column])
    text = df[column].astype("string").str.strip()
    found = text.map(lambda v: bool(compiled.search(v)) if isinstance(v, str) else False)

    mask = found & (~blanks)

    offenders = sorted(
        {
            char
            for value in text[mask].dropna().unique()
            for char in compiled.findall(str(value))
        }
    )
    detail = (
        pd.DataFrame({"Unexpected Character": offenders}) if offenders else None
    )
    return outcome(
        mask,
        message=f"{int(mask.sum())} rows in '{column}' contain unexpected characters.",
        detail_table=detail,
    )


def length_range(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag values whose text length falls outside the expected bounds."""
    column = require_columns(df, columns, count=1)[0]
    min_length = get_param(params, "min_length")
    max_length = get_param(params, "max_length")

    blanks = blank_mask(df[column])
    lengths = df[column].astype("string").str.strip().str.len()

    below = lengths < int(min_length) if min_length not in (None, "") else pd.Series(False, index=df.index)
    above = lengths > int(max_length) if max_length not in (None, "") else pd.Series(False, index=df.index)
    mask = (below.fillna(False) | above.fillna(False)) & (~blanks)

    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} rows in '{column}' have a length outside "
            f"[{min_length or '0'}, {max_length or 'inf'}]."
        ),
    )
