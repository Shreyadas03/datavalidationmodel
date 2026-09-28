"""Report writers (Excel workbook and standalone HTML dashboard)."""

from dq_platform.report.comparison import (
    write_revenue_comparison_excel,
    write_revenue_comparison_html,
)
from dq_platform.report.excel import write_excel_report
from dq_platform.report.html import write_html_report
from dq_platform.report.hybrid import write_hybrid_combined_excel, write_hybrid_combined_html

__all__ = [
    "write_excel_report",
    "write_html_report",
    "write_revenue_comparison_excel",
    "write_revenue_comparison_html",
    "write_hybrid_combined_excel",
    "write_hybrid_combined_html",
]
