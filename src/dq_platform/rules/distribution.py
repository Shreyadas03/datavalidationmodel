"""Distribution rules: value profiling and targeted category counts."""

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


def value_profile(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Informational value_counts profile, optionally capped at ``max_distinct``."""
    column = require_columns(df, columns, count=1)[0]
    top_n = int(get_param(params, "top_n", 25) or 25)
    max_distinct = get_param(params, "max_distinct")

    counts = df[column].value_counts(dropna=False)
    total = len(df)
    detail = counts.head(top_n).reset_index()
    detail.columns = ["Value", "Count"]
    detail["Percent"] = (detail["Count"] / total * 100).round(2) if total else 0.0

    distinct = int(df[column].nunique(dropna=True))
    too_many = max_distinct not in (None, "") and distinct > int(max_distinct)

    return outcome(
        None,
        message=(
            f"'{column}' has {distinct} distinct values"
            + (f", above the limit of {max_distinct}" if too_many else "")
            + f"; showing the top {min(top_n, len(counts))}."
        ),
        detail_table=detail,
        rule_failed=bool(too_many),
    )


def category_count(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Count occurrences of specific categories (e.g. ZDEP / ZCRN document types)."""
    column = require_columns(df, columns, count=1)[0]
    targets = split_list_param(get_param(params, "values"))
    if not targets:
        raise ValueError("Provide the category value(s) to count, e.g. 'ZDEP, ZCRN'.")
    case_sensitive = bool(get_param(params, "case_sensitive", False))
    flag_others = bool(get_param(params, "flag_others", False))
    min_count = get_param(params, "min_count")

    text = df[column].astype("string").str.strip()
    if case_sensitive:
        comparable = text
        wanted = list(targets)
    else:
        comparable = text.str.upper()
        wanted = [t.upper() for t in targets]

    total = len(df)
    rows = []
    shortfalls = []
    for original, key in zip(targets, wanted):
        hits = int((comparable == key).fillna(False).sum())
        rows.append(
            {
                "Value": original,
                "Count": hits,
                "Percent": round(hits / total * 100, 2) if total else 0.0,
            }
        )
        if min_count not in (None, "") and hits < int(min_count):
            shortfalls.append(f"{original} ({hits})")

    detail = pd.DataFrame(rows)

    if flag_others:
        blanks = blank_mask(df[column])
        mask = (~comparable.isin(wanted).fillna(False)) & (~blanks)
        message = (
            f"{int(mask.sum())} rows in '{column}' are outside "
            f"{', '.join(targets)}."
        )
    elif shortfalls:
        return outcome(
            None,
            message=f"Below the minimum count of {min_count}: {', '.join(shortfalls)}.",
            detail_table=detail,
            rule_failed=True,
        )
    else:
        mask = None
        counted = ", ".join(f"{r['Value']}={r['Count']}" for r in rows)
        message = f"Counts in '{column}': {counted}."

    return outcome(mask, message=message, detail_table=detail)
