import pandas as pd
import pytest
from openpyxl import load_workbook

from dq_platform.comparison import (
    build_revenue_comparison_report,
    build_revenue_comparison_report_from_dataframes,
)
from dq_platform.report.comparison import (
    write_revenue_comparison_excel,
    write_revenue_comparison_html,
)


@pytest.fixture
def comparison_workbooks(tmp_path):
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100, 200, None],
            "Document type": ["ZDEL", "ZDEL", "ZRPT"],
            "Total Contract Value Global": [1000, 500, 200],
            "Sales Channel Route Name": ["direct", "indirect", "direct"],
            "Tier 2 Reseller Id": ["A", "B", "C"],
            "Renewal Status": ["Renewed", "Renewed", "Open"],
            "Renewal Quote Nbr": ["Q1", "Q2", ""],
            "Renewal Contract Doc Nbr": ["C1", "C2", ""],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [120, 250, 80],
            "Document type": ["ZDEL", "ZDEL", "ZRPT"],
            "Total Contract Value Global": [1200, 400, 250],
            "Sales Channel Route Name": ["indirect", "direct", "INDIRECT"],
            "Tier 2 Reseller Id": ["", "R2", None],
            "Renewal Status": ["Renewed", "Renewed", "Open"],
            "Renewal Quote Nbr": ["", "Q3", ""],
            "Renewal Contract Doc Nbr": ["RC1", "RC2", ""],
        }
    )
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    old_df.to_excel(old_path, sheet_name="Contracts", index=False)
    new_df.to_excel(new_path, sheet_name="Contracts", index=False)
    return old_path, new_path


def test_build_revenue_comparison_report_uses_defaults(comparison_workbooks):
    old_path, new_path = comparison_workbooks
    report = build_revenue_comparison_report(old_path, new_path, "Contracts", "Contracts")

    assert report.old_row_count == 3
    assert report.new_row_count == 3
    assert report.row_count_delta == 0
    assert report.old_revenue_sum == 300
    assert report.new_revenue_sum == 450
    assert report.revenue_delta == 150
    assert report.revenue_column_old == "Total Net Value Global"
    assert report.revenue_column_new == "Total Net Value Global"
    assert report.indirect_row_count == 2
    assert report.indirect_missing_tier2_count == 2
    assert len(report.invalid_rows) == 2
    assert list(report.invalid_rows["Source Row"]) == [2, 4]
    assert report.zdel_check_applied is True
    assert report.zdel_old_sum == 300
    assert report.zdel_new_sum == 370
    assert report.zdel_delta == 70
    assert round(report.zdel_delta_pct or 0, 2) == 23.33
    assert report.zdel_threshold_exceeded is True
    assert "exceeds the 5.0% threshold" in report.zdel_threshold_message.lower()
    assert report.zdel_document_type_value == "ZDEL"
    assert report.renewal_threshold_exceeded is True
    assert report.renewal_old_missing_pct == 0.0
    assert round(report.renewal_new_missing_pct, 2) == 50.0


def test_build_revenue_comparison_report_raises_when_default_revenue_is_missing(tmp_path):
    old_df = pd.DataFrame({"Amount": [10, 20]})
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [10, 20],
            "Sales Channel Route Name": ["indirect", "direct"],
            "Tier 2 Reseller Id": ["", "X"],
            "Renewal Status": ["Renewed", "Open"],
            "Renewal Quote Nbr": ["Q1", ""],
            "Renewal Contract Doc Nbr": ["C1", ""],
        }
    )
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    old_df.to_excel(old_path, index=False)
    new_df.to_excel(new_path, index=False)

    with pytest.raises(
        ValueError, match="Revenue column 'Total Net Value Global' was not found"
    ):
        build_revenue_comparison_report(old_path, new_path)


