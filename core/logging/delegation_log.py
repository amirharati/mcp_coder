from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Executor-options audit for the active delegation (P10-001).
# Set by AiderEngine._execute_delegation before coder creation so that
# build_delegation_record can include the fields without mcp_server.py changes.
executor_options_audit_var: ContextVar[dict] = ContextVar(
    "executor_options_audit", default={}
)

from core.logging.server_log import server_log_emit
from core.logging.stderr import log_stderr
from core.storage.paths import (
    legacy_workspace_log_path,
    mirror_log_targets,
    sessions_root,
)
from core.storage.workspace_session import load_workspace_pointer
from core.storage.session_paths import touch_session_last_delegation

TOOL_NAME = "delegate_to_agent"
CONTEXT_MODE_FALLBACK = "fallback"
CONTEXT_MODE_HOST_TRANSCRIPT = "host_transcript"
PROMPT_PREVIEW_CHARS = 500

CLARITY_CHECK_CLEAR = "clear"
CLARITY_CHECK_CLARIFICATION_NEEDED = "clarification_needed"
CLARITY_CHECK_SKIPPED = "skipped"
CLARITY_CHECK_ERROR = "error"


def resolve_clarity_check_result(
    *,
    enabled: bool,
    ran: bool | None,
    passed: bool | None,
    blocked: bool,
    error: str | None = None,
) -> str | None:
    """Map clarity-check phase state to delegation JSONL audit value."""
    if not enabled:
        return CLARITY_CHECK_SKIPPED
    if blocked:
        return CLARITY_CHECK_CLARIFICATION_NEEDED
    if ran is True and passed is True:
        return CLARITY_CHECK_CLEAR
    if error or ran is False:
        return CLARITY_CHECK_ERROR
    return None


def supervisor_audit_fields(tokens: dict[str, Any] | None) -> dict[str, Any]:
    """Optional supervisor counters for delegation JSONL context block."""
    data = tokens or {}
    out: dict[str, Any] = {}
    count = data.get("supervisor_decisions_count")
    if count is not None:
        out["supervisor_decisions_count"] = int(count)
    aborts = data.get("supervisor_aborts_count")
    if aborts is not None:
        out["supervisor_aborts_count"] = int(aborts)
    last = data.get("supervisor_last_decision")
    if last:
        out["supervisor_last_decision"] = str(last)[:120]
    return out

# delegations.jsonl record schema (lean — see D-P6-3)
# Each line is a delegation audit row. Bodies live in:
#   - Aider output:    response_digest.output_sha256 (full text → Cursor received it)
#   - RAG hit bodies:  delegation_rag.db (join on context_refs[].id)
#   - LLM I/O bodies:  trace_ref path → sessions/.../traces/<delegation_id>.jsonl
#   - Context package: context_package_hash (reconstruct from spec + candidate_files)


def _slim_response_to_cursor(response: dict[str, Any]) -> dict[str, Any]:
    output: str = response.get("output") or ""
    output_bytes = len(output.encode("utf-8"))
    output_sha256 = hashlib.sha256(output.encode("utf-8")).hexdigest()
    preview = output[:200]
    if len(output) > 200:
        preview += "…"
    return {
        "output_sha256": output_sha256,
        "output_bytes": output_bytes,
        "output_preview": preview,
        "success": response.get("success"),
        "files_changed": response.get("files_changed", []),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def workspace_path() -> str:
    return os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())


def delegation_log_paths_for_workspace(ws: str | None = None) -> list[Path]:
    """All session delegation logs for a workspace (mtime ascending)."""
    base = ws or workspace_path()
    resolved = str(Path(base).resolve())

    root = sessions_root(resolved)
    if root.is_dir():
        paths = [
            p
            for p in root.glob("*/delegations.jsonl")
            if p.is_file()
        ]
        if paths:
            paths.sort(key=lambda p: p.stat().st_mtime)
            return paths

    data = load_workspace_pointer(resolved)
    sessions_root_raw = data.get("sessions_root")
    if sessions_root_raw:
        try:
            sessions_root_path = Path(sessions_root_raw)
            if sessions_root_path.is_dir():
                paths = [
                    p
                    for p in sessions_root_path.glob("*/delegations.jsonl")
                    if p.is_file()
                ]
                if paths:
                    paths.sort(key=lambda p: p.stat().st_mtime)
                    return paths
        except (TypeError, OSError):
            pass

    legacy = legacy_workspace_log_path(resolved)
    if legacy.is_file():
        return [legacy]

    return []


def delegation_log_path(ws: str | None = None) -> Path:
    """Default read path: most recently written session log, else legacy fallback."""
    paths = delegation_log_paths_for_workspace(ws)
    if paths:
        return paths[-1]

    base = ws or workspace_path()
    return legacy_workspace_log_path(base)


def log_verbose() -> bool:
    return os.environ.get("MCP_CODER_LOG_VERBOSE", "").strip() in ("1", "true", "yes")


