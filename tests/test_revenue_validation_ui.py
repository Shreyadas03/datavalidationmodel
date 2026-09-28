import pandas as pd
import pytest

import dq_platform.ui.revenue_comparison_widgets as revenue_module
from dq_platform.ui.revenue_comparison_widgets import build_revenue_validation_ui


@pytest.fixture(autouse=True)
def _stub_sql_table_listing(monkeypatch):
    monkeypatch.setattr(revenue_module, "list_sql_tables", lambda *_a, **_k: [])


def _use_excel_mode(app) -> None:
    app.old_source_mode_toggle.value = "excel"
    app.new_source_mode_toggle.value = "excel"


@pytest.fixture
def revenue_workbooks(tmp_path, contract_df):
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    contract_df.to_excel(old_path, sheet_name="Contracts", index=False)
    contract_df.to_excel(new_path, sheet_name="Contracts", index=False)
    return old_path, new_path


def test_inline_browser_lists_folders_and_excel_files(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    (tmp_path / "sample.xlsx").write_text("not a real workbook", encoding="utf-8")

    app = build_revenue_validation_ui()
    app._open_browser(tmp_path, "old")

    labels = [label for label, _ in app.browser_list.options]
    assert any("nested" in label for label in labels)
    assert any("sample.xlsx" in label for label in labels)
    assert not any("notes.txt" in label for label in labels)


def test_inline_browser_use_sets_old_and_new_paths(revenue_workbooks):
    old_path, new_path = revenue_workbooks
    app = build_revenue_validation_ui()
    _use_excel_mode(app)

    app._open_browser(old_path.parent, "old")
    app.browser_list.value = str(old_path)
    app._on_browser_use()
    assert app.old_path_box.value == str(old_path)
    assert list(app.old_sheet_dropdown.options) == ["Contracts"]

    app._open_browser(new_path.parent, "new")
    app.browser_list.value = str(new_path)
    app._on_browser_use()
    assert app.new_path_box.value == str(new_path)
    assert list(app.new_sheet_dropdown.options) == ["Contracts"]


def test_browser_use_without_file_shows_error(tmp_path):
    app = build_revenue_validation_ui()
    app._open_browser(tmp_path, "old")
    app._on_browser_use()

    assert "select an excel file" in app.browser_status.value.lower()


def test_sql_mode_lists_tables_for_old_and_new(monkeypatch):
    call_count = {"count": 0}

    def fake_list_sql_tables(*_args, **_kwargs):
        call_count["count"] += 1
        return ["dbo.old_data", "dbo.new_data"]

    monkeypatch.setattr(revenue_module, "list_sql_tables", fake_list_sql_tables)

    app = build_revenue_validation_ui()
    app.old_source_mode_toggle.value = "sql"
    app.new_source_mode_toggle.value = "sql"

    assert list(app.old_sql_table_dropdown.options) == ["dbo.old_data", "dbo.new_data"]
    assert list(app.new_sql_table_dropdown.options) == ["dbo.old_data", "dbo.new_data"]
    # Old and new sides now use independent connections/caches, so each is
    # fetched once (previously a single shared cache meant only one call).
    assert call_count["count"] == 2


def test_sql_mode_refresh_button_forces_refetch(monkeypatch):
    responses = iter(
        [
            ["dbo.old_data", "dbo.new_data"],  # initial fetch for old
            ["dbo.old_data", "dbo.new_data"],  # initial fetch for new
            ["dbo.old_data", "dbo.new_data", "dbo.delta_data"],  # forced refetch for old
        ]
    )

    monkeypatch.setattr(revenue_module, "list_sql_tables", lambda *_a, **_k: next(responses))
    app = build_revenue_validation_ui()

    assert list(app.old_sql_table_dropdown.options) == ["dbo.old_data", "dbo.new_data"]

    app._on_refresh_old_tables()

    assert list(app.old_sql_table_dropdown.options) == [
        "dbo.old_data",
        "dbo.new_data",
        "dbo.delta_data",
    ]
    # New side has its own independent connection/cache, so it keeps the
    # options from its own initial fetch and is unaffected by refreshing old.
    assert list(app.new_sql_table_dropdown.options) == ["dbo.old_data", "dbo.new_data"]


def test_sql_mode_load_button_loads_selected_old_and_new_tables(monkeypatch):
    old_df = pd.DataFrame(
        {
            "Amount": [1],
            "Renewal Status": ["Renewed"],
            "Renewal Quote Nbr": ["Q1"],
            "Renewal Contract Doc Nbr": ["C1"],
        }
    )
    new_df = pd.DataFrame(
        {
            "Amount": [2],
            "Renewal Status": ["Renewed"],
            "Renewal Quote Nbr": ["Q2"],
            "Renewal Contract Doc Nbr": ["C2"],
        }
    )
    loaded_tables = []

    monkeypatch.setattr(revenue_module, "list_sql_tables", lambda *_a, **_k: ["dbo.old_data", "dbo.new_data"])

    def fake_load_source_dataframe(source):
        loaded_tables.append(source.table_name)
        return old_df.copy() if source.table_name == "dbo.old_data" else new_df.copy()

    monkeypatch.setattr(revenue_module, "load_source_dataframe", fake_load_source_dataframe)
    monkeypatch.setattr(
        revenue_module,
        "describe_source",
        lambda source: f"SQL Server table {source.table_name}",
    )

    app = build_revenue_validation_ui()
    app.old_source_mode_toggle.value = "sql"
    app.new_source_mode_toggle.value = "sql"
    app.old_sql_table_dropdown.value = "dbo.old_data"
    app.new_sql_table_dropdown.value = "dbo.new_data"

    app._on_load_sql_sources()

    assert loaded_tables == ["dbo.old_data", "dbo.new_data"]
    assert "data loaded" in app.old_status.value.lower()
    assert "data loaded" in app.new_status.value.lower()
    assert app.sql_load_button.description == "Data loaded"


def test_sql_mode_run_builds_report_from_selected_tables(monkeypatch, tmp_path):
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
            "Total Net Value Global": [150, 210],
            "Document type": ["ZDEL", "ZDEL"],
            "Total Contract Value Global": [520, 510],
            "Sales Channel Route Name": ["indirect", "direct"],
            "Tier 2 Reseller Id": ["", "C"],
            "Renewal Status": ["Renewed", "Open"],
            "Renewal Quote Nbr": ["Q2", ""],
            "Renewal Contract Doc Nbr": ["C2", ""],
        }
    )

    monkeypatch.setattr(revenue_module, "list_sql_tables", lambda *_a, **_k: ["dbo.old_data", "dbo.new_data"])
    monkeypatch.setattr(
        revenue_module,
        "load_source_dataframe",
        lambda source: old_df.copy() if source.table_name == "dbo.old_data" else new_df.copy(),
    )
    monkeypatch.setattr(
        revenue_module,
        "describe_source",
        lambda source: f"SQL Server table {source.table_name}",
    )

    app = build_revenue_validation_ui(default_output_dir=str(tmp_path / "out"))
    app.old_source_mode_toggle.value = "sql"
    app.new_source_mode_toggle.value = "sql"
    app.old_sql_table_dropdown.value = "dbo.old_data"
    app.new_sql_table_dropdown.value = "dbo.new_data"
    app.zdel_threshold_pct_box.value = 30.0
    app._on_run()

    assert app.report is not None
    assert app.report.old_path == "SQL Server table dbo.old_data"
    assert app.report.new_path == "SQL Server table dbo.new_data"
    assert app.excel_path.exists()
    assert app.html_path.exists()
    assert "validation complete" in app.run_status.value.lower()


