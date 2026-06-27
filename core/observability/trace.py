"""Per-delegation LLM trace file builders (P6-003, D-P6-3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from core.config.observability import (
    VERBOSITY_FULL,
    VERBOSITY_STANDARD,
)
from core.context.summary import redact_secrets, sha256_hex
from core.logging.delegation_log import _append_jsonl_line, utc_now_iso

TRACE_TYPE_LLM_CALL = "llm_call"
TRACE_TYPE_BACKEND_LLM_CALL = "backend_llm_call"
TRACE_TYPE_PROXY_LLM_CALL = "proxy_llm_call"
TRACE_TYPE_HEADER = "trace_header"
TRACE_TYPE_TOOL_CALL = "tool_call"
TRACE_TYPE_ACTION = "action"
TRACE_TYPE_SUPERVISOR_INTERCEPT = "supervisor_intercept"

# tool enum values (v1)
TOOL_FILE_WRITE = "file_write"
TOOL_SHELL_EXEC = "shell_exec"

# action kind enum values (v1)
ACTION_LINT_RETRY = "lint_retry"
ACTION_AUTO_CONFIRM = "auto_confirm"
ACTION_SCOPE_EXPANSION_CHECK = "scope_expansion_check"
ACTION_EXECUTOR_STALL = "executor_stall"

PREVIEW_MAX_CHARS = 500
BRIEF_MAX_CHARS = 200


def _provider_from_model(model: str | None) -> str | None:
    """Best-effort provider slug from model id."""
    if not model:
        return None
    model_s = str(model).strip()
    if not model_s:
        return None
    if "/" in model_s:
        return model_s.split("/", 1)[0]
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_proxy_usage_from_raw_response(raw_response: str | None) -> dict[str, int | None] | None:
    """Best-effort usage extraction from proxy raw JSON response body."""
    if not raw_response:
        return None
    try:
        payload = json.loads(raw_response)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = _coerce_int(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("inputTokens")
        or usage.get("promptTokens")
    )
    output_tokens = _coerce_int(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("outputTokens")
        or usage.get("completionTokens")
    )
    total_tokens = _coerce_int(
        usage.get("total_tokens")
        or usage.get("totalTokenCount")
        or usage.get("totalTokens")
    )

    completion_details = usage.get("completion_tokens_details") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    reasoning_tokens = _coerce_int(
        usage.get("reasoning_tokens")
        or (completion_details.get("reasoning_tokens") if isinstance(completion_details, dict) else None)
    )
    cached_tokens = _coerce_int(
        prompt_details.get("cached_tokens") if isinstance(prompt_details, dict) else None
    )

    if (
        input_tokens is None
        and output_tokens is None
        and total_tokens is None
        and reasoning_tokens is None
        and cached_tokens is None
    ):
        return None
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cached_tokens": cached_tokens,
    }


# compile_event stage constants (P7-003)
TRACE_TYPE_COMPILE_EVENT = "compile_event"
STAGE_MECHANICAL_BRIEF = "mechanical_brief"
STAGE_BUILDER_INPUT = "builder_input"
STAGE_BUILDER_OUTPUT = "builder_output"
STAGE_PLANNER_INPUT = "planner_input"
STAGE_PLANNER_OUTPUT = "planner_output"
# Backward-compat aliases (old traces used architect_* names; keep for reader tools)
STAGE_ARCHITECT_INPUT = STAGE_PLANNER_INPUT
STAGE_ARCHITECT_OUTPUT = STAGE_PLANNER_OUTPUT
# P15-003: clarity-resolution sub-agent lifecycle bracket events.
STAGE_CLARITY_RESOLUTION_START = "clarity_resolution_start"
STAGE_CLARITY_RESOLUTION_END = "clarity_resolution_end"
STAGE_VALIDATION_INPUT = "validation_input"
STAGE_VALIDATION_OUTPUT = "validation_output"
STAGE_FINAL_EXECUTOR_PROMPT = "final_executor_prompt"


def _truncate_preview(text: str, *, max_chars: int = PREVIEW_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _normalize_brief_text(text: str) -> str:
    """Collapse whitespace for deterministic compile-event briefs."""
    import re

    return re.sub(r"\s+", " ", text.strip())


def _truncate_brief(text: str, *, max_chars: int = BRIEF_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def ensure_trace_header(
    *,
    session_dir: str | Path,
    delegation_id: str,
    workspace: str | Path,
) -> None:
    """Write trace_header line once when the per-delegation trace file is first created."""
    path = Path(session_dir) / "traces" / f"{delegation_id}.jsonl"
    if path.is_file() and path.stat().st_size > 0:
        return

    from core.observability.version_tags import build_trace_version_tags

    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "type": TRACE_TYPE_HEADER,
        "delegation_id": delegation_id,
        "timestamp": utc_now_iso(),
        "version_tags": build_trace_version_tags(workspace),
    }
    _append_jsonl_line(path, header)


def annotate_trace_header_context_package_hash(
    *,
    session_dir: str | Path,
    delegation_id: str,
    context_package_hash: str | None,
) -> bool:
    """Set context_package_hash on the first trace_header line when the trace file exists."""
    if not context_package_hash:
        return False

    path = Path(session_dir) / "traces" / f"{delegation_id}.jsonl"
    if not path.is_file() or path.stat().st_size == 0:
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return False

    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError:
        return False

    if header.get("type") != TRACE_TYPE_HEADER:
        return False

    header["context_package_hash"] = context_package_hash
    lines[0] = json.dumps(header, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def build_trace_record(
    *,
    delegation_id: str,
    role: str,
    model: str | None,
    call_index: int,
    timestamp: str | None = None,
    duration_ms: int | None,
    tokens: dict[str, Any] | None,
    verbosity: str,
    prompt_text: str | None,
    response_text: str | None,
    reasoning_text: str | None = None,
    policy_applied: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one JSONL trace line for an LLM completion."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_LLM_CALL,
        "delegation_id": delegation_id,
        "role": role,
        "model": model,
        "call_index": call_index,
        "timestamp": timestamp or utc_now_iso(),
        "verbosity": verbosity,
    }

    if policy_applied:
        record["policy_applied"] = policy_applied

    if duration_ms is not None:
        record["duration_ms"] = duration_ms

    if tokens:
        token_payload = {
            "input": tokens.get("input"),
            "output": tokens.get("output"),
            "total": tokens.get("total"),
        }
        # P14-ISS-002: always emit reasoning_tokens (null when the model returned
        # none) so consumers can distinguish "field absent = capture broken" from
        # "field null = model chose not to think". Do not add a reason string in v1.
        reasoning_tokens = tokens.get("reasoning_tokens")
        cached_tokens = tokens.get("cached_tokens")
        token_payload["reasoning_tokens"] = reasoning_tokens
        if reasoning_tokens is not None:
            # Keep a top-level alias for quick log scans.
            record["thinking_tokens"] = reasoning_tokens
        if cached_tokens is not None:
            token_payload["cached_tokens"] = cached_tokens
        record["tokens"] = token_payload

    if prompt_text:
        record["prompt_hash"] = sha256_hex(prompt_text)
    if response_text:
        record["response_hash"] = sha256_hex(response_text)

    redacted_prompt = redact_secrets(prompt_text) if prompt_text else None
    redacted_response = redact_secrets(response_text) if response_text else None
    redacted_reasoning = redact_secrets(reasoning_text) if reasoning_text else None

    if redacted_prompt:
        record["prompt_body"] = redacted_prompt
    if redacted_response:
        record["response_body"] = redacted_response
    if redacted_reasoning:
        record["reasoning_body"] = redacted_reasoning

    if verbosity in (VERBOSITY_STANDARD, VERBOSITY_FULL):
        if redacted_prompt:
            record["prompt_preview"] = _truncate_preview(redacted_prompt)
        if redacted_response:
            record["response_preview"] = _truncate_preview(redacted_response)

    return record


def build_backend_llm_call_record(
    *,
    delegation_id: str,
    step_index: int | None,
    call_index: int | None = None,
    call_type: str,
    role: str | None = None,
    model: str | None,
    provider: str | None = None,
    verbosity: str,
    timestamp: str | None = None,
    ok: bool | None = True,
    duration_ms: int | None = None,
    thinking_text: str | None = None,
    thinking_tokens: int | None = None,
    usage: dict[str, Any] | None = None,
    prompt_text: str | None = None,
    response_text: str | None = None,
    policy_applied: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one JSONL trace line for an Aider inner-loop LLM completion."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_BACKEND_LLM_CALL,
        "delegation_id": delegation_id,
        "call_type": call_type,
        "role": role,
        "model": model,
        "provider": provider or _provider_from_model(model),
        "ok": ok,
        "timestamp": timestamp or utc_now_iso(),
        "verbosity": verbosity,
    }

    if policy_applied:
        record["policy_applied"] = policy_applied

    if step_index is not None:
        record["step_index"] = step_index

    if call_index is not None:
        record["call_index"] = call_index

    if duration_ms is not None:
        record["duration_ms"] = duration_ms

    if thinking_text:
        record["thinking_text"] = thinking_text
    if thinking_tokens is not None and thinking_tokens > 0:
        record["thinking_tokens"] = thinking_tokens

    if usage:
        record["usage"] = {
            "input": usage.get("input"),
            "output": usage.get("output"),
            "total": usage.get("total"),
        }

    if prompt_text:
        record["prompt_hash"] = sha256_hex(prompt_text)
    if response_text:
        record["response_hash"] = sha256_hex(response_text)

    redacted_prompt = redact_secrets(prompt_text) if prompt_text else None
    redacted_response = redact_secrets(response_text) if response_text else None
    redacted_thinking = redact_secrets(thinking_text) if thinking_text else None

    if redacted_prompt:
        record["prompt_body"] = redacted_prompt
    if redacted_response:
        record["response_body"] = redacted_response
    if redacted_thinking:
        record["thinking_body"] = redacted_thinking

    if verbosity in (VERBOSITY_STANDARD, VERBOSITY_FULL):
        if redacted_prompt:
            record["prompt_preview"] = _truncate_preview(
                redacted_prompt, max_chars=BRIEF_MAX_CHARS
            )
        if redacted_response:
            record["response_preview"] = _truncate_preview(
                redacted_response, max_chars=BRIEF_MAX_CHARS
            )
        if redacted_thinking:
            record["thinking_preview"] = _truncate_preview(
                redacted_thinking, max_chars=BRIEF_MAX_CHARS
            )

    return record


def build_proxy_llm_call_record(
    *,
    delegation_id: str | None,
    step_index: int | None,
    call_index: int | None,
    role: str | None = None,
    model: str | None,
    provider: str | None = None,
    verbosity: str,
    request_received_at: str,
    response_received_at: str,
    wire_latency_ms: int,
    status_code: int,
    raw_request: str | None = None,
    raw_response: str | None = None,
    attribution_source: str = "none",
    ok: bool | None = None,
    tokens: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build one JSONL trace line for a proxy-captured LLM HTTP call."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_PROXY_LLM_CALL,
        "delegation_id": delegation_id,
        "step_index": step_index,
        "call_index": call_index,
        "role": role,
        "model": model,
        "provider": provider or _provider_from_model(model),
        "request_received_at": request_received_at,
        "response_received_at": response_received_at,
        "wire_latency_ms": wire_latency_ms,
        "status_code": status_code,
        "ok": bool(status_code < 400) if ok is None else bool(ok),
        "attribution_source": attribution_source,
        "timestamp": timestamp or utc_now_iso(),
        "verbosity": verbosity,
    }
    token_source = tokens or _extract_proxy_usage_from_raw_response(raw_response)
    if token_source:
        token_payload = {
            "input": token_source.get("input"),
            "output": token_source.get("output"),
            "total": token_source.get("total"),
        }
        reasoning_tokens = token_source.get("reasoning_tokens")
        cached_tokens = token_source.get("cached_tokens")
        if reasoning_tokens is not None:
            token_payload["reasoning_tokens"] = reasoning_tokens
            record["thinking_tokens"] = reasoning_tokens
        if cached_tokens is not None:
            token_payload["cached_tokens"] = cached_tokens
        record["tokens"] = token_payload

    redacted_request = redact_secrets(raw_request) if raw_request else None
    redacted_response = redact_secrets(raw_response) if raw_response else None
    if redacted_request:
        record["raw_request"] = redacted_request
    if redacted_response:
        record["raw_response"] = redacted_response

    return record


def append_trace_record(
    record: dict[str, Any],
    *,
    session_dir: str | Path,
    delegation_id: str,
    workspace: str | Path | None = None,
) -> Path:
    """Append one trace line under session_dir/traces/<delegation_id>.jsonl."""
    if workspace is not None:
        ensure_trace_header(
            session_dir=session_dir,
            delegation_id=delegation_id,
            workspace=workspace,
        )
    path = Path(session_dir) / "traces" / f"{delegation_id}.jsonl"
    _append_jsonl_line(path, record)
    return path


# ── Executor-step trace builders (P7-002, D-P7-3 / D-P7-4) ─────────────────


def build_executor_llm_trace_record(
    *,
    delegation_id: str,
    step_index: int,
    model: str | None,
    timestamp: str | None = None,
    duration_ms: int | None = None,
    tokens: dict[str, Any] | None = None,
    verbosity: str,
    prompt_text: str | None = None,
    response_text: str | None = None,
    policy_applied: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one llm_call trace line for an executor step (role=executor, executor_turn=true)."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_LLM_CALL,
        "delegation_id": delegation_id,
        "role": "executor",
        "executor_turn": True,
        "step_index": step_index,
        "model": model,
        "timestamp": timestamp or utc_now_iso(),
        "verbosity": verbosity,
    }
    if policy_applied is not None:
        record["policy_applied"] = policy_applied

    if duration_ms is not None:
        record["duration_ms"] = duration_ms

    if tokens:
        # P14-ISS-001: mirror helper path (build_trace_record) so the executor
        # summary also carries reasoning/cached token counts and the top-level
        # thinking_tokens alias. Without this the executor role silently dropped
        # reasoning_tokens even though backend_llm_call captured them.
        token_payload = {
            "input": tokens.get("input"),
            "output": tokens.get("output"),
            "total": tokens.get("total"),
        }
        reasoning_tokens = tokens.get("reasoning_tokens")
        cached_tokens = tokens.get("cached_tokens")
        if reasoning_tokens is not None:
            token_payload["reasoning_tokens"] = reasoning_tokens
            # Keep a top-level alias for quick log scans (parity with helper path).
            record["thinking_tokens"] = reasoning_tokens
        if cached_tokens is not None:
            token_payload["cached_tokens"] = cached_tokens
        record["tokens"] = token_payload

    if prompt_text:
        record["prompt_hash"] = sha256_hex(prompt_text)
    if response_text:
        record["response_hash"] = sha256_hex(response_text)

    redacted_prompt = redact_secrets(prompt_text) if prompt_text else None
    redacted_response = redact_secrets(response_text) if response_text else None

    if redacted_prompt:
        record["prompt_body"] = redacted_prompt
    if redacted_response:
        record["response_body"] = redacted_response

    if verbosity in (VERBOSITY_STANDARD, VERBOSITY_FULL):
        if redacted_prompt:
            record["prompt_preview"] = _truncate_preview(redacted_prompt)
        if redacted_response:
            record["response_preview"] = _truncate_preview(redacted_response)

    return record


def build_tool_call_trace_record(
    *,
    delegation_id: str,
    step_index: int,
    timestamp: str | None = None,
    tool: str,
    path: str | None = None,
    bytes_written: int | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    exit_code: int | None = None,
) -> dict[str, Any]:
    """Build a non-LLM tool_call trace record (type=tool_call)."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_TOOL_CALL,
        "delegation_id": delegation_id,
        "step_index": step_index,
        "timestamp": timestamp or utc_now_iso(),
        "tool": tool,
    }
    if tool == TOOL_FILE_WRITE:
        if path is not None:
            record["path"] = path
        if bytes_written is not None:
            record["bytes_written"] = bytes_written
    elif tool == TOOL_SHELL_EXEC:
        if command is not None:
            record["command"] = command
        if args is not None:
            record["args"] = args
        if exit_code is not None:
            record["exit_code"] = exit_code
    return record


