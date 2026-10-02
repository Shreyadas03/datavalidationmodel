"""Decision-tree root cause analysis for the AI Insights section.

Two complementary trees, both run locally on numbers the platform has
already computed or loaded -- no external AI service is ever called:

1. :func:`rule_based_root_causes` -- a hand-authored IF/THEN decision tree.
   Each failing finding on the dashboard (ZDEL revenue delta, renewal
   completeness, Tier 2 reseller gaps, Multiyear Flag violations, errored
   checks, unusual trends) is walked down a fixed set of branches to the
   most likely root-cause hypothesis. Every branch taken is recorded in
   ``RootCauseFinding.path`` so the reasoning is fully auditable.

2. :func:`learned_segment_root_causes` -- a learned CART decision tree
   (scikit-learn ``DecisionTreeClassifier``) trained per failing data
   quality check on the row-level data. The target is "this row failed the
   check"; features are low-cardinality categorical columns (region,
   channel, document type, ...). Leaves whose failure rate is well above
   the overall baseline are turned into segment statements such as
   "62% of failures fall in Region = APJ AND Channel = Indirect".
   This shows *association*, not proven causation, and the wording says so.

Neither tree changes any validation/rule logic; both only read results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Sequence

import numpy as np
import pandas as pd

from dq_platform.ai_insights.trend import TRACKED_METRICS, TrendResult
from dq_platform.models import QualityReport

if TYPE_CHECKING:
    from dq_platform.ai_insights.dashboard_summary import DashboardFacts

METHOD_RULE_TREE = "rule_tree"
METHOD_LEARNED_TREE = "learned_tree"

# Learned-tree tuning. Kept shallow so every leaf reads as a short,
# human-sized segment description.
_MAX_DEPTH = 3
_MIN_LEAF_ROWS = 20
_MIN_LEAF_FRACTION = 0.01
_MIN_FAILURES = 5
_MAX_CATEGORIES = 25
_MAX_FEATURE_COLUMNS = 40
_MIN_LIFT = 1.5
_MIN_COVERAGE = 0.2
_RANDOM_STATE = 0

# Rule-tree tuning.
_VOLUME_EXPLAINS_SHARE = 0.5  # row-count change explains >= half the revenue change
_REGIONAL_CONCENTRATION = 0.5  # top geography holds >= half of missing Tier 2 rows
_HIGH_LIFT = 2.0
_HIGH_COVERAGE = 0.5


@dataclass
class RootCauseFinding:
    area: str
    symptom: str
    root_cause: str
    evidence: str
    recommendation: str
    method: str  # METHOD_RULE_TREE | METHOD_LEARNED_TREE
    severity: str = "Medium"  # High | Medium | Low
    path: list[str] = field(default_factory=list)


def _pct(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:,.2f}%"


# ---------------------------------------------------------------------------
# 1. Rule-based decision tree
# ---------------------------------------------------------------------------


def _zdel_branch(facts: "DashboardFacts") -> Optional[RootCauseFinding]:
    if not facts.zdel_threshold_exceeded:
        return None
    path = [f"{facts.zdel_document_type} revenue delta {_pct(facts.zdel_delta_pct)} exceeds "
            f"{_pct(facts.zdel_threshold_pct)} threshold"]
    symptom = (
        f"{facts.zdel_document_type} revenue moved {_pct(facts.zdel_delta_pct)} "
        f"(threshold {_pct(facts.zdel_threshold_pct)})."
    )

    if not facts.zdel_old_sum:
        path.append("Previous total is zero")
        return RootCauseFinding(
            area="Revenue Validation",
            symptom=symptom,
            root_cause="No baseline: the previous extract has no revenue for this document type.",
            evidence=f"Previous total is 0; current total is {facts.zdel_new_sum:,.2f}.",
            recommendation="Confirm the previous extract was filtered/loaded correctly before comparing.",
            method=METHOD_RULE_TREE,
            severity="High",
            path=path,
        )
    path.append("Previous total is non-zero")

    if facts.new_non_numeric_revenue_count > facts.old_non_numeric_revenue_count:
        path.append("Unreadable (non-numeric) revenue values increased")
        return RootCauseFinding(
            area="Revenue Validation",
            symptom=symptom,
            root_cause="Load/format issue: more revenue values could not be read as numbers in the new extract.",
            evidence=(
                f"Non-numeric revenue values: {facts.old_non_numeric_revenue_count:,} -> "
                f"{facts.new_non_numeric_revenue_count:,}."
            ),
            recommendation="Fix the revenue column format (text, currency symbols, separators) in the new extract.",
            method=METHOD_RULE_TREE,
            severity="High",
            path=path,
        )
    path.append("Non-numeric revenue values did not increase")

    row_change_pct: Optional[float] = None
    if facts.old_row_count:
        row_change_pct = (facts.new_row_count - facts.old_row_count) / facts.old_row_count * 100
    delta = facts.zdel_delta_pct or 0.0
    volume_explains = (
        row_change_pct is not None
        and delta != 0
        and np.sign(row_change_pct) == np.sign(delta)
        and abs(row_change_pct) >= _VOLUME_EXPLAINS_SHARE * abs(delta)
    )
    if volume_explains:
        path.append(f"Row count moved in the same direction ({_pct(row_change_pct)})")
        return RootCauseFinding(
            area="Revenue Validation",
            symptom=symptom,
            root_cause="Volume change: records were added to or dropped from the extract.",
            evidence=(
                f"Overall row count {facts.old_row_count:,} -> {facts.new_row_count:,} "
                f"({_pct(row_change_pct)}), in line with the revenue change."
            ),
            recommendation="Reconcile the record population (filters, date range, missing loads) between extracts.",
            method=METHOD_RULE_TREE,
            severity="Medium",
            path=path,
        )
    path.append(f"Row count does not explain the change ({_pct(row_change_pct)})")
    return RootCauseFinding(
        area="Revenue Validation",
        symptom=symptom,
        root_cause="Per-record value change: revenue per record shifted while volume stayed comparable.",
        evidence=(
            f"Overall row count {facts.old_row_count:,} -> {facts.new_row_count:,} "
            f"({_pct(row_change_pct)}) vs revenue change {_pct(facts.zdel_delta_pct)}."
        ),
        recommendation="Check pricing updates, currency conversion and revenue column mapping in the new extract.",
        method=METHOD_RULE_TREE,
        severity="High",
        path=path,
    )


def _renewal_branch(facts: "DashboardFacts") -> Optional[RootCauseFinding]:
    if not facts.renewal_threshold_exceeded:
        return None
    threshold = facts.renewal_threshold_pct
    old_over = facts.renewal_old_missing_pct > threshold
    new_over = facts.renewal_new_missing_pct > threshold
    path = [f"Renewal missing % exceeds {_pct(threshold)} threshold"]
    symptom = (
        f"Renewal Quote / Contract Doc missing: old {_pct(facts.renewal_old_missing_pct)}, "
        f"new {_pct(facts.renewal_new_missing_pct)}."
    )
    evidence = (
        f"Old {_pct(facts.renewal_old_missing_pct)} vs new {_pct(facts.renewal_new_missing_pct)} "
        f"(threshold {_pct(threshold)})."
    )
    if new_over and not old_over:
        path.append("Only the new extract is over threshold")
        return RootCauseFinding(
            area="Revenue Validation",
            symptom=symptom,
            root_cause="Regression in the new extract: renewal document numbers stopped being populated.",
            evidence=evidence,
            recommendation="Compare the new load's renewal quote/contract mapping with the previous load.",
            method=METHOD_RULE_TREE,
            severity="High",
            path=path,
        )
    if new_over and old_over:
        path.append("Both extracts are over threshold")
        return RootCauseFinding(
            area="Revenue Validation",
            symptom=symptom,
            root_cause="Systemic upstream gap: renewals are marked renewed without document numbers in the source.",
            evidence=evidence,
            recommendation="Raise with the source system owners; the gap exists before extraction.",
            method=METHOD_RULE_TREE,
            severity="High",
            path=path,
        )
    path.append("Only the old extract is over threshold")
    return RootCauseFinding(
        area="Revenue Validation",
        symptom=symptom,
        root_cause="Historical gap already resolved in the new extract.",
        evidence=evidence,
        recommendation="No action on the new extract; confirm the fix is permanent on the next refresh.",
        method=METHOD_RULE_TREE,
        severity="Low",
        path=path,
    )


def _tier2_branch(facts: "DashboardFacts") -> Optional[RootCauseFinding]:
    if facts.indirect_missing_tier2_count <= 0 or facts.tier2_severity.lower() in ("low", ""):
        return None
    path = [f"Tier 2 reseller missing on indirect rows, severity {facts.tier2_severity}"]
    symptom = (
        f"{facts.indirect_missing_tier2_count:,} of {facts.indirect_row_count:,} indirect rows "
        f"have no Tier 2 reseller ({_pct(facts.tier2_missing_pct)})."
    )
    share = facts.tier2_top_geography_share
    if facts.tier2_top_geography and share is not None and share >= _REGIONAL_CONCENTRATION:
        path.append(f"{share:.0%} of gaps are in one geography ({facts.tier2_top_geography})")
        return RootCauseFinding(
            area="Revenue Validation",
            symptom=symptom,
            root_cause=f"Regional process gap concentrated in {facts.tier2_top_geography}.",
            evidence=f"{share:.0%} of missing Tier 2 rows are in {facts.tier2_top_geography}.",
            recommendation=f"Review partner/reseller capture for indirect deals in {facts.tier2_top_geography}.",
            method=METHOD_RULE_TREE,
            severity=facts.tier2_severity,
            path=path,
        )
    path.append("Gaps are spread across geographies")
    if facts.tier2_top_geography and share is not None:
        evidence = f"No single geography holds the majority of gaps (top: {facts.tier2_top_geography}, {share:.0%})."
    else:
        evidence = "No single geography holds the majority of gaps."
    return RootCauseFinding(
        area="Revenue Validation",
        symptom=symptom,
        root_cause="Channel-wide capture gap: Tier 2 reseller is not enforced for indirect deals.",
        evidence=evidence,
        recommendation="Make Tier 2 reseller mandatory for indirect channel profiles at data entry.",
        method=METHOD_RULE_TREE,
        severity=facts.tier2_severity,
        path=path,
    )


def _business_case_branch(facts: "DashboardFacts") -> Optional[RootCauseFinding]:
    if not facts.business_case_violations:
        return None
    return RootCauseFinding(
        area="Business Case Validation",
        symptom=f"{facts.business_case_violations:,} row(s) with Months Duration > 12 lack the Multiyear Flag.",
        root_cause="Multiyear Flag derivation is not applied for contracts longer than 12 months.",
        evidence=f"{facts.business_case_violations:,} violating row(s).",
        recommendation="Derive the Multiyear Flag from Months Duration in the upstream transformation.",
        method=METHOD_RULE_TREE,
        severity="Medium",
        path=["Multiyear Flag violations > 0"],
    )


def _errored_checks_branch(facts: "DashboardFacts") -> Optional[RootCauseFinding]:
    if not facts.dq_checks_errored:
        return None
    return RootCauseFinding(
        area="Data Quality",
        symptom=f"{facts.dq_checks_errored} data quality check(s) errored.",
        root_cause="Check configuration mismatch: a required column is missing or has an unexpected type.",
        evidence=f"{facts.dq_checks_errored} of {facts.dq_checks_total} checks could not be evaluated.",
        recommendation="Open the Details section for the error message and align the column/parameter.",
        method=METHOD_RULE_TREE,
        severity="Medium",
        path=["Errored checks > 0"],
    )


def _trend_branch(trends: Sequence[TrendResult]) -> list[RootCauseFinding]:
    higher_is_better = {key: good for key, _label, good in TRACKED_METRICS}
    findings: list[RootCauseFinding] = []
    for trend in trends:
        values_str = ", ".join(f"{v:,.2f}" for v in trend.values)
        if trend.direction == "unusual":
            findings.append(
                RootCauseFinding(
                    area="Trend",
                    symptom=f"{trend.label} jumped unusually vs. recent refreshes.",
                    root_cause="One-off event (load, filter or process change) rather than gradual drift.",
                    evidence=f"Recent values: {values_str}; latest step is an outlier.",
                    recommendation="Check what changed in this refresh's load or source process.",
                    method=METHOD_RULE_TREE,
                    severity="Medium",
                    path=["Trend direction = unusual"],
                )
            )
            continue
        good = higher_is_better.get(trend.metric_key)
        worsening = (trend.direction == "decreasing" and good is True) or (
            trend.direction == "increasing" and good is False
        )
        if worsening and trend.follows_recent_trend:
            findings.append(
                RootCauseFinding(
                    area="Trend",
                    symptom=f"{trend.label} has been getting worse across recent refreshes.",
                    root_cause="Gradual drift: an upstream process is degrading over time.",
                    evidence=f"Recent values: {values_str}; this refresh continues the trend.",
                    recommendation="Assign an owner to the upstream process before the metric breaches threshold.",
                    method=METHOD_RULE_TREE,
                    severity="Medium",
                    path=[f"Trend direction = {trend.direction}", "Current refresh follows the trend"],
                )
            )
    return findings


def rule_based_root_causes(
    facts: "DashboardFacts", trends: Optional[Sequence[TrendResult]] = None
) -> list[RootCauseFinding]:
    """Walk every dashboard finding through the hand-authored decision tree."""
    findings: list[RootCauseFinding] = []
    for branch in (_zdel_branch, _renewal_branch, _tier2_branch, _business_case_branch, _errored_checks_branch):
        finding = branch(facts)
        if finding is not None:
            findings.append(finding)
    findings.extend(_trend_branch(trends or []))
    return findings


# ---------------------------------------------------------------------------
# 2. Learned decision tree (row-level segments)
# ---------------------------------------------------------------------------


def _candidate_features(df: pd.DataFrame, exclude: Sequence[str]) -> pd.DataFrame:
    """Low-cardinality categorical columns, as clean strings."""
    excluded = {str(col) for col in exclude}
    selected: dict[str, pd.Series] = {}
    row_count = len(df)
    for column in df.columns:
        if str(column) in excluded:
            continue
        series = df[column]
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            continue
        if pd.api.types.is_datetime64_any_dtype(series):
            continue
        cleaned = series.astype("string").str.strip().replace("", pd.NA).fillna("(blank)")
        distinct = cleaned.nunique()
        if distinct < 2 or distinct > _MAX_CATEGORIES or distinct > 0.5 * row_count:
            continue
        selected[str(column)] = cleaned.astype(str)
        if len(selected) >= _MAX_FEATURE_COLUMNS:
            break
    return pd.DataFrame(selected, index=df.index)


def _one_hot(features: pd.DataFrame) -> tuple[np.ndarray, list[tuple[str, str]]]:
    """One-hot encode; returns the matrix and (column, value) per feature."""
    blocks: list[np.ndarray] = []
    names: list[tuple[str, str]] = []
    for column in features.columns:
        series = features[column]
        for value in sorted(series.unique()):
            blocks.append((series == value).to_numpy(dtype=np.uint8))
            names.append((column, value))
    return np.column_stack(blocks), names


def _leaf_conditions(
    tree, feature_names: list[tuple[str, str]], categories: dict[str, list[str]], leaf: int
) -> list[str]:
    left = tree.children_left
    right = tree.children_right
    parent: dict[int, tuple[int, bool]] = {}
    for node in range(tree.node_count):
        if left[node] != -1:
            parent[left[node]] = (node, False)
            parent[right[node]] = (node, True)

    # One-hot features split at 0.5: right branch means "column = value".
    positive: dict[str, str] = {}
    negative: dict[str, list[str]] = {}
    node = leaf
    while node in parent:
        parent_node, is_right = parent[node]
        column, value = feature_names[tree.feature[parent_node]]
        if is_right:
            positive[column] = value
        else:
            negative.setdefault(column, []).append(value)
        node = parent_node

    conditions = [f"{column} = {value}" for column, value in positive.items()]
    for column, values in negative.items():
        if column in positive:
            continue
        excluded = set(values)
        remaining = [value for value in categories.get(column, []) if value not in excluded]
        if len(remaining) == 1:
            conditions.append(f"{column} = {remaining[0]}")
        else:
            conditions.append(f"{column} is not {' / '.join(sorted(excluded))}")
    return conditions


def learned_segment_root_causes(
    quality_report: Optional[QualityReport],
    quality_df: Optional[pd.DataFrame],
    *,
    max_checks: int = 5,
    max_findings_per_check: int = 2,
) -> list[RootCauseFinding]:
    """Train a shallow decision tree per failing check to find the row
    segments most associated with its failures. Never raises."""
    if quality_report is None or quality_df is None or quality_df.empty:
        return []

    try:
        from sklearn.tree import DecisionTreeClassifier
    except ImportError:
        return []

    row_count = len(quality_df)
    failing = sorted(
        (
            result
            for result in quality_report.results
            if result.error is None
            and len(result.failed_index)
            and _MIN_FAILURES <= result.failed_count < row_count
        ),
        key=lambda result: result.failed_count,
        reverse=True,
    )[:max_checks]

    findings: list[RootCauseFinding] = []
    min_leaf = max(_MIN_LEAF_ROWS, int(row_count * _MIN_LEAF_FRACTION))

    for result in failing:
        try:
            findings.extend(
                _segments_for_check(
                    DecisionTreeClassifier, result, quality_df, min_leaf, max_findings_per_check
                )
            )
        except (ValueError, TypeError, MemoryError):
            continue
    return findings


def _segments_for_check(tree_cls, result, df: pd.DataFrame, min_leaf: int, limit: int) -> list[RootCauseFinding]:
    target = np.asarray(df.index.isin(pd.Index(result.failed_index)), dtype=int)
    total_failures = int(target.sum())
    row_count = len(df)
    if total_failures < _MIN_FAILURES or total_failures == row_count or row_count < 2 * min_leaf:
        return []

    features = _candidate_features(df, exclude=result.columns)
    if features.empty:
        return []
    matrix, feature_names = _one_hot(features)
    categories: dict[str, list[str]] = {}
    for column, value in feature_names:
        categories.setdefault(column, []).append(value)

    model = tree_cls(
        max_depth=_MAX_DEPTH,
        min_samples_leaf=min_leaf,
        class_weight="balanced",
        random_state=_RANDOM_STATE,
    )
    model.fit(matrix, target)
    if model.tree_.node_count <= 1:
        return []

    leaves = model.apply(matrix)
    baseline = total_failures / row_count
    candidates = []
    for leaf in np.unique(leaves):
        in_leaf = leaves == leaf
        leaf_rows = int(in_leaf.sum())
        leaf_failures = int(target[in_leaf].sum())
        if leaf_failures < _MIN_FAILURES:
            continue
        rate = leaf_failures / leaf_rows
        lift = rate / baseline
        coverage = leaf_failures / total_failures
        if lift < _MIN_LIFT or coverage < _MIN_COVERAGE:
            continue
        conditions = _leaf_conditions(model.tree_, feature_names, categories, int(leaf))
        if not conditions:
            continue
        candidates.append((leaf_failures, rate, lift, coverage, conditions))

    candidates.sort(key=lambda item: item[0], reverse=True)
    findings = []
    for leaf_failures, rate, lift, coverage, conditions in candidates[:limit]:
        segment = " AND ".join(conditions)
        severity = "High" if coverage >= _HIGH_COVERAGE and lift >= _HIGH_LIFT else "Medium"
        findings.append(
            RootCauseFinding(
                area="Data Quality",
                symptom=(
                    f"{result.label} failed on {total_failures:,} of {row_count:,} rows "
                    f"({baseline:.1%})."
                ),
                root_cause=f"Failures are most associated with the segment: {segment}.",
                evidence=(
                    f"{coverage:.0%} of failures ({leaf_failures:,} rows) fall in this segment; "
                    f"failure rate {rate:.1%} vs {baseline:.1%} overall ({lift:.1f}x). "
                    "This is a statistical association, not a proven cause."
                ),
                recommendation=(
                    f"Review how {result.column_label} is populated for records where {segment}."
                ),
                method=METHOD_LEARNED_TREE,
                severity=severity,
                path=conditions,
            )
        )
    return findings
