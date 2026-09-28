"""AI narrative generation for the Data Quality Insights section.

Design goals (per product requirement):
 - AI is used *only* for interpretation/narrative wording -- every number it
   is given comes from :mod:`dq_platform.ai_insights.trend` /
   :mod:`dq_platform.ai_insights.history`. The prompt explicitly instructs
   the model to never invent figures or unverified root causes.
 - No hardcoded API keys. Configuration is entirely environment-variable
   driven so it stays out of source control.
 - No default public/open AI endpoint. Nothing is contacted unless the
   required configuration for the selected provider is explicitly supplied
   -- if it isn't, the deterministic fallback narrative is used instead.
 - No new third-party dependency: the HTTP call is made with the stdlib
   ``urllib.request``.
 - Never blocks or breaks report generation: any missing config, network
   error, timeout, or malformed response falls back to a deterministic,
   template-built narrative derived from the same calculated values.

Supported providers (``DQ_AI_PROVIDER``):
 - ``azure_openai`` (default) -- Azure OpenAI Service, the enterprise-approved
   option. Requires ``DQ_AI_API_KEY``, ``DQ_AI_AZURE_ENDPOINT`` and
   ``DQ_AI_AZURE_DEPLOYMENT``.
 - ``openai_compatible`` -- any other internally-approved OpenAI-compatible
   Chat Completions gateway (e.g. a company-hosted proxy). Requires
   ``DQ_AI_API_KEY`` and ``DQ_AI_BASE_URL`` (no default -- must be set
   explicitly, so nothing ever silently calls a public endpoint).

Environment variables (all optional -- unset means "use fallback"):
 - ``DQ_AI_PROVIDER``           ``azure_openai`` (default) or
   ``openai_compatible``.
 - ``DQ_AI_API_KEY``            ****** for the selected provider.
 - ``DQ_AI_AZURE_ENDPOINT``     Azure OpenAI resource endpoint, e.g.
   ``https://<resource>.openai.azure.com`` (azure_openai only).
 - ``DQ_AI_AZURE_DEPLOYMENT``   Azure OpenAI deployment name (azure_openai
   only).
 - ``DQ_AI_AZURE_API_VERSION``  Azure API version, default ``2024-06-01``
   (azure_openai only).
 - ``DQ_AI_BASE_URL``           Base URL of the Chat Completions endpoint
   (openai_compatible only -- no default).
 - ``DQ_AI_MODEL``              Model name (openai_compatible only), default
   ``gpt-4o-mini``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from dq_platform.ai_insights.history import MetricSnapshot
from dq_platform.ai_insights.trend import MetricChange, TrendResult

_DEFAULT_PROVIDER = "azure_openai"
_DEFAULT_AZURE_API_VERSION = "2024-06-01"
_DEFAULT_MODEL = "gpt-4o-mini"
_REQUEST_TIMEOUT_SECONDS = 15
_AUTH_PREFIX = "Bearer"


@dataclass
class AIConfig:
    provider: str
    api_key: Optional[str]
    # Azure OpenAI fields
    azure_endpoint: Optional[str] = None
    azure_deployment: Optional[str] = None
    azure_api_version: str = _DEFAULT_AZURE_API_VERSION
    # openai_compatible fields
    base_url: Optional[str] = None
    model: str = _DEFAULT_MODEL

    @property
    def enabled(self) -> bool:
        if not self.api_key:
            return False
        if self.provider == "azure_openai":
            return bool(self.azure_endpoint and self.azure_deployment)
        if self.provider == "openai_compatible":
            return bool(self.base_url)
        return False

    @classmethod
    def from_env(cls) -> "AIConfig":
        return cls(
            provider=os.environ.get("DQ_AI_PROVIDER") or _DEFAULT_PROVIDER,
            api_key=os.environ.get("DQ_AI_API_KEY") or None,
            azure_endpoint=os.environ.get("DQ_AI_AZURE_ENDPOINT") or None,
            azure_deployment=os.environ.get("DQ_AI_AZURE_DEPLOYMENT") or None,
            azure_api_version=os.environ.get("DQ_AI_AZURE_API_VERSION") or _DEFAULT_AZURE_API_VERSION,
            base_url=os.environ.get("DQ_AI_BASE_URL") or None,
            model=os.environ.get("DQ_AI_MODEL") or _DEFAULT_MODEL,
        )


@dataclass
class InsightsNarrative:
    executive_summary: str
    current_scenario: str
    change_from_previous: str
    three_month_trend: str
    key_observations: list[str]
    areas_to_investigate: list[str]
    source: str  # "ai" or "fallback"


def _fmt(value: Optional[float], suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    return f"{value:,}{suffix}"


def _format_metric_change_line(change: MetricChange) -> str:
    if change.current_value is None:
        return f"- {change.label}: no current value available."
    if change.previous_value is None:
        return f"- {change.label}: current {_fmt(change.current_value)} (no prior refresh to compare)."
    arrow = "up" if (change.absolute_change or 0) > 0 else (
        "down" if (change.absolute_change or 0) < 0 else "unchanged"
    )
    flag = " [SIGNIFICANT]" if change.significant else ""
    return (
        f"- {change.label}: {_fmt(change.previous_value)} -> {_fmt(change.current_value)} "
        f"({arrow}, {_fmt(change.absolute_change)} abs / {_fmt(change.percent_change, '%')}){flag}"
    )


def _format_trend_line(trend: TrendResult) -> str:
    if trend.direction == "insufficient_data":
        return f"- {trend.label}: not enough history yet to establish a trend."
    values_str = ", ".join(_fmt(v) for v in trend.values)
    follow_str = (
        "current change follows this trend"
        if trend.follows_recent_trend is True
        else "current change deviates from this trend"
        if trend.follows_recent_trend is False
        else "not enough data to judge whether the current change follows this trend"
    )
    return f"- {trend.label}: {trend.direction} (recent values: {values_str}); {follow_str}."


def build_prompt(
    changes: list[MetricChange], trends: list[TrendResult], current: MetricSnapshot
) -> str:
    """Assemble a strict, numbers-only prompt. The model must not invent data."""
    change_lines = "\n".join(_format_metric_change_line(c) for c in changes)
    trend_lines = "\n".join(_format_trend_line(t) for t in trends)
    return (
        "You are a data quality analyst writing a concise, business-friendly "
        "narrative for a validation dashboard. Use ONLY the numbers provided "
        "below. Do not invent any figures, root causes, or facts that are not "
        "explicitly stated. If information is insufficient, say so plainly.\n\n"
        f"Current run timestamp: {current.timestamp}\n\n"
        "Change from previous refresh:\n"
        f"{change_lines}\n\n"
        "3-month trend per metric:\n"
        f"{trend_lines}\n\n"
        "Respond as compact JSON with exactly these keys: "
        "executive_summary (1-2 sentences), current_scenario (1-2 sentences), "
        "change_from_previous (2-3 sentences), three_month_trend (2-3 sentences), "
        "key_observations (array of short strings), "
        "areas_to_investigate (array of short strings). "
        "No markdown, no extra keys, no commentary outside the JSON object."
    )


def _build_request(config: AIConfig, prompt: str) -> "urllib.request.Request":
    """Build the outbound HTTP request for the configured provider."""
    body = json.dumps(
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write factual, numbers-grounded data quality "
                        "narratives. You never invent data."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    )

    if config.provider == "azure_openai":
        url = (
            f"{config.azure_endpoint.rstrip('/')}/openai/deployments/"
            f"{config.azure_deployment}/chat/completions"
            f"?api-version={config.azure_api_version}"
        )
        headers = {
            "Content-Type": "application/json",
            "api-key": config.api_key,
        }
    elif config.provider == "openai_compatible":
        payload = json.loads(body)
        payload["model"] = config.model
        body = json.dumps(payload)
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": _AUTH_PREFIX + " " + config.api_key,
        }
    else:
        raise ValueError(f"Unsupported DQ_AI_PROVIDER: {config.provider!r}")

    return urllib.request.Request(
        url, data=body.encode("utf-8"), method="POST", headers=headers
    )


def _call_chat_completions(config: AIConfig, prompt: str) -> Optional[dict]:
    """POST to the configured provider's Chat Completions endpoint (Azure
    OpenAI or another internally-approved OpenAI-compatible gateway).
    Returns the parsed JSON payload the model produced, or None on any
    failure -- callers always fall back to the deterministic narrative."""
    try:
        request = _build_request(config, prompt)
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        KeyError,
        IndexError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None


def _fallback_narrative(
    changes: list[MetricChange], trends: list[TrendResult], current: MetricSnapshot
) -> InsightsNarrative:
    """Deterministic, template-built narrative -- used whenever the AI call
    is unavailable, unconfigured, or fails. Built solely from calculated
    values, same as the AI path."""
    significant = [c for c in changes if c.significant]
    unusual = [t for t in trends if t.direction == "unusual"]
    # "unusual" trends already get their own dedicated bullet below; exclude
    # them here so a spike isn't reported twice under two different wordings.
    deviating = [
        t for t in trends if t.follows_recent_trend is False and t.direction != "unusual"
    ]

    executive_summary = (
        f"Current DQ Score is {_fmt(current.dq_score_pct, '%')} with "
        f"{current.critical_count} critical issue(s) flagged this refresh."
    )
    current_scenario = (
        f"{current.dq_checks_passed}/{current.dq_checks_total} data quality checks passed; "
        f"revenue total is {_fmt(current.revenue_new_sum)}; "
        f"Tier 2 reseller missing rate is {_fmt(current.tier2_missing_pct, '%')}; "
        f"renewal missing rate is {_fmt(current.renewal_new_missing_pct, '%')}."
    )
    if significant:
        change_from_previous = "Significant changes since the previous refresh: " + "; ".join(
            f"{c.label} moved {_fmt(c.percent_change, '%')}" for c in significant
        ) + "."
    else:
        change_from_previous = (
            "No metric changed by more than the significance threshold "
            "(10%) since the previous refresh."
        )
    if unusual:
        three_month_trend = "Unusual movement detected in: " + ", ".join(
            t.label for t in unusual
        ) + ". Other tracked metrics show typical increasing/decreasing/stable patterns."
    else:
        directional = [t for t in trends if t.direction in ("increasing", "decreasing")]
        insufficient = [t for t in trends if t.direction == "insufficient_data"]
        stable_or_fluctuating = [
            t for t in trends if t.direction in ("stable", "fluctuating")
        ]
        if directional:
            three_month_trend = "Over the recent months: " + "; ".join(
                f"{t.label} is {t.direction}" for t in directional
            ) + "."
        elif insufficient and not stable_or_fluctuating:
            three_month_trend = (
                "Not enough historical refreshes are logged yet (fewer than 2 prior "
                "months of data) to establish a 3-month trend for the tracked metrics."
            )
        else:
            three_month_trend = (
                "Tracked metrics are stable or fluctuating without a clear "
                "directional trend over the recent months."
            )

    key_observations = [
        f"{c.label}: {_fmt(c.previous_value)} -> {_fmt(c.current_value)} "
        f"({_fmt(c.percent_change, '%')})"
        for c in significant
    ] or ["No individually significant metric changes this refresh."]

    areas_to_investigate = [
        f"{t.label}: current change deviates from the established {t.direction} trend."
        for t in deviating
    ] + [f"{t.label}: unusual movement vs. recent history." for t in unusual]
    if not areas_to_investigate:
        areas_to_investigate = ["No metrics currently deviate from their recent trend."]

    return InsightsNarrative(
        executive_summary=executive_summary,
        current_scenario=current_scenario,
        change_from_previous=change_from_previous,
        three_month_trend=three_month_trend,
        key_observations=key_observations,
        areas_to_investigate=areas_to_investigate,
        source="fallback",
    )


def generate_narrative(
    changes: list[MetricChange],
    trends: list[TrendResult],
    current: MetricSnapshot,
    *,
    config: Optional[AIConfig] = None,
) -> InsightsNarrative:
    """Generate the AI Insights narrative, falling back to a deterministic
    template if the AI backend is unconfigured or unavailable."""
    config = config or AIConfig.from_env()
    fallback = _fallback_narrative(changes, trends, current)

    if not config.enabled:
        return fallback

    prompt = build_prompt(changes, trends, current)
    ai_payload = _call_chat_completions(config, prompt)
    if not ai_payload:
        return fallback

    try:
        return InsightsNarrative(
            executive_summary=str(ai_payload.get("executive_summary") or fallback.executive_summary),
            current_scenario=str(ai_payload.get("current_scenario") or fallback.current_scenario),
            change_from_previous=str(
                ai_payload.get("change_from_previous") or fallback.change_from_previous
            ),
            three_month_trend=str(
                ai_payload.get("three_month_trend") or fallback.three_month_trend
            ),
            key_observations=list(ai_payload.get("key_observations") or fallback.key_observations),
            areas_to_investigate=list(
                ai_payload.get("areas_to_investigate") or fallback.areas_to_investigate
            ),
            source="ai",
        )
    except (TypeError, ValueError):
        return fallback
