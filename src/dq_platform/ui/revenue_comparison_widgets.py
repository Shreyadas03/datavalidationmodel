"""ipywidgets UI for two-workbook revenue validation."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Optional

import ipywidgets as widgets
import pandas as pd

from dq_platform.comparison import (
    RevenueComparisonReport,
    build_revenue_comparison_report,
    build_revenue_comparison_report_from_dataframes,
)
from dq_platform.io_utils import list_sheets, read_header_columns, resolve_path
from dq_platform.report.comparison import (
    write_revenue_comparison_excel,
    write_revenue_comparison_html,
)
from dq_platform.sources import SourceSpec, describe_source, list_sql_tables, load_source_dataframe
from dq_platform.ui.connection_widgets import ConnectionPanel

_WIDE = widgets.Layout(width="470px")
_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}
_DEFAULT_REVENUE_COLUMN = "Total Net Value Global"
_DEFAULT_CHANNEL_COLUMN = "Sales Channel Route Name"
_DEFAULT_TIER2_COLUMN = "Tier 2 Reseller Id"
_DEFAULT_ZDEL_DOCUMENT_TYPE_COLUMN = "Document type"
_DEFAULT_ZDEL_DOCUMENT_TYPE_VALUE = "ZDEL"
_DEFAULT_ZDEL_THRESHOLD_PCT = 5.0
_DEFAULT_RENEWAL_STATUS_COLUMN = "Renewal Status"
_DEFAULT_RENEWAL_STATUS_VALUE = "Renewed"
_DEFAULT_RENEWAL_QUOTE_COLUMN = "Renewal Quote Nbr"
_DEFAULT_RENEWAL_CONTRACT_DOC_COLUMN = "Renewal Contract Doc Nbr"
_DEFAULT_RENEWAL_THRESHOLD_PCT = 5.0


def _style() -> dict[str, str]:
    return {"description_width": "180px"}


def _native_file_dialog(initial_dir: Optional[Path] = None) -> Optional[str]:
    """Open the OS file picker, returning the selected workbook path."""
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            parent=root,
            title="Select an Excel workbook",
            initialdir=str(initial_dir) if initial_dir else None,
            filetypes=[
                ("Excel workbooks", "*.xlsx *.xlsm *.xltx *.xltm *.xls"),
                ("All files", "*.*"),
            ],
        )
        root.update()
    finally:
        root.destroy()
    return selected or None


class RevenueValidationApp:
    """Stateful controller for the two-workbook validation notebook app."""

    def __init__(self, default_output_dir: str = "../reports"):
        self.report: Optional[RevenueComparisonReport] = None
        self.excel_path: Optional[Path] = None
        self.html_path: Optional[Path] = None
        self._old_source: Optional[SourceSpec] = None
        self._new_source: Optional[SourceSpec] = None
        self._old_columns: list[str] = []
        self._new_columns: list[str] = []
        self._old_df: Optional[pd.DataFrame] = None
        self._new_df: Optional[pd.DataFrame] = None
        self._old_sql_tables_cache: Optional[list[str]] = None
        self._new_sql_tables_cache: Optional[list[str]] = None
        self._browse_dir: Path = Path.cwd()
        self._browse_target: Optional[str] = None
        self._build(default_output_dir)

    def _build(self, default_output_dir: str) -> None:
        self.old_source_mode_toggle = widgets.ToggleButtons(
            description="Old source",
            options=[("Excel", "excel"), ("SQL", "sql")],
            value="sql",
            style=_style(),
            layout=_WIDE,
        )
        self.old_path_box = widgets.Text(
            description="Old workbook",
            placeholder=r"C:\path\to\old.xlsx",
            style=_style(),
            layout=widgets.Layout(width="80%"),
        )
        self.old_browse_button = widgets.Button(
            description="Browse…",
            icon="folder-open",
            tooltip="Pick old workbook",
            layout=widgets.Layout(width="120px"),
        )
        self.new_path_box = widgets.Text(
            description="New workbook",
            placeholder=r"C:\path\to\new.xlsx",
            style=_style(),
            layout=widgets.Layout(width="80%"),
        )
        self.new_browse_button = widgets.Button(
            description="Browse…",
            icon="folder-open",
            tooltip="Pick new workbook",
            layout=widgets.Layout(width="120px"),
        )
        self.old_load_button = widgets.Button(description="Load old workbook", button_style="primary")
        self.new_load_button = widgets.Button(description="Load new workbook", button_style="primary")
        self.old_sheet_dropdown = widgets.Dropdown(
            description="Old sheet",
            options=[],
            style=_style(),
            layout=_WIDE,
            disabled=True,
        )
        self.old_sql_refresh_button = widgets.Button(description="Refresh tables", icon="refresh")
        self.old_sql_table_dropdown = widgets.Dropdown(
            description="Old SQL table",
            options=[],
            style=_style(),
            layout=_WIDE,
            disabled=True,
        )
        self.old_excel_panel = widgets.VBox(
            [
                widgets.HBox([self.old_path_box, self.old_browse_button]),
                widgets.HBox([self.old_load_button, self.old_sheet_dropdown]),
            ]
        )
        self.old_connection_panel = ConnectionPanel(title="Old source connection")
        self.old_sql_panel = widgets.VBox(
            [
                self.old_connection_panel.panel,
                self.old_sql_refresh_button,
                self.old_sql_table_dropdown,
            ],
            layout=widgets.Layout(display="none"),
        )
        self.new_source_mode_toggle = widgets.ToggleButtons(
            description="New source",
            options=[("Excel", "excel"), ("SQL", "sql")],
            value="sql",
            style=_style(),
            layout=_WIDE,
        )
        self.new_sheet_dropdown = widgets.Dropdown(
            description="New sheet",
            options=[],
            style=_style(),
            layout=_WIDE,
            disabled=True,
        )
        self.new_sql_refresh_button = widgets.Button(description="Refresh tables", icon="refresh")
        self.new_sql_table_dropdown = widgets.Dropdown(
            description="New SQL table",
            options=[],
            style=_style(),
            layout=_WIDE,
            disabled=True,
        )
        self.sql_load_button = widgets.Button(
            description="Load selected data",
            icon="database",
            button_style="primary",
            layout=widgets.Layout(display="none"),
            disabled=True,
        )
        self.new_excel_panel = widgets.VBox(
            [
                widgets.HBox([self.new_path_box, self.new_browse_button]),
                widgets.HBox([self.new_load_button, self.new_sheet_dropdown]),
            ]
        )
        self.new_connection_panel = ConnectionPanel(title="New source connection")
        self.new_sql_panel = widgets.VBox(
            [
                self.new_connection_panel.panel,
                self.new_sql_refresh_button,
                self.new_sql_table_dropdown,
            ],
            layout=widgets.Layout(display="none"),
        )
        self.old_status = widgets.HTML()
        self.new_status = widgets.HTML()
        self.browser_location = widgets.HTML()
        self.browser_list = widgets.Select(
            options=[],
            rows=10,
            layout=widgets.Layout(width="98%"),
        )
        self.browser_up = widgets.Button(description="Up one folder", icon="level-up")
        self.browser_use = widgets.Button(description="Use this file", icon="check", button_style="primary")
        self.browser_close = widgets.Button(description="Close", icon="times")
        self.browser_status = widgets.HTML()
        self.browser_panel = widgets.VBox(
            [
                widgets.HTML(
                    "<b style='font-family:Segoe UI,sans-serif'>Browse for a workbook</b>"
                    "<span style='color:#5f6b6d;font-size:12px'> — click a folder to open it, "
                    "click a file then <i>Use this file</i>.</span>"
                ),
                self.browser_location,
                self.browser_list,
                widgets.HBox([self.browser_up, self.browser_use, self.browser_close]),
                self.browser_status,
            ],
            layout=widgets.Layout(
                display="none",
                border="1px solid #c9d1d3",
                padding="8px",
                margin="6px 0",
                width="98%",
            ),
        )

        self.revenue_column_box = widgets.Combobox(
            description="Revenue column",
            value=_DEFAULT_REVENUE_COLUMN,
            options=[_DEFAULT_REVENUE_COLUMN],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.channel_profile_column_box = widgets.Combobox(
            description="Channel profile column",
            value=_DEFAULT_CHANNEL_COLUMN,
            options=[_DEFAULT_CHANNEL_COLUMN],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.tier2_reseller_column_box = widgets.Combobox(
            description="Tier 2 reseller column",
            value=_DEFAULT_TIER2_COLUMN,
            options=[_DEFAULT_TIER2_COLUMN],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.zdel_document_type_column_box = widgets.Combobox(
            description="Document type column name",
            value=_DEFAULT_ZDEL_DOCUMENT_TYPE_COLUMN,
            options=[_DEFAULT_ZDEL_DOCUMENT_TYPE_COLUMN],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.zdel_document_type_value_box = widgets.Combobox(
            description="Document type",
            value=_DEFAULT_ZDEL_DOCUMENT_TYPE_VALUE,
            options=[_DEFAULT_ZDEL_DOCUMENT_TYPE_VALUE],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.zdel_threshold_pct_box = widgets.FloatText(
            description="ZDEL threshold %",
            value=_DEFAULT_ZDEL_THRESHOLD_PCT,
            style=_style(),
            layout=_WIDE,
        )
        self.renewal_status_column_box = widgets.Combobox(
            description="Renewal status column",
            value=_DEFAULT_RENEWAL_STATUS_COLUMN,
            options=[_DEFAULT_RENEWAL_STATUS_COLUMN],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.renewal_status_value_box = widgets.Combobox(
            description="Renewal status value",
            value=_DEFAULT_RENEWAL_STATUS_VALUE,
            options=[_DEFAULT_RENEWAL_STATUS_VALUE],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.renewal_quote_column_box = widgets.Combobox(
            description="Renewal quote column",
            value=_DEFAULT_RENEWAL_QUOTE_COLUMN,
            options=[_DEFAULT_RENEWAL_QUOTE_COLUMN],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.renewal_contract_doc_column_box = widgets.Combobox(
            description="Renewal contract doc column",
            value=_DEFAULT_RENEWAL_CONTRACT_DOC_COLUMN,
            options=[_DEFAULT_RENEWAL_CONTRACT_DOC_COLUMN],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.renewal_threshold_pct_box = widgets.FloatText(
            description="Renewal threshold %",
            value=_DEFAULT_RENEWAL_THRESHOLD_PCT,
            style=_style(),
            layout=_WIDE,
        )
        self.subregion_column_box = widgets.Combobox(
            description="Subregion column",
            placeholder="Optional: geography column for Tier 2 missing breakdown",
            value="",
            options=[],
            ensure_option=False,
            style=_style(),
            layout=_WIDE,
        )
        self.output_dir_box = widgets.Text(
            description="Output folder",
            value=default_output_dir,
            style=_style(),
            layout=_WIDE,
        )

        self.run_button = widgets.Button(
            description="Run revenue validation",
            icon="play",
            button_style="danger",
        )
        self.run_status = widgets.HTML()
        self.results_area = widgets.VBox()

        self.old_browse_button.on_click(self._on_browse_old)
        self.new_browse_button.on_click(self._on_browse_new)
        self.old_source_mode_toggle.observe(self._on_old_source_mode_change, names="value")
        self.new_source_mode_toggle.observe(self._on_new_source_mode_change, names="value")
        self.old_load_button.on_click(self._on_load_old)
        self.new_load_button.on_click(self._on_load_new)
        self.old_sql_refresh_button.on_click(self._on_refresh_old_tables)
        self.new_sql_refresh_button.on_click(self._on_refresh_new_tables)
        self.sql_load_button.on_click(self._on_load_sql_sources)
        self.old_sql_table_dropdown.observe(
            self._on_sql_table_selection_change,
            names="value",
        )
        self.new_sql_table_dropdown.observe(
            self._on_sql_table_selection_change,
            names="value",
        )
        self.zdel_document_type_column_box.observe(
            self._on_zdel_document_type_column_change,
            names="value",
        )
        self.renewal_status_column_box.observe(
            self._on_renewal_status_column_change,
            names="value",
        )
        self.browser_list.observe(self._on_browser_select, names="value")
        self.browser_up.on_click(self._on_browser_up)
        self.browser_use.on_click(self._on_browser_use)
        self.browser_close.on_click(self._on_browser_close)
        self.run_button.on_click(self._on_run)

        self._sync_source_panels()
        self._sync_validation_column_options()
        if self.old_source_mode == "sql" or self.new_source_mode == "sql":
            self._on_refresh_sql_tables(status_target="both", force=False)

        self.widget = widgets.VBox(
            [
                self._section("1. Select old and new sources"),
                self.old_source_mode_toggle,
                self.old_excel_panel,
                self.old_sql_panel,
                self.old_status,
                self.new_source_mode_toggle,
                self.new_excel_panel,
                self.new_sql_panel,
                self.new_status,
                self.sql_load_button,
                self.browser_panel,
                self._section("2. Validation columns"),
                self.revenue_column_box,
                self.channel_profile_column_box,
                self.tier2_reseller_column_box,
                self.zdel_document_type_column_box,
                self.zdel_document_type_value_box,
                self.zdel_threshold_pct_box,
                self.renewal_status_column_box,
                self.renewal_status_value_box,
                self.renewal_quote_column_box,
                self.renewal_contract_doc_column_box,
                self.renewal_threshold_pct_box,
                self.subregion_column_box,
                self._section("3. Generate comparison report"),
                self.output_dir_box,
                self.run_button,
                self.run_status,
                self.results_area,
            ]
        )

    @staticmethod
    def _section(title: str) -> widgets.HTML:
        return widgets.HTML(
            f"<h3 style='margin:18px 0 6px;border-left:4px solid #01a982;"
            f"padding-left:8px;font-family:Segoe UI,sans-serif'>{html.escape(title)}</h3>"
        )

    @staticmethod
    def _error(message: str) -> str:
        return f"<span style='color:#b00020'><b>Error:</b> {html.escape(message)}</span>"

    @staticmethod
    def _ok(message: str) -> str:
        return f"<span style='color:#00674f'>{html.escape(message)}</span>"

    @property
    def old_source_mode(self) -> str:
        return str(self.old_source_mode_toggle.value)

    @property
    def new_source_mode(self) -> str:
        return str(self.new_source_mode_toggle.value)

    def _start_dir(self, raw_path: str) -> Path:
        cleaned = str(raw_path).strip().strip('"').strip("'")
        if cleaned:
            candidate = Path(cleaned)
            if candidate.is_file():
                return candidate.parent
            if candidate.is_dir():
                return candidate
        return Path.cwd()

    def _browse_for_target(self, target: str, path_value: str) -> None:
        start = self._start_dir(path_value)
        try:
            selected = _native_file_dialog(start)
        except Exception:
            self._open_browser(start, target)
            return

        if not selected:
            return
        self.browser_panel.layout.display = "none"
        if target == "old":
            self.old_path_box.value = selected
            self._on_load_old()
        else:
            self.new_path_box.value = selected
            self._on_load_new()

    def _on_browse_old(self, _button=None) -> None:
        self._browse_for_target("old", self.old_path_box.value)

    def _on_browse_new(self, _button=None) -> None:
        self._browse_for_target("new", self.new_path_box.value)

    def _on_old_source_mode_change(self, _change=None) -> None:
        self._old_source = None
        self._old_columns = []
        self._old_df = None
        self.old_status.value = ""
        self.old_sheet_dropdown.options = []
        self.old_sheet_dropdown.disabled = True
        self.old_sql_table_dropdown.options = []
        self.old_sql_table_dropdown.disabled = True
        self.browser_panel.layout.display = "none"
        self._sync_source_panels()
        self._sync_validation_column_options()
        if self.old_source_mode == "sql":
            self._on_refresh_sql_tables(status_target="old", force=False)

    def _on_new_source_mode_change(self, _change=None) -> None:
        self._new_source = None
        self._new_columns = []
        self._new_df = None
        self.new_status.value = ""
        self.new_sheet_dropdown.options = []
        self.new_sheet_dropdown.disabled = True
        self.new_sql_table_dropdown.options = []
        self.new_sql_table_dropdown.disabled = True
        self.browser_panel.layout.display = "none"
        self._sync_source_panels()
        self._sync_validation_column_options()
        if self.new_source_mode == "sql":
            self._on_refresh_sql_tables(status_target="new", force=False)

    def _sync_source_panels(self) -> None:
        self.old_excel_panel.layout.display = "" if self.old_source_mode == "excel" else "none"
        self.old_sql_panel.layout.display = "" if self.old_source_mode == "sql" else "none"
        self.new_excel_panel.layout.display = "" if self.new_source_mode == "excel" else "none"
        self.new_sql_panel.layout.display = "" if self.new_source_mode == "sql" else "none"
        self.sql_load_button.layout.display = (
            ""
            if self.old_source_mode == "sql" or self.new_source_mode == "sql"
            else "none"
        )
        self._set_sql_load_button_ready()

    def _open_browser(self, start: Path, target: str) -> None:
        self._browse_dir = start
        self._browse_target = target
        self.browser_panel.layout.display = ""
        self.browser_status.value = (
            "<span style='color:#5f6b6d'>Selecting for <b>{}</b> workbook.</span>".format(
                "old" if target == "old" else "new"
            )
        )
        self._render_browser()

    def _render_browser(self) -> None:
        self.browser_location.value = (
            "<code style='font-size:12px'>{}</code>".format(html.escape(str(self._browse_dir)))
        )
        try:
            entries = sorted(
                self._browse_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except OSError as exc:
            self.browser_list.options = []
            self.browser_status.value = self._error(str(exc))
            return

        options = []
        for entry in entries:
            try:
                if entry.is_dir():
                    options.append((f"📁 {entry.name}", str(entry)))
                elif entry.suffix.lower() in _EXCEL_SUFFIXES:
                    options.append((f"📄 {entry.name}", str(entry)))
            except OSError:
                continue

        self.browser_list.unobserve(self._on_browser_select, names="value")
        self.browser_list.options = options
        self.browser_list.index = None
        self.browser_list.observe(self._on_browser_select, names="value")
        if not options:
            self.browser_status.value = (
                "<span style='color:#5f6b6d'>No sub-folders or Excel files here.</span>"
            )

    def _on_browser_select(self, _change=None) -> None:
        selected = self.browser_list.value
        if selected and Path(selected).is_dir():
            self._browse_dir = Path(selected)
            self._render_browser()

    def _on_browser_up(self, _button=None) -> None:
        parent = self._browse_dir.parent
        if parent != self._browse_dir:
            self._browse_dir = parent
            self._render_browser()

    def _on_browser_use(self, _button=None) -> None:
        selected = self.browser_list.value
        if not selected or Path(selected).is_dir():
            self.browser_status.value = self._error("Select an Excel file first.")
            return
        if self._browse_target == "old":
            self.old_path_box.value = selected
            self._on_load_old()
        else:
            self.new_path_box.value = selected
            self._on_load_new()
        self.browser_panel.layout.display = "none"
        self.browser_status.value = ""

    def _on_browser_close(self, _button=None) -> None:
        self.browser_panel.layout.display = "none"

    def _status_targets(self, status_target: str) -> list[str]:
        if status_target == "old":
            return ["old"]
        if status_target == "new":
            return ["new"]
        return ["old", "new"]

    def _set_sql_load_button_ready(self) -> None:
        self.sql_load_button.description = "Load selected data"
        self.sql_load_button.icon = "database"
        self.sql_load_button.button_style = "primary"
        self._sync_sql_load_button_disabled()

    def _set_sql_load_button_loading(self) -> None:
        self.sql_load_button.description = "Loading data…"
        self.sql_load_button.icon = "hourglass-half"
        self.sql_load_button.button_style = "warning"
        self.sql_load_button.disabled = True

    def _set_sql_load_button_loaded(self) -> None:
        self.sql_load_button.description = "Data loaded"
        self.sql_load_button.icon = "check"
        self.sql_load_button.button_style = "success"
        self._sync_sql_load_button_disabled()

    def _sync_sql_load_button_disabled(self) -> None:
        requires_old_table = self.old_source_mode == "sql"
        requires_new_table = self.new_source_mode == "sql"
        has_old_table = bool(str(self.old_sql_table_dropdown.value or "").strip())
        has_new_table = bool(str(self.new_sql_table_dropdown.value or "").strip())
        self.sql_load_button.disabled = (requires_old_table and not has_old_table) or (
            requires_new_table and not has_new_table
        )

    def _on_sql_table_selection_change(self, _change=None) -> None:
        self._sync_sql_load_button_disabled()

    def _sync_validation_column_options(self) -> None:
        options: list[str] = []
        seen: set[str] = set()
        for column in [*self._old_columns, *self._new_columns]:
            if column and column not in seen:
                seen.add(column)
                options.append(column)
        if not options:
            options = [
                _DEFAULT_REVENUE_COLUMN,
                _DEFAULT_CHANNEL_COLUMN,
                _DEFAULT_TIER2_COLUMN,
                _DEFAULT_ZDEL_DOCUMENT_TYPE_COLUMN,
                _DEFAULT_RENEWAL_STATUS_COLUMN,
                _DEFAULT_RENEWAL_QUOTE_COLUMN,
                _DEFAULT_RENEWAL_CONTRACT_DOC_COLUMN,
            ]

        self.revenue_column_box.options = options
        self.channel_profile_column_box.options = options
        self.tier2_reseller_column_box.options = options
        self.zdel_document_type_column_box.options = options
        self.renewal_status_column_box.options = options
        self.renewal_quote_column_box.options = options
        self.renewal_contract_doc_column_box.options = options
        self.subregion_column_box.options = options
        self._sync_document_type_value_options()
        self._sync_renewal_status_value_options()

    def _on_zdel_document_type_column_change(self, _change=None) -> None:
        self._sync_document_type_value_options()

    def _distinct_values_from(self, frame: Optional[pd.DataFrame], column_name: str) -> list[str]:
        if frame is None:
            return []
        candidate = str(column_name).strip()
        if not candidate:
            return []
        resolved = next(
            (str(col) for col in frame.columns if str(col).strip().lower() == candidate.lower()),
            None,
        )
        if resolved is None:
            return []
        series = frame[resolved].astype("string").str.strip()
        values: list[str] = []
        seen: set[str] = set()
        for value in series.dropna():
            text = str(value).strip()
            if not text:
                continue
            key = text.upper()
            if key in seen:
                continue
            seen.add(key)
            values.append(text)
        return values

    def _sync_document_type_value_options(self) -> None:
        selected_column = str(self.zdel_document_type_column_box.value or "").strip()
        old_values = self._distinct_values_from(self._old_df, selected_column)
        new_values = self._distinct_values_from(self._new_df, selected_column)
        options: list[str] = []
        seen: set[str] = set()
        for value in [*old_values, *new_values]:
            key = value.upper()
            if key in seen:
                continue
            seen.add(key)
            options.append(value)
        if not options:
            options = [_DEFAULT_ZDEL_DOCUMENT_TYPE_VALUE]
        current_value = str(self.zdel_document_type_value_box.value or "").strip()
        self.zdel_document_type_value_box.options = options
        if not current_value:
            self.zdel_document_type_value_box.value = options[0]
            return
        matching = next((value for value in options if value.lower() == current_value.lower()), None)
        self.zdel_document_type_value_box.value = matching if matching is not None else options[0]

    def _on_renewal_status_column_change(self, _change=None) -> None:
        self._sync_renewal_status_value_options()

    def _sync_renewal_status_value_options(self) -> None:
        selected_column = str(self.renewal_status_column_box.value or "").strip()
        old_values = self._distinct_values_from(self._old_df, selected_column)
        new_values = self._distinct_values_from(self._new_df, selected_column)
        options: list[str] = []
        seen: set[str] = set()
        for value in [*old_values, *new_values]:
            key = value.upper()
            if key in seen:
                continue
            seen.add(key)
            options.append(value)
        if not options:
            options = [_DEFAULT_RENEWAL_STATUS_VALUE]
        current_value = str(self.renewal_status_value_box.value or "").strip()
        self.renewal_status_value_box.options = options
        if not current_value:
            self.renewal_status_value_box.value = options[0]
            return
        matching = next((value for value in options if value.lower() == current_value.lower()), None)
        self.renewal_status_value_box.value = matching if matching is not None else options[0]

    def _apply_sql_tables_to(self, dropdown: widgets.Dropdown, tables: list[str]) -> None:
        selected = str(dropdown.value or "")
        dropdown.options = tables
        dropdown.disabled = not bool(tables)
        if tables:
            dropdown.value = selected if selected in tables else tables[0]

    def _get_sql_tables_for(self, which: str, force: bool) -> list[str]:
        cache_attr = "_old_sql_tables_cache" if which == "old" else "_new_sql_tables_cache"
        cached = getattr(self, cache_attr, None)
        if force or cached is None:
            connection_panel = self.old_connection_panel if which == "old" else self.new_connection_panel
            cached = list_sql_tables(connection_panel.current_settings())
            setattr(self, cache_attr, cached)
        return list(cached)

    def _on_refresh_sql_tables(self, status_target: str, force: bool) -> None:
        targets = self._status_targets(status_target)
        for target in targets:
            if target == "old":
                self.old_status.value = "<span style='color:#5f6b6d'>Reading SQL Server tables…</span>"
            else:
                self.new_status.value = "<span style='color:#5f6b6d'>Reading SQL Server tables…</span>"

        for target in targets:
            dropdown = self.old_sql_table_dropdown if target == "old" else self.new_sql_table_dropdown
            try:
                tables = self._get_sql_tables_for(target, force=force)
                self._apply_sql_tables_to(dropdown, tables)
            except Exception as exc:
                dropdown.options = []
                dropdown.disabled = True
                cache_attr = "_old_sql_tables_cache" if target == "old" else "_new_sql_tables_cache"
                setattr(self, cache_attr, None)
                message = self._error(str(exc))
                if target == "old":
                    self.old_status.value = message
                else:
                    self.new_status.value = message
                continue

            message = (
                self._ok(f"Found {len(tables)} SQL table(s).")
                if tables
                else self._error("No SQL tables or views were returned.")
            )
            if target == "old":
                self.old_status.value = message
            else:
                self.new_status.value = message
        self._set_sql_load_button_ready()

    def _on_refresh_old_tables(self, _button=None) -> None:
        self._on_refresh_sql_tables(status_target="old", force=True)

    def _on_refresh_new_tables(self, _button=None) -> None:
        self._on_refresh_sql_tables(status_target="new", force=True)

    def _load_sheets_into(self, path_value: str, dropdown: widgets.Dropdown) -> tuple[str, list[str]]:
        path = resolve_path(path_value)
        sheets = list_sheets(path)
        if not sheets:
            raise ValueError(f"No sheets found in workbook: {path}")
        dropdown.options = sheets
        dropdown.value = sheets[0]
        dropdown.disabled = False
        columns = [str(column) for column in read_header_columns(path, str(dropdown.value))]
        return str(path), columns

    def _load_sql_source_into(
        self,
        table_name: str,
        which: str,
    ) -> tuple[SourceSpec, list[str], pd.DataFrame]:
        connection_panel = self.old_connection_panel if which == "old" else self.new_connection_panel
        source = SourceSpec(
            mode="sql", table_name=table_name, connection_settings=connection_panel.current_settings()
        )
        df = load_source_dataframe(source)
        columns = [str(column) for column in df.columns]
        if which == "old":
            self._old_source = source
            self._old_columns = columns
            self._old_df = df
        else:
            self._new_source = source
            self._new_columns = columns
            self._new_df = df
        return source, columns, df

    def _on_load_old(self, _button=None) -> None:
        if self.old_source_mode == "sql":
            self._on_load_sql_sources()
            return
        try:
            path, columns = self._load_sheets_into(self.old_path_box.value, self.old_sheet_dropdown)
        except Exception as exc:
            self.old_sheet_dropdown.options = []
            self.old_sheet_dropdown.disabled = True
            self._old_columns = []
            self.old_status.value = self._error(str(exc))
            self._sync_validation_column_options()
            return
        self._old_source = SourceSpec(
            mode="excel",
            path=path,
            sheet_name=str(self.old_sheet_dropdown.value),
        )
        try:
            self._old_df = load_source_dataframe(self._old_source)
        except Exception as exc:
            self._old_source = None
            self._old_columns = []
            self._old_df = None
            self.old_status.value = self._error(str(exc))
            self._sync_validation_column_options()
            return
        self._old_columns = columns
        self.old_status.value = self._ok(f"Loaded old workbook: {path}")
        self._sync_validation_column_options()

    def _on_load_new(self, _button=None) -> None:
        if self.new_source_mode == "sql":
            self._on_load_sql_sources()
            return
        try:
            path, columns = self._load_sheets_into(self.new_path_box.value, self.new_sheet_dropdown)
        except Exception as exc:
            self.new_sheet_dropdown.options = []
            self.new_sheet_dropdown.disabled = True
            self._new_columns = []
            self.new_status.value = self._error(str(exc))
            self._sync_validation_column_options()
            return
        self._new_source = SourceSpec(
            mode="excel",
            path=path,
            sheet_name=str(self.new_sheet_dropdown.value),
        )
        try:
            self._new_df = load_source_dataframe(self._new_source)
        except Exception as exc:
            self._new_source = None
            self._new_columns = []
            self._new_df = None
            self.new_status.value = self._error(str(exc))
            self._sync_validation_column_options()
            return
        self._new_columns = columns
        self.new_status.value = self._ok(f"Loaded new workbook: {path}")
        self._sync_validation_column_options()

    def _on_load_sql_sources(self, _button=None) -> None:
        load_old = self.old_source_mode == "sql"
        load_new = self.new_source_mode == "sql"
        if not load_old and not load_new:
            self.old_status.value = self._error("Switch a source to SQL mode before loading SQL data.")
            return

        self._set_sql_load_button_loading()
        has_errors = False

        if load_old:
            self.old_status.value = "<span style='color:#5f6b6d'>Loading old SQL table…</span>"
            try:
                old_source, _old_columns, _old_df = self._load_sql_source_into(
                    str(self.old_sql_table_dropdown.value or "").strip(), "old"
                )
            except Exception as exc:
                self._old_source = None
                self._old_columns = []
                self._old_df = None
                self.old_status.value = self._error(str(exc))
                has_errors = True
            else:
                self.old_status.value = self._ok(f"Data loaded: {describe_source(old_source)}")

        if load_new:
            self.new_status.value = "<span style='color:#5f6b6d'>Loading new SQL table…</span>"
            try:
                new_source, _new_columns, _new_df = self._load_sql_source_into(
                    str(self.new_sql_table_dropdown.value or "").strip(), "new"
                )
            except Exception as exc:
                self._new_source = None
                self._new_columns = []
                self._new_df = None
                self.new_status.value = self._error(str(exc))
                has_errors = True
            else:
                self.new_status.value = self._ok(f"Data loaded: {describe_source(new_source)}")

        self._sync_validation_column_options()
        if has_errors:
            self._set_sql_load_button_ready()
            return
        self._set_sql_load_button_loaded()

    def _old_source_spec(self) -> SourceSpec:
        if self.old_source_mode == "excel":
            sheet_name = self.old_sheet_dropdown.value if self.old_sheet_dropdown.options else None
            return SourceSpec(mode="excel", path=self.old_path_box.value, sheet_name=sheet_name)
        return SourceSpec(
            mode="sql",
            table_name=str(self.old_sql_table_dropdown.value or "").strip(),
            connection_settings=self.old_connection_panel.current_settings(),
        )

    def _new_source_spec(self) -> SourceSpec:
        if self.new_source_mode == "excel":
            sheet_name = self.new_sheet_dropdown.value if self.new_sheet_dropdown.options else None
            return SourceSpec(mode="excel", path=self.new_path_box.value, sheet_name=sheet_name)
        return SourceSpec(
            mode="sql",
            table_name=str(self.new_sql_table_dropdown.value or "").strip(),
            connection_settings=self.new_connection_panel.current_settings(),
        )

    def build_revenue_report(self) -> RevenueComparisonReport:
        old_source = self._old_source_spec()
        new_source = self._new_source_spec()
        if old_source.mode == "excel" and new_source.mode == "excel":
            return build_revenue_comparison_report(
                old_workbook_path=self.old_path_box.value,
                new_workbook_path=self.new_path_box.value,
                old_sheet_name=self.old_sheet_dropdown.value if self.old_sheet_dropdown.options else None,
                new_sheet_name=self.new_sheet_dropdown.value if self.new_sheet_dropdown.options else None,
                revenue_column=self.revenue_column_box.value,
                channel_profile_column=self.channel_profile_column_box.value,
                tier2_reseller_column=self.tier2_reseller_column_box.value,
                zdel_document_type_column=self.zdel_document_type_column_box.value,
                zdel_document_type_value=self.zdel_document_type_value_box.value,
                zdel_threshold_pct=float(self.zdel_threshold_pct_box.value),
                renewal_status_column=self.renewal_status_column_box.value,
                renewal_status_value=self.renewal_status_value_box.value,
                renewal_quote_number_column=self.renewal_quote_column_box.value,
                renewal_contract_doc_number_column=self.renewal_contract_doc_column_box.value,
                renewal_threshold_pct=float(self.renewal_threshold_pct_box.value),
                subregion_column=self.subregion_column_box.value or None,
            )

        old_df = load_source_dataframe(old_source)
        new_df = load_source_dataframe(new_source)
        return build_revenue_comparison_report_from_dataframes(
            old_df,
            new_df,
            old_source_label=describe_source(old_source),
            new_source_label=describe_source(new_source),
            old_selection_label=str(
                old_source.sheet_name if old_source.mode == "excel" else old_source.table_name
            ),
            new_selection_label=str(
                new_source.sheet_name if new_source.mode == "excel" else new_source.table_name
            ),
            revenue_column=self.revenue_column_box.value,
            channel_profile_column=self.channel_profile_column_box.value,
            tier2_reseller_column=self.tier2_reseller_column_box.value,
            zdel_document_type_column=self.zdel_document_type_column_box.value,
            zdel_document_type_value=self.zdel_document_type_value_box.value,
            zdel_threshold_pct=float(self.zdel_threshold_pct_box.value),
            renewal_status_column=self.renewal_status_column_box.value,
            renewal_status_value=self.renewal_status_value_box.value,
            renewal_quote_number_column=self.renewal_quote_column_box.value,
            renewal_contract_doc_number_column=self.renewal_contract_doc_column_box.value,
            renewal_threshold_pct=float(self.renewal_threshold_pct_box.value),
            subregion_column=self.subregion_column_box.value or None,
        )

    def _on_run(self, _button=None) -> None:
        self.results_area.children = ()
        self.run_status.value = "<span style='color:#5f6b6d'>Running…</span>"

        try:
            report = self.build_revenue_report()
        except Exception as exc:
            self.run_status.value = self._error(str(exc))
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(self.output_dir_box.value.strip() or "reports")
        output_dir.mkdir(parents=True, exist_ok=True)

        excel_path = output_dir / f"Revenue_Validation_Report_{timestamp}.xlsx"
        html_path = output_dir / f"Revenue_Validation_Report_{timestamp}.html"

        self.excel_path = write_revenue_comparison_excel(report, excel_path)
        self.html_path = write_revenue_comparison_html(report, html_path)
        self.report = report

        summary = report.summary_frame().head(12)
        summary_table = widgets.HTML(summary.to_html(index=False, escape=True, border=0))
        links = widgets.HTML(
            "<div style='margin:8px 0'><b>Run complete.</b><br>"
            f"Excel: <code>{html.escape(str(self.excel_path))}</code><br>"
            f"HTML: <code>{html.escape(str(self.html_path))}</code></div>"
        )
        self.results_area.children = [links, summary_table]
        error_messages: list[str] = []
        if report.zdel_threshold_exceeded:
            error_messages.append(
                f'{report.zdel_threshold_message} (difference: {round(report.zdel_delta, 2)})'
            )
        if report.renewal_threshold_exceeded:
            error_messages.append(report.renewal_threshold_message)
        if error_messages:
            self.run_status.value = self._error(" | ".join(error_messages))
            return
        self.run_status.value = self._ok(
            "Validation complete: "
            f"{report.indirect_missing_tier2_count} indirect rows missing Tier 2 reseller. "
            f"ZDEL difference: {round(report.zdel_delta, 2)}. "
            f"Renewal missing rows old/new: {report.renewal_old_missing_count}/{report.renewal_new_missing_count}."
        )


def build_revenue_validation_ui(default_output_dir: str = "../reports") -> RevenueValidationApp:
    return RevenueValidationApp(default_output_dir=default_output_dir)
