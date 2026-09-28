import pytest

import dq_platform.ui.widgets as widget_module
from dq_platform.registry import RULE_DEFINITIONS
from dq_platform.ui.widgets import build_ui


@pytest.fixture(autouse=True)
def _stub_sql_table_listing(monkeypatch):
    monkeypatch.setattr(widget_module, "list_sql_tables", lambda *_a, **_k: [])


def _use_excel_mode(app) -> None:
    app.source_mode_toggle.value = "excel"


@pytest.fixture
def workbook(tmp_path, contract_df):
    path = tmp_path / "sample.xlsx"
    contract_df.to_excel(path, sheet_name="Contracts", index=False)
    return path


def test_every_rule_renders_its_widget_panel():
    app = build_ui()
    for definition in RULE_DEFINITIONS:
        app.rule_dropdown.value = definition.rule_id
        assert len(app._param_widgets) == len(definition.params)
        if definition.arity == 0:
            assert app._column_widgets == []
        elif definition.arity == "many":
            assert len(app._column_widgets) == 1
        else:
            assert len(app._column_widgets) == int(definition.arity)


def test_loading_populates_columns_from_the_header_row(workbook, contract_df):
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    assert app.columns == list(contract_df.columns)
    assert list(app.sheet_dropdown.options) == ["Contracts"]
    assert len(app.df) == len(contract_df)


def test_bad_path_shows_an_error_instead_of_raising():
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = "does-not-exist.xlsx"
    app._on_load()

    assert app.df is None
    assert "not found" in app.load_status.value.lower()


def test_adding_a_check_collects_columns_and_params(workbook):
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    app.rule_dropdown.value = "validity.email_domain"
    app._column_widgets[0].value = "Email"
    app._on_add()

    assert len(app.specs) == 1
    spec = app.specs[0]
    assert spec.rule_id == "validity.email_domain"
    assert spec.columns == ["Email"]
    assert spec.params["domains"] == "hpe.com"


def test_adding_the_same_check_twice_keeps_one_spec(workbook):
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    app.rule_dropdown.value = "validity.email_domain"
    app._column_widgets[0].value = "Email"
    app._on_add()
    app._on_add()

    assert len(app.specs) == 1
    assert "already selected" in app.add_status.value.lower()


def test_unknown_column_is_rejected(workbook):
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    app.rule_dropdown.value = "completeness.null_blank"
    app._column_widgets[0].value = "Not A Column"
    app._on_add()

    assert app.specs == []
    assert "not a column" in app.add_status.value.lower()


def test_empty_number_param_is_omitted(workbook):
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    app.rule_dropdown.value = "validity.numeric_range"
    app._column_widgets[0].value = "Amount"
    app._param_widgets["min_value"].value = "0"
    app._param_widgets["max_value"].value = ""
    app._on_add()

    assert app.specs[0].params["min_value"] == 0
    assert "max_value" not in app.specs[0].params


def test_non_numeric_param_reports_an_error(workbook):
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    app.rule_dropdown.value = "validity.numeric_range"
    app._column_widgets[0].value = "Amount"
    app._param_widgets["min_value"].value = "abc"
    app._on_add()

    assert app.specs == []
    assert "must be a number" in app.add_status.value


def test_preset_button_adds_and_clear_removes(workbook):
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    app.preset_dropdown.value = "HPE Contract QC"
    app._on_preset()
    assert len(app.specs) > 5

    app._on_clear()
    assert app.specs == []


def test_adding_the_same_preset_twice_keeps_unique_checks(workbook):
    app = build_ui()
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    app.preset_dropdown.value = "HPE Contract QC"
    app._on_preset()
    selected_count = len(app.specs)
    app._on_preset()

    assert len(app.specs) == selected_count
    assert "already selected" in app.preset_help.value.lower()


def test_preset_requires_a_loaded_workbook():
    app = build_ui()
    app._on_preset()
    assert app.specs == []
    assert "load a workbook" in app.preset_help.value.lower()


def test_inline_browser_lists_folders_and_workbooks_then_loads(workbook, tmp_path):
    (tmp_path / "archive").mkdir()
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    app = build_ui()
    _use_excel_mode(app)
    app._open_browser(tmp_path)

    labels = [label for label, _ in app.browser_list.options]
    assert any("archive" in label for label in labels)
    assert any("sample.xlsx" in label for label in labels)
    assert not any("notes.txt" in label for label in labels)

    app.browser_list.value = str(workbook)
    app._on_browser_use()

    assert app.path_box.value == str(workbook)
    assert app.browser_panel.layout.display == "none"
    assert app.df is not None


def test_inline_browser_navigates_into_and_out_of_folders(tmp_path):
    nested = tmp_path / "archive"
    nested.mkdir()

    app = build_ui()
    app._open_browser(tmp_path)

    app.browser_list.value = str(nested)
    assert app._browse_dir == nested

    app._on_browser_up()
    assert app._browse_dir == tmp_path


def test_browser_use_without_a_file_selected_reports_an_error(tmp_path):
    app = build_ui()
    app._open_browser(tmp_path)
    app._on_browser_use()

    assert app.path_box.value == ""
    assert "select an excel file" in app.browser_status.value.lower()


def test_sql_mode_refreshes_tables_and_loads_dataframe(contract_df, monkeypatch):
    monkeypatch.setattr(widget_module, "list_sql_tables", lambda *_a, **_k: ["dbo.Contracts"])
    monkeypatch.setattr(
        widget_module,
        "load_source_dataframe",
        lambda source: contract_df.copy(),
    )
    monkeypatch.setattr(
        widget_module,
        "describe_source",
        lambda source: f"SQL Server table {source.table_name}",
    )

    app = build_ui()

    assert list(app.sql_table_dropdown.options) == ["dbo.Contracts"]

    app._on_load_sql()

    assert app.columns == list(contract_df.columns)
    assert len(app.df) == len(contract_df)
    assert "sql server table dbo.contracts" in app.load_status.value.lower()


def test_run_writes_both_reports(workbook, tmp_path):
    app = build_ui(default_output_dir=str(tmp_path / "out"))
    _use_excel_mode(app)
    app.path_box.value = str(workbook)
    app._on_load()

    app.preset_dropdown.value = "HPE Contract QC"
    app._on_preset()
    app._on_run()

    assert app.report is not None
    assert app.report.errored_checks == 0
    assert app.excel_path.exists()
    assert app.html_path.exists()
    assert len(app.run_output.children) == 2
    assert app.run_output.children[0].value.count("Run complete") == 1


def test_run_button_has_one_click_callback():
    app = build_ui()

    assert len(app.run_button._click_handlers.callbacks) == 1


def test_data_quality_defaults_to_sql_mode():
    app = build_ui()
    assert app.source_mode == "sql"
