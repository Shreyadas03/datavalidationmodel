"""ipywidgets front end.

Everything the user can configure is derived from :data:`dq_platform.registry.RULE_REGISTRY`,
so new rules appear in the UI automatically.
"""

from __future__ import annotations

import html
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import ipywidgets as widgets
import pandas as pd
from IPython.display import display

from dq_platform.engine import run_checks
from dq_platform.io_utils import list_sheets, load_dataframe, resolve_path
from dq_platform.models import QualityReport, RuleSpec
from dq_platform.presets import PRESETS, build_preset_specs
from dq_platform.registry import RULE_DEFINITIONS, RuleDefinition, get_rule
from dq_platform.report.excel import write_excel_report
from dq_platform.report.html import write_html_report
from dq_platform.sources import SourceSpec, describe_source, list_sql_tables, load_source_dataframe
from dq_platform.ui.connection_widgets import ConnectionPanel

_WIDE = widgets.Layout(width="440px")
_FULL = widgets.Layout(width="98%")

_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}


def _style() -> Dict[str, str]:
    return {"description_width": "190px"}


def _native_file_dialog(initial_dir: Optional[Path] = None) -> Optional[str]:
    """Open the operating-system file picker.

    Raises when no GUI toolkit is reachable (remote kernel, container, WSL without
    an X server) so the caller can fall back to the inline browser.
    """
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


def _rule_options() -> List[tuple]:
    grouped: Dict[str, List[RuleDefinition]] = {}
    for definition in RULE_DEFINITIONS:
        grouped.setdefault(definition.dimension, []).append(definition)

    options: List[tuple] = []
    for dimension in sorted(grouped):
        for definition in grouped[dimension]:
            options.append((f"{dimension}  \u2022  {definition.label}", definition.rule_id))
    return options


