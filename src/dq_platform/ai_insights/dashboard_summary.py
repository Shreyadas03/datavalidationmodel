"""Whole-dashboard AI narrative summary.

This module produces a single, business-friendly summary of *everything*
the combined report is doing/found -- Data Quality checks, Revenue
Validation (ZDEL / Tier 2 Reseller / Renewal Quote), and Business Case
(Multiyear Flag) validation -- as opposed to
:mod:`dq_platform.ai_insights.narrative`, which only narrates the
current-vs-previous / 3-month trend comparison.

Same design rules as the trend narrative:
 - Every fact comes from already-computed report/KPI objects. Nothing here
   re-implements or changes the underlying validation logic.
 - AI (when configured) is used only to phrase the summary; the prompt is
   built strictly from the facts below and instructs the model never to
   invent numbers or root causes.
 - Falls back to a deterministic, template-built summary when the AI
   backend is unconfigured or unavailable -- report generation is never
   blocked by AI availability.
"""

from __future__ import annotations

import html as html_lib
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from dq_platform.ai_insights.narrative import AIConfig, InsightsNarrative, _call_chat_completions
from dq_platform.comparison import RevenueComparisonReport
from dq_platform.models import QualityReport
from dq_platform.report.scoring import DashboardKpis


@dataclass
class DashboardFacts:
    """Every already-computed fact needed for a whole-dashboard summary."""

    # Data Quality
    dq_checks_total: int
    dq_checks_passed: int
    dq_checks_failed: int
    dq_checks_errored: int
    dq_score_pct: float

    # Revenue Validation -- ZDEL revenue check
    zdel_document_type: str
    zdel_old_sum: float
    zdel_new_sum: float
    zdel_delta_pct: Optional[float]
    zdel_threshold_pct: float
    zdel_threshold_exceeded: bool

    # Revenue Validation -- Missing Tier 2 Reseller (indirect channel)
    indirect_row_count: int
    indirect_missing_tier2_count: int
    tier2_missing_pct: float
    tier2_severity: str

    # Revenue Validation -- Renewal Quote completeness
    renewal_old_missing_pct: float
    renewal_new_missing_pct: float
    renewal_threshold_pct: float
    renewal_threshold_exceeded: bool

    # Business Case Validation -- Multiyear Flag
    business_case_violations: Optional[int]

    # Overall
    validation_passed: int
    validation_total: int
    critical_count: int


def collect_dashboard_facts(
    quality_report: Optional[QualityReport],
    revenue_report: RevenueComparisonReport,
    kpis: DashboardKpis,
    quality_df: Optional[pd.DataFrame],
) -> DashboardFacts:
    """Build :class:`DashboardFacts` purely from already-computed values."""
    from dq_platform.report.dashboard import _multiyear_flag_violation_count

    dq_checks_failed = (
        quality_report.failed_checks if quality_report is not None else 0
    )
    dq_checks_errored = (
        quality_report.errored_checks if quality_report is not None else 0
    )

    return DashboardFacts(
        dq_checks_total=kpis.dq_checks_total,
        dq_checks_passed=kpis.dq_checks_passed,
        dq_checks_failed=dq_checks_failed,
        dq_checks_errored=dq_checks_errored,
        dq_score_pct=kpis.dq_score_pct,
        zdel_document_type=revenue_report.zdel_document_type_value,
        zdel_old_sum=revenue_report.zdel_old_sum,
        zdel_new_sum=revenue_report.zdel_new_sum,
        zdel_delta_pct=revenue_report.zdel_delta_pct,
        zdel_threshold_pct=revenue_report.zdel_threshold_pct,
        zdel_threshold_exceeded=revenue_report.zdel_threshold_exceeded,
        indirect_row_count=revenue_report.indirect_row_count,
        indirect_missing_tier2_count=revenue_report.indirect_missing_tier2_count,
        tier2_missing_pct=revenue_report.tier2_missing_pct,
        tier2_severity=revenue_report.tier2_severity,
        renewal_old_missing_pct=revenue_report.renewal_old_missing_pct,
        renewal_new_missing_pct=revenue_report.renewal_new_missing_pct,
        renewal_threshold_pct=revenue_report.renewal_threshold_pct,
        renewal_threshold_exceeded=revenue_report.renewal_threshold_exceeded,
        business_case_violations=_multiyear_flag_violation_count(quality_df),
        validation_passed=kpis.validation_passed,
        validation_total=kpis.validation_total,
        critical_count=kpis.critical_count,
    )


