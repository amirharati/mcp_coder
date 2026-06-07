"""Delegation usage telemetry: preflight estimate, actual tokens, approximate cost."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from core.context.summary import estimate_tokens
from core.usage.rates import estimate_cost_usd

PREFLIGHT_NOTE = (
    "Preflight covers MCP-assembled prompt only; excludes Aider target_files "
    "bodies and session history."
)


@dataclass
class UsageReport:
    model: str
    preflight_tokens_est: int
    preflight_chars: int
    actual: dict[str, Any]
    cost_est_usd: dict[str, Any] | None
    note: str | None = PREFLIGHT_NOTE

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "preflight_tokens_est": self.preflight_tokens_est,
            "preflight_chars": self.preflight_chars,
            "actual": self.actual,
        }
        if self.cost_est_usd is not None:
            payload["cost_est_usd"] = self.cost_est_usd
        if self.note:
            payload["note"] = self.note
        return payload


def normalize_actual_tokens(tokens: dict[str, Any] | None) -> dict[str, Any]:
    if not tokens or tokens.get("source") == "unavailable":
        return {
            "input": None,
            "output": None,
            "total": None,
            "source": "unavailable",
        }
    return {
        "input": tokens.get("input"),
        "output": tokens.get("output"),
        "total": tokens.get("total"),
        "source": tokens.get("source", "unknown"),
    }


def build_usage_report(
    *,
    model: str,
    prompt: str,
    actual_tokens: dict[str, Any] | None,
    preflight_tokens_est: int | None = None,
    preflight_chars: int | None = None,
) -> dict[str, Any]:
    """Build usage dict for JSONL, MCP response, and spec report."""
    chars = preflight_chars if preflight_chars is not None else len(prompt)
    tokens_est = (
        preflight_tokens_est
        if preflight_tokens_est is not None
        else estimate_tokens(prompt)
    )
    actual = normalize_actual_tokens(actual_tokens)

    cost: dict[str, Any] | None = None
    if actual["input"] is not None or actual["output"] is not None:
        cost = estimate_cost_usd(
            model,
            actual["input"],
            actual["output"],
        )
    elif tokens_est and lookup_has_model(model):
        cost = estimate_cost_usd(
            model,
            tokens_est,
            0,
            preflight_only=True,
        )

    report = UsageReport(
        model=model,
        preflight_tokens_est=tokens_est,
        preflight_chars=chars,
        actual=actual,
        cost_est_usd=cost,
    )
    return report.to_dict()


def lookup_has_model(model: str) -> bool:
    from core.usage.rates import lookup_model_rates

    return lookup_model_rates(model) is not None


def format_usage_run_log_line(usage: dict[str, Any]) -> str:
    """One-line markdown summary for spec report Run log."""
    model = usage.get("model", "unknown")
    preflight = usage.get("preflight_tokens_est", 0)
    actual = usage.get("actual") or {}
    cost = usage.get("cost_est_usd")

    in_tok = actual.get("input")
    out_tok = actual.get("output")
    total_tok = actual.get("total")
    actual_source = actual.get("source", "unavailable")

    if actual_source == "unavailable" or total_tok is None:
        actual_part = "actual n/a"
    else:
        actual_part = f"actual {total_tok} tok (in {in_tok} / out {out_tok})"

    if cost and cost.get("total") is not None:
        cost_part = f"cost ~${cost['total']:.2f}"
    else:
        cost_part = "cost n/a"

    return (
        f"- **usage:** model `{model}`; preflight ~{preflight} tok; "
        f"{actual_part}; {cost_part}"
    )


def build_usage_warnings(preflight_tokens_est: int) -> list[str]:
    """Optional soft warn when preflight exceeds MCP_CODER_USAGE_WARN_TOKENS."""
    raw = os.environ.get("MCP_CODER_USAGE_WARN_TOKENS", "").strip()
    if not raw:
        return []
    try:
        threshold = int(raw)
    except ValueError:
        return []
    if preflight_tokens_est <= threshold:
        return []
    return [
        f"Preflight prompt estimate exceeds {threshold} tokens; "
        "consider host_transcript: none or shorter context_summary."
    ]
