"""Pure statistical logic for current-vs-previous and 3-month trend analysis.

No AI is used anywhere in this module -- every classification is derived
from simple, explainable arithmetic (signed differences, relative change,
mean/standard-deviation of the step sequence). The AI layer (see
``narrative.py``) only ever interprets the outputs of this module; it never
computes numbers itself.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from dq_platform.ai_insights.history import MetricSnapshot

# Metrics tracked for comparison/trend purposes, with a human label and
# whether an increase is considered "good" (used only to phrase
# observations neutrally; it never changes the underlying math).
TRACKED_METRICS: list[tuple[str, str, bool]] = [
    ("dq_score_pct", "DQ Score %", True),
    ("revenue_new_sum", "Revenue Total", True),
    ("tier2_missing_pct", "Tier 2 Reseller Missing %", False),
    ("renewal_new_missing_pct", "Renewal Missing %", False),
    ("business_case_violations", "Business Case (Multiyear Flag) Violations", False),
    ("critical_count", "Critical Issues", False),
]

# A relative change below this threshold is treated as noise / "stable".
STABLE_RELATIVE_THRESHOLD = 0.02  # 2%
# A relative change above this threshold is flagged "significant".
SIGNIFICANT_RELATIVE_THRESHOLD = 0.10  # 10%


@dataclass
class MetricChange:
    metric_key: str
    label: str
    previous_value: Optional[float]
    current_value: Optional[float]
    absolute_change: Optional[float]
    percent_change: Optional[float]
    significant: bool


@dataclass
class TrendResult:
    metric_key: str
    label: str
    direction: str  # increasing | decreasing | stable | fluctuating | unusual | insufficient_data
    values: list[float]
    follows_recent_trend: Optional[bool]  # None when not enough data to judge


def _relative_change(previous: float, current: float) -> Optional[float]:
    if previous == 0:
        return None if current == 0 else 1.0
    return (current - previous) / abs(previous)


def compare_to_previous(
    current: MetricSnapshot, previous: Optional[MetricSnapshot]
) -> list[MetricChange]:
    """Absolute + percent change per tracked metric vs. the prior snapshot."""
    changes: list[MetricChange] = []
    for key, label, _higher_is_better in TRACKED_METRICS:
        current_value = getattr(current, key)
        previous_value = getattr(previous, key) if previous is not None else None
        if current_value is None or previous_value is None:
            changes.append(
                MetricChange(key, label, previous_value, current_value, None, None, False)
            )
            continue
        absolute_change = current_value - previous_value
        rel = _relative_change(previous_value, current_value)
        percent_change = round(rel * 100, 2) if rel is not None else None
        significant = rel is not None and abs(rel) >= SIGNIFICANT_RELATIVE_THRESHOLD
        changes.append(
            MetricChange(
                key,
                label,
                previous_value,
                current_value,
                round(absolute_change, 2),
                percent_change,
                significant,
            )
        )
    return changes


def _classify_series(values: list[float]) -> str:
    """Classify a chronological series of >=2 numeric values."""
    if len(values) < 2:
        return "insufficient_data"

    steps = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    signs = [1 if s > 0 else (-1 if s < 0 else 0) for s in steps]
    magnitude_reference = max(abs(v) for v in values) or 1.0
    relative_steps = [abs(s) / magnitude_reference for s in steps]

    # All steps within the stable threshold -> stable, regardless of sign.
    if all(rel <= STABLE_RELATIVE_THRESHOLD for rel in relative_steps):
        return "stable"

    # Outlier detection: a step far larger than the typical step size.
    if len(steps) >= 2:
        mean_abs_step = statistics.mean(abs(s) for s in steps)
        stdev_abs_step = statistics.pstdev(abs(s) for s in steps) if len(steps) > 1 else 0.0
        last_step = abs(steps[-1])
        if stdev_abs_step > 0 and last_step > mean_abs_step + 2 * stdev_abs_step:
            return "unusual"
        if mean_abs_step > 0 and last_step > 3 * mean_abs_step:
            return "unusual"

    non_zero_signs = [s for s in signs if s != 0]
    if non_zero_signs and all(s == non_zero_signs[0] for s in non_zero_signs):
        return "increasing" if non_zero_signs[0] > 0 else "decreasing"

    return "fluctuating"


def classify_trend(
    history: list[MetricSnapshot], current: MetricSnapshot, metric_key: str, label: str
) -> TrendResult:
    """Classify the last-3-months trend for one metric and whether the
    current run's change follows or deviates from it.

    The historical (established) direction is derived purely from the
    history points. The transition from the last historical point into the
    current run is then separately checked for being an outlier relative to
    the historical step sizes -- a large, unexpected jump is reported as
    "unusual" (overriding the established direction), since that is the
    signal most worth surfacing.
    """
    ordered = sorted(history, key=lambda snap: snap.timestamp)
    values = [
        getattr(snap, metric_key)
        for snap in ordered
        if getattr(snap, metric_key) is not None
    ]
    current_value = getattr(current, metric_key)

    if not values:
        return TrendResult(metric_key, label, "insufficient_data", [], None)

    direction = _classify_series(values)

    follows_recent_trend: Optional[bool] = None
    if current_value is not None:
        last_historical = values[-1]
        current_step = current_value - last_historical
        current_step_sign = 1 if current_step > 0 else (-1 if current_step < 0 else 0)

        # Check whether the jump into the current run is an outlier vs. the
        # historical step distribution (only meaningful with >=2 history
        # steps, i.e. >=3 history points).
        if len(values) >= 3:
            hist_steps = [values[i + 1] - values[i] for i in range(len(values) - 1)]
            mean_abs_step = statistics.mean(abs(s) for s in hist_steps)
            stdev_abs_step = statistics.pstdev(abs(s) for s in hist_steps)
            is_outlier = (
                stdev_abs_step > 0 and abs(current_step) > mean_abs_step + 2 * stdev_abs_step
            ) or (mean_abs_step > 0 and abs(current_step) > 3 * mean_abs_step)
            if is_outlier:
                direction = "unusual"

        if direction == "unusual":
            follows_recent_trend = False
        elif direction in ("increasing", "decreasing"):
            expected_sign = 1 if direction == "increasing" else -1
            follows_recent_trend = current_step_sign == expected_sign
        elif direction == "stable":
            magnitude_reference = max(abs(v) for v in values + [current_value]) or 1.0
            rel = abs(current_value - last_historical) / magnitude_reference
            follows_recent_trend = rel <= STABLE_RELATIVE_THRESHOLD
        # For "fluctuating"/"unusual"/"insufficient_data" we don't assert a
        # follow/deviate judgement -- there's no single trend to compare to.

    return TrendResult(metric_key, label, direction, values, follows_recent_trend)


def build_trend_results(
    history: list[MetricSnapshot], current: MetricSnapshot
) -> list[TrendResult]:
    return [
        classify_trend(history, current, key, label)
        for key, label, _higher_is_better in TRACKED_METRICS
    ]
