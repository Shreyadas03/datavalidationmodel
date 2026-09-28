"""AI-powered Data Quality Narrative & Trend Analysis layer.

This package is purely additive: it reads already-computed validation
results/KPIs, maintains a local history log, performs deterministic
statistical trend analysis, and (optionally) asks an AI model to phrase the
findings as a narrative. It never modifies or recomputes any existing
validation/rule logic.
"""

from dq_platform.ai_insights.history import (
    HistoryStore,
    MetricSnapshot,
    collect_metric_snapshot,
)
from dq_platform.ai_insights.dashboard_summary import (
    DashboardFacts,
    DashboardSummary,
    build_dashboard_summary_section_html,
    collect_dashboard_facts,
    generate_dashboard_summary,
)
from dq_platform.ai_insights.narrative import (
    AIConfig,
    InsightsNarrative,
    generate_narrative,
)
from dq_platform.ai_insights.trend import (
    MetricChange,
    TrendResult,
    build_trend_results,
    compare_to_previous,
)

__all__ = [
    "HistoryStore",
    "MetricSnapshot",
    "collect_metric_snapshot",
    "AIConfig",
    "InsightsNarrative",
    "generate_narrative",
    "MetricChange",
    "TrendResult",
    "build_trend_results",
    "compare_to_previous",
    "DashboardFacts",
    "DashboardSummary",
    "collect_dashboard_facts",
    "generate_dashboard_summary",
    "build_dashboard_summary_section_html",
]
