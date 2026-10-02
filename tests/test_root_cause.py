import numpy as np
import pandas as pd

from dq_platform.ai_insights.dashboard_summary import (
    DashboardFacts,
    build_dashboard_summary_section_html,
    generate_dashboard_summary,
)
from dq_platform.ai_insights.root_cause import (
    METHOD_LEARNED_TREE,
    METHOD_RULE_TREE,
    learned_segment_root_causes,
    rule_based_root_causes,
)
from dq_platform.ai_insights.trend import TrendResult
from dq_platform.models import QualityReport, RuleResult


def _facts(**overrides) -> DashboardFacts:
    base = dict(
        dq_checks_total=10,
        dq_checks_passed=10,
        dq_checks_failed=0,
        dq_checks_errored=0,
        dq_score_pct=100.0,
        zdel_document_type="ZDEL",
        zdel_old_sum=1_000_000.0,
        zdel_new_sum=1_010_000.0,
        zdel_delta_pct=1.0,
        zdel_threshold_pct=5.0,
        zdel_threshold_exceeded=False,
        indirect_row_count=100,
        indirect_missing_tier2_count=0,
        tier2_missing_pct=0.0,
        tier2_severity="Low",
        renewal_old_missing_pct=1.0,
        renewal_new_missing_pct=1.0,
        renewal_threshold_pct=5.0,
        renewal_threshold_exceeded=False,
        business_case_violations=0,
        validation_passed=5,
        validation_total=5,
        critical_count=0,
        old_row_count=1000,
        new_row_count=1000,
    )
    base.update(overrides)
    return DashboardFacts(**base)


def _single(findings, area):
    matches = [f for f in findings if f.area == area]
    assert len(matches) == 1, findings
    return matches[0]


def test_clean_facts_produce_no_root_causes():
    assert rule_based_root_causes(_facts()) == []


def test_zdel_volume_change_branch():
    facts = _facts(
        zdel_threshold_exceeded=True, zdel_delta_pct=-20.0, zdel_new_sum=800_000.0,
        old_row_count=1000, new_row_count=820,
    )
    finding = _single(rule_based_root_causes(facts), "Revenue Validation")
    assert finding.method == METHOD_RULE_TREE
    assert "Volume change" in finding.root_cause


def test_zdel_per_record_value_branch():
    facts = _facts(zdel_threshold_exceeded=True, zdel_delta_pct=15.0, zdel_new_sum=1_150_000.0)
    finding = _single(rule_based_root_causes(facts), "Revenue Validation")
    assert "Per-record value change" in finding.root_cause


def test_zdel_non_numeric_branch_takes_priority():
    facts = _facts(
        zdel_threshold_exceeded=True, zdel_delta_pct=-30.0,
        old_non_numeric_revenue_count=0, new_non_numeric_revenue_count=50,
        old_row_count=1000, new_row_count=700,
    )
    finding = _single(rule_based_root_causes(facts), "Revenue Validation")
    assert "Load/format issue" in finding.root_cause


def test_zdel_no_baseline_branch():
    facts = _facts(zdel_threshold_exceeded=True, zdel_old_sum=0.0, zdel_delta_pct=None)
    finding = _single(rule_based_root_causes(facts), "Revenue Validation")
    assert "No baseline" in finding.root_cause


def test_renewal_branches():
    regression = _single(
        rule_based_root_causes(_facts(renewal_threshold_exceeded=True, renewal_new_missing_pct=12.0)),
        "Revenue Validation",
    )
    assert "Regression" in regression.root_cause

    systemic = _single(
        rule_based_root_causes(
            _facts(renewal_threshold_exceeded=True, renewal_old_missing_pct=9.0, renewal_new_missing_pct=12.0)
        ),
        "Revenue Validation",
    )
    assert "Systemic" in systemic.root_cause


