"""Shared helpers for rule implementations.

Every rule runner receives ``(df, columns, params)`` and returns a
:class:`RuleOutcome`.  The engine turns that into a
:class:`~dq_platform.models.RuleResult` by adding registry metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd


@dataclass
class RuleOutcome:
    """What a rule runner reports back to the engine."""

    failed_index: Sequence[Any] = field(default_factory=list)
    message: str = ""
    detail_table: Optional[pd.DataFrame] = None
    derived: Optional[pd.Series] = None
    rows_checked: Optional[int] = None
    # Set by dataset-level checks that fail without pointing at specific rows.
    rule_failed: bool = False


def outcome(
    mask: Optional[pd.Series] = None,
    message: str = "",
    detail_table: Optional[pd.DataFrame] = None,
    derived: Optional[pd.Series] = None,
    rows_checked: Optional[int] = None,
    rule_failed: bool = False,
) -> RuleOutcome:
    """Build a :class:`RuleOutcome` from a boolean *failure* mask."""
    if mask is None:
        failed_index: Sequence[Any] = []
    else:
        failed_index = mask.fillna(False).astype(bool)
        failed_index = failed_index[failed_index].index
    return RuleOutcome(
        failed_index=list(failed_index),
        message=message,
        detail_table=detail_table,
        derived=derived,
        rows_checked=rows_checked,
        rule_failed=rule_failed,
    )


def require_columns(df: pd.DataFrame, columns: Sequence[str], count: Optional[int] = None) -> List[str]:
    """Validate that the requested columns exist, returning them as a list."""
    selected = [c for c in (columns or []) if c not in (None, "")]
    if count is not None and len(selected) != count:
        raise ValueError(f"This check needs exactly {count} column(s); got {len(selected)}.")
    if not selected:
        raise ValueError("No column selected for this check.")
    missing = [c for c in selected if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found in the sheet: {', '.join(missing)}")
    return selected


def blank_mask(series: pd.Series) -> pd.Series:
    """True where the value is null, an empty string, or whitespace only."""
    is_null = series.isna()
    text = series.astype("string").str.strip()
    return (is_null | (text == "") | text.isna()).fillna(True)


def get_param(params: Dict[str, Any], name: str, default: Any = None) -> Any:
    value = (params or {}).get(name, default)
    if isinstance(value, str) and value.strip() == "":
        return default
    return value


def split_list_param(value: Any) -> List[str]:
    """Accept a comma separated string or an iterable and return a clean list."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = list(value)
    return [str(p).strip() for p in parts if str(p).strip() != ""]