def test_build_revenue_comparison_report_from_dataframes_supports_sql_labels():
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100, 200],
            "Document type": ["ZDEL", "ZDEL"],
            "Total Contract Value Global": [500, 500],
            "Sales Channel Route Name": ["direct", "indirect"],
            "Tier 2 Reseller Id": ["A", "B"],
            "Renewal Status": ["Renewed", "Open"],
            "Renewal Quote Nbr": ["Q1", ""],
            "Renewal Contract Doc Nbr": ["C1", ""],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [110, 260],
            "Document type": ["ZDEL", "ZDEL"],
            "Total Contract Value Global": [530, 500],
            "Sales Channel Route Name": ["INDIRECT", "direct"],
            "Tier 2 Reseller Id": ["", "C"],
            "Renewal Status": ["Renewed", "Open"],
            "Renewal Quote Nbr": ["Q2", ""],
            "Renewal Contract Doc Nbr": ["C2", ""],
        }
    )

    report = build_revenue_comparison_report_from_dataframes(
        old_df,
        new_df,
        old_source_label="SQL Server table dbo.old_data",
        new_source_label="SQL Server table dbo.new_data",
        old_selection_label="dbo.old_data",
        new_selection_label="dbo.new_data",
    )

    assert report.old_path == "SQL Server table dbo.old_data"
    assert report.new_path == "SQL Server table dbo.new_data"
    assert report.row_count_delta == 0
    assert report.revenue_delta == 70
    assert report.indirect_missing_tier2_count == 1
    assert report.zdel_threshold_exceeded is True


def test_build_revenue_comparison_report_supports_configurable_zdel_inputs():
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100, 200],
            "Doc Type": ["ZDEL", "ZRPT"],
            "Sales Channel Route Name": ["direct", "indirect"],
            "Tier 2 Reseller Id": ["A", "B"],
            "Renewal Flag": ["Renewed", "Open"],
            "Renew Quote": ["Q1", ""],
            "Renew Contract": ["C1", ""],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [110, 260],
            "Doc Type": ["ZDEL", "ZRPT"],
            "Sales Channel Route Name": ["INDIRECT", "direct"],
            "Tier 2 Reseller Id": ["", "C"],
            "Renewal Flag": ["Renewed", "Open"],
            "Renew Quote": ["Q2", ""],
            "Renew Contract": ["C2", ""],
        }
    )

    report = build_revenue_comparison_report_from_dataframes(
        old_df,
        new_df,
        old_source_label="old",
        new_source_label="new",
        old_selection_label="old_sheet",
        new_selection_label="new_sheet",
        zdel_document_type_column="Doc Type",
        zdel_document_type_value="ZDEL",
        zdel_threshold_pct=10.0,
        renewal_status_column="Renewal Flag",
        renewal_status_value="Renewed",
        renewal_quote_number_column="Renew Quote",
        renewal_contract_doc_number_column="Renew Contract",
        renewal_threshold_pct=10.0,
    )

    assert report.zdel_document_type_column_old == "Doc Type"
    assert report.zdel_document_type_column_new == "Doc Type"
    assert report.zdel_document_type_value == "ZDEL"
    assert report.zdel_threshold_pct == 10.0
    assert report.zdel_delta == 10
    assert round(report.zdel_delta_pct or 0, 2) == 10.0
    assert report.zdel_threshold_exceeded is False
    assert report.renewal_threshold_exceeded is False


def test_build_revenue_comparison_report_rejects_non_positive_zdel_threshold():
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100],
            "Document type": ["ZDEL"],
            "Total Contract Value Global": [1000],
            "Sales Channel Route Name": ["direct"],
            "Tier 2 Reseller Id": ["A"],
            "Renewal Status": ["Renewed"],
            "Renewal Quote Nbr": ["Q1"],
            "Renewal Contract Doc Nbr": ["C1"],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [110],
            "Document type": ["ZDEL"],
            "Total Contract Value Global": [1200],
            "Sales Channel Route Name": ["direct"],
            "Tier 2 Reseller Id": ["A"],
            "Renewal Status": ["Renewed"],
            "Renewal Quote Nbr": ["Q2"],
            "Renewal Contract Doc Nbr": ["C2"],
        }
    )

    with pytest.raises(ValueError, match="ZDEL threshold percent must be greater than 0"):
        build_revenue_comparison_report_from_dataframes(
            old_df,
            new_df,
            old_source_label="old",
            new_source_label="new",
            old_selection_label="old_sheet",
            new_selection_label="new_sheet",
            zdel_threshold_pct=0,
        )


