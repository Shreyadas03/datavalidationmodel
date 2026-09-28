"""Validity rules: format, domain, pattern, range and type conformity checks."""

from __future__ import annotations

import re
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

# Pragmatic email pattern: one @, no spaces, a dotted domain with a 2+ char TLD.
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$"
)


def _text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def _apply_by_unique(series: pd.Series, func) -> pd.Series:
    """Evaluate ``func`` once per distinct value; large sheets repeat a lot of values."""
    values = pd.unique(series.dropna())
    lookup = {value: func(value) for value in values}
    return series.map(lambda v: lookup.get(v, False) if pd.notna(v) else False)


def email_format(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag values that are not syntactically valid email addresses."""
    column = require_columns(df, columns, count=1)[0]
    allow_blank = get_param(params, "allow_blank", True)

    blanks = blank_mask(df[column])
    text = _text(df[column])
    valid = text.map(lambda v: bool(EMAIL_PATTERN.match(v)) if isinstance(v, str) else False)

    mask = (~valid) & (~blanks) if allow_blank else (~valid) | blanks
    return outcome(
        mask,
        message=f"{int(mask.sum())} rows in '{column}' are not valid email addresses.",
    )


def email_domain(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag emails outside the allowed domain list (defaults to hpe.com)."""
    column = require_columns(df, columns, count=1)[0]
    domains = [d.lower().lstrip("@") for d in split_list_param(get_param(params, "domains", "hpe.com"))]
    allow_subdomains = bool(get_param(params, "allow_subdomains", True))
    allow_blank = get_param(params, "allow_blank", True)

    if not domains:
        raise ValueError("Provide at least one allowed domain, e.g. 'hpe.com'.")

    blanks = blank_mask(df[column])
    text = _text(df[column]).str.lower()

    def matches(value: Any) -> bool:
        if not isinstance(value, str) or "@" not in value:
            return False
        host = value.rsplit("@", 1)[1]
        for domain in domains:
            if host == domain or (allow_subdomains and host.endswith("." + domain)):
                return True
        return False

    ok = text.map(matches)
    mask = (~ok) & (~blanks) if allow_blank else (~ok) | blanks
    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} rows in '{column}' are not on an allowed domain "
            f"({', '.join(domains)})."
        ),
    )


