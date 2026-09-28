import pandas as pd
import pytest
from openpyxl import load_workbook

from dq_platform.engine import run_checks
from dq_platform.io_utils import list_sheets, load_dataframe, read_header_columns, resolve_path
from dq_platform.models import RuleSpec
from dq_platform.report.excel import write_excel_report
from dq_platform.report.html import write_html_report


@pytest.fixture
def workbook(tmp_path, contract_df):
    path = tmp_path / "sample.xlsx"
    contract_df.to_excel(path, sheet_name="Contracts", index=False)
    return path


# ------------------------------------------------------------------------- io


def test_resolve_path_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_path(tmp_path / "nope.xlsx")


def test_resolve_path_rejects_wrong_extension(tmp_path):
    bad = tmp_path / "data.txt"
    bad.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError):
        resolve_path(bad)


def test_resolve_path_strips_quotes(workbook):
    assert resolve_path(f'"{workbook}"') == workbook


def test_list_sheets_and_header_columns(workbook, contract_df):
    assert list_sheets(workbook) == ["Contracts"]
    assert read_header_columns(workbook, "Contracts") == list(contract_df.columns)


def test_load_dataframe(workbook, contract_df):
    frame = load_dataframe(workbook, "Contracts")
    assert list(frame.columns) == list(contract_df.columns)
    assert len(frame) == len(contract_df)


# --------------------------------------------------------------------- reports


@pytest.fixture
def report(contract_df):
    specs = [
        RuleSpec(rule_id="completeness.missing_summary", columns=[]),
        RuleSpec(rule_id="uniqueness.duplicate_key", columns=["Sales Doc Nbr"]),
        RuleSpec(rule_id="validity.email_domain", columns=["Email"], params={"domains": "hpe.com"}),
        RuleSpec(
            rule_id="consistency.duration_range",
            columns=["Hdr Start Date", "Hdr End Date"],
            params={"min_days": 0},
        ),
        RuleSpec(rule_id="distribution.value_profile", columns=["Document Type"]),
    ]
    return run_checks(contract_df, specs, source_path="sample.xlsx", sheet_name="Contracts")


def test_excel_report_has_expected_sheets(tmp_path, report, contract_df):
    destination = write_excel_report(report, contract_df, tmp_path / "Quality_Report.xlsx")
    assert destination.exists()

    book = load_workbook(destination, read_only=True)
    try:
        names = book.sheetnames
    finally:
        book.close()

    assert "Summary" in names
    assert "Rule_Details" in names
    assert "Missing_Values" in names
    assert "Column_Profile" in names
    # One flagged-rows sheet per failing check plus detail sheets.
    assert any(name.startswith("F") for name in names)
    assert any(name.startswith("D") for name in names)


def test_excel_flagged_sheet_contains_the_offending_rows(tmp_path, report, contract_df):
    destination = write_excel_report(report, contract_df, tmp_path / "R.xlsx")
    sheets = pd.read_excel(destination, sheet_name=None)
    flagged = [name for name in sheets if "Duplicate" in name and name.startswith("F")]
    assert flagged
    frame = sheets[flagged[0]]
    assert "Source Row" in frame.columns
    assert len(frame) == 2


def test_excel_respects_the_row_limit(tmp_path, report, contract_df):
    destination = write_excel_report(report, contract_df, tmp_path / "R.xlsx", row_limit=1)
    sheets = pd.read_excel(destination, sheet_name=None)
    flagged = [name for name in sheets if name.startswith("F")]
    assert all(len(sheets[name]) <= 1 for name in flagged)


def test_excel_sheet_names_are_sanitised(tmp_path, contract_df):
    specs = [
        RuleSpec(
            rule_id="completeness.null_blank",
            columns=["Party Name"],
            label="Blank / customer: name [check] *very* long label indeed",
        )
    ]
    built = run_checks(contract_df, specs)
    destination = write_excel_report(built, contract_df, tmp_path / "R.xlsx")

    book = load_workbook(destination, read_only=True)
    try:
        names = book.sheetnames
    finally:
        book.close()

    assert all(len(name) <= 31 for name in names)
    assert all(not set(name) & set("[]:*?/\\") for name in names)


def test_html_report_is_written(tmp_path, report, contract_df):
    destination = write_html_report(report, contract_df, tmp_path / "Quality_Report.html")
    content = destination.read_text(encoding="utf-8")

    assert "<html" in content
    assert "Data Quality Report" in content
    assert "data:image/png;base64," in content
    assert "Duplicate key values" in content


def test_html_report_escapes_hostile_values(tmp_path):
    frame = pd.DataFrame({"<script>evil</script>": ["<img src=x onerror=alert(1)>", None]})
    built = run_checks(
        frame,
        [RuleSpec(rule_id="completeness.null_blank", columns=["<script>evil</script>"])],
        source_path="<script>path</script>",
        sheet_name="Sheet1",
    )
    destination = write_html_report(built, frame, tmp_path / "x.html")
    content = destination.read_text(encoding="utf-8")

    assert "<script>evil</script>" not in content
    assert "&lt;script&gt;evil&lt;/script&gt;" in content
    assert "onerror=alert(1)>" not in content


def test_reports_handle_a_run_with_no_failures(tmp_path, contract_df):
    built = run_checks(
        contract_df, [RuleSpec(rule_id="completeness.null_blank", columns=["Document Type"])]
    )
    assert built.failed_checks == 0
    assert write_excel_report(built, contract_df, tmp_path / "R.xlsx").exists()
    assert write_html_report(built, contract_df, tmp_path / "R.html").exists()
