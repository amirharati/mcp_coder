"""Per-role usage records for delegation JSONL model_roles audit (D-P4-8)."""

from __future__ import annotations

from typing import Any

from core.usage.rates import estimate_cost_usd


def build_role_usage_record(
    *,
    role: str,
    model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    duration_ms: int | None = None,
    source: str = "unavailable",
) -> dict[str, Any]:
    """Build one auditable model_roles entry for a single LLM role call."""
    tokens: dict[str, Any] = {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens,
        "source": source,
    }

    record: dict[str, Any] = {
        "role": role,
        "model": model,
        "tokens": tokens,
    }

    if input_tokens is not None or output_tokens is not None:
        cost = estimate_cost_usd(model, input_tokens, output_tokens)
        if cost is not None:
            record["cost_est_usd"] = cost
    elif total_tokens is not None and source != "unavailable":
        cost = estimate_cost_usd(model, total_tokens, 0)
        if cost is not None:
            record["cost_est_usd"] = cost

    if duration_ms is not None:
        record["duration_ms"] = duration_ms

    return record


def merge_model_roles(*records: dict[str, Any] | None) -> dict[str, Any] | None:
    """Merge role usage records keyed by role; skip None/empty."""
    merged: dict[str, Any] = {}
    for record in records:
        if not record:
            continue
        role = record.get("role")
        if isinstance(role, str) and role:
            merged[role] = record
    return merged or None
