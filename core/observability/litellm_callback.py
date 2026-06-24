"""LiteLLM success_callback token accumulator (P6-002, D-P6-2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config.role_models import ROLE_EXECUTOR
from core.observability.context import (
    CLI_FALLBACK_ROLE,
    _backend_call_active,
    delegation_id_var,
    is_backend_stream_call_active,
    role_var,
    session_dir_var,
    step_index_var,
    workspace_var,
)
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
_reasoning_text: dict[str, list[str]] = {}
REASONING_SUMMARY_MAX_CHARS = 2000


def note_delegation_start(delegation_id: str) -> None:
    """Clear accumulator for the previous delegation when a new one starts."""
    global _last_delegation_id
    if _last_delegation_id and _last_delegation_id != delegation_id:
        clear_delegation_tokens(_last_delegation_id)
        _reasoning_text.pop(_last_delegation_id, None)
    _last_delegation_id = delegation_id


def clear_delegation_reasoning_text(delegation_id: str) -> None:
    """Remove in-flight executor reasoning snippets for one delegation."""
    _reasoning_text.pop(delegation_id, None)


def _format_reasoning_summary(snippets: list[str]) -> str | None:
    if not snippets:
        return None
    from core.context.summary import redact_secrets

    combined = redact_secrets("\n\n---\n\n".join(snippets))
    if not combined.strip():
        return None
    suffix = "…[truncated]"
    if len(combined) <= REASONING_SUMMARY_MAX_CHARS:
        return combined
    keep = REASONING_SUMMARY_MAX_CHARS - len(suffix)
    return combined[:keep] + suffix


def _record_executor_reasoning(delegation_id: str, reasoning_text: str | None) -> None:
    if not reasoning_text or not reasoning_text.strip():
        return
    _reasoning_text.setdefault(delegation_id, []).append(reasoning_text.strip())


def finalize_delegation_reasoning_summary(delegation_id: str) -> str | None:
    """Join snippets, redact, truncate to 2000 chars; pop accumulator entry."""
    snippets = _reasoning_text.pop(delegation_id, None)
    if not snippets:
        return None
    return _format_reasoning_summary(snippets)


def peek_delegation_reasoning_summary(delegation_id: str) -> str | None:
    """Non-destructive read of in-flight executor reasoning (tests)."""
    snippets = _reasoning_text.get(delegation_id)
    if not snippets:
        return None
    return _format_reasoning_summary(list(snippets))


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
    if bucket is None:
        return None
    if (
        bucket.call_count == 0
        and bucket.input == 0
        and bucket.output == 0
        and bucket.total == 0
    ):
        return None
    return bucket.to_token_dict()


def get_cli_accumulated_usage() -> dict[str, Any] | None:
    """Usage captured under the CLI fallback key (test-model --via litellm)."""
    return get_accumulated_usage(_CLI_KEY[0], CLI_FALLBACK_ROLE)


def pop_cli_accumulated_usage() -> dict[str, Any] | None:
    """Read and remove CLI fallback usage."""
    key = _CLI_KEY
    bucket = _store.pop(key, None)
    if bucket is None:
        return None
    if bucket.input == 0 and bucket.output == 0 and bucket.total == 0:
        return None
    return bucket.to_token_dict()


def _ensure_bucket(key: _ACCUMULATOR_KEY) -> _UsageBucket:
    bucket = _store.get(key)
    if bucket is None:
        bucket = _UsageBucket()
        _store[key] = bucket
    return bucket


def _bump_call_index(key: _ACCUMULATOR_KEY) -> int:
    bucket = _ensure_bucket(key)
    bucket.call_count += 1
    return bucket.call_count


def _record_usage(
    key: _ACCUMULATOR_KEY,
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

    bucket = _ensure_bucket(key)
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


def _extract_prompt_text(kwargs: dict[str, Any]) -> str | None:
    messages = kwargs.get("messages")
    if isinstance(messages, list):
        parts: list[str] = []
        for message in messages:
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    parts.append(content)
        if parts:
            return "\n\n".join(parts)
    prompt = kwargs.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        return prompt
    return None


def _extract_response_parts(response_obj: Any) -> tuple[str | None, str | None]:
    if response_obj is None:
        return None, None
    try:
        choices = getattr(response_obj, "choices", None)
        if not choices and isinstance(response_obj, dict):
            choices = response_obj.get("choices")
        if not choices:
            return None, None
        first = choices[0]
        message = getattr(first, "message", None)
        if message is None and isinstance(first, dict):
            message = first.get("message")
        if message is None:
            return None, None
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)
        from core.observability.reasoning_extract import extract_reasoning_text

        text = content if isinstance(content, str) else None
        return text, extract_reasoning_text(message)
    except (AttributeError, IndexError, TypeError):
        return None, None


def _append_trace_for_completion(
    *,
    delegation_id: str,
    role: str,
    call_index: int,
    model: str | None,
    duration_ms: int | None,
    usage: dict[str, int | None] | None,
    kwargs: dict[str, Any],
    response_obj: Any,
) -> None:
    session_dir = session_dir_var.get()
    workspace = workspace_var.get()
    if not session_dir or not workspace:
        return

    from core.config.observability import resolve_observability_verbosity
    from core.observability.context import model_policy_var
    from core.observability.trace import append_trace_record, build_trace_record

    prompt_text = _extract_prompt_text(kwargs)
    response_text, reasoning_text = _extract_response_parts(response_obj)
    verbosity = resolve_observability_verbosity(workspace)

    # Respect MCP_CODER_CAPTURE_REASONING for helper (non-executor) roles too.
    # Executor reasoning text is gated separately in _extract_from_success; this
    # gate covers the synchronous owned-completion path used by helper roles.
    if reasoning_text is not None and role != ROLE_EXECUTOR:
        try:
            from core.config.observability import capture_reasoning_enabled

            if not capture_reasoning_enabled(workspace):
                reasoning_text = None
        except Exception:
            pass

    policy = model_policy_var.get()
    if policy is None and workspace is not None and role:
        # The async litellm callback can fire after the ContextVar is reset in
        # finally blocks (e.g. aider_engine resets model_policy_var after
        # _run_coder completes).  Re-derive from the registry so the trace
        # record still carries meaningful audit data.
        try:
            from core.config.model_registry import policy_applied as _pa
            from core.config.model_registry import resolve as _resolve

            params = _resolve(role, workspace, include_aider_metadata=False)
            policy = _pa(params, role)
        except Exception:
            pass

    record = build_trace_record(
        delegation_id=delegation_id,
        role=role,
        model=model,
        call_index=call_index,
        duration_ms=duration_ms,
        tokens=usage,
        verbosity=verbosity,
        prompt_text=prompt_text,
        response_text=response_text,
        reasoning_text=reasoning_text,
        policy_applied=policy,
    )
    append_trace_record(record, session_dir=session_dir, delegation_id=delegation_id, workspace=workspace)


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

    duration_ms = _duration_ms(start_time, end_time)
    model_str = str(model) if model else None

    delegation_id = delegation_id_var.get()
    role = role_var.get() or CLI_FALLBACK_ROLE
    key = _correlation_key()
    call_index: int | None = None
    if delegation_id:
        trace_key = (delegation_id, role)
        call_index = _bump_call_index(trace_key)
        _record_usage(
            trace_key,
            model=model_str,
            usage=usage,
            reasoning_tokens=reasoning,
            duration_ms=duration_ms,
        )
    else:
        _record_usage(
            key,
            model=model_str,
            usage=usage,
            reasoning_tokens=reasoning,
            duration_ms=duration_ms,
        )

    if delegation_id and call_index is not None:
        try:
            _append_trace_for_completion(
                delegation_id=delegation_id,
                role=role,
                call_index=call_index,
                model=model_str,
                duration_ms=duration_ms,
                usage=usage,
                kwargs=kwargs,
                response_obj=response_obj,
            )
        except Exception:
            pass

    if delegation_id and role == ROLE_EXECUTOR:
        try:
            workspace = workspace_var.get()
            if workspace:
                from core.config.observability import capture_reasoning_enabled

                if capture_reasoning_enabled(workspace):
                    _, reasoning_text = _extract_response_parts(response_obj)
                    _record_executor_reasoning(delegation_id, reasoning_text)
        except Exception:
            pass


def _is_cache_warm_probe(kwargs: dict[str, Any]) -> bool:
    return kwargs.get("max_tokens") == 1


def _is_backend_stream_owned_call(kwargs: dict[str, Any], response_obj: Any) -> bool:
    model = kwargs.get("model")
    if not model and response_obj is not None:
        model = getattr(response_obj, "model", None)
    return is_backend_stream_call_active(
        delegation_id=delegation_id_var.get(),
        role=role_var.get() or CLI_FALLBACK_ROLE,
        model=str(model) if model else None,
        messages=kwargs.get("messages"),
    )


def _record_cache_warm_backend_call(
    kwargs: dict[str, Any],
    response_obj: Any,
    start_time: Any,
    end_time: Any,
) -> None:
    try:
        from core.observability import get_observability

        model = kwargs.get("model")
        if not model and response_obj is not None:
            model = getattr(response_obj, "model", None)
        model_str = str(model) if model else None

        usage_raw = None
        if response_obj is not None:
            usage_raw = getattr(response_obj, "usage", None)
        if usage_raw is None:
            usage_raw = kwargs.get("usage")
        usage = _tokens_from_usage_mapping(usage_raw)

        get_observability().record_backend_llm_call(
            call_type="cache_warm",
            model=model_str,
            step_index=step_index_var.get(),
            usage=usage,
            duration_ms=_duration_ms(start_time, end_time),
            prompt_text=_extract_prompt_text(kwargs),
            response_text=_extract_response_parts(response_obj)[0],
        )
    except Exception:
        pass


def litellm_success_handler(
    kwargs: dict[str, Any],
    response_obj: Any,
    start_time: Any,
    end_time: Any,
) -> None:
    """LiteLLM success callback — accumulate usage per (delegation_id, role)."""
    from core.observability.gateway import _gateway_call_active

    try:
        if _gateway_call_active.get():
            return  # Gateway already recorded this call synchronously — skip.

        if _is_cache_warm_probe(kwargs) and delegation_id_var.get():
            _record_cache_warm_backend_call(kwargs, response_obj, start_time, end_time)
            return

        if _is_backend_stream_owned_call(kwargs, response_obj):
            return  # ObservableModel owns this streamed inner-loop call until stream cleanup.

        if _backend_call_active.get():
            return  # ObservableModel owns inner-loop capture — skip Route A duplicate.

        _extract_from_success(kwargs, response_obj, start_time, end_time)
    except Exception:
        # Observability must never break completions.
        pass


def record_owned_completion(
    *,
    role: str,
    model: str | None,
    messages: list[dict[str, Any]],
    response_obj: Any,
    duration_ms: int,
    reasoning_text: str | None = None,
) -> dict[str, Any]:
    """Synchronous token + trace capture for owned litellm.completion calls.

    Uses contextvars (delegation_id, session_dir, workspace) already bound by mcp_server.
    Returns token dict for helper_llm_pipeline model_roles.
    """
    unavailable = {"input": None, "output": None, "total": None, "source": "unavailable"}
    if response_obj is None:
        return unavailable

    usage_raw = getattr(response_obj, "usage", None)
    usage = _tokens_from_usage_mapping(usage_raw)
    reasoning = None
    if usage_raw is not None:
        reasoning = _coerce_int(
            getattr(usage_raw, "reasoning_tokens", None)
            if not isinstance(usage_raw, dict)
            else usage_raw.get("reasoning_tokens")
        )

    model_str = str(model) if model else None
    if not model_str:
        response_model = getattr(response_obj, "model", None)
        if response_model:
            model_str = str(response_model)

    delegation_id = delegation_id_var.get()
    kwargs = {"messages": messages, "model": model}
    call_index: int | None = None

    if delegation_id:
        trace_key = (delegation_id, role)
        call_index = _bump_call_index(trace_key)
        _record_usage(
            trace_key,
            model=model_str,
            usage=usage,
            reasoning_tokens=reasoning,
            duration_ms=duration_ms,
        )
        try:
            _append_trace_for_completion(
                delegation_id=delegation_id,
                role=role,
                call_index=call_index,
                model=model_str,
                duration_ms=duration_ms,
                usage=usage,
                kwargs=kwargs,
                response_obj=response_obj,
            )
        except Exception:
            pass

    if usage is None:
        return unavailable

    return {
        "input": usage.get("input"),
        "output": usage.get("output"),
        "total": usage.get("total"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "cached_tokens": usage.get("cached_tokens"),
        "source": "owned_completion",
    }


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
    _reasoning_text.clear()
    _registered = False
    _last_delegation_id = None
    from core.observability.reasoning_buffer import clear_all_session_reasoning
    from core.observability.context import clear_backend_stream_calls_for_tests

    clear_backend_stream_calls_for_tests()
    clear_all_session_reasoning()
