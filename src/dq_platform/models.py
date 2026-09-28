"""Core data structures shared by the rule engine, reports and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd


@dataclass
class RuleSpec:
    """A single configured check: which rule, on which column(s), with which parameters."""

    rule_id: str
    columns: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "columns": list(self.columns),
            "params": dict(self.params),
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RuleSpec":
        return cls(
            rule_id=payload["rule_id"],
            columns=list(payload.get("columns") or []),
            params=dict(payload.get("params") or {}),
            label=payload.get("label"),
        )


@dataclass
class RuleResult:
    """Outcome of running one :class:`RuleSpec` against a DataFrame."""

    rule_id: str
    label: str
    dimension: str
    columns: List[str]
    total_rows: int
    failed_count: int = 0
    failed_index: Sequence[Any] = field(default_factory=list)
    message: str = ""
    error: Optional[str] = None
    # Optional tabular payload (e.g. value-count profiles) surfaced in the report.
    detail_table: Optional[pd.DataFrame] = None
    # Optional derived column the rule computed (e.g. Duration_Days).
    derived: Optional[pd.Series] = None
    # Dataset-level failure that does not map to individual rows.
    rule_failed: bool = False

    @property
    def failed_pct(self) -> float:
        if not self.total_rows:
            return 0.0
        return round(self.failed_count / self.total_rows * 100, 2)

    @property
    def passed(self) -> bool:
        return self.error is None and self.failed_count == 0 and not self.rule_failed

    @property
    def status(self) -> str:
        if self.error:
            return "ERROR"
        return "PASS" if (self.failed_count == 0 and not self.rule_failed) else "FAIL"

    @property
    def column_label(self) -> str:
        return ", ".join(self.columns) if self.columns else "(dataset)"

    def failed_rows(self, df: pd.DataFrame, limit: Optional[int] = None) -> pd.DataFrame:
        """Return the offending rows from ``df``, optionally capped at ``limit``."""
        if self.error or not len(self.failed_index):
            return df.head(0)
        index = pd.Index(self.failed_index)
        index = index[index.isin(df.index)]
        if limit is not None:
            index = index[:limit]
        return df.loc[index]

    def to_row(self) -> Dict[str, Any]:
        return {
            "Rule ID": self.rule_id,
            "Check": self.label,
            "Dimension": self.dimension,
            "Column(s)": self.column_label,
            "Status": self.status,
            "Rows Checked": self.total_rows,
            "Failed Rows": self.failed_count,
            "Failed %": self.failed_pct,
            "Details": self.error or self.message,
        }


@dataclass
class QualityReport:
    """Full result set for one run, plus the metadata the report templates need."""

    source_path: str
    sheet_name: str
    row_count: int
    column_count: int
    results: List[RuleResult] = field(default_factory=list)
    missing_profile: Optional[pd.DataFrame] = None
    dtypes_profile: Optional[pd.DataFrame] = None
    notes: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def total_checks(self) -> int:
        return len(self.results)

    @property
    def passed_checks(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed_checks(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def errored_checks(self) -> int:
        return sum(1 for r in self.results if r.status == "ERROR")

    @property
    def total_failed_rows(self) -> int:
        return sum(r.failed_count for r in self.results)

    @property
    def dq_score_pct(self) -> float:
        """Share of checks that passed, as a percentage (0 when no checks ran)."""
        if not self.total_checks:
            return 0.0
        return round(self.passed_checks / self.total_checks * 100, 2)

    def summary_frame(self) -> pd.DataFrame:
        rows = [
            ("Source file", self.source_path),
            ("Sheet", self.sheet_name),
            ("Generated at", self.generated_at.strftime("%Y-%m-%d %H:%M:%S")),
            ("Rows", self.row_count),
            ("Columns", self.column_count),
            ("Checks run", self.total_checks),
            ("Checks passed", self.passed_checks),
            ("Checks failed", self.failed_checks),
            ("Checks errored", self.errored_checks),
            ("Total flagged rows", self.total_failed_rows),
        ]
        return pd.DataFrame(rows, columns=["Metric", "Value"])

    def details_frame(self) -> pd.DataFrame:
        if not self.results:
            return pd.DataFrame(columns=list(RuleResult("", "", "", [], 0).to_row().keys()))
        return pd.DataFrame([r.to_row() for r in self.results])

    def specs_as_dicts(self) -> List[Dict[str, Any]]:
        """Round-trippable configuration for saving a run definition."""
        return [
            {"rule_id": r.rule_id, "columns": r.columns, "label": r.label}
            for r in self.results
        ]
