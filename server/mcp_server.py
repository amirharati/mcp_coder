from __future__ import annotations

import json
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from core.context.summary import assemble_prompt, prompt_metadata
from core.context.transcript_policy import POLICY_DUMP, resolve_host_transcript_policy
from core.engine import get_engine, list_backends
from core.engine.factory import UnknownBackendError
from core.host import apply_host_hint, get_host_provider
from core.host.base import HostSessionHint
from core.host.cursor_transcript import (
    empty_transcript_result,
    load_cursor_transcript,
    transcript_log_context,
)
from core.logging.delegation_log import (
    CONTEXT_MODE_FALLBACK,
    CONTEXT_MODE_HOST_TRANSCRIPT,
    append_delegation_record,
    build_delegation_record,
    log_delegation_received,
    log_delegation_sent,
    log_host_resolved,
    new_delegation_id,
    should_log_full_prompt,
    utc_now_iso,
    workspace_path,
)
from core.logging.server_log import server_log_emit
from core.session.policy import resolve_session_policy
from core.session.store import SessionStore

OUTPUT_MAX_CHARS = 16_000

mcp = FastMCP(
    "mcp-coder",
    instructions=(
        "Implementation delegate for this repo. Use delegate_to_agent when the user "
        "wants code written or changed on disk—especially HTML/CSS/JS, multi-file "
        "work, or refactors. Do not use for chat-only answers. Requires context_summary."
    ),
)


