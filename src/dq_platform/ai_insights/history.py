"""Metric snapshot model and a lightweight local JSON history log.

This module adds the historical persistence layer that did not previously
exist anywhere in the codebase. Every time the combined hybrid report is
generated, a :class:`MetricSnapshot` of the headline metrics is appended to a
JSON file next to the report output. Later runs read this file back to
compute current-vs-previous deltas and a rolling 3-month trend.

Nothing here touches or depends on the existing validation/rule engine
logic -- it only reads already-computed values off ``QualityReport``,
``RevenueComparisonReport`` and ``DashboardKpis``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from dq_platform.comparison import RevenueComparisonReport
from dq_platform.models import QualityReport
from dq_platform.report.scoring import DashboardKpis


@dataclass
class MetricSnapshot:
    """One point-in-time record of the headline metrics for trend analysis."""

    timestamp: str  # ISO-8601, e.g. "2026-01-15T10:30:00"
    dq_score_pct: float
    dq_checks_passed: int
    dq_checks_total: int
    revenue_old_sum: float
    revenue_new_sum: float
    revenue_delta_pct: Optional[float]
    tier2_missing_pct: float
    renewal_old_missing_pct: float
    renewal_new_missing_pct: float
    business_case_violations: Optional[int]
    critical_count: int

    @property
    def month_key(self) -> str:
        """``YYYY-MM`` bucket used for "previous N months" filtering."""
        return self.timestamp[:7]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MetricSnapshot":
        return cls(**{field: payload.get(field) for field in cls.__dataclass_fields__})


def collect_metric_snapshot(
    quality_report: Optional[QualityReport],
    revenue_report: RevenueComparisonReport,
    kpis: DashboardKpis,
    quality_df: Optional[pd.DataFrame],
    *,
    when: Optional[datetime] = None,
) -> MetricSnapshot:
    """Build a :class:`MetricSnapshot` purely from already-computed values.

    No new business logic or numbers are invented here -- every field is
    read directly off the existing report/KPI objects.
    """
    from dq_platform.report.dashboard import _multiyear_flag_violation_count

    # Microsecond precision avoids two runs that happen to land in the same
    # second colliding, which would otherwise make ``HistoryStore.recent``'s
    # strict "before" comparison silently drop a genuinely-prior snapshot.
    timestamp = (when or datetime.now()).isoformat()
    business_case_violations = _multiyear_flag_violation_count(quality_df)

    return MetricSnapshot(
        timestamp=timestamp,
        dq_score_pct=kpis.dq_score_pct,
        dq_checks_passed=kpis.dq_checks_passed,
        dq_checks_total=kpis.dq_checks_total,
        revenue_old_sum=revenue_report.zdel_old_sum,
        revenue_new_sum=revenue_report.zdel_new_sum,
        revenue_delta_pct=revenue_report.zdel_delta_pct,
        tier2_missing_pct=revenue_report.tier2_missing_pct,
        renewal_old_missing_pct=revenue_report.renewal_old_missing_pct,
        renewal_new_missing_pct=revenue_report.renewal_new_missing_pct,
        business_case_violations=business_case_violations,
        critical_count=kpis.critical_count,
    )


class HistoryStore:
    """Reads/writes a JSON list of :class:`MetricSnapshot` at a fixed path."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[MetricSnapshot]:
        """Load all stored snapshots, oldest first. Never raises."""
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            # Corrupt/unreadable history should never break report generation.
            return []
        if not isinstance(raw, list):
            return []
        snapshots: list[MetricSnapshot] = []
        for entry in raw:
            try:
                snapshots.append(MetricSnapshot.from_dict(entry))
            except (TypeError, KeyError):
                continue
        snapshots.sort(key=lambda snap: snap.timestamp)
        return snapshots

    def append(self, snapshot: MetricSnapshot) -> None:
        """Append ``snapshot`` to the history file, creating it if needed."""
        snapshots = self.load()
        snapshots.append(snapshot)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [snap.to_dict() for snap in snapshots]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def recent(self, months: int = 3, *, before: Optional[str] = None) -> list[MetricSnapshot]:
        """Snapshots from the last ``months`` distinct calendar months.

        ``before`` (an ISO timestamp) excludes the current run's own
        timestamp/anything at or after it, so a freshly-collected snapshot
        never compares against itself.
        """
        snapshots = self.load()
        if before is not None:
            snapshots = [snap for snap in snapshots if snap.timestamp < before]
        if not snapshots:
            return []
        distinct_months = sorted({snap.month_key for snap in snapshots}, reverse=True)[:months]
        wanted = set(distinct_months)
        return [snap for snap in snapshots if snap.month_key in wanted]