def test_build_revenue_comparison_report_rejects_non_positive_renewal_threshold():
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100],
            "Document type": ["ZDEL"],
            "Sales Channel Route Name": ["direct"],
            "Tier 2 Reseller Id": ["A"],
            "Renewal Status": ["Renewed"],
            "Renewal Quote Nbr": ["Q1"],
            "Renewal Contract Doc Nbr": ["C1"],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [110],
            "Document type": ["ZDEL"],
            "Sales Channel Route Name": ["direct"],
            "Tier 2 Reseller Id": ["A"],
            "Renewal Status": ["Renewed"],
            "Renewal Quote Nbr": ["Q2"],
            "Renewal Contract Doc Nbr": ["C2"],
        }
    )

    with pytest.raises(ValueError, match="Renewal threshold percent must be greater than 0"):
        build_revenue_comparison_report_from_dataframes(
            old_df,
            new_df,
            old_source_label="old",
            new_source_label="new",
            old_selection_label="old_sheet",
            new_selection_label="new_sheet",
            renewal_threshold_pct=0,
        )


def test_renewal_missing_percentage_uses_only_selected_status_rows():
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100, 200, 300],
            "Document type": ["ZDEL", "ZDEL", "ZRPT"],
            "Sales Channel Route Name": ["direct", "direct", "direct"],
            "Tier 2 Reseller Id": ["A", "B", "C"],
            "Renewal Status": ["Renewed", "Open", "Renewed"],
            "Renewal Quote Nbr": ["Q1", "", ""],
            "Renewal Contract Doc Nbr": ["C1", "", "C3"],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [120, 220, 320],
            "Document type": ["ZDEL", "ZDEL", "ZRPT"],
            "Sales Channel Route Name": ["direct", "direct", "direct"],
            "Tier 2 Reseller Id": ["A", "B", "C"],
            "Renewal Status": ["Renewed", "Open", "Renewed"],
            "Renewal Quote Nbr": ["", "", "Q3"],
            "Renewal Contract Doc Nbr": ["C2", "", ""],
        }
    )

    report = build_revenue_comparison_report_from_dataframes(
        old_df,
        new_df,
        old_source_label="old",
        new_source_label="new",
        old_selection_label="old_sheet",
        new_selection_label="new_sheet",
        renewal_threshold_pct=60.0,
    )

    assert report.renewal_old_filtered_count == 2
    assert report.renewal_old_missing_count == 1
    assert round(report.renewal_old_missing_pct, 2) == 50.0
    assert report.renewal_new_filtered_count == 2
    assert report.renewal_new_missing_count == 2
    assert round(report.renewal_new_missing_pct, 2) == 100.0
    assert report.renewal_threshold_exceeded is True


def test_comparison_report_writers_create_excel_and_html(tmp_path, comparison_workbooks):
    old_path, new_path = comparison_workbooks
    report = build_revenue_comparison_report(old_path, new_path, "Contracts", "Contracts")

    excel_path = write_revenue_comparison_excel(report, tmp_path / "Revenue.xlsx")
    html_path = write_revenue_comparison_html(report, tmp_path / "Revenue.html")

    assert excel_path.exists()
    assert html_path.exists()

    book = load_workbook(excel_path, read_only=True)
    try:
        assert "Summary" in book.sheetnames
        assert "Indirect_Tier2_Check" in book.sheetnames
        assert "ZDEL_Check" in book.sheetnames
        assert "Renewal_Check" in book.sheetnames
    finally:
        book.close()

    html = html_path.read_text(encoding="utf-8")
    assert "Revenue Validation Report" in html
    assert "Row count delta (new - old)" in html
    assert "Document Type Revenue Threshold Check" in html
    assert "Renewal Completeness Check" in html
