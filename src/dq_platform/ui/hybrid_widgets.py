"""ipywidgets host app that toggles between the notebook flows."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import ipywidgets as widgets
from IPython.display import display

from dq_platform.comparison import RevenueComparisonReport
from dq_platform.models import QualityReport
from dq_platform.report.hybrid import write_hybrid_combined_excel, write_hybrid_combined_html
from dq_platform.ui.revenue_comparison_widgets import (
    RevenueValidationApp,
    build_revenue_validation_ui,
)
from dq_platform.ui.widgets import DataQualityApp, build_ui

_FLOW_DATA_QUALITY = "Data Quality"
_FLOW_REVENUE_VALIDATION = "Revenue Validation"
_FLOW_DESCRIPTIONS = {
    _FLOW_DATA_QUALITY: (
        "Load one workbook and configure checks, then click Next to continue to "
        "Revenue Validation."
    ),
    _FLOW_REVENUE_VALIDATION: (
        "Compare old vs new sources and run the final combined report for both "
        "Data Quality and Revenue Validation."
    ),
}


def _style() -> dict[str, str]:
    return {"description_width": "160px"}


class HybridValidationApp:
    """Notebook host that switches between the two validation flows."""

    def __init__(self, default_output_dir: str = "../reports"):
        self.default_output_dir = default_output_dir
        self._data_quality_app: Optional[DataQualityApp] = None
        self._revenue_validation_app: Optional[RevenueValidationApp] = None
        self._latest_quality_report: Optional[QualityReport] = None
        self._latest_revenue_report: Optional[RevenueComparisonReport] = None
        self._latest_quality_error: Optional[str] = None
        self._combined_excel_path: Optional[Path] = None
        self._combined_html_path: Optional[Path] = None
        self._build()

    def _build(self) -> None:
        self.flow_toggle = widgets.ToggleButtons(
            description="Open flow",
            options=[_FLOW_DATA_QUALITY, _FLOW_REVENUE_VALIDATION],
            value=_FLOW_DATA_QUALITY,
            tooltips=[
                "Run the single-workbook data quality flow",
                "Run the old-vs-new revenue validation flow",
            ],
            style=_style(),
            layout=widgets.Layout(width="520px"),
        )
        self.flow_help = widgets.HTML()
        self.data_quality_panel = widgets.VBox(layout=widgets.Layout(display="none"))
        self.revenue_validation_panel = widgets.VBox(layout=widgets.Layout(display="none"))
        self.next_button = widgets.Button(
            description="Next: Revenue Validation",
            icon="arrow-right",
            button_style="primary",
            layout=widgets.Layout(display="none", width="240px"),
        )
        self.final_run_button = widgets.Button(
            description="Run both and generate combined report",
            icon="play",
            button_style="danger",
            layout=widgets.Layout(display="none", width="360px"),
        )
        self.combined_run_status = widgets.HTML()
        self.combined_results = widgets.VBox()
        self.flow_toggle.observe(self._on_flow_change, names="value")
        self.next_button.on_click(self._on_next_to_revenue)
        self.final_run_button.on_click(self._on_run_combined)

        self.widget = widgets.VBox(
            [
                widgets.HTML(
                    "<h2 style='margin:4px 0 10px;font-family:Segoe UI,sans-serif'>"
                    "Hybrid Validation App</h2>"
                    "<div style='color:#425563;font-size:13px;margin-bottom:6px'>"
                    "Use one notebook/runtime and switch between the Data Quality and "
                    "Revenue Validation flows with the toggle below."
                    "</div>"
                ),
                self.flow_toggle,
                self.flow_help,
                self.data_quality_panel,
                self.next_button,
                self.revenue_validation_panel,
                self.final_run_button,
                self.combined_run_status,
                self.combined_results,
            ]
        )

        self._set_active_flow(self.flow_toggle.value)

    @property
    def selected_flow(self) -> str:
        return str(self.flow_toggle.value)

    @property
    def current_app(self) -> DataQualityApp | RevenueValidationApp:
        return self._ensure_app(self.selected_flow)

    @property
    def data_quality_app(self) -> DataQualityApp:
        return self._ensure_app(_FLOW_DATA_QUALITY)

    @property
    def revenue_validation_app(self) -> RevenueValidationApp:
        return self._ensure_app(_FLOW_REVENUE_VALIDATION)

    @property
    def report(self) -> Any:
        return self._latest_revenue_report or getattr(self.current_app, "report", None)

    @property
    def excel_path(self) -> Any:
        return self._combined_excel_path or getattr(self.current_app, "excel_path", None)

    @property
    def html_path(self) -> Any:
        return self._combined_html_path or getattr(self.current_app, "html_path", None)

    def _ensure_app(self, flow: str) -> DataQualityApp | RevenueValidationApp:
        if flow == _FLOW_DATA_QUALITY:
            if self._data_quality_app is None:
                self._data_quality_app = build_ui(default_output_dir=self.default_output_dir)
                self._data_quality_app.run_button.layout.display = "none"
                self.data_quality_panel.children = [self._data_quality_app.widget]
            return self._data_quality_app

        if self._revenue_validation_app is None:
            self._revenue_validation_app = build_revenue_validation_ui(
                default_output_dir=self.default_output_dir
            )
            self._revenue_validation_app.run_button.layout.display = "none"
            self.revenue_validation_panel.children = [self._revenue_validation_app.widget]
        return self._revenue_validation_app

    def _set_active_flow(self, flow: str) -> None:
        self._ensure_app(flow)
        self.flow_help.value = (
            "<div style='color:#5f6b6d;font-size:13px;margin:6px 0 10px 160px'>"
            f"{html.escape(_FLOW_DESCRIPTIONS[flow])}</div>"
        )
        self.data_quality_panel.layout.display = "" if flow == _FLOW_DATA_QUALITY else "none"
        self.revenue_validation_panel.layout.display = (
            "" if flow == _FLOW_REVENUE_VALIDATION else "none"
        )
        self.next_button.layout.display = "" if flow == _FLOW_DATA_QUALITY else "none"
        self.final_run_button.layout.display = "" if flow == _FLOW_REVENUE_VALIDATION else "none"

    def _on_flow_change(self, change=None) -> None:
        new_flow = self.selected_flow if change is None else str(change["new"])
        self._set_active_flow(new_flow)

    @staticmethod
    def _error(message: str) -> str:
        return f"<span style='color:#b00020'><b>Error:</b> {html.escape(message)}</span>"

    @staticmethod
    def _ok(message: str) -> str:
        return f"<span style='color:#00674f'>{html.escape(message)}</span>"

    @staticmethod
    def _warn(message: str) -> str:
        return f"<span style='color:#8c4223'><b>Warning:</b> {html.escape(message)}</span>"

    def _on_next_to_revenue(self, _button=None) -> None:
        self.flow_toggle.value = _FLOW_REVENUE_VALIDATION

    def _on_run_combined(self, _button=None) -> None:
        self.combined_results.children = ()
        self.combined_run_status.value = "<span style='color:#5f6b6d'>Running combined validation…</span>"

        quality_report: Optional[QualityReport] = None
        quality_error: Optional[str] = None
        revenue_report: Optional[RevenueComparisonReport] = None

        quality_app = self.data_quality_app
        revenue_app = self.revenue_validation_app

        try:
            quality_report = quality_app.build_quality_report()
            quality_app.report = quality_report
        except Exception as exc:
            quality_error = str(exc)

        try:
            revenue_report = revenue_app.build_revenue_report()
            revenue_app.report = revenue_report
        except Exception as exc:
            self.combined_run_status.value = self._error(str(exc))
            return

        output_dir = Path(str(revenue_app.output_dir_box.value).strip() or "reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = output_dir / f"Hybrid_Validation_Report_{timestamp}.xlsx"
        html_path = output_dir / f"Hybrid_Validation_Report_{timestamp}.html"

        self._combined_excel_path = write_hybrid_combined_excel(
            revenue_report,
            excel_path,
            quality_report=quality_report,
            quality_error=quality_error,
        )
        self._combined_html_path = write_hybrid_combined_html(
            revenue_report,
            html_path,
            quality_report=quality_report,
            quality_error=quality_error,
            quality_df=quality_app.df,
        )
        self._latest_quality_report = quality_report
        self._latest_revenue_report = revenue_report
        self._latest_quality_error = quality_error

        revenue_errors: list[str] = []
        if revenue_report.zdel_threshold_exceeded:
            revenue_errors.append(
                f'{revenue_report.zdel_threshold_message} (difference: {round(revenue_report.zdel_delta, 2)})'
            )
        if revenue_report.renewal_threshold_exceeded:
            revenue_errors.append(revenue_report.renewal_threshold_message)

        quality_status = (
            f"Data Quality incomplete: {quality_error}" if quality_error else "Data Quality completed."
        )
        links = widgets.HTML(
            "<div style='margin:8px 0'><b>Combined run complete.</b><br>"
            f"Excel: <code>{html.escape(str(self._combined_excel_path))}</code><br>"
            f"HTML: <code>{html.escape(str(self._combined_html_path))}</code><br>"
            f"{html.escape(quality_status)}</div>"
        )
        revenue_summary = revenue_report.summary_frame().head(14)
        summary_table = widgets.HTML(revenue_summary.to_html(index=False, escape=True, border=0))
        self.combined_results.children = [links, summary_table]

        if revenue_errors:
            status_message = " | ".join(revenue_errors)
            if quality_error:
                status_message = f"{status_message} | Data Quality incomplete: {quality_error}"
            self.combined_run_status.value = self._error(status_message)
            return
        if quality_error:
            self.combined_run_status.value = self._warn(
                f"Revenue Validation completed. Data Quality incomplete: {quality_error}"
            )
            return
        self.combined_run_status.value = self._ok("Combined validation complete.")

    def _ipython_display_(self):
        display(self.widget)


def build_hybrid_ui(default_output_dir: str = "../reports") -> HybridValidationApp:
    """Create the toggle-based notebook host UI."""
    return HybridValidationApp(default_output_dir=default_output_dir)
