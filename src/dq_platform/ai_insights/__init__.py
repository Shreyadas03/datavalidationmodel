"""AI Insights layer: data quality narrative, trend and root cause analysis.

This package is purely additive: it reads already-computed validation
results/KPIs, maintains a local history log, performs deterministic
statistical trend analysis, and explains failures with decision-tree root
cause analysis (a rule-based tree plus a tree learned from row-level data).
No external AI service is called. It never modifies or recomputes any
existing validation/rule logic.
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
    InsightsNarrative,
    generate_narrative,
)
from dq_platform.ai_insights.root_cause import (
    RootCauseFinding,
    learned_segment_root_causes,
    rule_based_root_causes,
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
    "InsightsNarrative",
    "generate_narrative",
    "RootCauseFinding",
    "rule_based_root_causes",
    "learned_segment_root_causes",
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