@dataclass
class DashboardSummary:
    overview: str
    data_quality_summary: str
    revenue_validation_summary: str
    business_case_summary: str
    key_risks: list[str]
    source: str  # "ai" or "fallback"


def _fmt(value, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    return f"{value:,}{suffix}"


def _fmt_millions(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value / 1_000_000:,.2f}M"


def build_dashboard_summary_prompt(facts: DashboardFacts) -> str:
    """Assemble a strict, numbers-only prompt covering the whole dashboard."""
    return (
        "You are a data quality analyst writing a concise, business-friendly "
        "overview of an entire validation dashboard for a business "
        "stakeholder. Use ONLY the numbers provided below. Do not invent any "
        "figures, root causes, or facts that are not explicitly stated. If "
        "information is insufficient, say so plainly.\n\n"
        "Data Quality checks:\n"
        f"- Checks passed: {facts.dq_checks_passed}/{facts.dq_checks_total} "
        f"(DQ Score {_fmt(facts.dq_score_pct, '%')})\n"
        f"- Checks failed: {facts.dq_checks_failed}\n"
        f"- Checks errored: {facts.dq_checks_errored}\n\n"
        "Revenue Validation:\n"
        f"- {facts.zdel_document_type} revenue: {_fmt_millions(facts.zdel_old_sum)} -> "
        f"{_fmt_millions(facts.zdel_new_sum)} ({_fmt(facts.zdel_delta_pct, '%')} change; "
        f"threshold {_fmt(facts.zdel_threshold_pct, '%')}; "
        f"{'EXCEEDED' if facts.zdel_threshold_exceeded else 'within threshold'})\n"
        f"- Missing Tier 2 Reseller (indirect channel): {facts.indirect_missing_tier2_count} "
        f"of {facts.indirect_row_count} indirect rows missing "
        f"({_fmt(facts.tier2_missing_pct, '%')}, severity {facts.tier2_severity})\n"
        f"- Renewal Quote completeness: old missing {_fmt(facts.renewal_old_missing_pct, '%')}, "
        f"new missing {_fmt(facts.renewal_new_missing_pct, '%')} "
        f"(threshold {_fmt(facts.renewal_threshold_pct, '%')}; "
        f"{'EXCEEDED' if facts.renewal_threshold_exceeded else 'within threshold'})\n\n"
        "Business Case Validation:\n"
        f"- Multiyear Flag violations (Months Duration > 12 but Flag != X): "
        f"{_fmt(facts.business_case_violations)}\n\n"
        "Overall:\n"
        f"- Validation checks passed: {facts.validation_passed}/{facts.validation_total}\n"
        f"- Critical issues flagged: {facts.critical_count}\n\n"
        "Respond as compact JSON with exactly these keys: "
        "overview (1-2 sentences summarizing the whole dashboard), "
        "data_quality_summary (1-2 sentences), "
        "revenue_validation_summary (2-3 sentences covering ZDEL/Tier 2/Renewal), "
        "business_case_summary (1-2 sentences), "
        "key_risks (array of short strings, empty array if none). "
        "No markdown, no extra keys, no commentary outside the JSON object."
    )


def _fallback_dashboard_summary(facts: DashboardFacts) -> DashboardSummary:
    """Deterministic, template-built whole-dashboard summary -- used whenever
    the AI call is unavailable, unconfigured, or fails."""
    overview = (
        f"{facts.validation_passed}/{facts.validation_total} validation checks passed "
        f"this refresh, with {facts.critical_count} critical issue(s) flagged across "
        "Data Quality, Revenue Validation and Business Case checks."
    )

    data_quality_summary = (
        f"{facts.dq_checks_passed}/{facts.dq_checks_total} data quality checks passed "
        f"(DQ Score {_fmt(facts.dq_score_pct, '%')}), with {facts.dq_checks_failed} failed "
        f"and {facts.dq_checks_errored} errored."
    )

    revenue_parts = [
        f"{facts.zdel_document_type} revenue moved from {_fmt_millions(facts.zdel_old_sum)} "
        f"to {_fmt_millions(facts.zdel_new_sum)} ({_fmt(facts.zdel_delta_pct, '%')}), "
        + ("exceeding" if facts.zdel_threshold_exceeded else "within")
        + f" the {_fmt(facts.zdel_threshold_pct, '%')} threshold.",
        f"Missing Tier 2 Reseller affects {facts.indirect_missing_tier2_count} of "
        f"{facts.indirect_row_count} indirect-channel rows "
        f"({_fmt(facts.tier2_missing_pct, '%')}, {facts.tier2_severity} severity).",
        f"Renewal Quote completeness is {_fmt(facts.renewal_new_missing_pct, '%')} missing "
        f"(previously {_fmt(facts.renewal_old_missing_pct, '%')}), "
        + ("exceeding" if facts.renewal_threshold_exceeded else "within")
        + f" the {_fmt(facts.renewal_threshold_pct, '%')} threshold.",
    ]
    revenue_validation_summary = " ".join(revenue_parts)

    if facts.business_case_violations is None:
        business_case_summary = (
            "Business Case (Multiyear Flag) validation could not be evaluated -- "
            "required columns were not found in this dataset."
        )
    elif facts.business_case_violations == 0:
        business_case_summary = (
            "No Business Case violations found: every row with Months Duration > 12 "
            "has the Multiyear Flag correctly set."
        )
    else:
        business_case_summary = (
            f"{facts.business_case_violations} row(s) have Months Duration > 12 "
            "without the Multiyear Flag set, violating the Business Case rule."
        )

    key_risks: list[str] = []
    if facts.zdel_threshold_exceeded:
        key_risks.append(
            f"{facts.zdel_document_type} revenue change of "
            f"{_fmt(facts.zdel_delta_pct, '%')} exceeds the "
            f"{_fmt(facts.zdel_threshold_pct, '%')} threshold."
        )
    if facts.renewal_threshold_exceeded:
        key_risks.append(
            f"Renewal Quote missing rate of {_fmt(facts.renewal_new_missing_pct, '%')} "
            f"exceeds the {_fmt(facts.renewal_threshold_pct, '%')} threshold."
        )
    if facts.tier2_severity.lower() not in ("low", ""):
        key_risks.append(
            f"Missing Tier 2 Reseller severity is {facts.tier2_severity} "
            f"({_fmt(facts.tier2_missing_pct, '%')} of indirect rows)."
        )
    if facts.business_case_violations:
        key_risks.append(
            f"{facts.business_case_violations} Business Case (Multiyear Flag) violation(s) "
            "need review."
        )
    if facts.dq_checks_errored:
        key_risks.append(
            f"{facts.dq_checks_errored} data quality check(s) errored and could not be evaluated."
        )

    return DashboardSummary(
        overview=overview,
        data_quality_summary=data_quality_summary,
        revenue_validation_summary=revenue_validation_summary,
        business_case_summary=business_case_summary,
        key_risks=key_risks,
        source="fallback",
    )


def generate_dashboard_summary(
    facts: DashboardFacts, *, config: Optional[AIConfig] = None
) -> DashboardSummary:
    """Generate the whole-dashboard AI narrative summary, falling back to a
    deterministic template if the AI backend is unconfigured or unavailable."""
    config = config or AIConfig.from_env()
    fallback = _fallback_dashboard_summary(facts)

    if not config.enabled:
        return fallback

    prompt = build_dashboard_summary_prompt(facts)
    ai_payload = _call_chat_completions(config, prompt)
    if not ai_payload:
        return fallback

    try:
        return DashboardSummary(
            overview=str(ai_payload.get("overview") or fallback.overview),
            data_quality_summary=str(
                ai_payload.get("data_quality_summary") or fallback.data_quality_summary
            ),
            revenue_validation_summary=str(
                ai_payload.get("revenue_validation_summary")
                or fallback.revenue_validation_summary
            ),
            business_case_summary=str(
                ai_payload.get("business_case_summary") or fallback.business_case_summary
            ),
            key_risks=list(ai_payload.get("key_risks") or fallback.key_risks),
            source="ai",
        )
    except (TypeError, ValueError):
        return fallback


def _risk_chips_html(risks: list[str]) -> str:
    if not risks:
        return '<span class="risk-chip risk-chip-ok">No key risks identified this refresh.</span>'
    return "".join(
        f'<span class="risk-chip">{html_lib.escape(str(risk))}</span>' for risk in risks
    )


def _list_html(items: list[str]) -> str:
    if not items:
        return "<li>None.</li>"
    return "".join(f"<li>{html_lib.escape(str(item))}</li>" for item in items)


def build_dashboard_summary_section_html(
    summary: DashboardSummary, narrative: Optional[InsightsNarrative] = None
) -> str:
    """Render the whole-dashboard AI summary as an HTML fragment.

    When ``narrative`` (an :class:`~dq_platform.ai_insights.narrative.InsightsNarrative`)
    is provided, its current-vs-previous / 3-month trend content is folded
    into this same section (Change from Previous Refresh, 3-Month Trend,
    Key Observations, Areas to Investigate) instead of being rendered as a
    separate section elsewhere in the report.

    Expects the CSS classes ``.dash-summary-card``, ``.dash-summary-title``,
    ``.dash-summary-grid``, ``.dash-summary-block`` and ``.risk-chip`` to be
    defined by the caller's stylesheet (added to ``hybrid.py``'s existing
    ``<style>`` block).
    """
    source_note = (
        "AI-generated overview of the full dashboard."
        if summary.source == "ai"
        else "Deterministic overview (AI backend not configured or unavailable) "
        "based on the same calculated results."
    )

    trend_html = ""
    if narrative is not None:
        trend_html = f"""
  <div class="dash-summary-grid">
    <div class="dash-summary-block">
      <div class="dash-summary-title">Change from Previous Refresh</div>
      <p>{html_lib.escape(narrative.change_from_previous)}</p>
    </div>
    <div class="dash-summary-block">
      <div class="dash-summary-title">3-Month Trend</div>
      <p>{html_lib.escape(narrative.three_month_trend)}</p>
    </div>
  </div>
  <div class="dash-summary-grid">
    <div class="dash-summary-block">
      <div class="dash-summary-title">Key Observations</div>
      <ul>{_list_html(narrative.key_observations)}</ul>
    </div>
    <div class="dash-summary-block">
      <div class="dash-summary-title">Areas to Investigate</div>
      <ul>{_list_html(narrative.areas_to_investigate)}</ul>
    </div>
  </div>"""

    return f"""
  <h2>3. AI Insights: Dashboard Summary</h2>
  <p class="subtle">{html_lib.escape(source_note)}</p>
  <div class="dash-summary-card">
    <div class="dash-summary-title">Executive Overview</div>
    <p>{html_lib.escape(summary.overview)}</p>
  </div>
  <div class="dash-summary-grid">
    <div class="dash-summary-block">
      <div class="dash-summary-title">Data Quality</div>
      <p>{html_lib.escape(summary.data_quality_summary)}</p>
    </div>
    <div class="dash-summary-block">
      <div class="dash-summary-title">Revenue Validation</div>
      <p>{html_lib.escape(summary.revenue_validation_summary)}</p>
    </div>
    <div class="dash-summary-block">
      <div class="dash-summary-title">Business Case Validation</div>
      <p>{html_lib.escape(summary.business_case_summary)}</p>
    </div>
  </div>
  {trend_html}
  <div class="dash-summary-card">
    <div class="dash-summary-title">Key Risks</div>
    <div class="risk-chip-row">{_risk_chips_html(summary.key_risks)}</div>
  </div>
"""
