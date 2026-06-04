from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.context.summary import redact_secrets
from core.storage.paths import (
    legacy_workspace_log_path,
    mirror_log_targets,
    sessions_root,
)
from core.storage.workspace_session import load_workspace_pointer
from core.storage.session_paths import touch_session_last_delegation

TOOL_NAME = "delegate_to_agent"
CONTEXT_MODE = "fallback"
PROMPT_PREVIEW_CHARS = 500


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


def log_stderr(message: str) -> None:
    print(redact_secrets(message), file=sys.stderr, flush=True)


def should_log_full_prompt() -> bool:
    return os.environ.get("MCP_CODER_LOG_FULL_PROMPT", "").strip() in ("1", "true", "yes")


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
    context_block: dict[str, Any],
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
) -> dict[str, Any]:
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
        "context_mode": CONTEXT_MODE,
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
        "response_to_cursor": response_to_cursor,
        "files_requested": files_requested,
        "files_changed": files_changed,
        "context": {
            "specstory_path": None,
            "specstory_mtime": None,
            "specstory_hash": None,
            "specstory_bytes": None,
            "executor_reused": executor_reused,
            "executor_recreated": executor_recreated,
            **context_block,
            **(host_context or {}),
        },
        "timing": timing,
        "tokens": tokens,
    }
    if prompt_full is not None and should_log_full_prompt():
        record["context"]["prompt_full"] = prompt_full
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
    return log_path


def log_host_resolved(*, hint_host_kind: str | None, host_session_id: str | None, transcript_path: str | None) -> None:
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