def test_sql_mode_run_shows_error_when_zdel_delta_exceeds_threshold(monkeypatch, tmp_path):
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
            "Total Net Value Global": [150, 210],
            "Document type": ["ZDEL", "ZDEL"],
            "Total Contract Value Global": [700, 450],
            "Sales Channel Route Name": ["indirect", "direct"],
            "Tier 2 Reseller Id": ["", "C"],
            "Renewal Status": ["Renewed", "Open"],
            "Renewal Quote Nbr": ["Q2", ""],
            "Renewal Contract Doc Nbr": ["C2", ""],
        }
    )
    monkeypatch.setattr(revenue_module, "list_sql_tables", lambda *_a, **_k: ["dbo.old_data", "dbo.new_data"])
    monkeypatch.setattr(
        revenue_module,
        "load_source_dataframe",
        lambda source: old_df.copy() if source.table_name == "dbo.old_data" else new_df.copy(),
    )
    monkeypatch.setattr(
        revenue_module,
        "describe_source",
        lambda source: f"SQL Server table {source.table_name}",
    )

    app = build_revenue_validation_ui(default_output_dir=str(tmp_path / "out"))
    app.old_source_mode_toggle.value = "sql"
    app.new_source_mode_toggle.value = "sql"
    app.old_sql_table_dropdown.value = "dbo.old_data"
    app.new_sql_table_dropdown.value = "dbo.new_data"
    app._on_run()

    assert app.report is not None
    assert app.report.zdel_threshold_exceeded is True
    assert "error:" in app.run_status.value.lower()
    assert "exceeds the 5.0% threshold" in app.run_status.value.lower()