def _truncate_output(text: str, max_chars: int = OUTPUT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n…[truncated]"


def _response_payload(
    *,
    success: bool,
    output: str,
    files_changed: list[str],
    session_reused: bool,
    session_reason: str,
    session_policy: str,
    mcp_session_id: str | None = None,
    log_path: str | None = None,
    host_kind: str | None = None,
    host_session_id: str | None = None,
    executor_reused: bool = False,
    executor_recreated: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": success,
        "output": _truncate_output(output),
        "files_changed": files_changed,
        "session_reused": session_reused,
        "session_reason": session_reason,
        "session_policy": session_policy,
        "executor_reused": executor_reused,
        "executor_recreated": executor_recreated,
    }
    if mcp_session_id is not None:
        payload["mcp_session_id"] = mcp_session_id
    if log_path is not None:
        payload["log_path"] = log_path
    if host_kind is not None:
        payload["host_kind"] = host_kind
    if host_session_id is not None:
        payload["host_session_id"] = host_session_id
    return payload


@mcp.tool(
    name="delegate_to_agent",
    description=(
        "IMPLEMENTATION DELEGATE: Run Aider to edit files on disk. Use this instead of "
        "writing code yourself when the user asks to build, create, or change project files "
        "(web pages, scripts, multi-file features). Required: task, target_files (repo-relative), "
        "context_summary (decisions from chat—the delegate cannot see history). "
        "Returns success, output, files_changed. Default backend: aider."
    ),
)
def delegate_to_agent(
    task: str,
    target_files: list[str],
    context_summary: str,
    backend: str = "aider",
) -> str:
    """Run one delegated implementation via the selected backend; append JSONL log."""
    delegation_id = new_delegation_id()
    t0 = time.perf_counter()
    timestamp_start = utc_now_iso()

    mcp_request = {
        "task": task,
        "target_files": target_files,
        "context_summary": context_summary,
        "backend": backend,
    }
    ws = workspace_path()
    policy = resolve_session_policy(ws)
    host_transcript_policy = resolve_host_transcript_policy(ws)

    t_host = time.perf_counter()
    try:
        host_hint = get_host_provider().resolve_active_session(ws)
    except Exception as exc:
        host_hint = HostSessionHint(resolve_error=f"{type(exc).__name__}: {exc}")
    host_resolve_ms = int((time.perf_counter() - t_host) * 1000)

    t_sess = time.perf_counter()
    storage = SessionStore().acquire(ws, policy, host_hint)
    session_decision_ms = int((time.perf_counter() - t_sess) * 1000)

    server_log_emit(
        "session_acquired",
        level="info",
        workspace_path=ws,
        session_policy=storage.session_policy,
        session_action=storage.session_action,
        session_reason=storage.session_reason,
        mcp_session_id=storage.mcp_session_id,
        session_dir=str(storage.session_dir.resolve()),
        session_decision_ms=session_decision_ms,
    )

    host_context = apply_host_hint(storage.session_dir, host_hint)
    file_bytes = host_context.get("host_transcript_file_bytes")

    transcript_result = empty_transcript_result(
        file_bytes=file_bytes if isinstance(file_bytes, int) else None,
    )
    context_mode = CONTEXT_MODE_FALLBACK
    host_transcript_text: str | None = None
    context_load_ms = 0

    if (
        host_transcript_policy == POLICY_DUMP
        and host_hint.host_transcript_path
        and not host_hint.resolve_error
    ):
        t_ctx = time.perf_counter()
        transcript_result = load_cursor_transcript(host_hint.host_transcript_path)
        context_load_ms = int((time.perf_counter() - t_ctx) * 1000)
        if transcript_result.text:
            context_mode = CONTEXT_MODE_HOST_TRANSCRIPT
            host_transcript_text = transcript_result.text

    log_host_resolved(
        hint_host_kind=host_hint.host_kind,
        host_session_id=host_hint.host_session_id,
        transcript_path=host_hint.host_transcript_path,
        resolve_error=host_hint.resolve_error,
        host_resolve_ms=host_resolve_ms,
    )
    if host_hint.resolve_error:
        server_log_emit(
            "host_resolve_failed",
            level="warn",
            workspace_path=ws,
            resolve_error=host_hint.resolve_error,
        )

    log_delegation_received(
        delegation_id=delegation_id,
        target_files=target_files,
        backend=backend,
        task_preview=task,
    )
    model: str | None = None
    success = False
    error: str | None = None
    files_changed: list[str] = []
    output = ""
    tokens: dict[str, Any] = {"source": "unavailable"}
    executor_reused = False
    executor_recreated = False
    timing: dict[str, int] = {
        "context_load_ms": context_load_ms,
        "session_decision_ms": session_decision_ms + host_resolve_ms,
        "engine_run_ms": 0,
        "post_process_ms": 0,
    }

    prompt = assemble_prompt(
        context_summary,
        task,
        host_transcript=host_transcript_text,
    )
    transcript_meta = transcript_log_context(
        policy=host_transcript_policy,
        load_result=transcript_result,
        file_bytes=file_bytes if isinstance(file_bytes, int) else None,
        context_mode=context_mode,
    )
    context_block = prompt_metadata(
        prompt,
        context_summary=context_summary,
        transcript_meta=transcript_meta,
    )

    try:
        engine = get_engine(backend)
        model = engine.model_name

        t_engine = time.perf_counter()
        result = engine.run(
            prompt,
            target_files,
            workspace_path=ws,
            mcp_session_id=storage.mcp_session_id,
        )
        timing["engine_run_ms"] = int((time.perf_counter() - t_engine) * 1000)

        success = result.success
        output = result.output or ""
        files_changed = result.files_changed
        tokens = result.tokens or tokens
        model = result.model or model
        error = result.error
        executor_reused = result.executor_reused
        executor_recreated = result.executor_recreated
        if not success and error:
            output = error if not output else f"{output}\n{error}"

    except UnknownBackendError as exc:
        success = False
        error = str(exc)
        output = error
    except Exception as exc:
        success = False
        error = f"{type(exc).__name__}: {exc}"
        output = error

    t_post = time.perf_counter()
    response = _response_payload(
        success=success,
        output=output,
        files_changed=files_changed,
        session_reused=storage.session_action == "reuse",
        session_reason=storage.session_reason,
        session_policy=storage.session_policy,
        mcp_session_id=storage.mcp_session_id,
        log_path=str(storage.log_path),
        host_kind=host_hint.host_kind,
        host_session_id=host_hint.host_session_id,
        executor_reused=executor_reused,
        executor_recreated=executor_recreated,
    )
    duration_ms = int((time.perf_counter() - t0) * 1000)
    timestamp_end = utc_now_iso()
    timing["post_process_ms"] = int((time.perf_counter() - t_post) * 1000)

    record = build_delegation_record(
        delegation_id=delegation_id,
        timestamp_start=timestamp_start,
        timestamp_end=timestamp_end,
        duration_ms=duration_ms,
        mcp_request=mcp_request,
        backend=backend,
        model=model,
        success=success,
        error=error,
        response_to_cursor=response,
        files_requested=list(target_files),
        files_changed=files_changed,
        context_block=context_block,
        context_mode=context_mode,
        timing=timing,
        tokens=tokens,
        project_key=storage.project_key,
        mcp_session_id=storage.mcp_session_id,
        session_dir=storage.session_dir,
        log_path=storage.log_path,
        session_action=storage.session_action,
        session_reason=storage.session_reason,
        session_policy=storage.session_policy,
        host_kind=host_hint.host_kind,
        host_session_id=host_hint.host_session_id,
        host_transcript_path=host_hint.host_transcript_path,
        host_context=host_context,
        executor_reused=executor_reused,
        executor_recreated=executor_recreated,
        prompt_full=prompt if should_log_full_prompt() else None,
    )
    log_path = append_delegation_record(record, ws=ws)
    log_delegation_sent(
        delegation_id=delegation_id,
        success=success,
        duration_ms=duration_ms,
        files_changed=files_changed,
        log_path=log_path,
        error=error,
    )

    return json.dumps(response, ensure_ascii=False)


def run_stdio() -> None:
    mcp.run(transport="stdio")
