"""Per-delegation LLM trace file builders (P6-003, D-P6-3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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

# compile_event stage constants (P7-003)
TRACE_TYPE_COMPILE_EVENT = "compile_event"
STAGE_MECHANICAL_BRIEF = "mechanical_brief"
STAGE_BUILDER_INPUT = "builder_input"
STAGE_BUILDER_OUTPUT = "builder_output"
STAGE_ARCHITECT_INPUT = "architect_input"
STAGE_ARCHITECT_OUTPUT = "architect_output"
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
        record["tokens"] = {
            "input": tokens.get("input"),
            "output": tokens.get("output"),
            "total": tokens.get("total"),
        }

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
    model: str | None,
    verbosity: str,
    timestamp: str | None = None,
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
        "model": model,
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
    model: str | None,
    verbosity: str,
    request_received_at: str,
    response_received_at: str,
    wire_latency_ms: int,
    status_code: int,
    raw_request: str | None = None,
    raw_response: str | None = None,
    attribution_source: str = "none",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build one JSONL trace line for a proxy-captured LLM HTTP call."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_PROXY_LLM_CALL,
        "delegation_id": delegation_id,
        "step_index": step_index,
        "call_index": call_index,
        "model": model,
        "request_received_at": request_received_at,
        "response_received_at": response_received_at,
        "wire_latency_ms": wire_latency_ms,
        "status_code": status_code,
        "attribution_source": attribution_source,
        "timestamp": timestamp or utc_now_iso(),
        "verbosity": verbosity,
    }

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

    if duration_ms is not None:
        record["duration_ms"] = duration_ms

    if tokens:
        record["tokens"] = {
            "input": tokens.get("input"),
            "output": tokens.get("output"),
            "total": tokens.get("total"),
        }

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


# ── Compile provenance trace builders (P7-003, D-P7-5) ─────────────────────


def build_compile_event_record(
    *,
    delegation_id: str,
    stage: str,
    verbosity: str,
    timestamp: str | None = None,
    text_body: str | None = None,
    source_path: str | None = None,
    byte_start: int | None = None,
    byte_end: int | None = None,
    last_source_line: int | None = None,
) -> dict[str, Any]:
    """Build one compile_event trace line with verbosity-aware body handling."""
    record: dict[str, Any] = {
        "type": TRACE_TYPE_COMPILE_EVENT,
        "delegation_id": delegation_id,
        "stage": stage,
        "verbosity": verbosity,
        "timestamp": timestamp or utc_now_iso(),
    }

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