def test_revenue_validation_defaults_to_sql_mode():
    app = build_revenue_validation_ui()
    assert app.old_source_mode == "sql"
    assert app.new_source_mode == "sql"


def test_revenue_validation_column_fields_are_searchable_dropdowns(monkeypatch):
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100],
            "Sales Channel Route Name": ["indirect"],
            "Tier 2 Reseller Id": [""],
            "Renewal Status": ["Renewed"],
            "Renewal Quote Nbr": ["Q1"],
            "Renewal Contract Doc Nbr": ["C1"],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [200],
            "Sales Channel Route Name": ["direct"],
            "Tier 2 Reseller Id": ["A"],
            "Extra Column": ["x"],
            "Renewal Status": ["Open"],
            "Renewal Quote Nbr": [""],
            "Renewal Contract Doc Nbr": [""],
        }
    )

    monkeypatch.setattr(revenue_module, "list_sql_tables", lambda *_a, **_k: ["dbo.old_data", "dbo.new_data"])
    monkeypatch.setattr(
        revenue_module,
        "load_source_dataframe",
        lambda source: old_df.copy() if source.table_name == "dbo.old_data" else new_df.copy(),
    )

    app = build_revenue_validation_ui()
    app.old_sql_table_dropdown.value = "dbo.old_data"
    app.new_sql_table_dropdown.value = "dbo.new_data"
    app._on_load_sql_sources()

    assert isinstance(app.revenue_column_box, revenue_module.widgets.Combobox)
    assert isinstance(app.channel_profile_column_box, revenue_module.widgets.Combobox)
    assert isinstance(app.tier2_reseller_column_box, revenue_module.widgets.Combobox)
    assert isinstance(app.zdel_document_type_column_box, revenue_module.widgets.Combobox)
    assert isinstance(app.zdel_document_type_value_box, revenue_module.widgets.Combobox)
    assert isinstance(app.renewal_status_column_box, revenue_module.widgets.Combobox)
    assert isinstance(app.renewal_status_value_box, revenue_module.widgets.Combobox)
    assert isinstance(app.renewal_quote_column_box, revenue_module.widgets.Combobox)
    assert isinstance(app.renewal_contract_doc_column_box, revenue_module.widgets.Combobox)
    assert "Extra Column" in list(app.revenue_column_box.options)


