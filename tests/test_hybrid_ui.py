import pandas as pd

from dq_platform import build_hybrid_ui
from dq_platform.comparison import RevenueComparisonReport
from dq_platform.models import QualityReport, RuleResult
from dq_platform.report import dashboard
from dq_platform.report.hybrid import write_hybrid_combined_html
from openpyxl import load_workbook
from dq_platform.ui.hybrid_widgets import HybridValidationApp
from dq_platform.ui.revenue_comparison_widgets import RevenueValidationApp
from dq_platform.ui.widgets import DataQualityApp


def _fake_quality_report() -> QualityReport:
    return QualityReport(
        source_path="sample.xlsx",
        sheet_name="Contracts",
        row_count=2,
        column_count=3,
        results=[
            RuleResult(
                rule_id="completeness.not_blank",
                label="Not blank",
                dimension="Completeness",
                columns=["A"],
                total_rows=2,
                failed_count=0,
                message="ok",
            )
        ],
    )


def _fake_revenue_report() -> RevenueComparisonReport:
    return RevenueComparisonReport(
        old_path="old.xlsx",
        new_path="new.xlsx",
        old_sheet="Old",
        new_sheet="New",
        revenue_column_old="Total Net Value Global",
        revenue_column_new="Total Net Value Global",
        channel_profile_column="Sales Channel Route Name",
        tier2_reseller_column="Tier 2 Reseller Id",
        old_row_count=2,
        new_row_count=2,
        row_count_delta=0,
        old_revenue_sum=100.0,
        new_revenue_sum=105.0,
        revenue_delta=5.0,
        old_non_numeric_revenue_count=0,
        new_non_numeric_revenue_count=0,
        indirect_row_count=0,
        indirect_missing_tier2_count=0,
        conditional_message="ok",
        zdel_document_type_column_old="Document type",
        zdel_document_type_column_new="Document type",
        zdel_document_type_value="ZDEL",
        zdel_threshold_pct=5.0,
        zdel_check_applied=True,
        zdel_old_sum=100.0,
        zdel_new_sum=102.0,
        zdel_delta=2.0,
        zdel_delta_pct=2.0,
        zdel_threshold_exceeded=False,
        zdel_threshold_message="ok",
        renewal_status_column_old="Renewal Status",
        renewal_status_column_new="Renewal Status",
        renewal_status_value="Renewed",
        renewal_quote_number_column_old="Renewal Quote Nbr",
        renewal_quote_number_column_new="Renewal Quote Nbr",
        renewal_contract_doc_number_column_old="Renewal Contract Doc Nbr",
        renewal_contract_doc_number_column_new="Renewal Contract Doc Nbr",
        renewal_threshold_pct=5.0,
        renewal_old_filtered_count=1,
        renewal_old_missing_count=0,
        renewal_old_missing_pct=0.0,
        renewal_new_filtered_count=1,
        renewal_new_missing_count=0,
        renewal_new_missing_pct=0.0,
        renewal_threshold_exceeded=False,
        renewal_threshold_message="ok",
    )


def test_hybrid_ui_defaults_to_data_quality_flow():
    app = build_hybrid_ui()

    assert isinstance(app, HybridValidationApp)
    assert app.selected_flow == "Data Quality"
    assert isinstance(app.current_app, DataQualityApp)
    assert app.data_quality_panel.layout.display == ""
    assert app.revenue_validation_panel.layout.display == "none"
    assert app.next_button.layout.display == ""
    assert app.final_run_button.layout.display == "none"
    assert app.data_quality_app.run_button.layout.display == "none"


def test_hybrid_ui_switches_to_revenue_validation_and_keeps_instances():
    app = build_hybrid_ui()
    original_quality_app = app.current_app

    app.flow_toggle.value = "Revenue Validation"
    revenue_app = app.current_app

    assert isinstance(revenue_app, RevenueValidationApp)
    assert app.data_quality_panel.layout.display == "none"
    assert app.revenue_validation_panel.layout.display == ""
    assert app.next_button.layout.display == "none"
    assert app.final_run_button.layout.display == ""
    assert app.revenue_validation_app.run_button.layout.display == "none"

    app.flow_toggle.value = "Data Quality"

    assert app.current_app is original_quality_app


def test_next_button_moves_to_revenue_flow():
    app = build_hybrid_ui()
    app._on_next_to_revenue()
    assert app.selected_flow == "Revenue Validation"
    assert app.revenue_validation_panel.layout.display == ""


