"""Per-delegation LLM trace file builders (P6-003, D-P6-3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config.observability import (
    VERBOSITY_FULL,
    VERBOSITY_LEAN,
    VERBOSITY_STANDARD,
)
from core.context.summary import redact_secrets, sha256_hex
from core.logging.delegation_log import _append_jsonl_line, utc_now_iso

TRACE_TYPE_LLM_CALL = "llm_call"
TRACE_TYPE_HEADER = "trace_header"
PREVIEW_MAX_CHARS = 500


def _truncate_preview(text: str, *, max_chars: int = PREVIEW_MAX_CHARS) -> str:
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

    if verbosity == VERBOSITY_LEAN:
        return record

    redacted_prompt = redact_secrets(prompt_text) if prompt_text else None
    redacted_response = redact_secrets(response_text) if response_text else None
    redacted_reasoning = redact_secrets(reasoning_text) if reasoning_text else None

    if verbosity == VERBOSITY_STANDARD:
        if redacted_prompt:
            record["prompt_preview"] = _truncate_preview(redacted_prompt)
        if redacted_response:
            record["response_preview"] = _truncate_preview(redacted_response)
        return record

    if verbosity == VERBOSITY_FULL:
        if redacted_prompt:
            record["prompt_preview"] = _truncate_preview(redacted_prompt)
            record["prompt_body"] = redacted_prompt
        if redacted_response:
            record["response_preview"] = _truncate_preview(redacted_response)
            record["response_body"] = redacted_response
        if redacted_reasoning:
            record["reasoning_body"] = redacted_reasoning
        return record

    # Unknown tier — treat as standard.
    if redacted_prompt:
        record["prompt_preview"] = _truncate_preview(redacted_prompt)
    if redacted_response:
        record["response_preview"] = _truncate_preview(redacted_response)
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