def test_revenue_validation_zdel_controls_default_and_are_configurable(monkeypatch, tmp_path):
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100, 200],
            "Doc Type": ["ZDEL", "ZRPT"],
            "Contract Global Value": [1000, 120],
            "Sales Channel Route Name": ["direct", "indirect"],
            "Tier 2 Reseller Id": ["A", "B"],
            "Renewal Flag": ["Renewed", "Open"],
            "Renew Quote": ["Q1", ""],
            "Renew Contract": ["C1", ""],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [110, 210],
            "Doc Type": ["ZDEL", "ZRPT"],
            "Contract Global Value": [1080, 120],
            "Sales Channel Route Name": ["direct", "direct"],
            "Tier 2 Reseller Id": ["A", "B"],
            "Renewal Flag": ["Renewed", "Closed"],
            "Renew Quote": ["Q2", ""],
            "Renew Contract": ["C2", ""],
        }
    )
    monkeypatch.setattr(revenue_module, "list_sql_tables", lambda *_a, **_k: ["dbo.old_data", "dbo.new_data"])
    monkeypatch.setattr(
        revenue_module,
        "load_source_dataframe",
        lambda source: old_df.copy() if source.table_name == "dbo.old_data" else new_df.copy(),
    )
    monkeypatch.setattr(
        revenue_module,
        "describe_source",
        lambda source: f"SQL Server table {source.table_name}",
    )

    app = build_revenue_validation_ui(default_output_dir=str(tmp_path / "out"))
    assert app.zdel_threshold_pct_box.value == 5.0
    app.old_sql_table_dropdown.value = "dbo.old_data"
    app.new_sql_table_dropdown.value = "dbo.new_data"
    app._on_load_sql_sources()
    app.zdel_document_type_column_box.value = "Doc Type"
    assert set(app.zdel_document_type_value_box.options) >= {"ZDEL", "ZRPT"}
    app.renewal_status_column_box.value = "Renewal Flag"
    app.renewal_quote_column_box.value = "Renew Quote"
    app.renewal_contract_doc_column_box.value = "Renew Contract"
    assert set(app.renewal_status_value_box.options) >= {"Renewed", "Open", "Closed"}
    app.zdel_document_type_value_box.value = "ZDEL"
    app.zdel_threshold_pct_box.value = 10.0
    app.renewal_status_value_box.value = "Renewed"
    app.renewal_threshold_pct_box.value = 60.0
    app._on_run()

    assert app.report is not None
    assert app.report.zdel_threshold_pct == 10.0
    assert app.report.zdel_document_type_column_old == "Doc Type"
    assert app.report.zdel_document_type_value == "ZDEL"
    assert app.report.zdel_threshold_exceeded is False
    assert app.report.renewal_status_column_old == "Renewal Flag"
    assert app.report.renewal_status_value == "Renewed"
    assert app.report.renewal_threshold_exceeded is False


def test_sql_mode_run_shows_error_when_renewal_missing_exceeds_threshold(monkeypatch, tmp_path):
    old_df = pd.DataFrame(
        {
            "Total Net Value Global": [100, 200],
            "Document type": ["ZDEL", "ZRPT"],
            "Sales Channel Route Name": ["direct", "direct"],
            "Tier 2 Reseller Id": ["A", "B"],
            "Renewal Status": ["Renewed", "Open"],
            "Renewal Quote Nbr": ["Q1", ""],
            "Renewal Contract Doc Nbr": ["C1", ""],
        }
    )
    new_df = pd.DataFrame(
        {
            "Total Net Value Global": [110, 210],
            "Document type": ["ZDEL", "ZRPT"],
            "Sales Channel Route Name": ["direct", "direct"],
            "Tier 2 Reseller Id": ["A", "B"],
            "Renewal Status": ["Renewed", "Renewed"],
            "Renewal Quote Nbr": ["", "Q2"],
            "Renewal Contract Doc Nbr": ["", "C2"],
        }
    )
    monkeypatch.setattr(revenue_module, "list_sql_tables", lambda *_a, **_k: ["dbo.old_data", "dbo.new_data"])
    monkeypatch.setattr(
        revenue_module,
        "load_source_dataframe",
        lambda source: old_df.copy() if source.table_name == "dbo.old_data" else new_df.copy(),
    )
    monkeypatch.setattr(
        revenue_module,
        "describe_source",
        lambda source: f"SQL Server table {source.table_name}",
    )

    app = build_revenue_validation_ui(default_output_dir=str(tmp_path / "out"))
    app.old_source_mode_toggle.value = "sql"
    app.new_source_mode_toggle.value = "sql"
    app.old_sql_table_dropdown.value = "dbo.old_data"
    app.new_sql_table_dropdown.value = "dbo.new_data"
    app.zdel_threshold_pct_box.value = 50.0
    app.renewal_threshold_pct_box.value = 5.0
    app._on_run()

    assert app.report is not None
    assert app.report.renewal_threshold_exceeded is True
    assert "error:" in app.run_status.value.lower()
    assert "renewal completeness exceeds" in app.run_status.value.lower()