def phone_number(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag phone numbers that are not valid for the given region."""
    import phonenumbers

    column = require_columns(df, columns, count=1)[0]
    region = str(get_param(params, "region", "US") or "US").strip().upper() or None
    allow_blank = get_param(params, "allow_blank", True)

    blanks = blank_mask(df[column])
    text = _text(df[column])

    def is_valid(value: Any) -> bool:
        if not isinstance(value, str) or value == "":
            return False
        try:
            parsed = phonenumbers.parse(value, None if value.startswith("+") else region)
        except phonenumbers.NumberParseException:
            return False
        return phonenumbers.is_valid_number(parsed)

    ok = _apply_by_unique(text, is_valid)
    mask = (~ok) & (~blanks) if allow_blank else (~ok) | blanks
    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} rows in '{column}' are not valid phone numbers "
            f"(default region {region})."
        ),
    )


def regex_match(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag values that do (or do not) match a user supplied regular expression."""
    column = require_columns(df, columns, count=1)[0]
    pattern = get_param(params, "pattern")
    if not pattern:
        raise ValueError("A regular expression pattern is required for this check.")
    should_match = bool(get_param(params, "should_match", True))
    case_sensitive = bool(get_param(params, "case_sensitive", True))
    allow_blank = get_param(params, "allow_blank", True)

    try:
        compiled = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from exc

    blanks = blank_mask(df[column])
    text = _text(df[column])
    found = text.map(lambda v: bool(compiled.search(v)) if isinstance(v, str) else False)

    violation = (~found) if should_match else found
    mask = violation & (~blanks) if allow_blank else violation | blanks
    verb = "do not match" if should_match else "match"
    return outcome(
        mask,
        message=f"{int(mask.sum())} rows in '{column}' {verb} /{pattern}/.",
    )


def allowed_values(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag values outside a whitelist of accepted categories."""
    column = require_columns(df, columns, count=1)[0]
    accepted = split_list_param(get_param(params, "values"))
    if not accepted:
        raise ValueError("Provide the list of allowed values (comma separated).")
    case_sensitive = bool(get_param(params, "case_sensitive", False))
    allow_blank = get_param(params, "allow_blank", True)

    blanks = blank_mask(df[column])
    text = _text(df[column])
    if not case_sensitive:
        text = text.str.lower()
        accepted_set = {v.lower() for v in accepted}
    else:
        accepted_set = set(accepted)

    ok = text.map(lambda v: v in accepted_set if isinstance(v, str) else False)
    mask = (~ok) & (~blanks) if allow_blank else (~ok) | blanks

    counts = _text(df[column]).value_counts(dropna=False).reset_index()
    counts.columns = ["Value", "Count"]
    counts["Allowed"] = counts["Value"].map(
        lambda v: (str(v).lower() if not case_sensitive else str(v)) in accepted_set
    )

    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} rows in '{column}' are outside the allowed list "
            f"({', '.join(accepted)})."
        ),
        detail_table=counts,
    )


def numeric_range(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag numeric values outside ``[min_value, max_value]`` or that are not numeric."""
    column = require_columns(df, columns, count=1)[0]
    min_value = get_param(params, "min_value")
    max_value = get_param(params, "max_value")
    allow_blank = get_param(params, "allow_blank", True)

    blanks = blank_mask(df[column])
    numeric = pd.to_numeric(df[column], errors="coerce")

    not_numeric = numeric.isna() & (~blanks)
    below = numeric < float(min_value) if min_value not in (None, "") else pd.Series(False, index=df.index)
    above = numeric > float(max_value) if max_value not in (None, "") else pd.Series(False, index=df.index)

    mask = not_numeric | below.fillna(False) | above.fillna(False)
    if not allow_blank:
        mask = mask | blanks

    bounds = []
    if min_value not in (None, ""):
        bounds.append(f">= {min_value}")
    if max_value not in (None, ""):
        bounds.append(f"<= {max_value}")
    bound_text = " and ".join(bounds) if bounds else "numeric"
    return outcome(
        mask,
        message=f"{int(mask.sum())} rows in '{column}' are not {bound_text}.",
    )


def outlier_iqr(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag statistical outliers using the interquartile range method."""
    column = require_columns(df, columns, count=1)[0]
    multiplier = float(get_param(params, "iqr_multiplier", 1.5))

    numeric = pd.to_numeric(df[column], errors="coerce")
    if numeric.notna().sum() < 4:
        return outcome(None, message=f"'{column}' has too few numeric values for outlier detection.")

    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr

    mask = ((numeric < lower) | (numeric > upper)).fillna(False)
    detail = pd.DataFrame(
        [{"Column": column, "Q1": q1, "Q3": q3, "IQR": iqr, "Lower Bound": lower, "Upper Bound": upper}]
    )
    return outcome(
        mask,
        message=(
            f"{int(mask.sum())} rows in '{column}' fall outside "
            f"[{round(lower, 4)}, {round(upper, 4)}]."
        ),
        detail_table=detail,
    )


def dtype_numeric(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag values in the column that cannot be parsed as numbers."""
    column = require_columns(df, columns, count=1)[0]
    allow_blank = get_param(params, "allow_blank", True)

    blanks = blank_mask(df[column])
    numeric = pd.to_numeric(df[column], errors="coerce")
    mask = numeric.isna() & (~blanks) if allow_blank else numeric.isna()
    return outcome(
        mask,
        message=f"{int(mask.sum())} rows in '{column}' are not parseable as numbers.",
    )


def dtype_date(df: pd.DataFrame, columns: Sequence[str], params: Dict[str, Any]) -> RuleOutcome:
    """Flag values in the column that cannot be parsed as dates."""
    column = require_columns(df, columns, count=1)[0]
    allow_blank = get_param(params, "allow_blank", True)
    dayfirst = bool(get_param(params, "dayfirst", False))

    blanks = blank_mask(df[column])
    parsed = pd.to_datetime(df[column], errors="coerce", dayfirst=dayfirst)
    mask = parsed.isna() & (~blanks) if allow_blank else parsed.isna()
    return outcome(
        mask,
        message=f"{int(mask.sum())} rows in '{column}' are not parseable as dates.",
        derived=parsed.rename(f"{column} (parsed)"),
    )