def test_hybrid_final_run_generates_single_combined_outputs(monkeypatch, tmp_path):
    app = build_hybrid_ui(default_output_dir=str(tmp_path))
    app.flow_toggle.value = "Revenue Validation"

    monkeypatch.setattr(app.data_quality_app, "build_quality_report", _fake_quality_report)
    monkeypatch.setattr(app.revenue_validation_app, "build_revenue_report", _fake_revenue_report)

    app._on_run_combined()

    assert app.excel_path is not None
    assert app.html_path is not None
    assert app.excel_path.exists()
    assert app.html_path.exists()
    assert "combined validation complete" in app.combined_run_status.value.lower()
    html = app.html_path.read_text(encoding="utf-8")
    assert "1. Data Quality" in html
    assert "2. Validation" in html
    assert "3. AI Insights: Dashboard Summary" in html
    assert "4. Recommended Solutions" in html
    assert "5. Details" in html
    assert "ZDEL revenue previous vs current chart" in html
    assert "Renewal missing percent vs threshold chart" in html
    book = load_workbook(app.excel_path, read_only=True)
    try:
        assert "Overview" in book.sheetnames
        assert "DQ_Summary" in book.sheetnames
        assert "Revenue_Summary" in book.sheetnames
        assert "DQ_Details" in book.sheetnames
        assert "Revenue_Details" in book.sheetnames
    finally:
        book.close()


def test_hybrid_final_run_continues_when_data_quality_is_incomplete(monkeypatch, tmp_path):
    app = build_hybrid_ui(default_output_dir=str(tmp_path))
    app.flow_toggle.value = "Revenue Validation"

    def _fail_quality():
        raise ValueError("Load a workbook before running checks.")

    monkeypatch.setattr(app.data_quality_app, "build_quality_report", _fail_quality)
    monkeypatch.setattr(app.revenue_validation_app, "build_revenue_report", _fake_revenue_report)

    app._on_run_combined()

    assert app.excel_path is not None
    assert app.html_path is not None
    assert app.excel_path.exists()
    assert app.html_path.exists()
    assert "warning:" in app.combined_run_status.value.lower()
    assert "data quality incomplete" in app.combined_run_status.value.lower()
    book = load_workbook(app.excel_path, read_only=True)
    try:
        assert "DQ_Status" in book.sheetnames
        assert "Revenue_Summary" in book.sheetnames
    finally:
        book.close()


def test_data_completeness_blank_counts_filters_fields_and_blank_types():
    frame = pd.DataFrame(
        {
            "geography": [None, "", "  ", "Americas"],
            "SUBGEO1": ["North America", "North America", None, "North America"],
            "ISO Country Code": ["US", "US", "US", "US"],
            "Unrequested Field": [None, None, None, None],
        }
    )

    assert dashboard._data_completeness_blank_counts(frame) == [
        ("GEOGRAPHY", 3),
        ("SUBGEO1", 1),
    ]
    chart = dashboard.data_completeness_blank_chart(frame)
    assert chart is not None
    assert chart.startswith("data:image/png;base64,")


def test_data_completeness_chart_is_hidden_without_requested_blanks():
    frame = pd.DataFrame(
        {
            "GEOGRAPHY": ["Americas"],
            "SUBGEO1": ["North America"],
        }
    )

    assert dashboard.data_completeness_blank_chart(frame) is None
    assert dashboard.data_completeness_blank_chart(pd.DataFrame({"Other": [None]})) is None


def test_hybrid_html_uses_conditional_data_completeness_chart(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "data_completeness_blank_chart", lambda _: "data:image/png;base64,chart")
    monkeypatch.setattr(dashboard, "datatype_pattern_table", lambda _: None)

    output = write_hybrid_combined_html(
        _fake_revenue_report(),
        tmp_path / "report.html",
        quality_report=_fake_quality_report(),
        quality_df=pd.DataFrame({"GEOGRAPHY": [None]}),
    )
    html = output.read_text(encoding="utf-8")

    assert "<b>Status:</b> Data Completeness Validation" in html
    assert "Blank rows by field" in html
    assert 'alt="Blank row count by field chart"' in html
    assert "Completeness (Start Date)" not in html
    assert "Completeness (End Date)" not in html
    assert "Uniqueness (Sales Doc Nbr)" not in html
    assert "Validation checks failed record count" not in html


def test_hybrid_html_omits_completeness_chart_section_when_no_blanks(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "data_completeness_blank_chart", lambda _: None)
    monkeypatch.setattr(dashboard, "datatype_pattern_table", lambda _: None)

    output = write_hybrid_combined_html(
        _fake_revenue_report(),
        tmp_path / "report.html",
        quality_report=_fake_quality_report(),
        quality_df=pd.DataFrame({"GEOGRAPHY": ["Americas"]}),
    )
    html = output.read_text(encoding="utf-8")

    assert "Blank rows by field" not in html
    assert "Blank row count by field chart" not in html
