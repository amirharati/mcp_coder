"""Best-effort token usage extraction from LiteLLM / Aider Model objects (BL-335)."""

from __future__ import annotations

from typing import Any

_UNAVAILABLE = {
    "input": None,
    "output": None,
    "total": None,
    "source": "unavailable",
}


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tokens_from_usage_mapping(usage: Any) -> dict[str, int | None] | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        inp = _coerce_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
        out = _coerce_int(usage.get("output_tokens") or usage.get("completion_tokens"))
        total = _coerce_int(usage.get("total_tokens"))
    else:
        inp = _coerce_int(
            getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None)
        )
        out = _coerce_int(
            getattr(usage, "output_tokens", None)
            or getattr(usage, "completion_tokens", None)
        )
        total = _coerce_int(getattr(usage, "total_tokens", None))
    if inp is None and out is None and total is None:
        return None
    if total is None and (inp is not None or out is not None):
        total = (inp or 0) + (out or 0)
    return {"input": inp, "output": out, "total": total}


def _tokens_from_response(response: Any) -> dict[str, int | None] | None:
    if response is None:
        return None
    if isinstance(response, dict):
        usage = response.get("usage")
        if usage is not None:
            return _tokens_from_usage_mapping(usage)
        return None
    usage = getattr(response, "usage", None)
    return _tokens_from_usage_mapping(usage)


def extract_litellm_model_tokens(model_obj: Any, *, role_source: str) -> dict[str, Any]:
    """Extract token counts from a Model object after ``simple_send_with_retries``.

    Checks, in order: direct counter attrs, ``usage`` dict/object on the model,
    and common last-response attrs that expose LiteLLM ``usage``.

    When usage is found, ``source`` is ``role_source`` (e.g. ``context_builder_llm``).
    When usage is unavailable, returns null token fields with ``source: unavailable``.
    """
    if model_obj is None:
        return dict(_UNAVAILABLE)

    total = _coerce_int(getattr(model_obj, "total_tokens", None))
    sent = _coerce_int(getattr(model_obj, "tokens_sent", None))
    received = _coerce_int(getattr(model_obj, "tokens_received", None))
    if total is not None:
        return {
            "input": sent,
            "output": received,
            "total": total,
            "source": role_source,
        }
    if sent is not None or received is not None:
        return {
            "input": sent,
            "output": received,
            "total": (sent or 0) + (received or 0),
            "source": role_source,
        }

    usage_tokens = _tokens_from_usage_mapping(getattr(model_obj, "usage", None))
    if usage_tokens is not None:
        return {**usage_tokens, "source": role_source}

    for attr in ("last_response", "response", "_last_response", "last_completion"):
        response_tokens = _tokens_from_response(getattr(model_obj, attr, None))
        if response_tokens is not None:
            return {**response_tokens, "source": role_source}

    callback_tokens = _tokens_from_callback_accumulator()
    if callback_tokens is not None:
        return {**callback_tokens, "source": "litellm_callback"}

    return dict(_UNAVAILABLE)


def _tokens_from_callback_accumulator() -> dict[str, int | None] | None:
    """Best-effort read from LiteLLM success_callback accumulator for current context."""
    try:
        from core.observability.context import delegation_id_var, role_var
        from core.observability.litellm_callback import get_accumulated_usage

        delegation_id = delegation_id_var.get()
        role = role_var.get()
        if not delegation_id or not role:
            return None
        acc = get_accumulated_usage(delegation_id, role)
        if acc is None:
            return None
        return {
            "input": acc.get("input"),
            "output": acc.get("output"),
            "total": acc.get("total"),
        }
    except Exception:
        return None