def build_action_trace_record(
    *,
    delegation_id: str,
    step_index: int,
    timestamp: str | None = None,
    kind: str,
    detail: str | None = None,
) -> dict[str, Any]:
    """Build a non-LLM action trace record (type=action)."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_ACTION,
        "delegation_id": delegation_id,
        "step_index": step_index,
        "timestamp": timestamp or utc_now_iso(),
        "kind": kind,
    }
    if detail is not None:
        record["detail"] = detail
    return record


def build_supervisor_intercept_record(
    *,
    delegation_id: str | None,
    loop_id: str | None,
    turn_index: int | None,
    classification: Literal["in_spec_approve", "out_of_scope_deny", "ambiguous_escalate"],
    decision: str,
    reasoning: str,
    question_preview: str,
    mentioned_paths: list[str],
    context_ref: dict[str, Any],
    llm_used: bool,
    duration_ms: int,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a supervisor_intercept trace record (P14-002, BL-547 v1)."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_SUPERVISOR_INTERCEPT,
        "delegation_id": delegation_id,
        "loop_id": loop_id,
        "turn_index": turn_index,
        "classification": classification,
        "decision": decision,
        "reasoning": reasoning[:200],
        "question_preview": question_preview[:120],
        "mentioned_paths": mentioned_paths,
        "context_ref": context_ref,
        "llm_used": llm_used,
        "duration_ms": duration_ms,
        "timestamp": timestamp or utc_now_iso(),
    }
    return record


# ── Compile provenance trace builders (P7-003, D-P7-5) ─────────────────────


def build_compile_event_record(
    *,
    delegation_id: str,
    stage: str,
    verbosity: str,
    timestamp: str | None = None,
    text_body: str | None = None,
    status: str | None = None,
    detail: str | None = None,
    source_path: str | None = None,
    byte_start: int | None = None,
    byte_end: int | None = None,
    last_source_line: int | None = None,
) -> dict[str, Any]:
    """Build one compile_event trace line with verbosity-aware body handling.

    status: "ok" | "skipped" | "error" — present even when there is no text_body,
    so every pipeline stage leaves a trace entry regardless of whether it ran.
    detail: short human-readable reason (e.g. why skipped, or truncated error).
    """
    record: dict[str, Any] = {
        "type": TRACE_TYPE_COMPILE_EVENT,
        "delegation_id": delegation_id,
        "stage": stage,
        "verbosity": verbosity,
        "timestamp": timestamp or utc_now_iso(),
    }
    if status is not None:
        record["status"] = status
    if detail is not None:
        record["detail"] = detail

    if source_path is not None:
        record["source_path"] = source_path
    if byte_start is not None:
        record["byte_start"] = byte_start
    if byte_end is not None:
        record["byte_end"] = byte_end
    if last_source_line is not None:
        record["last_source_line"] = last_source_line

    if not text_body:
        return record

    record["sha256"] = sha256_hex(text_body)
    record["byte_count"] = len(text_body.encode("utf-8"))

    redacted = redact_secrets(text_body)
    record["body"] = redacted

    if verbosity in (VERBOSITY_STANDARD, VERBOSITY_FULL):
        record["brief"] = _truncate_brief(_normalize_brief_text(redacted))

    return record
