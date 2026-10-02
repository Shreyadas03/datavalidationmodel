"""Trend narrative for the AI Insights section.

Turns the current-vs-previous comparison and 3-month trend results from
:mod:`dq_platform.ai_insights.trend` into short, business-friendly text.
The wording is built deterministically from those calculated values -- no
external AI service is called, so the same inputs always produce the same
narrative. Root-cause reasoning lives in
:mod:`dq_platform.ai_insights.root_cause`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from dq_platform.ai_insights.history import MetricSnapshot
from dq_platform.ai_insights.trend import MetricChange, TrendResult

NARRATIVE_SOURCE = "decision_tree"


@dataclass
class InsightsNarrative:
    executive_summary: str
    current_scenario: str
    change_from_previous: str
    three_month_trend: str
    key_observations: list[str]
    areas_to_investigate: list[str]
    source: str = NARRATIVE_SOURCE


def _fmt(value: Optional[float], suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    return f"{value:,}{suffix}"


def generate_narrative(
    changes: list[MetricChange], trends: list[TrendResult], current: MetricSnapshot
) -> InsightsNarrative:
    """Build the trend narrative from calculated values only."""
    significant = [c for c in changes if c.significant]
    unusual = [t for t in trends if t.direction == "unusual"]
    # "unusual" trends already get their own dedicated bullet below; exclude
    # them here so a spike isn't reported twice under two different wordings.
    deviating = [
        t for t in trends if t.follows_recent_trend is False and t.direction != "unusual"
    ]

    executive_summary = (
        f"Current DQ Score is {_fmt(current.dq_score_pct, '%')} with "
        f"{current.critical_count} critical issue(s) flagged this refresh."
    )
    current_scenario = (
        f"{current.dq_checks_passed}/{current.dq_checks_total} data quality checks passed; "
        f"revenue total is {_fmt(current.revenue_new_sum)}; "
        f"Tier 2 reseller missing rate is {_fmt(current.tier2_missing_pct, '%')}; "
        f"renewal missing rate is {_fmt(current.renewal_new_missing_pct, '%')}."
    )
    if significant:
        change_from_previous = "Significant changes since the previous refresh: " + "; ".join(
            f"{c.label} moved {_fmt(c.percent_change, '%')}" for c in significant
        ) + "."
    else:
        change_from_previous = (
            "No metric changed by more than the significance threshold "
            "(10%) since the previous refresh."
        )
    if unusual:
        three_month_trend = "Unusual movement detected in: " + ", ".join(
            t.label for t in unusual
        ) + ". Other tracked metrics show typical increasing/decreasing/stable patterns."
    else:
        directional = [t for t in trends if t.direction in ("increasing", "decreasing")]
        insufficient = [t for t in trends if t.direction == "insufficient_data"]
        stable_or_fluctuating = [
            t for t in trends if t.direction in ("stable", "fluctuating")
        ]
        if directional:
            three_month_trend = "Over the recent months: " + "; ".join(
                f"{t.label} is {t.direction}" for t in directional
            ) + "."
        elif insufficient and not stable_or_fluctuating:
            three_month_trend = (
                "Not enough historical refreshes are logged yet (fewer than 2 prior "
                "months of data) to establish a 3-month trend for the tracked metrics."
            )
        else:
            three_month_trend = (
                "Tracked metrics are stable or fluctuating without a clear "
                "directional trend over the recent months."
            )

    key_observations = [
        f"{c.label}: {_fmt(c.previous_value)} -> {_fmt(c.current_value)} "
        f"({_fmt(c.percent_change, '%')})"
        for c in significant
    ] or ["No individually significant metric changes this refresh."]

    areas_to_investigate = [
        f"{t.label}: current change deviates from the established {t.direction} trend."
        for t in deviating
    ] + [f"{t.label}: unusual movement vs. recent history." for t in unusual]
    if not areas_to_investigate:
        areas_to_investigate = ["No metrics currently deviate from their recent trend."]

    return InsightsNarrative(
        executive_summary=executive_summary,
        current_scenario=current_scenario,
        change_from_previous=change_from_previous,
        three_month_trend=three_month_trend,
        key_observations=key_observations,
        areas_to_investigate=areas_to_investigate,
    )
