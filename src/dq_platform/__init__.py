"""Excel data quality reporting platform."""

from dq_platform.comparison import RevenueComparisonReport, build_revenue_comparison_report
from dq_platform.models import QualityReport, RuleResult, RuleSpec
from dq_platform.engine import run_checks
from dq_platform.io_utils import list_sheets, load_dataframe, read_header_columns
from dq_platform.registry import RULE_REGISTRY, get_rule
from dq_platform.presets import PRESETS, build_preset_specs
from dq_platform.report.excel import write_excel_report
from dq_platform.report.html import write_html_report
from dq_platform.report.comparison import (
    write_revenue_comparison_excel,
    write_revenue_comparison_html,
)

__all__ = [
    "QualityReport",
    "RevenueComparisonReport",
    "RuleResult",
    "RuleSpec",
    "build_revenue_comparison_report",
    "run_checks",
    "list_sheets",
    "load_dataframe",
    "read_header_columns",
    "RULE_REGISTRY",
    "get_rule",
    "PRESETS",
    "build_preset_specs",
    "write_excel_report",
    "write_html_report",
    "write_revenue_comparison_excel",
    "write_revenue_comparison_html",
    "build_hybrid_ui",
]

__version__ = "0.1.0"


def build_ui(*args, **kwargs):
    """Lazy wrapper so importing the package does not require ipywidgets."""
    from dq_platform.ui.widgets import build_ui as _build_ui

    return _build_ui(*args, **kwargs)


def build_hybrid_ui(*args, **kwargs):
    """Lazy wrapper for the hybrid notebook UI."""
    from dq_platform.ui.hybrid_widgets import build_hybrid_ui as _build_hybrid_ui

    return _build_hybrid_ui(*args, **kwargs)


def build_revenue_validation_ui(*args, **kwargs):
    """Lazy wrapper for the two-workbook revenue validation notebook UI."""
    from dq_platform.ui.revenue_comparison_widgets import (
        build_revenue_validation_ui as _build_revenue_validation_ui,
    )

    return _build_revenue_validation_ui(*args, **kwargs)
