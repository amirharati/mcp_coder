"""LiteLLM success_callback token accumulator (P6-002, D-P6-2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.observability.context import CLI_FALLBACK_ROLE, delegation_id_var, role_var
from core.usage.litellm_tokens import _coerce_int, _tokens_from_usage_mapping

_ACCUMULATOR_KEY = tuple[str, str]
_CLI_KEY = ("__cli__", CLI_FALLBACK_ROLE)

_registered = False


@dataclass
class _UsageBucket:
    model: str | None = None
    input: int = 0
    output: int = 0
    total: int = 0
    reasoning: int = 0
    duration_ms: int | None = None
    call_count: int = 0

    def to_token_dict(self) -> dict[str, Any]:
        return {
            "input": self.input or None,
            "output": self.output or None,
            "total": self.total or None,
            "reasoning_tokens": self.reasoning or None,
            "source": "litellm_callback",
            "model": self.model,
            "duration_ms": self.duration_ms,
            "call_count": self.call_count,
        }


_store: dict[_ACCUMULATOR_KEY, _UsageBucket] = {}
_last_delegation_id: str | None = None


def note_delegation_start(delegation_id: str) -> None:
    """Clear accumulator for the previous delegation when a new one starts."""
    global _last_delegation_id
    if _last_delegation_id and _last_delegation_id != delegation_id:
        clear_delegation_tokens(_last_delegation_id)
    _last_delegation_id = delegation_id


def clear_delegation_tokens(delegation_id: str) -> None:
    """Remove all accumulated usage for one delegation."""
    keys = [key for key in _store if key[0] == delegation_id]
    for key in keys:
        del _store[key]


def _correlation_key() -> _ACCUMULATOR_KEY:
    delegation_id = delegation_id_var.get()
    role = role_var.get() or CLI_FALLBACK_ROLE
    if delegation_id:
        return delegation_id, role
    return _CLI_KEY[0], role


def get_accumulated_usage(delegation_id: str, role: str) -> dict[str, Any] | None:
    """Return merged token usage for (delegation_id, role), or None."""
    bucket = _store.get((delegation_id, role))
    if bucket is None or bucket.call_count == 0:
        return None
    return bucket.to_token_dict()


def get_cli_accumulated_usage() -> dict[str, Any] | None:
    """Usage captured under the CLI fallback key (test-model --via litellm)."""
    return get_accumulated_usage(_CLI_KEY[0], CLI_FALLBACK_ROLE)


def pop_cli_accumulated_usage() -> dict[str, Any] | None:
    """Read and remove CLI fallback usage."""
    key = _CLI_KEY
    bucket = _store.pop(key, None)
    if bucket is None or bucket.call_count == 0:
        return None
    return bucket.to_token_dict()


def _record_usage(
    *,
    model: str | None,
    usage: dict[str, int | None] | None,
    reasoning_tokens: int | None,
    duration_ms: int | None,
) -> None:
    if usage is None:
        return
    inp = usage.get("input") or 0
    out = usage.get("output") or 0
    total = usage.get("total")
    if total is None:
        total = inp + out
    if inp == 0 and out == 0 and total == 0:
        return

    key = _correlation_key()
    bucket = _store.get(key)
    if bucket is None:
        bucket = _UsageBucket()
        _store[key] = bucket

    bucket.call_count += 1
    if model:
        bucket.model = model
    bucket.input += inp
    bucket.output += out
    bucket.total += total or 0
    if reasoning_tokens:
        bucket.reasoning += reasoning_tokens
    if duration_ms is not None:
        bucket.duration_ms = (bucket.duration_ms or 0) + duration_ms


def _duration_ms(start_time: Any, end_time: Any) -> int | None:
    if start_time is None or end_time is None:
        return None
    try:
        return max(0, int((end_time - start_time).total_seconds() * 1000))
    except (TypeError, AttributeError, ValueError):
        return None


def _extract_from_success(
    kwargs: dict[str, Any],
    response_obj: Any,
    start_time: Any,
    end_time: Any,
) -> None:
    model = kwargs.get("model")
    if not model and response_obj is not None:
        model = getattr(response_obj, "model", None)

    usage_raw = None
    if response_obj is not None:
        usage_raw = getattr(response_obj, "usage", None)
    if usage_raw is None:
        usage_raw = kwargs.get("usage")

    usage = _tokens_from_usage_mapping(usage_raw)
    reasoning = None
    if usage_raw is not None:
        reasoning = _coerce_int(
            getattr(usage_raw, "reasoning_tokens", None)
            if not isinstance(usage_raw, dict)
            else usage_raw.get("reasoning_tokens")
        )

    _record_usage(
        model=str(model) if model else None,
        usage=usage,
        reasoning_tokens=reasoning,
        duration_ms=_duration_ms(start_time, end_time),
    )


def litellm_success_handler(
    kwargs: dict[str, Any],
    response_obj: Any,
    start_time: Any,
    end_time: Any,
) -> None:
    """LiteLLM success callback — accumulate usage per (delegation_id, role)."""
    try:
        _extract_from_success(kwargs, response_obj, start_time, end_time)
    except Exception:
        # Observability must never break completions.
        pass


class _McpCoderLiteLLMLogger:
    """Sync success hook compatible with LiteLLM CustomLogger / callable callbacks."""

    def log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        litellm_success_handler(kwargs, response_obj, start_time, end_time)

    async def async_log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        litellm_success_handler(kwargs, response_obj, start_time, end_time)


_CALLBACK_INSTANCE = _McpCoderLiteLLMLogger()


def register_litellm_callbacks() -> None:
    """Register LiteLLM success callback once per process (idempotent)."""
    global _registered
    if _registered:
        return
    import litellm

    litellm.suppress_debug_info = True
    manager = litellm.logging_callback_manager
    if _CALLBACK_INSTANCE not in litellm.success_callback:
        manager.add_litellm_success_callback(_CALLBACK_INSTANCE)
    if _CALLBACK_INSTANCE not in litellm._async_success_callback:
        manager.add_litellm_async_success_callback(_CALLBACK_INSTANCE)
    _registered = True


def _tokens_missing(record: dict[str, Any] | None) -> bool:
    if not record:
        return True
    tokens = record.get("tokens") or {}
    return tokens.get("input") is None and tokens.get("output") is None


def overlay_role_record_from_callback(
    record: dict[str, Any] | None,
    *,
    delegation_id: str,
    role: str,
) -> dict[str, Any] | None:
    """Fill null token fields on a role record from the callback accumulator."""
    if record is None:
        return None
    if not _tokens_missing(record):
        return record

    acc = get_accumulated_usage(delegation_id, role)
    if acc is None:
        return record

    from core.usage.role_audit import build_role_usage_record

    tokens = record.get("tokens") or {}
    prior_source = str(tokens.get("source") or record.get("source") or "unavailable")
    source = "litellm_callback" if prior_source == "unavailable" else prior_source

    return build_role_usage_record(
        role=role,
        model=str(acc.get("model") or record.get("model") or ""),
        input_tokens=acc.get("input"),
        output_tokens=acc.get("output"),
        total_tokens=acc.get("total"),
        duration_ms=record.get("duration_ms") or acc.get("duration_ms"),
        source=source,
    )


def overlay_model_roles_from_callback(
    model_roles: dict[str, Any] | None,
    *,
    delegation_id: str,
    executor_fallback_tokens: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Merge callback accumulator tokens into model_roles before JSONL write."""
    if not model_roles:
        return model_roles

    from core.config.role_models import ROLE_EXECUTOR, ROLE_REVIEW
    from core.usage.role_audit import build_role_usage_record

    merged = dict(model_roles)
    for role, record in list(merged.items()):
        updated = overlay_role_record_from_callback(
            record, delegation_id=delegation_id, role=role
        )
        if updated is not None:
            merged[role] = updated

    executor = merged.get(ROLE_EXECUTOR)
    if executor is not None and _tokens_missing(executor):
        acc = get_accumulated_usage(delegation_id, ROLE_EXECUTOR)
        fallback = executor_fallback_tokens or {}
        inp = (acc or {}).get("input") if acc else fallback.get("input")
        out = (acc or {}).get("output") if acc else fallback.get("output")
        total = (acc or {}).get("total") if acc else fallback.get("total")
        if inp is not None or out is not None or total is not None:
            source = "litellm_callback" if acc else str(fallback.get("source") or "executor")
            merged[ROLE_EXECUTOR] = build_role_usage_record(
                role=ROLE_EXECUTOR,
                model=str(
                    (acc or {}).get("model")
                    or executor.get("model")
                    or ""
                ),
                input_tokens=inp,
                output_tokens=out,
                total_tokens=total,
                duration_ms=executor.get("duration_ms") or (acc or {}).get("duration_ms"),
                source=source,
            )

    review = merged.get(ROLE_REVIEW)
    if review is not None and _tokens_missing(review):
        acc = get_accumulated_usage(delegation_id, ROLE_REVIEW)
        if acc:
            merged[ROLE_REVIEW] = build_role_usage_record(
                role=ROLE_REVIEW,
                model=str(acc.get("model") or review.get("model") or ""),
                input_tokens=acc.get("input"),
                output_tokens=acc.get("output"),
                total_tokens=acc.get("total"),
                duration_ms=review.get("duration_ms") or acc.get("duration_ms"),
                source="litellm_callback",
            )

    return merged or None


def reset_callback_state_for_tests() -> None:
    """Clear accumulator and registration flag (tests only)."""
    global _registered, _last_delegation_id
    _store.clear()
    _registered = False
    _last_delegation_id = None
