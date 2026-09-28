"""Runs configured checks against a DataFrame and assembles a QualityReport."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from dq_platform.io_utils import profile_dtypes, profile_missing
from dq_platform.models import QualityReport, RuleResult, RuleSpec
from dq_platform.registry import RuleDefinition, get_rule


def _coerce_spec(spec: Any) -> RuleSpec:
    if isinstance(spec, RuleSpec):
        return spec
    if isinstance(spec, dict):
        return RuleSpec.from_dict(spec)
    raise TypeError(f"Cannot interpret {type(spec).__name__} as a RuleSpec.")


def _merged_params(definition: RuleDefinition, spec: RuleSpec) -> Dict[str, Any]:
    params = definition.default_params()
    params.update(spec.params or {})
    return params


def run_rule(df: pd.DataFrame, spec: Any) -> RuleResult:
    """Run a single check, converting any failure into an ERROR result."""
    spec = _coerce_spec(spec)
    try:
        definition = get_rule(spec.rule_id)
    except KeyError as exc:
        return RuleResult(
            rule_id=spec.rule_id,
            label=spec.label or spec.rule_id,
            dimension="Unknown",
            columns=list(spec.columns),
            total_rows=len(df),
            error=str(exc),
        )

    label = spec.label or definition.label
    result = RuleResult(
        rule_id=definition.rule_id,
        label=label,
        dimension=definition.dimension,
        columns=list(spec.columns),
        total_rows=len(df),
    )

    try:
        outcome = definition.runner(df, list(spec.columns), _merged_params(definition, spec))
    except Exception as exc:  # a bad rule must not abort the whole run
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.failed_index = list(outcome.failed_index)
    result.failed_count = len(result.failed_index)
    result.message = outcome.message
    result.detail_table = outcome.detail_table
    result.derived = outcome.derived
    result.rule_failed = outcome.rule_failed
    if outcome.rows_checked is not None:
        result.total_rows = outcome.rows_checked
    return result


def run_checks(
    df: pd.DataFrame,
    specs: Iterable[Any],
    source_path: str = "",
    sheet_name: str = "",
    notes: Optional[Sequence[str]] = None,
) -> QualityReport:
    """Run every spec and package the results into a :class:`QualityReport`."""
    results: List[RuleResult] = [run_rule(df, spec) for spec in specs]

    return QualityReport(
        source_path=source_path,
        sheet_name=sheet_name,
        row_count=len(df),
        column_count=len(df.columns),
        results=results,
        missing_profile=profile_missing(df),
        dtypes_profile=profile_dtypes(df),
        notes=list(notes or []),
    )
