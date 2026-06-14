"""Synchronous token + trace capture for owned litellm.completion calls (P6-008).

Deprecated (P7-001): prefer LlmGateway.complete() + ObservabilityBackend.record_llm_call().
Deprecated (P8-001): inner-loop Aider capture now via ObservableModel + backend_llm_call;
this module remains as a thin re-export for backward compatibility.
"""

from __future__ import annotations

from typing import Any

from core.observability.litellm_callback import record_owned_completion

__all__ = ["completion_and_record", "record_owned_completion"]


def completion_and_record(
    *,
    role: str,
    model: str,
    messages: list[dict[str, Any]],
    response_obj: Any,
    duration_ms: int,
) -> tuple[str, dict[str, Any]]:
    """Record tokens + trace after a litellm.completion response. Returns (text, tokens)."""
    text = ""
    try:
        text = (response_obj.choices[0].message.content or "").strip()
    except (AttributeError, IndexError, TypeError):
        text = ""

    tokens = record_owned_completion(
        role=role,
        model=model,
        messages=messages,
        response_obj=response_obj,
        duration_ms=duration_ms,
    )
    return text, tokens