def test_tier2_regional_vs_channel_wide():
    regional = _single(
        rule_based_root_causes(
            _facts(
                indirect_missing_tier2_count=40, tier2_missing_pct=40.0, tier2_severity="High",
                tier2_top_geography="APJ", tier2_top_geography_share=0.7,
            )
        ),
        "Revenue Validation",
    )
    assert "APJ" in regional.root_cause

    spread = _single(
        rule_based_root_causes(
            _facts(
                indirect_missing_tier2_count=40, tier2_missing_pct=40.0, tier2_severity="Medium",
                tier2_top_geography="APJ", tier2_top_geography_share=0.3,
            )
        ),
        "Revenue Validation",
    )
    assert "Channel-wide" in spread.root_cause


def test_business_case_errored_and_trend_branches():
    trends = [
        TrendResult("critical_count", "Critical Issues", "unusual", [1, 1, 2], False),
        TrendResult("tier2_missing_pct", "Tier 2 Reseller Missing %", "increasing", [1, 2, 3], True),
        TrendResult("dq_score_pct", "DQ Score %", "increasing", [90, 92, 94], True),
    ]
    findings = rule_based_root_causes(
        _facts(business_case_violations=3, dq_checks_errored=1), trends
    )
    areas = [f.area for f in findings]
    assert "Business Case Validation" in areas
    assert "Data Quality" in areas
    trend_causes = [f.root_cause for f in findings if f.area == "Trend"]
    assert any("One-off event" in cause for cause in trend_causes)
    assert any("Gradual drift" in cause for cause in trend_causes)
    # An improving metric (DQ score increasing) is not reported as drift.
    assert len(trend_causes) == 2


def _planted_dataset(rows: int = 600):
    rng = np.random.default_rng(7)
    df = pd.DataFrame(
        {
            "Customer ID": [f"C{i:05d}" for i in range(rows)],
            "Region": rng.choice(["AMS", "EMEA", "APJ"], size=rows),
            "Channel": rng.choice(["Direct", "Indirect"], size=rows),
            "Tier 2 reseller": "Partner",
            "Amount": rng.integers(100, 1000, size=rows),
        }
    )
    planted = (df["Region"] == "APJ") & (df["Channel"] == "Indirect")
    df.loc[planted, "Tier 2 reseller"] = None
    failed_index = df.index[df["Tier 2 reseller"].isna()]
    result = RuleResult(
        rule_id="completeness.not_blank",
        label="Blank values in Tier 2 reseller",
        dimension="Completeness",
        columns=["Tier 2 reseller"],
        total_rows=rows,
        failed_count=len(failed_index),
        failed_index=list(failed_index),
    )
    report = QualityReport(source_path="x.xlsx", sheet_name="Sheet1", row_count=rows,
                           column_count=len(df.columns), results=[result])
    return df, report


def test_learned_tree_finds_planted_segment():
    df, report = _planted_dataset()
    findings = learned_segment_root_causes(report, df)
    assert findings, "expected at least one learned segment"
    top = findings[0]
    assert top.method == METHOD_LEARNED_TREE
    assert "Region = APJ" in top.root_cause
    assert "Channel = Indirect" in top.root_cause
    # The rule's own column and the ID column must never be used as features.
    assert "Tier 2 reseller =" not in top.root_cause
    assert "Customer ID" not in top.root_cause


def test_learned_tree_skips_gracefully():
    df, report = _planted_dataset()
    assert learned_segment_root_causes(None, df) == []
    assert learned_segment_root_causes(report, None) == []
    assert learned_segment_root_causes(report, df.head(10)) == []
    only_target = df[["Tier 2 reseller"]]
    assert learned_segment_root_causes(report, only_target) == []


def test_summary_html_renders_root_causes_without_ai_service_note():
    facts = _facts(business_case_violations=2)
    summary = generate_dashboard_summary(facts, root_causes=rule_based_root_causes(facts))
    html = build_dashboard_summary_section_html(summary)
    assert "3. AI Insights: Dashboard Summary" in html
    assert "Root Cause Analysis (Decision Tree)" in html
    assert "Multiyear Flag derivation" in html
    assert "No external AI service" in html
