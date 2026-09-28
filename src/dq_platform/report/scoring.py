"""Top-level KPI computation for the hybrid dashboard report.

Combines a :class:`QualityReport` (Data Quality flow) and a
:class:`RevenueComparisonReport` (Revenue Validation flow) into the four
headline metrics shown at the top of the dashboard: Total Test Cases, Data
Quality Score, Validation Score and Critical.

The dashboard tracks 6 named checks:
  - Renewal Quote Check                         (Validation)
  - Revenue Validation (ZDEL)                    (Validation)
  - Missing Tier 2 Reseller (Indirect Channel)   (Validation)
  - Business Case Validation (Multiyear Flag)    (Data Quality)
  - Date & Renewal Consistency Check             (Data Quality)
  - Data Completeness Validation (Status)        (Data Quality)

A check "passes" when it shows zero bad/failing rows. A check is excluded
from the totals (``None``) when the columns it depends on are entirely
missing from the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from dq_platform.comparison import RevenueComparisonReport
from dq_platform.models import QualityReport
from dq_platform.report import dashboard

# Severity thresholds are intentionally centralized here so they are easy to
# tune without touching the report layout code.
CRITICAL_TIER2_MISSING_PCT = 20.0


@dataclass
class DashboardKpis:
    # Legacy fields (kept for the AI Insights narrative, which reads these
    # by name); derived from the QualityReport rule results and the 3
    # revenue checks.
    dq_score_pct: float
    dq_checks_passed: int
    dq_checks_total: int
    validation_passed: int
    validation_total: int
    revenue_checks_passed: int
    revenue_checks_total: int
    # Critical count now spans all 6 named checks (see module docstring),
    # not just errored DQ rules + failed revenue checks.
    critical_count: int

    # New fields backing the 4 headline KPI cards.
    total_test_cases: int
    total_test_cases_passed: int
    dq_subset_passed: int
    dq_subset_total: int
    validation_subset_passed: int
    validation_subset_total: int


def _revenue_check_results(report: RevenueComparisonReport) -> list[bool]:
    """True == passed, for each of the three revenue/validation checks."""
    tier2_ok = report.indirect_missing_tier2_count == 0
    zdel_ok = not report.zdel_threshold_exceeded
    renewal_ok = not report.renewal_threshold_exceeded
    return [tier2_ok, zdel_ok, renewal_ok]


def _date_renewal_consistency_ok(df: Optional[pd.DataFrame]) -> Optional[bool]:
    """Pass when start<=end, end+1==renewal and the 3 renewal columns are
    fully populated. ``None`` when no relevant date columns are present."""
    if df is None or df.empty:
        return None

    found_any = False
    failed_any = False

    if dashboard._find_column(df, dashboard._START_DATE_CANDIDATES) is not None:
        found_any = True
        _, failed = dashboard._start_after_end_check(df)
        failed_any = failed_any or failed > 0

    if dashboard._find_column(df, dashboard._END_DATE_CANDIDATES) is not None:
        found_any = True
        _, failed = dashboard._end_plus_one_renewal_check(df)
        failed_any = failed_any or failed > 0

    for candidates in (
        dashboard._RENEWAL_MONTH_CANDIDATES,
        dashboard._RENEWAL_QUARTER_CANDIDATES,
        dashboard._RENEWAL_FISCAL_YEAR_CANDIDATES,
    ):
        result = dashboard._column_blank_check(df, candidates)
        if result is None:
            continue
        found_any = True
        _, failed = result
        failed_any = failed_any or failed > 0

    if not found_any:
        return None
    return not failed_any


def _data_completeness_ok(
    df: Optional[pd.DataFrame], quality_error: Optional[str]
) -> Optional[bool]:
    """Pass when every configured completeness field has 0% blank rows.
    ``None`` when no relevant fields are present in the data."""
    if quality_error:
        return False
    counts = dashboard._data_completeness_blank_counts(df)
    if not counts:
        return None
    return all(pct == 0 for _, pct in counts)


def _named_check_results(
    quality_df: Optional[pd.DataFrame],
    quality_error: Optional[str],
    revenue_report: RevenueComparisonReport,
) -> list[tuple[str, Optional[bool]]]:
    """Ordered (check name, passed) for all 6 named checks. ``passed`` is
    ``None`` when the check is not applicable (required columns missing)."""
    business_case_violations = dashboard._multiyear_flag_violation_count(quality_df)
    business_case_ok = None if business_case_violations is None else business_case_violations == 0

    return [
        ("Renewal Quote Check", not revenue_report.renewal_threshold_exceeded),
        ("Revenue Validation (ZDEL)", not revenue_report.zdel_threshold_exceeded),
        (
            "Missing Tier 2 Reseller (Indirect Channel)",
            revenue_report.indirect_missing_tier2_count == 0,
        ),
        ("Business Case Validation", business_case_ok),
        ("Date & Renewal Consistency Check", _date_renewal_consistency_ok(quality_df)),
        ("Data Completeness Validation (Status)", _data_completeness_ok(quality_df, quality_error)),
    ]


def compute_dashboard_kpis(
    quality_report: Optional[QualityReport],
    revenue_report: RevenueComparisonReport,
    quality_df: Optional[pd.DataFrame] = None,
    quality_error: Optional[str] = None,
) -> DashboardKpis:
    dq_checks_total = quality_report.total_checks if quality_report is not None else 0
    dq_checks_passed = quality_report.passed_checks if quality_report is not None else 0
    dq_score_pct = quality_report.dq_score_pct if quality_report is not None else 0.0

    revenue_results = _revenue_check_results(revenue_report)
    revenue_checks_passed = sum(1 for ok in revenue_results if ok)
    revenue_checks_total = len(revenue_results)

    validation_passed = dq_checks_passed + revenue_checks_passed
    validation_total = dq_checks_total + revenue_checks_total

    named_results = _named_check_results(quality_df, quality_error, revenue_report)
    applicable = [(name, ok) for name, ok in named_results if ok is not None]
    total_test_cases = len(applicable)
    total_test_cases_passed = sum(1 for _, ok in applicable if ok)
    critical_count = sum(1 for _, ok in applicable if not ok)

    validation_names = {
        "Renewal Quote Check",
        "Revenue Validation (ZDEL)",
        "Missing Tier 2 Reseller (Indirect Channel)",
    }
    validation_subset = [ok for name, ok in applicable if name in validation_names]
    dq_subset = [ok for name, ok in applicable if name not in validation_names]

    return DashboardKpis(
        dq_score_pct=dq_score_pct,
        dq_checks_passed=dq_checks_passed,
        dq_checks_total=dq_checks_total,
        validation_passed=validation_passed,
        validation_total=validation_total,
        revenue_checks_passed=revenue_checks_passed,
        revenue_checks_total=revenue_checks_total,
        critical_count=critical_count,
        total_test_cases=total_test_cases,
        total_test_cases_passed=total_test_cases_passed,
        dq_subset_passed=sum(1 for ok in dq_subset if ok),
        dq_subset_total=len(dq_subset),
        validation_subset_passed=sum(1 for ok in validation_subset if ok),
        validation_subset_total=len(validation_subset),
    )