class DataQualityApp:
    """Stateful controller behind the notebook UI."""

    def __init__(self, default_output_dir: str = "../reports"):
        self.df: Optional[pd.DataFrame] = None
        self.columns: List[str] = []
        self.specs: List[RuleSpec] = []
        self.report: Optional[QualityReport] = None
        self.excel_path: Optional[Path] = None
        self.html_path: Optional[Path] = None
        self._loaded_source: Optional[SourceSpec] = None
        self._param_widgets: Dict[str, widgets.Widget] = {}
        self._column_widgets: List[widgets.Widget] = []
        self._browse_dir: Path = Path.cwd()
        self._build(default_output_dir)

    # ------------------------------------------------------------------ building

    def _build(self, default_output_dir: str) -> None:
        self.source_mode_toggle = widgets.ToggleButtons(
            description="Source mode",
            options=[("Excel", "excel"), ("SQL", "sql")],
            value="sql",
            style=_style(),
            layout=_WIDE,
        )
        self.source_help = widgets.HTML()
        self.path_box = widgets.Text(
            description="Excel file path",
            placeholder=r"C:\path\to\SAMPLE AI.xlsx",
            style=_style(),
            layout=widgets.Layout(width="72%"),
        )
        self.browse_button = widgets.Button(
            description="Browse\u2026",
            icon="folder-open",
            tooltip="Pick an Excel file from your computer",
            layout=widgets.Layout(width="140px"),
        )
        self.load_button = widgets.Button(
            description="Load file", icon="folder-open", button_style="primary"
        )
        self.sheet_dropdown = widgets.Dropdown(
            description="Sheet", options=[], style=_style(), layout=_WIDE, disabled=True
        )
        self.load_status = widgets.HTML()

        self.browser_location = widgets.HTML()
        self.browser_list = widgets.Select(
            options=[], rows=10, layout=widgets.Layout(width="98%")
        )
        self.browser_up = widgets.Button(description="Up one folder", icon="level-up")
        self.browser_use = widgets.Button(
            description="Use this file", icon="check", button_style="primary"
        )
        self.browser_close = widgets.Button(description="Close", icon="times")
        self.browser_status = widgets.HTML()
        self.browser_panel = widgets.VBox(
            [
                widgets.HTML(
                    "<b style='font-family:Segoe UI,sans-serif'>Browse for a workbook</b>"
                    "<span style='color:#5f6b6d;font-size:12px'> \u2014 click a folder to open it, "
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
        self.excel_panel = widgets.VBox(
            [
                widgets.HBox([self.path_box, self.browse_button]),
                self.browser_panel,
                widgets.HBox([self.load_button, self.sheet_dropdown]),
            ]
        )
        self.sql_refresh_button = widgets.Button(description="Refresh tables", icon="refresh")
        self.sql_table_dropdown = widgets.Dropdown(
            description="SQL table",
            options=[],
            style=_style(),
            layout=_WIDE,
            disabled=True,
        )
        self.sql_load_button = widgets.Button(
            description="Load table", icon="database", button_style="primary"
        )
        self.connection_panel = ConnectionPanel(title="Manage connections")
        self.sql_panel = widgets.VBox(
            [
                self.connection_panel.panel,
                widgets.HBox([self.sql_refresh_button, self.sql_load_button]),
                self.sql_table_dropdown,
            ],
            layout=widgets.Layout(display="none"),
        )

        self.preset_dropdown = widgets.Dropdown(
            description="Preset", options=list(PRESETS), style=_style(), layout=_WIDE
        )
        self.preset_button = widgets.Button(description="Add preset checks", icon="magic")
        self.preset_help = widgets.HTML()

        self.rule_dropdown = widgets.Dropdown(
            description="Validation",
            options=_rule_options(),
            style=_style(),
            layout=_FULL,
        )
        self.rule_help = widgets.HTML()
        self.column_area = widgets.VBox()
        self.param_area = widgets.VBox()
        self.add_button = widgets.Button(
            description="Add this check", icon="plus", button_style="success"
        )
        self.add_status = widgets.HTML()

        self.selected_area = widgets.VBox()
        self.clear_button = widgets.Button(description="Clear all", icon="trash")

        self.output_dir_box = widgets.Text(
            description="Output folder", value=default_output_dir, style=_style(), layout=_WIDE
        )
        self.row_limit_box = widgets.IntText(
            description="Max flagged rows/sheet", value=5000, style=_style(), layout=_WIDE
        )
        self.run_button = widgets.Button(
            description="Run quality checks", icon="play", button_style="danger"
        )
        self.run_output = widgets.VBox()

        self.load_button.on_click(self._on_load)
        self.browse_button.on_click(self._on_browse)
        self.source_mode_toggle.observe(self._on_source_mode_change, names="value")
        self.browser_list.observe(self._on_browser_select, names="value")
        self.browser_up.on_click(self._on_browser_up)
        self.browser_use.on_click(self._on_browser_use)
        self.browser_close.on_click(self._on_browser_close)
        self.sheet_dropdown.observe(self._on_sheet_change, names="value")
        self.sql_refresh_button.on_click(self._on_refresh_sql_tables)
        self.sql_load_button.on_click(self._on_load_sql)
        self.rule_dropdown.observe(self._on_rule_change, names="value")
        self.add_button.on_click(self._on_add)
        self.preset_button.on_click(self._on_preset)
        self.preset_dropdown.observe(self._on_preset_change, names="value")
        self.clear_button.on_click(self._on_clear)
        self.run_button.on_click(self._on_run)

        self._sync_source_mode_ui()
        if self.source_mode == "sql":
            self._on_refresh_sql_tables()
        self._on_rule_change()
        self._on_preset_change()
        self._refresh_selected()

        self.widget = widgets.VBox(
            [
                self._section("1. Source data"),
                self.source_mode_toggle,
                self.source_help,
                self.excel_panel,
                self.sql_panel,
                self.load_status,
                self._section("2. Quick start with a preset"),
                widgets.HBox([self.preset_dropdown, self.preset_button]),
                self.preset_help,
                self._section("3. Add individual validations"),
                self.rule_dropdown,
                self.rule_help,
                self.column_area,
                self.param_area,
                widgets.HBox([self.add_button, self.add_status]),
                self._section("4. Selected checks"),
                self.selected_area,
                self.clear_button,
                self._section("5. Generate the report"),
                widgets.HBox([self.output_dir_box, self.row_limit_box]),
                self.run_button,
                self.run_output,
            ]
        )

    @staticmethod
    def _section(title: str) -> widgets.HTML:
        return widgets.HTML(
            f"<h3 style='margin:18px 0 6px;border-left:4px solid #01a982;"
            f"padding-left:8px;font-family:Segoe UI,sans-serif'>{html.escape(title)}</h3>"
        )

    @property
    def source_mode(self) -> str:
        return str(self.source_mode_toggle.value)

    # ------------------------------------------------------------------ browsing

    def _on_browse(self, _button=None) -> None:
        start = self._start_dir()
        try:
            selected = _native_file_dialog(start)
        except Exception:
            # No desktop session (remote kernel, container, headless): use the
            # inline browser instead.
            self._open_browser(start)
            return

        if selected:
            self.browser_panel.layout.display = "none"
            self.path_box.value = selected
            self._on_load()

    def _start_dir(self) -> Path:
        raw = self.path_box.value.strip().strip('"')
        if raw:
            candidate = Path(raw)
            candidate = candidate.parent if candidate.is_file() else candidate
            if candidate.is_dir():
                return candidate
        return Path.cwd()

    def _open_browser(self, start: Path) -> None:
        self._browse_dir = start
        self.browser_panel.layout.display = ""
        self._render_browser()

    def _render_browser(self) -> None:
        self.browser_location.value = (
            "<code style='font-size:12px'>{}</code>".format(
                html.escape(str(self._browse_dir))
            )
        )
        try:
            entries = sorted(
                self._browse_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except OSError as exc:
            self.browser_list.options = []
            self.browser_status.value = self._error(str(exc))
            return

        options: List[tuple] = []
        for entry in entries:
            try:
                if entry.is_dir():
                    options.append((f"\U0001f4c1 {entry.name}", str(entry)))
                elif entry.suffix.lower() in _EXCEL_SUFFIXES:
                    options.append((f"\U0001f4c4 {entry.name}", str(entry)))
            except OSError:
                continue

        self.browser_list.unobserve(self._on_browser_select, names="value")
        self.browser_list.options = options
        self.browser_list.index = None
        self.browser_list.observe(self._on_browser_select, names="value")
        self.browser_status.value = (
            ""
            if options
            else "<span style='color:#5f6b6d'>No sub-folders or Excel files here.</span>"
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
        self.path_box.value = selected
        self.browser_panel.layout.display = "none"
        self.browser_status.value = ""
        self._on_load()

    def _on_browser_close(self, _button=None) -> None:
        self.browser_panel.layout.display = "none"

    # -------------------------------------------------------------------- events

    def _on_load(self, _button=None) -> None:
        if self.source_mode == "sql":
            self._on_load_sql()
            return
        self._on_load_excel()

    def _on_source_mode_change(self, _change=None) -> None:
        self.df = None
        self.columns = []
        self._loaded_source = None
        self.load_status.value = ""
        self.sheet_dropdown.options = []
        self.sheet_dropdown.disabled = True
        self.sql_table_dropdown.options = []
        self.sql_table_dropdown.disabled = True
        self.browser_panel.layout.display = "none"
        self._sync_source_mode_ui()
        self._on_rule_change()
        if self.source_mode == "sql":
            self._on_refresh_sql_tables()

    def _sync_source_mode_ui(self) -> None:
        excel_mode = self.source_mode == "excel"
        self.excel_panel.layout.display = "" if excel_mode else "none"
        self.sql_panel.layout.display = "none" if excel_mode else ""
        if excel_mode:
            self.source_help.value = (
                "<div style='color:#5f6b6d;font-size:13px;margin:6px 0 8px 190px'>"
                "Load a workbook and choose a sheet."
                "</div>"
            )
        else:
            self.source_help.value = (
                "<div style='color:#5f6b6d;font-size:13px;margin:6px 0 8px 190px'>"
                "Refresh SQL Server tables, choose one table, then load it into the validation flow."
                "</div>"
            )

    def _on_refresh_sql_tables(self, _button=None) -> None:
        self.load_status.value = "<span style='color:#5f6b6d'>Reading SQL Server tables…</span>"
        try:
            tables = list_sql_tables(self.connection_panel.current_settings())
        except Exception as exc:
            self.sql_table_dropdown.options = []
            self.sql_table_dropdown.disabled = True
            self.load_status.value = self._error(str(exc))
            return

        self.sql_table_dropdown.options = tables
        self.sql_table_dropdown.disabled = not bool(tables)
        if tables:
            self.sql_table_dropdown.value = tables[0]
            self.load_status.value = self._ok(f"Found {len(tables)} SQL table(s).")
        else:
            self.load_status.value = self._error("No SQL tables or views were returned.")

    def _on_load_sql(self, _button=None) -> None:
        source = SourceSpec(
            mode="sql",
            table_name=str(self.sql_table_dropdown.value or "").strip(),
            connection_settings=self.connection_panel.current_settings(),
        )
        self.load_status.value = "<span style='color:#5f6b6d'>Loading SQL table…</span>"
        try:
            self.df = load_source_dataframe(source)
            self.columns = [str(column) for column in self.df.columns]
            self._loaded_source = source
        except Exception as exc:
            self.df = None
            self.columns = []
            self._loaded_source = None
            self.load_status.value = self._error(str(exc))
            return

        self.load_status.value = (
            "<span style='color:#00674f'>Loaded <b>{rows}</b> rows &times; <b>{cols}</b> columns "
            "from <b>{source}</b>.</span>".format(
                rows=len(self.df),
                cols=len(self.columns),
                source=html.escape(describe_source(source)),
            )
        )
        self._on_rule_change()

    def _on_load_excel(self, _button=None) -> None:
        self.load_status.value = "<span style='color:#5f6b6d'>Loading…</span>"
        try:
            path = resolve_path(self.path_box.value)
            sheets = list_sheets(path)
        except Exception as exc:
            self.df = None
            self.columns = []
            self.sheet_dropdown.options = []
            self.sheet_dropdown.disabled = True
            self.load_status.value = self._error(str(exc))
            return

        self.sheet_dropdown.unobserve(self._on_sheet_change, names="value")
        self.sheet_dropdown.options = sheets
        self.sheet_dropdown.value = sheets[0]
        self.sheet_dropdown.disabled = False
        self.sheet_dropdown.observe(self._on_sheet_change, names="value")
        self._load_sheet()

    def _on_sheet_change(self, _change=None) -> None:
        self._load_sheet()

    def _load_sheet(self) -> None:
        try:
            path = resolve_path(self.path_box.value)
            self.df = load_dataframe(path, self.sheet_dropdown.value)
            self.columns = [str(c) for c in self.df.columns]
            self._loaded_source = SourceSpec(
                mode="excel",
                path=str(path),
                sheet_name=str(self.sheet_dropdown.value),
            )
        except Exception as exc:
            self.df = None
            self.columns = []
            self._loaded_source = None
            self.load_status.value = self._error(str(exc))
            return

        self.load_status.value = (
            "<span style='color:#00674f'>Loaded <b>{rows}</b> rows &times; <b>{cols}</b> columns "
            "from sheet <b>{sheet}</b>.</span>".format(
                rows=len(self.df),
                cols=len(self.columns),
                sheet=html.escape(str(self.sheet_dropdown.value)),
            )
        )
        self._on_rule_change()

    def _on_rule_change(self, _change=None) -> None:
        definition = get_rule(self.rule_dropdown.value)
        self.rule_help.value = (
            f"<div style='color:#5f6b6d;font-size:13px;margin:2px 0 8px 190px'>"
            f"{html.escape(definition.description)}</div>"
        )
        self._render_column_widgets(definition)
        self._render_param_widgets(definition)
        self.add_status.value = ""

    def _render_column_widgets(self, definition: RuleDefinition) -> None:
        self._column_widgets = []
        options = self.columns

        if definition.arity == 0:
            self.column_area.children = [
                widgets.HTML(
                    "<div style='color:#5f6b6d;font-size:13px;margin-left:190px'>"
                    "This check runs across the whole sheet — no column needed.</div>"
                )
            ]
            return

        if definition.arity == "many":
            search = widgets.Text(
                description="Search columns", placeholder="type to filter…", style=_style(), layout=_WIDE
            )
            picker = widgets.SelectMultiple(
                description=definition.column_labels[0] if definition.column_labels else "Columns",
                options=options,
                rows=min(10, max(4, len(options))),
                style=_style(),
                layout=_WIDE,
            )

            def _filter(change, picker=picker):
                needle = str(change["new"]).strip().lower()
                picker.options = [c for c in self.columns if needle in c.lower()] if needle else self.columns

            search.observe(_filter, names="value")
            self._column_widgets = [picker]
            self.column_area.children = [search, picker]
            return

        count = int(definition.arity)
        rows: List[widgets.Widget] = []
        for index in range(count):
            label = (
                definition.column_labels[index]
                if index < len(definition.column_labels)
                else f"Column {index + 1}"
            )
            box = widgets.Combobox(
                description=label,
                options=options,
                ensure_option=False,
                style=_style(),
                layout=_WIDE,
                disabled=not bool(options),
            )
            self._column_widgets.append(box)
            rows.append(box)
        self.column_area.children = rows

    def _render_param_widgets(self, definition: RuleDefinition) -> None:
        self._param_widgets = {}
        rows: List[widgets.Widget] = []

        for param in definition.params:
            if param.kind == "bool":
                widget: widgets.Widget = widgets.Checkbox(
                    description=param.label, value=bool(param.default), style=_style(), indent=True
                )
            elif param.kind == "choice":
                widget = widgets.Dropdown(
                    description=param.label,
                    options=param.choices or [],
                    value=param.default,
                    style=_style(),
                    layout=_WIDE,
                )
            else:
                # Text is used for numbers too, so "leave empty" means "no bound".
                widget = widgets.Text(
                    description=param.label,
                    value="" if param.default is None else str(param.default),
                    placeholder=param.placeholder or ("leave empty to skip" if param.kind == "number" else ""),
                    style=_style(),
                    layout=_WIDE,
                )

            self._param_widgets[param.name] = widget
            rows.append(widget)
            if param.help:
                rows.append(
                    widgets.HTML(
                        f"<div style='color:#5f6b6d;font-size:12px;margin:-6px 0 6px 190px'>"
                        f"{html.escape(param.help)}</div>"
                    )
                )

        self.param_area.children = rows

    def _collect_columns(self, definition: RuleDefinition) -> List[str]:
        if definition.arity == 0:
            return []
        if definition.arity == "many":
            return list(self._column_widgets[0].value)
        return [str(w.value).strip() for w in self._column_widgets]

    def _collect_params(self, definition: RuleDefinition) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for param in definition.params:
            widget = self._param_widgets.get(param.name)
            if widget is None:
                continue
            value = widget.value
            if param.kind == "bool":
                params[param.name] = bool(value)
            elif param.kind == "number":
                text = str(value).strip()
                if text == "":
                    continue
                try:
                    number = float(text)
                except ValueError as exc:
                    raise ValueError(f"'{param.label}' must be a number (got '{text}').") from exc
                params[param.name] = int(number) if number.is_integer() else number
            else:
                if str(value).strip() != "":
                    params[param.name] = value
        return params

    def _add_specs(self, specs: List[RuleSpec]) -> int:
        """Add only validations not already selected in this run."""
        existing = {
            (spec.rule_id, tuple(spec.columns), tuple(sorted(spec.params.items())))
            for spec in self.specs
        }
        added = 0
        for spec in specs:
            key = (spec.rule_id, tuple(spec.columns), tuple(sorted(spec.params.items())))
            if key not in existing:
                self.specs.append(spec)
                existing.add(key)
                added += 1
        return added

    def _on_add(self, _button=None) -> None:
        definition = get_rule(self.rule_dropdown.value)
        try:
            columns = self._collect_columns(definition)
            params = self._collect_params(definition)
        except Exception as exc:
            self.add_status.value = self._error(str(exc))
            return

        if definition.arity not in (0, "many") and any(c == "" for c in columns):
            self.add_status.value = self._error("Please choose a column for every field.")
            return
        if definition.arity == 1 and self.columns and columns[0] not in self.columns:
            self.add_status.value = self._error(f"'{columns[0]}' is not a column in this sheet.")
            return

        unknown = [c for c in columns if self.columns and c not in self.columns]
        if unknown:
            self.add_status.value = self._error(f"Unknown column(s): {', '.join(unknown)}")
            return

        added = self._add_specs([
            RuleSpec(rule_id=definition.rule_id, columns=columns, params=params, label=definition.label)
        ])
        if added:
            self.add_status.value = (
                f"<span style='color:#00674f;margin-left:8px'>Added &ldquo;"
                f"{html.escape(definition.label)}&rdquo;.</span>"
            )
        else:
            self.add_status.value = (
                "<span style='color:#5f6b6d;margin-left:8px'>This check is already selected.</span>"
            )
        self._refresh_selected()

    def _on_preset_change(self, _change=None) -> None:
        preset = PRESETS[self.preset_dropdown.value]
        self.preset_help.value = (
            f"<div style='color:#5f6b6d;font-size:13px;margin:2px 0 8px 190px'>"
            f"{html.escape(preset.description)}</div>"
        )

    def _on_preset(self, _button=None) -> None:
        if not self.columns:
            self.preset_help.value = self._error("Load a workbook first.")
            return

        specs, notes = build_preset_specs(self.preset_dropdown.value, self.columns)
        added = self._add_specs(specs)
        if added:
            message = f"<span style='color:#00674f'>Added {added} check(s) from the preset.</span>"
        else:
            message = "<span style='color:#5f6b6d'>All checks from this preset are already selected.</span>"
        if notes:
            skipped = "".join(f"<li>{html.escape(n)}</li>" for n in notes)
            message += f"<ul style='color:#8c4223;font-size:12px;margin:4px 0'>{skipped}</ul>"
        self.preset_help.value = f"<div style='margin-left:190px'>{message}</div>"
        self._refresh_selected()

    def _on_clear(self, _button=None) -> None:
        self.specs = []
        self._refresh_selected()

    def _refresh_selected(self) -> None:
        if not self.specs:
            self.selected_area.children = [
                widgets.HTML(
                    "<div style='color:#5f6b6d;font-size:13px'>No checks selected yet — "
                    "add a preset or build checks one by one.</div>"
                )
            ]
            return

        rows: List[widgets.Widget] = []
        for position, spec in enumerate(self.specs):
            columns = ", ".join(spec.columns) if spec.columns else "whole sheet"
            params = ", ".join(f"{k}={v}" for k, v in spec.params.items())
            text = f"<b>{html.escape(spec.label or spec.rule_id)}</b> &mdash; {html.escape(columns)}"
            if params:
                text += f" <span style='color:#5f6b6d'>({html.escape(params)})</span>"

            remove = widgets.Button(icon="times", tooltip="Remove", layout=widgets.Layout(width="40px"))

            def _remove(_b, position=position):
                del self.specs[position]
                self._refresh_selected()

            remove.on_click(_remove)
            rows.append(
                widgets.HBox(
                    [remove, widgets.HTML(f"<div style='padding-top:6px'>{text}</div>")]
                )
            )
        self.selected_area.children = rows

    def _on_run(self, _button=None) -> None:
        if self.df is None:
            self.run_output.children = [widgets.HTML(self._error("Load a workbook before running checks."))]
            return
        if not self.specs:
            self.run_output.children = [widgets.HTML(self._error("Add at least one validation."))]
            return

        self.run_output.children = [
            widgets.HTML(f"<span style='color:#5f6b6d'>Running {len(self.specs)} check(s)…</span>")
        ]
        try:
            self.report = self.build_quality_report()
            self.excel_path, self.html_path = self._write_reports()
        except Exception:
            self.run_output.children = [
                widgets.HTML(self._error("The run failed:")),
                widgets.HTML(f"<pre>{html.escape(traceback.format_exc())}</pre>"),
            ]
            return

        self.run_output.children = [
            widgets.HTML(self._run_summary_html()),
            widgets.HTML(self._details_html()),
        ]

    def _details_html(self) -> str:
        table = self.report.details_frame().to_html(index=False, escape=True, classes="dq-results")
        return (
            "<style>.dq-results{border-collapse:collapse;font-family:Segoe UI,sans-serif;font-size:13px;}"
            ".dq-results th,.dq-results td{border:1px solid #c9d1d3;padding:5px 8px;text-align:left;}"
            ".dq-results th{background:#e8f3f1;}</style>"
            + table
        )

    def _write_reports(self):
        output_dir = Path(str(self.output_dir_box.value).strip() or "reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        row_limit = max(1, int(self.row_limit_box.value or 5000))

        excel_path = write_excel_report(
            self.report, self.df, output_dir / f"Quality_Report_{stamp}.xlsx", row_limit=row_limit
        )
        html_path = write_html_report(
            self.report, self.df, output_dir / f"Quality_Report_{stamp}.html"
        )
        return excel_path, html_path

    def build_quality_report(self) -> QualityReport:
        if self.df is None:
            raise ValueError("Load a workbook before running checks.")
        if not self.specs:
            raise ValueError("Add at least one validation.")
        return run_checks(
            self.df,
            self.specs,
            source_path=describe_source(self._loaded_source)
            if self._loaded_source is not None
            else (str(resolve_path(self.path_box.value)) if self.source_mode == "excel" else "SQL Server table"),
            sheet_name=(
                str(self._loaded_source.sheet_name or self._loaded_source.table_name or "")
                if self._loaded_source is not None
                else str(self.sheet_dropdown.value or "")
            ),
        )

    def _run_summary_html(self) -> str:
        report = self.report
        excel = html.escape(str(self.excel_path))
        html_file = html.escape(str(self.html_path))
        return f"""
        <div style="font-family:Segoe UI,sans-serif">
          <h3 style="margin:6px 0">Run complete</h3>
          <p style="margin:2px 0">
            <b>{report.total_checks}</b> checks &middot;
            <span style="color:#00674f"><b>{report.passed_checks}</b> passed</span> &middot;
            <span style="color:#8c0b20"><b>{report.failed_checks}</b> failed</span> &middot;
            <span style="color:#8c4223"><b>{report.errored_checks}</b> errored</span> &middot;
            <b>{report.total_failed_rows}</b> flagged rows
          </p>
          <p style="margin:2px 0;font-size:13px">
            Excel: <a href="{excel}" target="_blank">{excel}</a><br>
            HTML: <a href="{html_file}" target="_blank">{html_file}</a>
          </p>
        </div>
        """

    @staticmethod
    def _error(message: str) -> str:
        return f"<span style='color:#8c0b20'>{html.escape(message)}</span>"

    @staticmethod
    def _ok(message: str) -> str:
        return f"<span style='color:#00674f'>{html.escape(message)}</span>"

    def _ipython_display_(self):
        display(self.widget)


def build_ui(default_output_dir: str = "../reports") -> DataQualityApp:
    """Create the notebook UI. Display the returned object in a cell."""
    return DataQualityApp(default_output_dir=default_output_dir)