def log_brief() -> bool:
    """One-line receive/send traces on stderr (default on; does not touch stdout)."""
    raw = os.environ.get("MCP_CODER_LOG_BRIEF", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def should_log_full_prompt() -> bool:
    """Deprecated — always returns True. MCP_CODER_LOG_FULL_PROMPT is ignored."""
    return True


def build_delegation_record(
    *,
    delegation_id: str,
    timestamp_start: str,
    timestamp_end: str,
    duration_ms: int,
    mcp_request: dict[str, Any],
    backend: str,
    model: str | None,
    success: bool,
    error: str | None,
    response_to_cursor: dict[str, Any],
    files_requested: list[str],
    files_changed: list[str],
    files_unexpected: list[str] | None = None,
    context_block: dict[str, Any],
    context_mode: str = CONTEXT_MODE_FALLBACK,
    timing: dict[str, int | float],
    tokens: dict[str, Any],
    project_key: str,
    mcp_session_id: str,
    session_dir: Path | str,
    log_path: Path | str,
    session_action: str,
    session_reason: str,
    session_policy: str,
    host_kind: str | None = None,
    host_session_id: str | None = None,
    host_transcript_path: str | None = None,
    host_context: dict[str, Any] | None = None,
    executor_reused: bool = False,
    executor_recreated: bool = False,
    prompt_full: str | None = None,
    spec_path: str | None = None,
    spec_report_path: str | None = None,
    spec_sha256: str | None = None,
    spec_mtime: str | None = None,
    outcome: str | None = None,
    delegate_mode: str | None = None,
    spec_files_missing_from_target: list[str] | None = None,
    contract_warnings: list[str] | None = None,
    delegation_policies: dict[str, Any] | None = None,
    scope_violations: list[str] | None = None,
    usage: dict[str, Any] | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    workspace_snapshot: dict[str, Any] | None = None,
    post_gateway: dict[str, Any] | None = None,
    checkpoint: dict[str, Any] | None = None,
    auto_merged_read_paths: list[str] | None = None,
    auto_merge_spec_read: bool | None = None,
    model_roles: dict[str, Any] | None = None,
    context_refs: list[dict[str, Any]] | None = None,
    trace_ref: str | None = None,
    system_prefix_applied: bool = False,
    edit_format_applied: str | None = None,
    executor_pull_hint_applied: bool = False,
    stall_type: str | None = None,
    stall_files_requested: list[str] | None = None,
    auto_retried: bool = False,
) -> dict[str, Any]:
    # Fall back to contextvar set by AiderEngine when params not explicitly passed.
    _audit = executor_options_audit_var.get()
    if not system_prefix_applied:
        system_prefix_applied = bool(_audit.get("system_prefix_applied", False))
    if edit_format_applied is None:
        edit_format_applied = _audit.get("edit_format") or None
    if not executor_pull_hint_applied:
        executor_pull_hint_applied = bool(_audit.get("executor_pull_hint_applied", False))

    session_dir_str = str(Path(session_dir).resolve())
    log_path_str = str(Path(log_path).resolve())
    record: dict[str, Any] = {
        "type": "delegation",
        "delegation_id": delegation_id,
        "timestamp_start": timestamp_start,
        "timestamp_end": timestamp_end,
        "duration_ms": duration_ms,
        "workspace_path": workspace_path(),
        "tool_name": TOOL_NAME,
        "mcp_request": mcp_request,
        "backend": backend,
        "context_mode": context_mode,
        "session_action": session_action,
        "session_reason": session_reason,
        "session_policy": session_policy,
        "session_id": mcp_session_id,
        "project_key": project_key,
        "mcp_session_id": mcp_session_id,
        "session_dir": session_dir_str,
        "log_path": log_path_str,
        "host_kind": host_kind,
        "host_session_id": host_session_id,
        "host_transcript_path": host_transcript_path,
        "model": model,
        "success": success,
        "error": error,
        "response_to_cursor": _slim_response_to_cursor(response_to_cursor),
        "files_requested": files_requested,
        "files_changed": files_changed,
        "files_unexpected": files_unexpected if files_unexpected is not None else [],
        "context": {
            "specstory_path": None,
            "specstory_mtime": None,
            "specstory_hash": None,
            "specstory_bytes": None,
            "executor_reused": executor_reused,
            "executor_recreated": executor_recreated,
            "system_prefix_applied": system_prefix_applied,
            "executor_pull_hint_applied": executor_pull_hint_applied,
            **({"edit_format": edit_format_applied} if edit_format_applied is not None else {}),
            **({"stall_type": stall_type} if stall_type else {}),
            **(
                {"stall_files_requested": stall_files_requested}
                if stall_files_requested
                else {}
            ),
            **({"auto_retried": True} if auto_retried else {}),
            **context_block,
            **(host_context or {}),
        },
        "timing": timing,
        "tokens": tokens,
        "context_refs": context_refs if context_refs is not None else [],
    }
    if prompt_full is not None:
        record["context"]["prompt_full"] = prompt_full
    if spec_path is not None:
        record["spec_path"] = spec_path
        if spec_report_path is not None:
            record["spec_report_path"] = spec_report_path
        if delegate_mode is not None:
            record["delegate_mode"] = delegate_mode
        record["spec_sha256"] = spec_sha256
        record["spec_mtime"] = spec_mtime
        record["outcome"] = outcome
    if spec_files_missing_from_target:
        record["spec_files_missing_from_target"] = spec_files_missing_from_target
    if contract_warnings:
        record["contract_warnings"] = contract_warnings
    if delegation_policies is not None:
        record["delegation_policies"] = delegation_policies
    if scope_violations:
        record["scope_violations"] = scope_violations
    if usage is not None:
        record["usage"] = usage
        record["context"]["token_estimate_preflight"] = usage.get("preflight_tokens_est")
    if error_class is not None:
        record["error_detail"] = {
            "error_class": error_class,
            "error_message": error_message,
        }
    if workspace_snapshot is not None:
        record["workspace_snapshot"] = workspace_snapshot
    if post_gateway is not None:
        record["post_gateway"] = post_gateway
    if checkpoint is not None:
        record["checkpoint"] = checkpoint
    if auto_merged_read_paths:
        record["auto_merged_read_paths"] = auto_merged_read_paths
    if auto_merge_spec_read is not None:
        record["auto_merge_spec_read"] = auto_merge_spec_read
    if model_roles:
        record["model_roles"] = model_roles
    if trace_ref is not None:
        record["trace_ref"] = trace_ref
    return record


def _append_jsonl_line(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def append_delegation_record(record: dict[str, Any], *, ws: str | None = None) -> Path:
    log_path = Path(record["log_path"])
    session_dir = Path(record["session_dir"])
    _append_jsonl_line(log_path, record)
    touch_session_last_delegation(session_dir)

    base = ws or workspace_path()
    for mirror_path in mirror_log_targets(base):
        _append_jsonl_line(mirror_path, record)

    if log_verbose():
        log_stderr(
            f"[mcp-coder] delegation {record.get('delegation_id')} "
            f"success={record.get('success')} duration_ms={record.get('duration_ms')}"
        )

    success = bool(record.get("success"))
    error = record.get("error")
    if success:
        err_field = None
        if error:
            err_text = str(error)
            err_field = err_text[:200] + ("…" if len(err_text) > 200 else "")
        server_log_emit(
            "delegation_completed",
            level="info",
            delegation_id=record.get("delegation_id"),
            success=True,
            duration_ms=record.get("duration_ms"),
            mcp_session_id=record.get("mcp_session_id"),
            log_path=str(log_path.resolve()),
            files_changed_count=len(record.get("files_changed") or []),
            error=err_field,
        )
    else:
        error_detail = record.get("error_detail") or {}
        server_log_emit(
            "delegation_failed",
            level="error",
            delegation_id=record.get("delegation_id"),
            error=str(error) if error else "unknown",
            error_class=error_detail.get("error_class"),
            error_message=error_detail.get("error_message"),
        )
    return log_path


def log_host_resolved(
    *,
    hint_host_kind: str | None,
    host_session_id: str | None,
    transcript_path: str | None,
    resolve_error: str | None = None,
    host_resolve_ms: int | None = None,
) -> None:
    server_log_emit(
        "host_resolved",
        level="info",
        host_kind=hint_host_kind,
        host_session_id=host_session_id,
        host_transcript_path=transcript_path,
        resolve_error=resolve_error,
        host_resolve_ms=host_resolve_ms,
    )
    if not log_brief() or not host_session_id:
        return
    sid = host_session_id[:8] + "…"
    path = transcript_path or "(none)"
    log_stderr(f"[mcp-coder] host {hint_host_kind or 'unknown'} session={sid} transcript={path}")


def log_delegation_received(
    *,
    delegation_id: str,
    target_files: list[str],
    backend: str,
    task_preview: str,
) -> None:
    preview = task_preview[:120] + ("…" if len(task_preview) > 120 else "")
    server_log_emit(
        "delegation_received",
        level="info",
        delegation_id=delegation_id,
        backend=backend,
        target_files_count=len(target_files),
        task_preview=preview,
    )
    if not log_brief():
        return
    files = ",".join(target_files[:5]) or "(none)"
    if len(target_files) > 5:
        files += ",…"
    task_short = (task_preview[:60] + "…") if len(task_preview) > 60 else task_preview
    log_stderr(
        f"[mcp-coder] ← delegate_to_agent id={delegation_id[:8]}… "
        f"backend={backend} files=[{files}] ws={workspace_path()}\n"
        f"           task: {task_short}"
    )


def log_delegation_sent(
    *,
    delegation_id: str,
    success: bool,
    duration_ms: int,
    files_changed: list[str],
    log_path: Path,
    error: str | None = None,
) -> None:
    # delegation_completed / delegation_failed emitted from append_delegation_record
    if not log_brief():
        return
    changed = ",".join(files_changed[:5]) or "(none)"
    if len(files_changed) > 5:
        changed += ",…"
    err = f" error={error[:80]}…" if error else ""
    log_stderr(
        f"[mcp-coder] → id={delegation_id[:8]}… success={success} "
        f"{duration_ms}ms changed=[{changed}]{err}\n"
        f"           log: {log_path}"
    )


def new_delegation_id() -> str:
    return str(uuid.uuid4())
