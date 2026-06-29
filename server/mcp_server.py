from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from core.config.host_model_policy import (
    normalize_host_model_policy,
    summarize_model_policy_applied,
)
from core.config.auto_merge import auto_merge_spec_read_enabled
from core.config.auto_verify import (
    auto_verify_enabled,
    resolve_verify_command,
    resolve_verify_timeout_s,
)
from core.engine.architect_trigger import should_run_architect_pass
from core.config.aider_runtime import (
    OUTCOME_NEEDS_INPUT_CLARIFICATION,
    OUTCOME_NEEDS_INPUT_FILES,
    build_needs_input_payload,
    resolve_executor_max_steps,
    resolve_executor_step_timeout_s,
    resolve_executor_total_timeout_s,
    stall_auto_retry_enabled,
)
from core.config.context_builder import (
    context_builder_enabled,
    context_builder_llm_enabled,
)
from core.config.rag import (
    builder_history_rag_enabled,
    rag_enabled,
    workspace_file_hints_enabled,
)
from core.config.spec_validation import (
    clarity_pass_enabled,
    reviewer_pass_enabled,
    spec_validation_enabled,
)
from core.config.models import resolve_model_name
from core.config.observability import resolve_observability_verbosity
from core.config.role_models import (
    ROLE_CONTEXT_BUILDER,
    ROLE_EXECUTOR,
    ROLE_REVIEW,
    ROLE_SUPERVISOR,
    resolve_role_model_name,
)
from core.engine.base import ExecutionResult
from core.observability.trace import (
    ACTION_EXECUTOR_STALL,
    ACTION_SCOPE_EXPANSION_CHECK,
    STAGE_ARCHITECT_INPUT,
    STAGE_ARCHITECT_OUTPUT,
    STAGE_BUILDER_INPUT,
    STAGE_BUILDER_OUTPUT,
    STAGE_FINAL_EXECUTOR_PROMPT,
    STAGE_MECHANICAL_BRIEF,
    STAGE_VALIDATION_INPUT,
    STAGE_VALIDATION_OUTPUT,
    TOOL_FILE_WRITE,
    append_trace_record,
    annotate_trace_header_context_package_hash,
    build_action_trace_record,
    build_compile_event_record,
    build_executor_llm_trace_record,
    build_tool_call_trace_record,
)
from core.context.assemble import assemble_context
from core.context.file_picker import CandidateFilesResult, pick_candidate_files
from core.context.budget import apply_context_budget, resolve_context_budget_tokens
from core.context.capability_adjust import apply_backend_capabilities
from core.context.helper_llm_pipeline import (
    SPEC_VALIDATION_BLOCK_OUTPUT,
    apply_planner_pass as _shared_apply_planner_pass,
    apply_builder_llm as _shared_apply_builder_llm,
    apply_clarity_check as _shared_apply_clarity_check,
    apply_reviewer_pass as _shared_apply_reviewer_pass,
    apply_spec_validation as _shared_apply_spec_validation,
    merge_architect_plan as _merge_architect_plan,
    merge_brief as _merge_brief,
)
from core.context.inspect import inspect_context_package
from core.context.mcp_summary import build_mcp_context_summary
from core.context.package import (
    TIER_EDIT_FULL,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
)
from core.context.summary import assemble_prompt, estimate_tokens, prompt_metadata, sha256_hex
from core.context.transcript_policy import POLICY_DUMP, resolve_host_transcript_policy
from core.delegation.errors import classify_delegation_error
from core.host import apply_host_hint, get_host_provider
from core.host.base import HostSessionHint
from core.host.cursor_transcript import (
    empty_transcript_result,
    load_cursor_transcript,
    transcript_log_context,
)
from core.logging.read_delegations import load_delegations_for_workspace
from core.observability.context import host_model_policy_var
from core.observability import (
    CONTEXT_MODE_FALLBACK,
    CONTEXT_MODE_HOST_TRANSCRIPT,
    bind_delegation_trace_scope,
    delegation_context,
    executor_step_context,
    get_observability,
    role_context,
)
from core.engine import get_engine, list_backends
from core.engine.factory import UnknownBackendError
from core.session.policy import resolve_session_policy
from core.session.store import SessionStore
from core.server.singleton import stale_mcp_pids
from core.specs.bootstrap import ensure_task_report, ensure_workspace_spec_layout
from core.engine.spec_review import run_spec_review
from core.specs.delegation_policies import (
    DelegationPolicies,
    PolicyValidationError,
    load_delegation_policies,
)
from core.workspace.gateway import apply_post_delegation_gateway
from core.specs.read_deps_merge import resolve_spec_read_deps
from core.specs.modes import DELEGATE_MODE_IMPLEMENT, DELEGATE_MODE_REVIEW, normalize_delegate_mode
from core.specs.outcome import (
    OUTCOME_INVALID_SPEC,
    OUTCOME_NEEDS_INPUT,
    OUTCOME_SUCCESS,
    apply_scope_outcome,
    apply_verify_outcome,
    compute_spec_outcome,
)
from core.verify.runner import VerifyResult, run_verify_command
from core.specs.paths import normalize_spec_path_arg, resolve_spec_path
from core.specs.read import read_task_spec
from core.specs.write import apply_post_delegation_report_updates
from core.state.supervisor_state import SupervisorState
from core.rag.builder_retrieval import (
    rag_retrieval_should_run,
    run_builder_workspace_file_retrieval,
    run_merged_builder_rag_retrieval,
)
from core.rag.retrieval import ContextRef, context_refs_to_dict, context_refs_to_lean_dict

OUTPUT_MAX_CHARS = 16_000

obs = get_observability()
from core.observability.bootstrap import ensure_observability_bootstrap

ensure_observability_bootstrap(obs)

# Keyed by project_key. Long-lived per MCP server process lifetime.
_SUPERVISOR_REGISTRY: dict[str, "SupervisorAgent"] = {}


def _sanitize_notification_text(text: str, *, max_chars: int = 180) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1] + "…"


class _DelegationProgressBridge:
    """Thread-safe bridge from sync delegate flow to async ctx.info()."""

    def __init__(self, ctx: Context | None, *, throttle_seconds: float = 2.0) -> None:
        self._ctx = ctx
        self._throttle_seconds = throttle_seconds
        self._last_emit = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._stopped = False

        if ctx is None:
            return
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            # No active loop in this thread (e.g. sync entrypoint).
            self._loop = None

        self._worker = threading.Thread(target=self._drain_worker, daemon=True)
        self._worker.start()

    def notify(self, message: str, *, force: bool = False) -> None:
        if self._ctx is None or self._stopped:
            return
        now = time.monotonic()
        if not force and self._last_emit and (now - self._last_emit) < self._throttle_seconds:
            return
        self._last_emit = now
        self._queue.put(_sanitize_notification_text(message))

    def _drain_worker(self) -> None:
        while True:
            try:
                msg = self._queue.get(timeout=0.2)
            except queue.Empty:
                if self._stopped:
                    return
                continue
            if msg is None:
                return
            if self._ctx is None:
                continue
            try:
                if self._loop is not None:
                    fut = asyncio.run_coroutine_threadsafe(self._ctx.info(msg), self._loop)
                    fut.result(timeout=5)
                else:
                    asyncio.run(self._ctx.info(msg))
            except Exception:
                # Notification path must never fail a delegation.
                pass

    def close(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._worker is not None:
            self._queue.put(None)
            self._worker.join(timeout=1.0)


def _emit_compile_event(
    *,
    delegation_id: str,
    stage: str,
    text_body: str | None,
    workspace: str,
    session_dir: "Path | str",
    obs_verbosity: str,
    status: str | None = None,
    detail: str | None = None,
    source_path: str | None = None,
    byte_start: int | None = None,
    byte_end: int | None = None,
    last_source_line: int | None = None,
) -> None:
    """Append one compile_event line; never raises (P7-003)."""
    try:
        record = build_compile_event_record(
            delegation_id=delegation_id,
            stage=stage,
            verbosity=obs_verbosity,
            text_body=text_body,
            status=status,
            detail=detail,
            source_path=source_path,
            byte_start=byte_start,
            byte_end=byte_end,
            last_source_line=last_source_line,
        )
        append_trace_record(
            record,
            session_dir=session_dir,
            delegation_id=delegation_id,
            workspace=workspace,
        )
    except Exception:
        pass


def _emit_compile_skip(
    *,
    delegation_id: str,
    stage: str,
    workspace: str,
    session_dir: "Path | str",
    obs_verbosity: str,
    reason: str,
) -> None:
    """Emit a compile_event with status=skipped and no body; never raises."""
    _emit_compile_event(
        delegation_id=delegation_id,
        stage=stage,
        text_body=None,
        workspace=workspace,
        session_dir=session_dir,
        obs_verbosity=obs_verbosity,
        status="skipped",
        detail=reason,
    )


def _emit_compile_provenance_pair(
    *,
    delegation_id: str,
    workspace: str,
    session_dir: "Path | str",
    obs_verbosity: str,
    input_stage: str,
    output_stage: str,
    provenance: dict[str, Any],
    source_path: str | None = None,
    byte_start: int | None = None,
    byte_end: int | None = None,
    last_source_line: int | None = None,
) -> None:
    """Emit input/output compile events for a helper stage."""
    input_prompt = provenance.get("input_prompt")
    output_text = provenance.get("output_text")
    if input_prompt:
        _emit_compile_event(
            delegation_id=delegation_id,
            stage=input_stage,
            text_body=str(input_prompt),
            workspace=workspace,
            session_dir=session_dir,
            obs_verbosity=obs_verbosity,
            source_path=source_path,
            byte_start=byte_start,
            byte_end=byte_end,
            last_source_line=last_source_line,
        )
    if output_text:
        _emit_compile_event(
            delegation_id=delegation_id,
            stage=output_stage,
            text_body=str(output_text),
            workspace=workspace,
            session_dir=session_dir,
            obs_verbosity=obs_verbosity,
        )


def _bounded_executor_loop(
    *,
    step_fn: "Any",
    delegation_id: str,
    session_dir: "Path | str",
    workspace: str,
    obs_verbosity: str,
    progress_notify: "Any | None" = None,
) -> "tuple[ExecutionResult, int]":
    """Bounded outer executor loop (P7-002, D-P7-2, Route A).

    step_fn(timeout_s: float | None) -> ExecutionResult
    Returns (final_result, executor_turns) where executor_turns counts
    steps with actual engine calls.
    """
    max_steps = resolve_executor_max_steps()
    step_timeout_s = resolve_executor_step_timeout_s()
    total_timeout_s = resolve_executor_total_timeout_s()
    loop_t0 = time.perf_counter()
    executor_turns = 0
    last_output: str = ""
    result: ExecutionResult | None = None

    # Resolve executor policy once (stable for the whole delegation) so every
    # executor llm_call trace event carries a populated policy_applied field.
    _executor_policy: "dict | None" = None
    try:
        from core.config.model_registry import ROLE_EXECUTOR
        from core.config.model_registry import policy_applied as _pa
        from core.config.model_registry import resolve as _resolve

        _executor_policy = _pa(_resolve(ROLE_EXECUTOR, workspace), ROLE_EXECUTOR)
    except Exception:
        pass

    for step_idx in range(1, max_steps + 1):
        elapsed = time.perf_counter() - loop_t0
        if elapsed >= total_timeout_s:
            result = ExecutionResult(
                success=False,
                output=f"Delegation total timeout exceeded ({total_timeout_s:.0f}s).",
                error=(
                    f"total_timeout ({total_timeout_s:.0f}s) exceeded "
                    f"after {step_idx - 1} executor steps"
                ),
                error_class="timeout",
                tokens={"source": "unavailable"},
            )
            break

        # Emit scope_expansion_check before each executor step.
        action_rec = build_action_trace_record(
            delegation_id=delegation_id,
            step_index=step_idx,
            kind=ACTION_SCOPE_EXPANSION_CHECK,
        )
        append_trace_record(
            action_rec,
            session_dir=session_dir,
            delegation_id=delegation_id,
            workspace=workspace,
        )

        step_t0 = time.perf_counter()
        with executor_step_context(step_idx):
            step_result = step_fn(step_timeout_s)
        step_ms = int((time.perf_counter() - step_t0) * 1000)
        executor_turns += 1
        if progress_notify is not None:
            try:
                progress_notify(
                    (
                        f"[executor] Step {step_idx} complete "
                        f"({len(step_result.files_changed or [])} file changes)."
                    )
                )
            except Exception:
                pass

        # Emit executor llm_call trace record.
        exec_llm_rec = build_executor_llm_trace_record(
            delegation_id=delegation_id,
            step_index=step_idx,
            model=step_result.model,
            duration_ms=step_ms,
            tokens=step_result.tokens,
            verbosity=obs_verbosity,
            prompt_text=step_result.prompt_used,
            response_text=step_result.output,
            policy_applied=_executor_policy,
        )
        append_trace_record(
            exec_llm_rec,
            session_dir=session_dir,
            delegation_id=delegation_id,
            workspace=workspace,
        )

        # Emit tool_call record for each file changed in this step.
        for fc in step_result.files_changed or []:
            fc_abs = Path(workspace) / fc
            bytes_written: int | None = None
            try:
                if fc_abs.is_file():
                    bytes_written = fc_abs.stat().st_size
            except OSError:
                pass
            tc_rec = build_tool_call_trace_record(
                delegation_id=delegation_id,
                step_index=step_idx,
                tool=TOOL_FILE_WRITE,
                path=fc,
                bytes_written=bytes_written,
            )
            append_trace_record(
                tc_rec,
                session_dir=session_dir,
                delegation_id=delegation_id,
            )

        # Emit executor_stall when no files changed and no output progression.
        if (
            not step_result.files_changed
            and last_output
            and step_result.output
            and step_result.output.strip() == last_output.strip()
        ):
            stall_rec = build_action_trace_record(
                delegation_id=delegation_id,
                step_index=step_idx,
                kind=ACTION_EXECUTOR_STALL,
                detail="no files changed and no output progression",
            )
            append_trace_record(
                stall_rec,
                session_dir=session_dir,
                delegation_id=delegation_id,
            )

        last_output = step_result.output or ""
        result = step_result

        # ── Stop conditions (in order) ───────────────────────────────────────
        if step_result.success:
            break  # normal completion — step produced complete output

        # Any non-success result stops the loop in v1.
        # The loop is infrastructure (safety rails + per-step tracing); explicit
        # retry signals are not implemented yet in P7-002.
        if not step_result.success:
            break

    if result is None:
        # Safeguard: max_steps == 0 or total_timeout fired before loop body.
        result = ExecutionResult(
            success=False,
            output="Executor loop did not run any steps.",
            error="no_steps_executed",
            error_class="internal",
            tokens={"source": "unavailable"},
        )

    return result, executor_turns


def _stall_from_tokens(tokens: dict[str, Any] | None) -> dict[str, Any]:
    data = tokens or {}
    stall_type = data.get("stall_type")
    if not stall_type:
        return {}
    out: dict[str, Any] = {
        "stall_type": stall_type,
        "files_requested": list(data.get("files_requested") or []),
        "executor_output_tail": data.get("executor_output_tail") or "",
    }
    if data.get("supervisor_reason"):
        out["supervisor_reason"] = data.get("supervisor_reason")
    if data.get("supervisor_decisions_count") is not None:
        out["supervisor_decisions_count"] = data.get("supervisor_decisions_count")
    if data.get("supervisor_aborts_count") is not None:
        out["supervisor_aborts_count"] = data.get("supervisor_aborts_count")
    if data.get("supervisor_decisions"):
        out["supervisor_decisions"] = list(data.get("supervisor_decisions") or [])
    return out


def _emit_supervisor_decision_traces(
    *,
    delegation_id: str,
    session_dir: Path | str,
    workspace: str,
    decisions: list[dict[str, Any]],
    step_index: int = 1,
) -> None:
    import json

    for row in decisions:
        snippet = {
            "decision": row.get("decision"),
            "risk_tier": row.get("risk_tier"),
            "question": (row.get("question") or "")[:160],
        }
        action_rec = build_action_trace_record(
            delegation_id=delegation_id,
            step_index=step_index,
            kind="supervisor_decision",
            detail=json.dumps(snippet, ensure_ascii=False),
        )
        append_trace_record(
            action_rec,
            session_dir=session_dir,
            delegation_id=delegation_id,
            workspace=workspace,
        )


def _supervisor_record_from_tokens(tokens: dict[str, Any] | None) -> dict[str, Any] | None:
    data = tokens or {}
    usage = data.get("supervisor_usage")
    if isinstance(usage, dict) and usage.get("model"):
        return obs.build_role_usage_record(
            role=ROLE_SUPERVISOR,
            model=str(usage.get("model")),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            duration_ms=usage.get("duration_ms"),
            source=str(usage.get("source") or "supervisor"),
        )
    count = data.get("supervisor_decisions_count")
    if count:
        return obs.build_role_usage_record(
            role=ROLE_SUPERVISOR,
            model=resolve_role_model_name(ROLE_SUPERVISOR, os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())),
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            duration_ms=None,
            source="supervisor_auto_only",
        )
    return None


def _append_read_paths_to_context_package(
    package: ContextPackage,
    paths: list[str],
    workspace: str,
) -> ContextPackage:
    from core.context.package import PathEntry, TIER_READ_FULL

    existing = {entry.path for entry in package.entries}
    entries = list(package.entries)
    ws = Path(workspace)
    for path in paths:
        if path in existing:
            continue
        abs_path = ws / path
        payload = None
        byte_count = None
        if abs_path.is_file():
            try:
                payload = abs_path.read_text(encoding="utf-8", errors="replace")
                byte_count = len(payload.encode("utf-8"))
            except OSError:
                pass
        entries.append(
            PathEntry(path=path, tier=TIER_READ_FULL, bytes=byte_count, payload=payload)
        )
        existing.add(path)
    return ContextPackage(
        brief=package.brief,
        entries=entries,
        policies=package.policies,
        metadata=dict(package.metadata),
    )


def _run_executor_with_optional_stall_retry(
    *,
    step_fn: Any,
    delegation_id: str,
    session_dir: "Path | str",
    workspace: str,
    obs_verbosity: str,
    progress_notify: Any | None,
    context_package: ContextPackage | None,
    effective_target_files: list[str],
    auto_merged_read_paths: list[str],
    already_retried: bool,
) -> tuple[
    ExecutionResult,
    int,
    list[str],
    list[str],
    ContextPackage | None,
    bool,
]:
    result, turns = _bounded_executor_loop(
        step_fn=step_fn,
        delegation_id=delegation_id,
        session_dir=session_dir,
        workspace=workspace,
        obs_verbosity=obs_verbosity,
        progress_notify=progress_notify,
    )
    stall = _stall_from_tokens(result.tokens)
    if (
        already_retried
        or not stall_auto_retry_enabled()
        or stall.get("stall_type") != OUTCOME_NEEDS_INPUT_FILES
        or not stall.get("files_requested")
    ):
        return result, turns, effective_target_files, auto_merged_read_paths, context_package, False

    new_paths = [
        path
        for path in stall["files_requested"]
        if path not in set(effective_target_files)
    ]
    if not new_paths:
        return result, turns, effective_target_files, auto_merged_read_paths, context_package, False

    merged_targets = sorted(set(effective_target_files) | set(new_paths))
    merged_reads = sorted(set(auto_merged_read_paths or []) | set(new_paths))
    updated_package = context_package
    if updated_package is not None:
        updated_package = _append_read_paths_to_context_package(
            updated_package,
            new_paths,
            workspace,
        )
    retry_result, extra_turns = _bounded_executor_loop(
        step_fn=step_fn,
        delegation_id=delegation_id,
        session_dir=session_dir,
        workspace=workspace,
        obs_verbosity=obs_verbosity,
        progress_notify=progress_notify,
    )
    return (
        retry_result,
        turns + extra_turns,
        merged_targets,
        merged_reads,
        updated_package,
        True,
    )


def use_context_package() -> bool:
    """Return True unless MCP_CODER_USE_CONTEXT_PACKAGE is explicitly 0/false/no."""
    raw = os.environ.get("MCP_CODER_USE_CONTEXT_PACKAGE", "1").strip().lower()
    return raw not in ("0", "false", "no")


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


def _spec_files_from_read(spec_read: Any) -> list[str]:
    """Extract file paths from spec_read Files section."""
    if spec_read is None:
        return []
    raw = (spec_read.sections.get("Files") or "").strip()
    if not raw:
        return []
    lines = [ln.strip().lstrip("-*").strip() for ln in raw.splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def _apply_builder_llm(
    *,
    context_package: "ContextPackage",
    picker_result: "CandidateFilesResult | None",
    workspace: str,
    task: str,
    context_summary: str,
    spec_rel_path: str | None,
    host_transcript: str | None,
    timing: dict[str, int | float],
    delegation_id: str,
    mcp_session_id: str,
    rag_refs: list[ContextRef] | None = None,
) -> tuple["ContextPackage", bool, str | None, dict[str, Any] | None, dict[str, Any]]:
    return _shared_apply_builder_llm(
        context_package=context_package,
        picker_result=picker_result,
        workspace=workspace,
        task=task,
        context_summary=context_summary,
        spec_rel_path=spec_rel_path,
        host_transcript=host_transcript,
        timing=timing,
        delegation_id=delegation_id,
        mcp_session_id=mcp_session_id,
        log_warn=obs.warn,
        rag_refs=rag_refs,
    )


def _apply_architect_pass(
    *,
    context_package: "ContextPackage",
    spec_read: "Any",
    picker_result: "CandidateFilesResult | None",
    workspace: str,
    task: str,
    context_summary: str,
    host_transcript: str | None,
    timing: dict[str, int | float],
    delegation_id: str,
    project_state: Any | None = None,
    spec_files: list[str] | None = None,
    planner_context_sources: list[str] | None = None,
    spec_path: str | None = None,
    session_dir: str | None = None,
) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, Any]]:
    return _shared_apply_planner_pass(
        context_package=context_package,
        spec_read=spec_read,
        picker_result=picker_result,
        workspace=workspace,
        task=task,
        context_summary=context_summary,
        host_transcript=host_transcript,
        timing=timing,
        delegation_id=delegation_id,
        log_warn=obs.warn,
        project_state=project_state,
        spec_files=spec_files,
        planner_context_sources=planner_context_sources,
        spec_path=spec_path,
        session_dir=session_dir,
    )


def _apply_spec_validation(
    *,
    spec_read: "Any",
    workspace: str,
    task: str,
    context_summary: str,
    host_transcript: str,
    timing: dict[str, int | float],
    delegation_id: str,
) -> tuple[
    bool,
    list[str] | None,
    bool,
    bool | None,
    str | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any],
]:
    return _shared_apply_spec_validation(
        spec_read=spec_read,
        workspace=workspace,
        task=task,
        context_summary=context_summary,
        host_transcript=host_transcript,
        timing=timing,
        delegation_id=delegation_id,
        log_warn=obs.warn,
    )


def _apply_clarity_check(
    *,
    spec_read: "Any",
    workspace: str,
    task: str,
    context_summary: str,
    prior_blocked_count: int,
    recent_delegation_titles: list[str],
    timing: dict[str, int | float],
    delegation_id: str,
) -> tuple[
    bool,
    list[str] | None,
    bool,
    bool | None,
    str | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any],
]:
    return _shared_apply_clarity_check(
        spec_read=spec_read,
        workspace=workspace,
        task=task,
        context_summary=context_summary,
        prior_blocked_count=prior_blocked_count,
        recent_delegation_titles=recent_delegation_titles,
        timing=timing,
        delegation_id=delegation_id,
        log_warn=obs.warn,
    )


def _apply_reviewer_pass(
    *,
    spec_read: "Any",
    workspace: str,
    task: str,
    files_changed: list[str],
    unified_diff: str,
    timing: dict[str, int | float],
    delegation_id: str,
) -> tuple[
    bool,
    str,
    str | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any],
]:
    return _shared_apply_reviewer_pass(
        workspace=workspace,
        task=task,
        spec_read=spec_read,
        files_changed=files_changed,
        unified_diff=unified_diff,
        timing=timing,
        delegation_id=delegation_id,
        log_warn=obs.warn,
    )


def _count_clarity_blocked_rounds(
    session_dir: "Path | str",
    spec_rel_path: str | None,
) -> int:
    """Count how many prior delegations in this session were blocked by clarity for this spec."""
    import json as _json

    log_path = Path(session_dir) / "delegations.jsonl"
    if not log_path.is_file():
        return 0
    count = 0
    try:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = _json.loads(line)
            except Exception:
                continue
            if _is_clarity_blocked_record_for_spec(rec, spec_rel_path):
                count += 1
    except Exception:
        return 0
    return count


def _count_workspace_clarity_blocked_delegations(
    workspace: "Path | str",
    spec_rel_path: str | None,
) -> int:
    """Count prior clarity-blocked delegations across workspace session logs."""
    try:
        records = load_delegations_for_workspace(workspace)
    except Exception:
        return 0
    return sum(
        1
        for rec in records
        if _is_clarity_blocked_record_for_spec(rec, spec_rel_path)
    )


def _is_clarity_blocked_record_for_spec(
    rec: dict[str, Any],
    spec_rel_path: str | None,
) -> bool:
    from core.logging.delegation_log import CLARITY_CHECK_CLARIFICATION_NEEDED

    if rec.get("outcome") != "needs_input":
        return False
    ctx = rec.get("context") or {}
    clarity_result = str(ctx.get("clarity_check_result") or "").strip().lower()
    if clarity_result != CLARITY_CHECK_CLARIFICATION_NEEDED:
        return False

    target_spec = _normalize_spec_for_match(spec_rel_path)
    if not target_spec:
        return True
    req = rec.get("mcp_request") or {}
    rec_spec = _normalize_spec_for_match(
        req.get("spec_path")
        or rec.get("spec_path")
        or ctx.get("task_spec")
        or ""
    )
    return bool(rec_spec and _same_spec_for_match(rec_spec, target_spec))


def _normalize_spec_for_match(path: str | None) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    return text


def _same_spec_for_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def _collect_reviewer_unified_diff(workspace: str, files_changed: list[str]) -> str:
    """Unified diff for reviewer prompt. Falls back to file content when not a git repo."""
    from core.engine.git_diff import normalize_repo_path

    if not files_changed:
        return ""
    paths = [normalize_repo_path(p) for p in files_changed]
    try:
        for args in (
            ["git", "diff", "HEAD", "--", *paths],
            ["git", "diff", "--", *paths],
        ):
            proc = subprocess.run(
                args,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout or ""
            stderr = (proc.stderr or "").lower()
            if "not a git repository" in stderr:
                break  # no point retrying; fall through to file-content fallback
        # Not a git repo or git unavailable — include file contents as a best-effort diff
        parts: list[str] = []
        for rel in files_changed[:10]:  # cap to avoid huge prompts
            abs_p = Path(workspace) / rel
            try:
                content = abs_p.read_text(encoding="utf-8", errors="replace")
                parts.append(f"--- /dev/null\n+++ {rel}\n" + "\n".join(f"+{l}" for l in content.splitlines()))
            except OSError:
                pass
        return "\n\n".join(parts)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc


def _collect_reviewer_changed_file_contents(
    workspace: str,
    files_changed: list[str],
) -> dict[str, str]:
    """Read current changed-file contents for deterministic reviewer sanity checks."""
    from core.engine.git_diff import normalize_repo_path

    root = Path(workspace).resolve()
    contents: dict[str, str] = {}
    for rel in files_changed[:10]:
        normalized = normalize_repo_path(rel)
        abs_path = (root / normalized).resolve()
        try:
            abs_path.relative_to(root)
        except ValueError:
            continue
        if not abs_path.is_file():
            continue
        try:
            contents[normalized] = abs_path.read_text(
                encoding="utf-8",
                errors="replace",
            )[:50_000]
        except OSError:
            continue
    return contents


_SPEC_VALIDATION_BLOCK_OUTPUT = SPEC_VALIDATION_BLOCK_OUTPUT
_CLARITY_CHECK_BLOCK_OUTPUT = (
    "Clarity check found the task unclear. Answer the questions in Cursor, "
    "then retry delegate_to_agent."
)


def _build_model_roles_payload(
    *,
    delegation_id: str,
    delegate_mode: str,
    resolved_model: str,
    tokens: dict[str, Any],
    timing: dict[str, int | float],
    workspace: str,
    builder_record: dict[str, Any] | None = None,
    spec_validation_record: dict[str, Any] | None = None,
    clarity_check_record: dict[str, Any] | None = None,
    reviewer_record: dict[str, Any] | None = None,
    architect_record: dict[str, Any] | None = None,
    supervisor_record: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Per-role audit block for JSONL + MCP response (D-P4-8 Stage 1)."""
    engine_ms = timing.get("engine_run_ms")
    duration_ms = int(engine_ms) if engine_ms is not None else None

    if delegate_mode == DELEGATE_MODE_REVIEW:
        roles = obs.merge_model_roles(
            obs.build_role_usage_record(
                role=ROLE_REVIEW,
                model=resolved_model,
                input_tokens=tokens.get("input"),
                output_tokens=tokens.get("output"),
                total_tokens=tokens.get("total"),
                duration_ms=duration_ms,
                source=str(tokens.get("source") or "unavailable"),
            )
        )
    elif delegate_mode == DELEGATE_MODE_IMPLEMENT:
        executor_acc = obs.get_role_tokens(delegation_id, ROLE_EXECUTOR)
        executor_inp = (executor_acc or {}).get("input") or tokens.get("input")
        executor_out = (executor_acc or {}).get("output") or tokens.get("output")
        executor_total = (executor_acc or {}).get("total") or tokens.get("total")
        executor_source = (
            "litellm_callback"
            if executor_acc
            else str(tokens.get("source") or "executor")
        )
        roles = obs.merge_model_roles(
            obs.build_role_usage_record(
                role=ROLE_EXECUTOR,
                model=resolve_role_model_name(ROLE_EXECUTOR, workspace),
                input_tokens=executor_inp,
                output_tokens=executor_out,
                total_tokens=executor_total,
                duration_ms=duration_ms,
                source=executor_source,
            ),
            builder_record,
            architect_record,
        )
    else:
        roles = None

    if spec_validation_record:
        if roles is None:
            roles = {}
        roles["spec_validation"] = spec_validation_record

    if clarity_check_record:
        if roles is None:
            roles = {}
        roles["clarity_check"] = clarity_check_record

    if reviewer_record:
        if roles is None:
            roles = {}
        roles["reviewer_pass"] = reviewer_record

    if supervisor_record:
        if roles is None:
            roles = {}
        roles["supervisor"] = supervisor_record

    roles = obs.overlay_model_roles_tokens(
        roles,
        delegation_id=delegation_id,
        executor_fallback_tokens=tokens,
    )
    return roles or None


def _response_payload(
    *,
    success: bool,
    output: str,
    files_changed: list[str],
    files_unexpected: list[str] | None = None,
    session_reused: bool,
    session_reason: str,
    session_policy: str,
    mcp_session_id: str | None = None,
    log_path: str | None = None,
    host_kind: str | None = None,
    host_session_id: str | None = None,
    executor_reused: bool = False,
    executor_recreated: bool = False,
    outcome: str | None = None,
    spec_path: str | None = None,
    spec_report_path: str | None = None,
    spec_sha256: str | None = None,
    spec_bytes: int | None = None,
    delegate_mode: str | None = None,
    spec_files_missing_from_target: list[str] | None = None,
    contract_warnings: list[str] | None = None,
    delegation_policies: dict[str, Any] | None = None,
    scope_violations: list[str] | None = None,
    reverted_paths: list[str] | None = None,
    revert_skipped: list[str] | None = None,
    usage: dict[str, Any] | None = None,
    usage_warnings: list[str] | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    context_package_summary: dict[str, Any] | None = None,
    capability_warnings: list[str] | None = None,
    preflight_token_estimate: int | None = None,
    delegation_diff: dict[str, Any] | None = None,
    judgment_checklist: dict[str, Any] | None = None,
    prior_failed_attempts: list[dict[str, Any]] | None = None,
    prior_failed_attempts_reminder: str | None = None,
    auto_merged_read_paths: list[str] | None = None,
    auto_merge_spec_read: bool | None = None,
    model_roles: dict[str, Any] | None = None,
    suggested_edit_paths: list[str] | None = None,
    context_builder_llm_enabled: bool | None = None,
    builder_brief_applied: bool | None = None,
    auto_verify_enabled_flag: bool | None = None,
    verify_result: dict[str, Any] | None = None,
    clarification_needed: list[str] | None = None,
    clarity_questions: list[str] | None = None,
    clarity_round_index: int | None = None,
    clarity_round_cap: int | None = None,
    clarity_auto_passed: bool | None = None,
    reviewer_mode: str | None = None,
    reviewer_outcome: str | None = None,
    reviewer_action: str | None = None,
    spec_validation_ran: bool | None = None,
    spec_validation_passed: bool | None = None,
    delegation_pipeline: list[dict[str, Any]] | None = None,
    executor_turns: int | None = None,
    executor_stop_reason: str | None = None,
    needs_input: dict[str, Any] | None = None,
    paused_questions: list[str] | None = None,
    auto_retried: bool = False,
    stall_type: str | None = None,
    server_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # When spec advisor has questions (advisory, execution ran), prepend them
    # to the output so the host always sees them in the text it reads.
    # Note: clarity questions are NOT prepended here — when clarity blocks,
    # output is set to just the questions before this function is called.
    advisory_parts: list[str] = []
    if clarification_needed:
        advisory_parts.append(
            "📋 **Spec advisor questions** (consider updating spec or context_summary before next delegation):\n"
            + "\n".join(f"- {q}" for q in clarification_needed)
        )
    if advisory_parts:
        output = "\n\n".join(advisory_parts) + "\n\n---\n\n" + output

    payload: dict[str, Any] = {
        "success": success,
        "output": _truncate_output(output),
        "files_changed": files_changed,
        "files_unexpected": files_unexpected if files_unexpected is not None else [],
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
    if outcome is not None:
        payload["outcome"] = outcome
    if spec_path is not None:
        payload["spec_path"] = spec_path
    if spec_report_path is not None:
        payload["spec_report_path"] = spec_report_path
    if spec_sha256 is not None:
        payload["spec_sha256"] = spec_sha256
    if spec_bytes is not None:
        payload["spec_bytes"] = spec_bytes
    if delegate_mode is not None:
        payload["delegate_mode"] = delegate_mode
    if spec_files_missing_from_target:
        payload["spec_files_missing_from_target"] = spec_files_missing_from_target
    if contract_warnings:
        payload["contract_warnings"] = contract_warnings
    if delegation_policies is not None:
        payload["delegation_policies"] = delegation_policies
    if scope_violations:
        payload["scope_violations"] = scope_violations
    if reverted_paths:
        payload["reverted_paths"] = reverted_paths
    if revert_skipped:
        payload["revert_skipped"] = revert_skipped
    if usage is not None:
        payload["usage"] = usage
    if usage_warnings:
        payload["usage_warnings"] = usage_warnings
    if error_class is not None:
        payload["error_class"] = error_class
    if error_message is not None:
        payload["error_message"] = error_message
    if context_package_summary is not None:
        payload["context_package_summary"] = context_package_summary
    if capability_warnings:
        payload["capability_warnings"] = capability_warnings
    if preflight_token_estimate is not None:
        payload["preflight_token_estimate"] = preflight_token_estimate
    if delegation_diff is not None:
        payload["delegation_diff"] = delegation_diff
    if judgment_checklist is not None:
        payload["judgment_checklist"] = judgment_checklist
    if prior_failed_attempts:
        payload["prior_failed_attempts"] = prior_failed_attempts
    if prior_failed_attempts_reminder is not None:
        payload["prior_failed_attempts_reminder"] = prior_failed_attempts_reminder
    if auto_merged_read_paths:
        payload["auto_merged_read_paths"] = auto_merged_read_paths
    if auto_merge_spec_read is not None:
        payload["auto_merge_spec_read"] = auto_merge_spec_read
    if model_roles:
        payload["model_roles"] = model_roles
    if suggested_edit_paths:
        payload["suggested_edit_paths"] = suggested_edit_paths
    if context_builder_llm_enabled is not None:
        payload["context_builder_llm_enabled"] = context_builder_llm_enabled
    if builder_brief_applied is not None:
        payload["builder_brief_applied"] = builder_brief_applied
    if auto_verify_enabled_flag:
        payload["auto_verify_enabled"] = True
        if verify_result is not None:
            payload["verify_result"] = verify_result
    if clarification_needed:
        payload["clarification_needed"] = clarification_needed
    if clarity_questions:
        payload["clarity_questions"] = clarity_questions
    if clarity_round_index is not None:
        payload["clarity_round_index"] = clarity_round_index
    if clarity_round_cap is not None:
        payload["clarity_round_cap"] = clarity_round_cap
    if clarity_auto_passed is not None:
        payload["clarity_auto_passed"] = clarity_auto_passed
    if reviewer_mode is not None:
        payload["reviewer_mode"] = reviewer_mode
    if reviewer_outcome is not None:
        payload["reviewer_outcome"] = reviewer_outcome
    if reviewer_action is not None:
        payload["reviewer_action"] = reviewer_action
    if spec_validation_ran is not None:
        payload["spec_validation_ran"] = spec_validation_ran
    if spec_validation_passed is not None:
        payload["spec_validation_passed"] = spec_validation_passed
    if delegation_pipeline is not None:
        payload["delegation_pipeline"] = delegation_pipeline
    if executor_turns is not None:
        payload["executor_turns"] = executor_turns
    if executor_stop_reason is not None:
        payload["executor_stop_reason"] = executor_stop_reason
    if needs_input is not None:
        payload["needs_input"] = needs_input
        payload["status"] = needs_input.get("status")
    if paused_questions is not None:
        payload["paused_questions"] = paused_questions
    if auto_retried:
        payload["auto_retried"] = True
    if stall_type:
        payload["stall_type"] = stall_type
    if server_status is not None:
        payload["server_status"] = server_status
    return payload


def _safe_parse_lstart(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None


def _build_server_status(workspace: str | Path) -> dict[str, Any]:
    """Best-effort runtime freshness snapshot for host visibility."""
    from core.version import repo_root, source_revision

    ws = str(workspace)
    root = repo_root()
    pid = os.getpid()
    started_at: str | None = None
    latest_dirty_change_at: str | None = None
    dirty_count = 0
    stale_vs_local_changes: bool | None = None
    started: datetime | None = None

    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        started = _safe_parse_lstart(proc.stdout)
        if started is not None:
            started_at = started.isoformat(timespec="seconds")
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        gs = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if gs.returncode == 0:
            paths: list[Path] = []
            for line in gs.stdout.splitlines():
                if len(line) < 4:
                    continue
                rel = line[3:].strip()
                if not rel:
                    continue
                path = root / rel
                if path.is_file():
                    paths.append(path)
            dirty_count = len(paths)
            if paths:
                latest_ts = max(p.stat().st_mtime for p in paths)
                latest_dt = datetime.fromtimestamp(latest_ts)
                latest_dirty_change_at = latest_dt.isoformat(timespec="seconds")
                if started is not None:
                    stale_vs_local_changes = started < latest_dt
            elif started is not None:
                stale_vs_local_changes = False
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass

    try:
        stale_pids = stale_mcp_pids(ws, main_script=str(root / "main.py"))
    except Exception:
        stale_pids = []

    return {
        "pid": pid,
        "workspace_path": ws,
        "source_root": str(root),
        "source_revision": source_revision(),
        "started_at": started_at,
        "dirty_files_count": dirty_count,
        "latest_dirty_change_at": latest_dirty_change_at,
        "stale_vs_local_changes": stale_vs_local_changes,
        "stale_sibling_pids": stale_pids,
    }


def _find_delegation_record_for_resume(
    workspace: str, delegation_id: str | None
) -> dict[str, Any] | None:
    if not delegation_id:
        return None
    try:
        records = load_delegations_for_workspace(workspace)
    except Exception:
        return None
    for record in records:
        if str(record.get("delegation_id") or "") == delegation_id:
            return record
    return None


def _abandon_paused_state(state: SupervisorState) -> None:
    """Delete paused state file and emit abandonment trace event."""
    path = SupervisorState.state_dir(state.project_key) / f"{state.resume_token}.json"
    try:
        ws = obs.default_workspace_path()
        record = _find_delegation_record_for_resume(ws, state.context_ref)
        session_dir_raw = (record or {}).get("session_dir")
        if session_dir_raw:
            append_trace_record(
                {
                    "type": "supervisor_state_abandoned",
                    "timestamp": obs.utc_now_iso(),
                    "resume_token": state.resume_token,
                    "project_key": state.project_key,
                    "pause_reason": state.pause_reason,
                },
                delegation_id=str(state.context_ref or "abandon"),
                session_dir=Path(str(session_dir_raw)),
                workspace=ws,
            )
    except Exception:
        pass
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _response_payload_paused_reminder(state: SupervisorState) -> str:
    """Return needs_input reminder when a paused delegation awaits answer."""
    questions = list(state.questions or [])
    msg = questions[0] if questions else "Supervisor is paused and awaiting your answer."
    payload = _response_payload(
        success=False,
        output=msg,
        files_changed=[],
        session_reused=False,
        session_reason="paused_reminder",
        session_policy="resume",
        outcome=OUTCOME_NEEDS_INPUT,
        error_class="paused_awaiting_answer",
        error_message=msg,
        needs_input=build_needs_input_payload(
            {
                "outcome": OUTCOME_NEEDS_INPUT_CLARIFICATION,
                "supervisor_reason": msg,
                "message": msg,
                "files_requested": [],
                "executor_output_tail": "",
            }
        ),
        paused_questions=questions,
    )
    return json.dumps(payload, ensure_ascii=False)


def _get_or_create_supervisor(
    project_key: str,
    workspace_path: str,
    spec_path: str | None,
) -> "SupervisorAgent":
    """Return the existing SupervisorAgent for this project_key, or create a fresh one.

    Creation loads project_state from disk (first call or after server restart).
    P13-007: on a cache miss, also rehydrate the agent's steady-state identity +
    lifecycle context from `agent_state.json` (the AgentCheckpoint) so the
    freshly-created agent is the same agent that ran before the restart —
    CLI and server mode become behaviorally identical. The in-memory registry
    is a cache; the on-disk checkpoint is the source of truth.
    The returned agent has NOT had begin_delegation() called yet — caller must do that.
    """
    from core.engine.supervisor_agent import SupervisorAgent

    agent = _SUPERVISOR_REGISTRY.get(project_key)
    if agent is None:
        agent = SupervisorAgent(
            delegation_id=None,  # will be set by begin_delegation()
            workspace_path=workspace_path,
            executor_fn=lambda _t, _c, _reset=False: None,  # placeholder; overwritten by begin_delegation
            spec_path=spec_path,
        )
        # P13-007: rehydrate steady-state identity + lifecycle context from disk
        try:
            from core.state.agent_checkpoint import AgentCheckpoint

            checkpoint = AgentCheckpoint.find_for_project(project_key)
            if checkpoint is not None:
                agent.rehydrate_from(checkpoint)
        except Exception:
            # Best-effort: never block delegation on checkpoint rehydrate failure.
            pass
        _SUPERVISOR_REGISTRY[project_key] = agent
    return agent


def _handle_resume(
    state: SupervisorState,
    answer: str,
    task: str,
    ctx: Context | None,
    mcp_session_id: str | None = None,
) -> str:
    from core.engine.supervisor_agent import SupervisorAgent

    progress = _DelegationProgressBridge(ctx)
    try:
        ws = obs.default_workspace_path()
        record = _find_delegation_record_for_resume(ws, state.context_ref)
        mcp_request = (record or {}).get("mcp_request") or {}
        backend = str((record or {}).get("backend") or "aider")
        target_files = (
            list(mcp_request.get("effective_target_files") or [])
            or list(mcp_request.get("target_files") or [])
        )
        context_block = (record or {}).get("context") or {}
        base_prompt = str(context_block.get("prompt_full") or task or "").strip()
        if not base_prompt:
            base_prompt = task
        model_hint = str((record or {}).get("model") or "")

        engine = get_engine(backend)
        event_sink = None
        session_dir_raw = (record or {}).get("session_dir")
        if session_dir_raw:
            session_dir = Path(str(session_dir_raw))

            def _resume_event_sink(rec: dict[str, Any]) -> None:
                append_trace_record(
                    rec,
                    delegation_id=str(state.context_ref or rec.get("delegation_id") or "resume"),
                    session_dir=session_dir,
                    workspace=ws,
                )

            event_sink = _resume_event_sink

        def _executor_fn(
            _turn_index: int,
            correction_note: str | None,
            reset_session: bool = False,
        ) -> ExecutionResult:
            if reset_session and mcp_session_id:
                from core.session.executor_cache import drop_coder

                drop_coder(mcp_session_id)
            prompt = base_prompt
            if correction_note:
                prompt = f"{prompt}\n\n{correction_note}"
            with role_context(ROLE_EXECUTOR):
                return engine.run(
                    prompt,
                    target_files,
                    workspace_path=ws,
                    mcp_session_id=mcp_session_id,
                )

        progress.notify("[resume] Continuing delegation from paused turn…", force=True)
        agent = SupervisorAgent.resume(
            state,
            answer,
            workspace_path=ws,
            executor_fn=_executor_fn,
            reviewer_fn=None,
            event_sink=event_sink,
        )
        from core.state.project_key import ProjectKeyResolver

        _pk = ProjectKeyResolver.from_spec_path(state.spec_path)
        _SUPERVISOR_REGISTRY[_pk] = agent
        try:
            result = agent.run()
        except Exception:
            if hasattr(agent, "emit_lifecycle_phase_end"):
                agent.emit_lifecycle_phase_end("loop", status="error")
            if hasattr(agent, "emit_lifecycle_end"):
                agent.emit_lifecycle_end("error")
            raise
        exec_result = result.executor_result or ExecutionResult(success=False, output="")

        # P13-005: close lifecycle for resumed delegation (loop phase started in resume())
        # Guard with hasattr for test mocks / future subclasses that may not implement lifecycle.
        needs_input_payload = None
        payload_outcome = OUTCOME_SUCCESS if result.outcome == "success" else "error"
        payload_success = result.outcome == "success" and exec_result.success
        payload_error_class = exec_result.error_class if not payload_success else None
        payload_error_message = exec_result.error if not payload_success else None
        paused_questions_out: list[str] | None = None

        if result.outcome == "escalated":
            payload_outcome = OUTCOME_NEEDS_INPUT
            payload_success = False
            paused_questions_out = list(result.paused_questions or [])
            needs_input_payload = build_needs_input_payload(
                {
                    "outcome": OUTCOME_NEEDS_INPUT_CLARIFICATION,
                    "supervisor_reason": (
                        paused_questions_out[0]
                        if paused_questions_out
                        else "Supervisor requires host clarification."
                    ),
                    "message": (
                        paused_questions_out[0]
                        if paused_questions_out
                        else "Supervisor requires host clarification."
                    ),
                    "files_requested": [],
                    "executor_output_tail": (exec_result.output or "")[-500:],
                }
            )
            payload_error_class = "needs_input"
            payload_error_message = (
                paused_questions_out[0]
                if paused_questions_out
                else "Supervisor requires host clarification."
            )
        elif payload_error_class == "unknown" and not payload_error_message:
            payload_error_message = (
                "supervisor_loop_unknown"
                if str(result.end_reason or "") == "unknown"
                else "executor_unknown_failure"
            )

        if hasattr(agent, "emit_lifecycle_phase_end"):
            _resume_loop_status = (
                "escalated" if result.outcome == "escalated"
                else ("error" if result.outcome == "error" else "ok")
            )
            agent.emit_lifecycle_phase_end("loop", status=_resume_loop_status)
        if hasattr(agent, "emit_lifecycle_end"):
            agent.emit_lifecycle_end(payload_outcome)

        payload = _response_payload(
            success=payload_success,
            output=exec_result.output or "",
            files_changed=list(exec_result.files_changed or []),
            files_unexpected=list(exec_result.files_unexpected or []),
            session_reused=False,
            session_reason="resumed",
            session_policy="resume",
            outcome=payload_outcome,
            error_class=payload_error_class,
            error_message=payload_error_message,
            needs_input=needs_input_payload,
            paused_questions=paused_questions_out,
            model_roles=(
                {"executor": {"model": model_hint}}
                if model_hint and payload_outcome != "error"
                else None
            ),
        )
        progress.notify("[done] Resume delegation complete.", force=True)
        return json.dumps(payload, ensure_ascii=False)
    finally:
        progress.close()


@mcp.tool(
    name="delegate_to_agent",
    description=(
        "IMPLEMENTATION DELEGATE: Run Aider to edit files on disk. Use this instead of "
        "writing code yourself when the user asks to build, create, or change project files "
        "(web pages, scripts, multi-file features). Required: task, target_files (repo-relative), "
        "context_summary (decisions from chat—the delegate cannot see history). "
        "Optional spec_path: step task under .mcp-coder/specs/tasks/ (e.g. tasks/my-epic-02-cli.md). "
        "mode: implement (default) edits target_files; review asks questions only (target_files must be []). "
        "Optional model_policy: per-delegation role overrides (executor, reviewer, supervisor, architect). "
        "Optional answer: continue a paused delegation by answering pending supervisor question(s). "
        "Optional start_fresh=true: abandon paused state (if any) and run a fresh delegation. "
        "MCP appends audit to specs/reports/<same-name>.md. Returns success, output, files_changed, outcome; "
        "implement mode may include delegation_diff and judgment_checklist for post-delegate verification. "
        "Default backend: aider."
    ),
)
def delegate_to_agent(
    task: str,
    target_files: list[str],
    context_summary: str,
    backend: str = "aider",
    spec_path: str | None = None,
    mode: str = "implement",
    cli_artifacts: bool = False,
    model_policy: dict | None = None,
    answer: str | None = None,
    start_fresh: bool = False,
    ctx: Context | None = None,
) -> str:
    """Run one delegated implementation via the selected backend; append JSONL log."""
    progress = _DelegationProgressBridge(ctx)
    delegation_id = obs.new_delegation_id()
    _delegation_scope = delegation_context(delegation_id)
    _delegation_scope.__enter__()
    host_policy_token = None
    host_policy_overrides: dict[str, dict] = {}
    model_policy_warnings: list[str] = []
    t0 = time.perf_counter()
    timestamp_start = obs.utc_now_iso()
    mcp_request: dict[str, Any] = {
        "task": task,
        "target_files": target_files,
        "context_summary": context_summary,
        "backend": backend,
    }
    ws = obs.default_workspace_path()
    storage = None
    delegate_mode = DELEGATE_MODE_IMPLEMENT
    spec_rel_path: str | None = None
    model: str | None = None
    _obs_verbosity = resolve_observability_verbosity(ws)
    _delegation_record_appended = False
    _interrupted_record_armed = False
    supervisor_agent: Any | None = None
    _lifecycle_closed = False
    try:
        host_policy_overrides, model_policy_warnings = normalize_host_model_policy(model_policy)
        host_policy_token = host_model_policy_var.set(
            host_policy_overrides if host_policy_overrides else None
        )
        if host_policy_overrides:
            mcp_request["model_policy_applied"] = summarize_model_policy_applied(
                host_policy_overrides
            )
        if model_policy_warnings:
            mcp_request["model_policy_warnings"] = model_policy_warnings
        if spec_path is not None:
            mcp_request["spec_path"] = spec_path
        try:
            delegate_mode = normalize_delegate_mode(mode)
        except ValueError as exc:
            delegate_mode = "implement"
            return json.dumps(
                _response_payload(
                    success=False,
                    output=str(exc),
                    files_changed=[],
                    session_reused=False,
                    session_reason="invalid_mode",
                    session_policy="n/a",
                    delegate_mode=mode,
                ),
                ensure_ascii=False,
            )
        mcp_request["mode"] = delegate_mode
        from core.state.project_key import ProjectKeyResolver

        _project_key = ProjectKeyResolver.from_spec_path(spec_path)
        usage_report_enabled = obs.resolve_usage_report_enabled(ws)
        ensure_workspace_spec_layout(ws)
        progress.notify("[compile] Starting context compilation…", force=True)

        spec_abs_path = None
        spec_read = None
        spec_invalid_reason: str | None = None
        spec_read_duration_ms = 0
        t_spec_read = time.perf_counter()
        if spec_path:
            try:
                spec_rel_path = normalize_spec_path_arg(spec_path)
                spec_abs_path = resolve_spec_path(ws, spec_rel_path)
            except ValueError as exc:
                spec_invalid_reason = str(exc)
            else:
                if not spec_abs_path.is_file():
                    spec_invalid_reason = (
                        f"Step task spec not found: {spec_rel_path}. "
                        f"Copy .mcp-coder/spec-template.md to {spec_rel_path} "
                        "(one file per step; link epic: in front matter). "
                        "For multi-step work, also create .mcp-coder/specs/epics/<slug>.md "
                        "from spec-epic-template.md."
                    )
                else:
                    spec_read = read_task_spec(spec_abs_path, workspace=ws)
        delegation_policies: DelegationPolicies | None = None
        if spec_read is not None and not spec_invalid_reason:
            try:
                delegation_policies = load_delegation_policies(
                    spec_read.front_matter,
                    spec_read.sections.get("Files", ""),
                )
            except PolicyValidationError as exc:
                spec_invalid_reason = str(exc)
        spec_read_duration_ms = int((time.perf_counter() - t_spec_read) * 1000)

        pipeline_recorder: Any | None = None
        if delegate_mode == DELEGATE_MODE_IMPLEMENT:
            pipeline_recorder = obs.new_pipeline_recorder()
            if spec_read is not None and not spec_invalid_reason:
                pipeline_recorder.mark("spec_read", status="ok", duration_ms=spec_read_duration_ms)
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

        _paused_state = SupervisorState.find_latest(_project_key)
        if start_fresh and _paused_state is not None:
            _abandon_paused_state(_paused_state)
            _paused_state = None
        # P13-016 (ISS-014, revised): when the last delegation paused for any
        # reason, the host coming back is a resume — not a fresh start. Two
        # pause shapes are handled:
        #
        # - Escalation pause (``needs_input`` / ``max_turns_reached``): the
        #   supervisor asked a question mid-loop. Resume = continue the executor
        #   loop with the host's answer. Routed through ``_handle_resume``.
        #   The host may pass the answer via ``answer`` or via context; either
        #   way the next delegation resumes. Without any new signal at all, we
        #   still resume (the host returning IS the signal) — but if ``answer``
        #   is empty we fall back to the paused reminder so the host sees the
        #   pending question rather than silently re-running.
        # - Clarity-block pause (``clarity_check``): a soft preloop handoff.
        #   Resume = re-enter the preloop pipeline (re-run clarity, round-cap
        #   auto-pass still applies). The host may have answered via edited spec
        #   Q&A, ``answer``, or ``context_summary``. We abandon the stale pause
        #   (so a new one can be recorded if this round also blocks) but carry a
        #   ``_resumed_from_pause`` flag so the fresh delegation emits resume
        #   lineage markers (``lifecycle_start(resumed=true)`` +
        #   ``supervisor_resumed``) — the host returning is resume continuity,
        #   not a fresh start.
        _paused_is_clarity_block = bool(
            _paused_state is not None
            and str(getattr(_paused_state, "pause_reason", "") or "") == "clarity_check"
        )
        _resumed_from_pause_token: str | None = None
        if _paused_state is not None and _paused_is_clarity_block:
            # Clarity-block pause: re-run the preloop pipeline as a resume.
            _resumed_from_pause_token = _paused_state.resume_token
            _abandon_paused_state(_paused_state)
            _paused_state = None
        elif _paused_state is not None and answer is not None:
            return _handle_resume(
                state=_paused_state,
                answer=answer,
                task=task,
                ctx=ctx,
                mcp_session_id=storage.mcp_session_id,
            )
        elif _paused_state is not None and answer is None:
            # Escalation pause without a host answer: surface the pending
            # question rather than silently re-running.
            return _response_payload_paused_reminder(_paused_state)

        _interrupted_record_armed = True
        bind_delegation_trace_scope(
            workspace=ws,
            session_dir=storage.session_dir,
            mcp_session_id=storage.mcp_session_id,
        )
        _compile_verbosity = resolve_observability_verbosity(ws)

        obs.emit(
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

        obs.log_host_resolved(
            hint_host_kind=host_hint.host_kind,
            host_session_id=host_hint.host_session_id,
            transcript_path=host_hint.host_transcript_path,
            resolve_error=host_hint.resolve_error,
            host_resolve_ms=host_resolve_ms,
        )
        if host_hint.resolve_error:
            obs.emit(
                "host_resolve_failed",
                level="warn",
                workspace_path=ws,
                resolve_error=host_hint.resolve_error,
            )

        obs.log_delegation_received(
            delegation_id=delegation_id,
            target_files=target_files,
            backend=backend,
            task_preview=task,
        )
        # P13-006: create the SupervisorAgent early so it OWNS the lifecycle envelope
        # from the very first event. Phase events are emitted by the agent as it
        # transitions, not retroactively by the server after each phase completes.
        from core.engine.supervisor_agent import (
            SupervisorAgent,
            resolve_supervisor_max_turns,
        )

        supervisor_agent = None
        supervisor_agent_result = None
        _supervisor_max_turns = resolve_supervisor_max_turns(ws)

        def _supervisor_event_sink(rec: dict[str, Any]) -> None:
            append_trace_record(
                rec,
                delegation_id=delegation_id,
                session_dir=storage.session_dir,
                workspace=ws,
            )

        # P13-006: agent owns lifecycle — create early, set context, emit start + preloop
        if delegate_mode == DELEGATE_MODE_IMPLEMENT:
            supervisor_agent = _get_or_create_supervisor(
                _project_key, ws, None  # spec_rel_path not yet known; set later
            )
            supervisor_agent.begin_delegation(
                delegation_id=delegation_id,
                executor_fn=lambda _turn, _correction, _reset=False: ExecutionResult(
                    success=False,
                    output="",
                ),
                max_turns=_supervisor_max_turns,
                event_sink=_supervisor_event_sink,
                spec_path=spec_rel_path,
            )
            supervisor_agent.set_lifecycle_event_sink(_supervisor_event_sink)
            supervisor_agent.set_lifecycle_context(
                project_key=_project_key,
                session_policy=storage.session_policy,
                session_action=storage.session_action,
                mcp_session_id=storage.mcp_session_id,
            )
            supervisor_agent.set_delegation_id(delegation_id)
            # P13-016 (revised): if this delegation is resuming from a prior
            # clarity-block pause, emit resume lineage markers so the trace
            # shows pause→resume continuity (the host returning is a resume,
            # not a fresh start). The preloop pipeline still runs normally
            # (clarity re-runs, round-cap auto-pass applies); only the lineage
            # labeling changes.
            if _resumed_from_pause_token is not None:
                supervisor_agent.emit_lifecycle_start(resumed=True)
                supervisor_agent._emit(
                    {
                        "type": "supervisor_resumed",
                        "resume_token": _resumed_from_pause_token,
                        "resumed_at_turn": 0,
                        "project_key": _project_key,
                        "host_answer_chars": len(answer or ""),
                        "resume_reason": "clarity_block_reentry",
                    }
                )
                supervisor_agent.emit_lifecycle_phase_start("preloop", resumed=True)
            else:
                supervisor_agent.emit_lifecycle_start(resumed=False)
                supervisor_agent.emit_lifecycle_phase_start("preloop", resumed=False)
        # P13-008: tracks whether an early-close preloop gate (clarity_check /
        # invalid_spec / review_target_files_error) has already emitted
        # ``delegation_lifecycle_end`` for this delegation. When True, the
        # postloop closure block (loop phase_end + postloop phase_start/end +
        # a second lifecycle_end) must be skipped — the envelope is closed.
        # The agent-side emit_lifecycle_end is also idempotent (P13-008), so
        # this flag is the source fix and the agent guard is the backstop.
        _lifecycle_closed = False

        def _close_lifecycle_once(
            lifecycle_outcome: str,
            *,
            phase: str | None = None,
            phase_status: str = "ok",
            detail: str | None = None,
        ) -> None:
            """Close the implement lifecycle envelope exactly once."""
            nonlocal _lifecycle_closed
            if (
                delegate_mode != DELEGATE_MODE_IMPLEMENT
                or supervisor_agent is None
                or _lifecycle_closed
            ):
                return
            if bool(getattr(supervisor_agent, "_lifecycle_closed", False)):
                _lifecycle_closed = True
                return

            if phase is not None and hasattr(supervisor_agent, "emit_lifecycle_phase_end"):
                supervisor_agent.emit_lifecycle_phase_end(
                    phase,
                    status=phase_status,
                    detail=detail,
                )
            elif hasattr(supervisor_agent, "emit_lifecycle_phase_end"):
                phases = getattr(supervisor_agent, "_lifecycle_phases", {}) or {}
                in_progress = [
                    name for name, status in phases.items() if status == "in_progress"
                ]
                if in_progress:
                    supervisor_agent.emit_lifecycle_phase_end(
                        in_progress[-1],
                        status=phase_status,
                        detail=detail,
                    )

            if hasattr(supervisor_agent, "emit_lifecycle_end"):
                supervisor_agent.emit_lifecycle_end(lifecycle_outcome)
            _lifecycle_closed = True
        # P13-008: tracks whether the delegation record was appended to
        # delegations.jsonl on the normal completion path. If an exception or
        # host cancellation propagates before line ~3587, the finally block
        # builds + appends a minimal "interrupted" record so the delegations
        # log and the trace tree stay 1:1 (ISS-009).
        result: ExecutionResult | None = None
        success = False
        error: str | None = None
        error_class: str | None = None
        error_message: str | None = None
        files_changed: list[str] = []
        files_unexpected: list[str] = []
        output = ""
        tokens: dict[str, Any] = {"source": "unavailable"}
        executor_reused = False
        executor_recreated = False
        workspace_snapshot: dict[str, Any] | None = None
        _executor_turns: int = 0
        timing: dict[str, int] = {
            "context_load_ms": context_load_ms,
            "session_decision_ms": session_decision_ms + host_resolve_ms,
            "engine_run_ms": 0,
            "post_process_ms": 0,
        }

        spec_block = spec_read.prompt_block if spec_read else None
        prompt = assemble_prompt(
            context_summary,
            task,
            host_transcript=host_transcript_text,
            spec_block=spec_block,
        )
        transcript_meta = transcript_log_context(
            policy=host_transcript_policy,
            load_result=transcript_result,
            file_bytes=file_bytes if isinstance(file_bytes, int) else None,
            context_mode=context_mode,
        )

        # Context package flag — active for implement + valid spec + env default on
        _use_pkg = (
            delegate_mode == DELEGATE_MODE_IMPLEMENT
            and spec_read is not None
            and not spec_invalid_reason
            and use_context_package()
        )
        context_package: ContextPackage | None = None
        context_package_hash: str | None = None
        executor_prompt = prompt  # overridden if context package path is taken

        planner_target_files = list(target_files)
        effective_target_files = planner_target_files
        auto_merged_read_paths: list[str] = []
        auto_merge_spec_read: bool | None = None
        spec_files_missing: list[str] = []
        contract_warnings: list[str] = []
        if (
            delegate_mode == DELEGATE_MODE_IMPLEMENT
            and delegation_policies is not None
            and not spec_invalid_reason
        ):
            merge_enabled = bool(spec_path) and auto_merge_spec_read_enabled(ws)
            if spec_path:
                auto_merge_spec_read = merge_enabled
            if delegation_policies.all_paths:
                merge_result, spec_files_missing, contract_warnings = resolve_spec_read_deps(
                    files_edit=delegation_policies.files_edit,
                    files_read=delegation_policies.files_read,
                    all_paths=delegation_policies.all_paths,
                    target_files=planner_target_files,
                    auto_merge_enabled=merge_enabled,
                )
                effective_target_files = merge_result.effective_target_files
                auto_merged_read_paths = merge_result.auto_merged_read_paths
                if contract_warnings:
                    obs.emit(
                        "spec_files_contract_warn",
                        level="warn",
                        delegation_id=delegation_id,
                        spec_path=spec_rel_path,
                        spec_files_missing_from_target=spec_files_missing,
                        contract_warnings=contract_warnings,
                    )

        review_target_files_error: str | None = None
        if delegate_mode == DELEGATE_MODE_REVIEW and target_files:
            review_target_files_error = (
                "mode=review requires target_files=[] (no file edits). "
                "Use mode=implement to change files, or mode=review with an empty target_files list."
            )

        caps = None
        cap_warnings: list[str] = []
        picker_result: CandidateFilesResult | None = None
        architect_enabled = False
        architect_reason: str | None = None
        architect_plan_applied = False
        architect_pass_error: str | None = None
        architect_record: dict[str, Any] | None = None
        planner_pass_audit: dict[str, Any] | None = None
        architect_plan: str | None = None
        builder_llm_enabled = False
        builder_brief_applied = False
        builder_llm_error: str | None = None
        builder_record: dict[str, Any] | None = None
        spec_validation_blocked = False
        clarification_needed: list[str] | None = None
        spec_validation_ran: bool | None = None
        spec_validation_passed: bool | None = None
        spec_validation_audit: dict[str, Any] | None = None
        spec_validation_record: dict[str, Any] | None = None
        spec_validation_provenance: dict[str, Any] = {}
        clarity_check_blocked = False
        clarity_check_questions: list[str] | None = None
        clarity_check_ran: bool | None = None
        clarity_check_passed: bool | None = None
        clarity_check_audit: dict[str, Any] | None = None
        clarity_check_record: dict[str, Any] | None = None
        clarity_check_error: str | None = None
        clarity_round_index: int | None = None
        clarity_round_cap: int | None = None
        clarity_auto_passed: bool | None = None
        clarity_followup_lineage: dict[str, Any] | None = None
        reviewer_pass_ran = False
        reviewer_pass_outcome: str | None = None
        reviewer_pass_note: str | None = None
        reviewer_pass_error: str | None = None
        reviewer_pass_audit: dict[str, Any] | None = None
        reviewer_pass_record: dict[str, Any] | None = None
        reviewer_policy_fields: dict[str, str] = {}
        builder_provenance: dict[str, Any] = {}
        architect_provenance: dict[str, Any] = {}
        builder_history_rag_on = False
        workspace_file_hints_on = False
        rag_retrieval_on = False
        rag_retrieval_refs: list[ContextRef] = []
        workspace_file_rag_refs: list[ContextRef] = []
        delegation_rag_refs: list[ContextRef] = []
        stall_auto_retried = False
        stall_type: str | None = None
        stall_files_requested: list[str] = []
        needs_input_payload: dict[str, Any] | None = None
        supervisor_paused_questions: list[str] | None = None
        # P12-001: unified supervisor agent loop owns all post-planning control flow
        # (replaces the former supervisor_outer_loop_* events). The agent emits the
        # canonical supervisor_loop_* / supervisor_turn_* / supervisor_decision events.
        # P13-006: agent was created early (before preloop) and already owns the
        # lifecycle envelope. The block below only remains for variable initialization
        # that other code references; agent/sink/max_turns are already set above.

        if (
            pipeline_recorder is not None
            and not review_target_files_error
            and spec_validation_enabled(ws)
            and spec_read is not None  # spec_validation requires a loaded spec
        ):
            pipeline_recorder.start("spec_validation")
            (
                spec_validation_blocked,
                clarification_needed,
                spec_validation_ran,
                spec_validation_passed,
                _spec_val_err,
                spec_validation_audit,
                spec_validation_record,
                spec_validation_provenance,
            ) = _apply_spec_validation(
                spec_read=spec_read,
                workspace=ws,
                task=task,
                context_summary=context_summary,
                host_transcript=host_transcript_text or "",
                timing=timing,
                delegation_id=delegation_id,
            )
            _emit_compile_provenance_pair(
                delegation_id=delegation_id,
                workspace=ws,
                session_dir=storage.session_dir,
                obs_verbosity=_compile_verbosity,
                input_stage=STAGE_VALIDATION_INPUT,
                output_stage=STAGE_VALIDATION_OUTPUT,
                provenance=spec_validation_provenance,
                source_path=host_hint.host_transcript_path,
                last_source_line=(
                    transcript_result.lines_parsed
                    if transcript_result.lines_parsed > 0
                    else None
                ),
                byte_start=transcript_result.source_byte_start,
                byte_end=transcript_result.source_byte_end,
            )
            if spec_validation_blocked:
                pipeline_recorder.end("spec_validation", status="blocked")
            elif _spec_val_err:
                pipeline_recorder.end(
                    "spec_validation", status="error", detail=_spec_val_err[:200]
                )
            else:
                pipeline_recorder.end("spec_validation", status="ok")
        elif pipeline_recorder is not None and not review_target_files_error:
            pipeline_recorder.mark(
                "spec_validation",
                status="skipped",
                detail="disabled",
            )
            _emit_compile_skip(
                delegation_id=delegation_id,
                stage=STAGE_VALIDATION_INPUT,
                workspace=ws,
                session_dir=storage.session_dir,
                obs_verbosity=_compile_verbosity,
                reason="disabled",
            )

        clarity_pass_on = clarity_pass_enabled(ws)
        reviewer_pass_on = reviewer_pass_enabled(ws)
        if (
            pipeline_recorder is not None
            and not review_target_files_error
            and clarity_pass_on
        ):
            from core.context.builder_history import gather_builder_history

            _history = gather_builder_history(Path(ws), spec_path=spec_rel_path)
            _titles = [r.get("task", "")[:80] for r in _history.same_spec[:3]]
            if not _titles:
                _titles = [r.get("task", "")[:80] for r in _history.project_recent[:3]]

            _prior_blocked = _count_clarity_blocked_rounds(
                storage.session_dir, spec_rel_path
            )
            _prior_clarity_lineage_count = _prior_blocked or (
                _count_workspace_clarity_blocked_delegations(ws, spec_rel_path)
            )
            if _prior_clarity_lineage_count > 0 and start_fresh:
                clarity_followup_lineage = {
                    "mode": "fresh_by_override",
                    "reason": "start_fresh_true",
                    "prior_clarity_blocked_count": _prior_clarity_lineage_count,
                    "resumed": False,
                }
                mcp_request["clarity_followup_lineage"] = clarity_followup_lineage

            pipeline_recorder.start("clarity_check")
            (
                clarity_check_blocked,
                clarity_check_questions,
                clarity_check_ran,
                clarity_check_passed,
                clarity_check_error,
                clarity_check_audit,
                clarity_check_record,
                _clarity_provenance,
            ) = _apply_clarity_check(
                spec_read=spec_read,
                workspace=ws,
                task=task,
                context_summary=context_summary,
                prior_blocked_count=_prior_blocked,
                recent_delegation_titles=_titles,
                timing=timing,
                delegation_id=delegation_id,
            )
            if clarity_check_audit is not None:
                # Stable telemetry keys used by trace + delegation visibility.
                clarity_round_index = int(clarity_check_audit.get("round_index") or 0) or None
                clarity_round_cap = int(clarity_check_audit.get("round_cap") or 0) or None
                _auto_passed = clarity_check_audit.get("auto_passed")
                clarity_auto_passed = bool(_auto_passed) if _auto_passed is not None else None
            if clarity_check_blocked:
                pipeline_recorder.end("clarity_check", status="blocked")
            elif clarity_check_error:
                pipeline_recorder.end(
                    "clarity_check", status="error", detail=clarity_check_error[:200]
                )
            else:
                pipeline_recorder.end("clarity_check", status="ok")
            # Emit structured clarity result as a trace event (P11-ISS-010)
            append_trace_record(
                {
                    "type": "clarity_result",
                    "delegation_id": delegation_id,
                    "has_questions": bool(clarity_check_questions),
                    "ran": clarity_check_ran,
                    "passed": clarity_check_passed,
                    "questions": clarity_check_questions or [],
                    "questions_count": len(clarity_check_questions or []),
                    "clarity_round_index": clarity_round_index,
                    "clarity_round_cap": clarity_round_cap,
                    "clarity_auto_passed": clarity_auto_passed,
                    "clarity_followup_lineage": clarity_followup_lineage,
                    "error": clarity_check_error,
                    "timestamp": obs.utc_now_iso(),
                },
                delegation_id=delegation_id,
                session_dir=storage.session_dir,
                workspace=ws,
            )
        elif pipeline_recorder is not None and not review_target_files_error:
            pipeline_recorder.mark("clarity_check", status="skipped", detail="disabled")

        validation_status = "skipped"
        if spec_validation_blocked:
            validation_status = "blocked (needs input)"
        elif spec_validation_ran is True:
            validation_status = "passed" if spec_validation_passed else "failed"
        progress.notify(f"[validation] Spec validation {validation_status}.", force=True)

        # P15-003: _proceed_to_executor flag controls whether the delegation
        # proceeds past the preloop gates. Set True when clarity resolves or
        # when no gate is blocking.
        _proceed_to_executor = False

        if spec_invalid_reason:
            success = False
            error = spec_invalid_reason
            output = spec_invalid_reason
            # P13-006: agent closes preloop + lifecycle on hard gate
            if supervisor_agent is not None and delegate_mode == DELEGATE_MODE_IMPLEMENT:
                supervisor_agent.set_spec_path(spec_rel_path)
                _close_lifecycle_once(
                    OUTCOME_INVALID_SPEC,
                    phase="preloop",
                    phase_status="blocked",
                    detail="invalid_spec",
                )
        elif review_target_files_error:
            success = False
            error = review_target_files_error
            output = review_target_files_error
            if supervisor_agent is not None and delegate_mode == DELEGATE_MODE_IMPLEMENT:
                _close_lifecycle_once(
                    "error",
                    phase="preloop",
                    phase_status="blocked",
                    detail="review_target_files_error",
                )
        elif clarity_check_blocked:
            # P15-003: try supervisor sub-agent resolution before hard pause.
            clarity_resolution_result = None
            if clarity_check_questions and spec_rel_path:
                # Opt-out gate: skip sub-agent when disabled.
                try:
                    from core.engine.clarity_resolution import _clarity_resolution_enabled
                    _resolution_on = _clarity_resolution_enabled(ws)
                except Exception:
                    _resolution_on = True
                if _resolution_on:
                    try:
                        from core.engine.clarity_resolution import run_clarity_resolution

                        append_trace_record(
                            {
                                "type": "clarity_resolution_start",
                                "delegation_id": delegation_id,
                                "questions": clarity_check_questions,
                                "timestamp": obs.utc_now_iso(),
                            },
                            delegation_id=delegation_id,
                            session_dir=storage.session_dir,
                            workspace=ws,
                        )
                        clarity_resolution_result = run_clarity_resolution(
                            questions=clarity_check_questions,
                            workspace_path=ws,
                            spec_path=spec_rel_path,
                            project_state=(
                                supervisor_agent._project_state
                                if supervisor_agent is not None
                                else None
                            ),
                            spec_read=spec_read,
                            task=task,
                            context_summary=context_summary,
                            event_sink=None,
                        )
                        append_trace_record(
                            {
                                "type": "clarity_resolution_end",
                                "delegation_id": delegation_id,
                                "resolved": bool(clarity_resolution_result.resolved),
                                "answers": clarity_resolution_result.answers,
                                "escalate_reason": clarity_resolution_result.escalate_reason,
                                "tool_calls": clarity_resolution_result.tool_calls,
                                "model": clarity_resolution_result.model,
                                "duration_ms": clarity_resolution_result.duration_ms,
                                "error": clarity_resolution_result.error,
                                "timestamp": obs.utc_now_iso(),
                            },
                            delegation_id=delegation_id,
                            session_dir=storage.session_dir,
                            workspace=ws,
                        )
                        # Add clarity_resolution_ms to the clarity audit dict.
                        if clarity_check_audit is not None:
                            try:
                                clarity_check_audit["clarity_resolution_ms"] = (
                                    clarity_resolution_result.duration_ms
                                )
                            except Exception:
                                pass
                    except Exception:
                        clarity_resolution_result = None
                        # Best-effort: emit end event marking escalate, never block.
                        try:
                            append_trace_record(
                                {
                                    "type": "clarity_resolution_end",
                                    "delegation_id": delegation_id,
                                    "resolved": False,
                                    "answers": [],
                                    "escalate_reason": "sub_agent_exception",
                                    "tool_calls": 0,
                                    "model": None,
                                    "duration_ms": 0,
                                    "error": "sub_agent_exception",
                                    "timestamp": obs.utc_now_iso(),
                                },
                                delegation_id=delegation_id,
                                session_dir=storage.session_dir,
                                workspace=ws,
                            )
                        except Exception:
                            pass

            if clarity_resolution_result is not None and clarity_resolution_result.resolved:
                # Sub-agent answered -> write answers to Q&A, re-read spec,
                # clear flags -> proceed to executor.
                from core.specs.write import append_clarity_qa

                _spec_abs = Path(ws) / spec_rel_path
                append_clarity_qa(
                    _spec_abs, clarity_check_questions, clarity_resolution_result.answers
                )
                # Re-read the spec so planner/executor see the Q&A answers.
                spec_read = read_task_spec(_spec_abs, workspace=ws)
                clarity_check_blocked = False
                clarity_check_passed = True
                progress.notify(
                    "[clarity] Supervisor sub-agent resolved questions — proceeding.",
                    force=True,
                )
                _proceed_to_executor = True
            else:
                # Escalate or sub-agent failed -> current hard-pause behavior.
                success = False
                error = None
                supervisor_paused_questions = list(clarity_check_questions or [])
                _spec_hint = (
                    f" in `{spec_rel_path}`" if spec_rel_path else " in the spec"
                )
                output = (
                    "🔍 **Clarity questions** — add answers to the `## Q&A` section"
                    f"{_spec_hint} then re-call `delegate_to_agent`:\n"
                    + "\n".join(f"- {q}" for q in (clarity_check_questions or []))
                )
                # Auto-append unanswered questions to the spec so the host can fill them in-place.
                if spec_rel_path and clarity_check_questions:
                    try:
                        from core.specs.write import append_clarity_qa

                        _spec_abs = Path(ws) / spec_rel_path
                        append_clarity_qa(_spec_abs, clarity_check_questions)
                    except Exception:
                        pass  # best-effort; never block
                # P13-006: agent closes preloop + lifecycle on clarity gate
                if (
                    supervisor_agent is not None
                    and delegate_mode == DELEGATE_MODE_IMPLEMENT
                ):
                    supervisor_agent.set_spec_path(spec_rel_path)
                    try:
                        _pause_lifecycle_context = dict(
                            getattr(supervisor_agent, "_lifecycle_context", {}) or {}
                        )
                        _pause_lifecycle_context.setdefault("project_key", _project_key)
                        _paused_state = SupervisorState.create(
                            spec_path=spec_rel_path,
                            context_ref=delegation_id,
                            plan=architect_plan,
                            decision_log=[],
                            completed_turn_artifacts=[],
                            turn_index=0,
                            questions=supervisor_paused_questions,
                            pause_reason="clarity_check",
                            lifecycle_context=_pause_lifecycle_context,
                        )
                        _paused_state.save()
                        append_trace_record(
                            {
                                "type": "supervisor_paused",
                                "resume_token": _paused_state.resume_token,
                                "turn_index": _paused_state.turn_index,
                                "pause_reason": _paused_state.pause_reason,
                                "questions": _paused_state.questions,
                                "expires_at": _paused_state.expires_at,
                                "timestamp": obs.utc_now_iso(),
                            },
                            delegation_id=delegation_id,
                            session_dir=storage.session_dir,
                            workspace=ws,
                        )
                    except Exception:
                        # Best-effort: clarity gate response should not fail if pause
                        # persistence cannot be written for any reason.
                        pass
                    _close_lifecycle_once(
                        "needs_input",
                        phase="preloop",
                        phase_status="blocked",
                        detail="clarity_check",
                    )
        else:
            _proceed_to_executor = True

        if _proceed_to_executor:
            progress.notify(
                (
                    "[compile] Context ready — "
                    f"targets={len(effective_target_files)} files."
                ),
                force=True,
            )
            progress.notify("[executor] Starting delegated run…", force=True)
            # P13-006: agent owns lifecycle — close preloop, open loop.
            # (lifecycle_start + phase_start(preloop) were emitted earlier before
            # spec_validation/clarity ran; this is the honest, non-retroactive path.)
            if delegate_mode == DELEGATE_MODE_IMPLEMENT and supervisor_agent is not None:
                supervisor_agent.set_spec_path(spec_rel_path)
                supervisor_agent.emit_lifecycle_phase_end("preloop", status="ok")
                supervisor_agent.emit_lifecycle_phase_start("loop", resumed=False)
            else:
                # REVIEW mode (or agent not yet created): create here without lifecycle
                # envelope — review mode does not participate in the implement lifecycle.
                supervisor_agent = _get_or_create_supervisor(
                    _project_key, ws, spec_rel_path
                )
            supervisor_agent.begin_delegation(
                delegation_id=delegation_id,
                # executor_fn/reviewer_fn unused in host-driven mode (mcp_server owns
                # the executor + reviewer plumbing and drives the loop turn-by-turn).
                executor_fn=lambda _turn, _correction, _reset=False: result,
                max_turns=_supervisor_max_turns,
                event_sink=_supervisor_event_sink,
                spec_path=spec_rel_path,
                plan=architect_plan,
            )
            supervisor_agent.begin()
            supervisor_agent.begin_turn()
            executor_phase_started = False
            _executor_turns = 0
            try:
                t_engine = time.perf_counter()
                if delegate_mode == DELEGATE_MODE_REVIEW:
                    with role_context(ROLE_REVIEW):
                        result = run_spec_review(prompt, workspace_path=ws)
                elif _use_pkg:
                    builder_on = context_builder_enabled(ws)
                    workspace_rag_paths_for_picker: list[str] = []
                    if builder_on and delegation_policies is not None:
                        rag_should_run, _rag_skip = rag_retrieval_should_run(
                            ws, builder_on=builder_on, implement_mode=True
                        )
                        if workspace_file_hints_enabled(ws):
                            workspace_file_hints_on = True
                            try:
                                spec_sections_pre = (
                                    spec_read.sections if spec_read is not None else None
                                )
                                workspace_file_rag_refs = run_builder_workspace_file_retrieval(
                                    ws,
                                    task=task,
                                    spec_sections=spec_sections_pre,
                                )
                                workspace_rag_paths_for_picker = [
                                    ref.id for ref in workspace_file_rag_refs
                                ]
                            except Exception:
                                workspace_file_rag_refs = []
                                workspace_rag_paths_for_picker = []
                        if builder_history_rag_enabled(ws):
                            builder_history_rag_on = True
                        if rag_should_run:
                            rag_retrieval_on = True
                        if pipeline_recorder is not None:
                            pipeline_recorder.start("file_picker")
                        try:
                            picker_result = pick_candidate_files(
                                workspace=Path(ws),
                                task=task,
                                spec_text=spec_read.raw_text if spec_read else None,
                                policies=delegation_policies,
                                target_files=effective_target_files,
                                workspace_rag_paths=workspace_rag_paths_for_picker or None,
                            )
                        except Exception as exc:
                            if pipeline_recorder is not None:
                                pipeline_recorder.end(
                                    "file_picker",
                                    status="error",
                                    detail=f"{type(exc).__name__}: {exc}"[:200],
                                )
                            raise
                        else:
                            if pipeline_recorder is not None:
                                pipeline_recorder.end("file_picker", status="ok")
                    elif pipeline_recorder is not None:
                        pipeline_recorder.mark(
                            "file_picker",
                            status="skipped",
                            detail="context_builder_disabled",
                        )
                    rag_skip_detail: str | None = None
                    if not rag_retrieval_on:
                        _, rag_skip_detail = rag_retrieval_should_run(
                            ws,
                            builder_on=builder_on,
                            implement_mode=delegate_mode == DELEGATE_MODE_IMPLEMENT,
                        )

                    if pipeline_recorder is not None:
                        if rag_retrieval_on:
                            pipeline_recorder.start("rag_retrieval")
                            try:
                                spec_sections = (
                                    spec_read.sections if spec_read is not None else None
                                )
                                (
                                    delegation_rag_refs,
                                    workspace_file_rag_refs,
                                    rag_retrieval_refs,
                                ) = run_merged_builder_rag_retrieval(
                                    ws,
                                    task=task,
                                    spec_sections=spec_sections,
                                )
                                pipeline_recorder.end(
                                    "rag_retrieval",
                                    status="ok",
                                    detail=(
                                        f"{len(delegation_rag_refs)} delegation + "
                                        f"{len(workspace_file_rag_refs)} file hits"
                                    ),
                                )
                            except Exception as exc:
                                rag_retrieval_refs = []
                                delegation_rag_refs = []
                                workspace_file_rag_refs = []
                                pipeline_recorder.end(
                                    "rag_retrieval",
                                    status="error",
                                    detail=f"{type(exc).__name__}: {exc}"[:200],
                                )
                        else:
                            pipeline_recorder.mark(
                                "rag_retrieval",
                                status="skipped",
                                detail=rag_skip_detail or "disabled",
                            )
                    if pipeline_recorder is not None:
                        pipeline_recorder.start("context_assemble")
                    try:
                        context_package = assemble_context(
                            workspace=Path(ws),
                            spec_path=spec_rel_path,
                            target_files=effective_target_files,
                            task=task,
                            context_summary=context_summary,
                            policies=delegation_policies,
                            picker_result=picker_result,
                            include_repo_map=picker_result is not None,
                        )
                    except Exception as exc:
                        if pipeline_recorder is not None:
                            pipeline_recorder.end(
                                "context_assemble",
                                status="error",
                                detail=f"{type(exc).__name__}: {exc}"[:200],
                            )
                        raise
                    else:
                        if pipeline_recorder is not None:
                            pipeline_recorder.end("context_assemble", status="ok")
                        _emit_compile_event(
                            delegation_id=delegation_id,
                            stage=STAGE_MECHANICAL_BRIEF,
                            text_body=context_package.brief,
                            workspace=ws,
                            session_dir=storage.session_dir,
                            obs_verbosity=_compile_verbosity,
                        )

                    architect_enabled, architect_reason = should_run_architect_pass(
                        workspace=ws,
                        task=task,
                        target_files=effective_target_files,
                        spec_read=spec_read,
                    )
                    _planner_context_sources: list[str] = []
                    if architect_enabled:
                        if pipeline_recorder is not None:
                            pipeline_recorder.start("planner_pass")
                        (
                            architect_plan,
                            architect_pass_error,
                            architect_record,
                            architect_provenance,
                        ) = _apply_architect_pass(
                            context_package=context_package,
                            spec_read=spec_read,
                            picker_result=picker_result,
                            workspace=ws,
                            task=task,
                            context_summary=context_summary,
                            host_transcript=host_transcript_text,
                            timing=timing,
                            delegation_id=delegation_id,
                            project_state=(
                                supervisor_agent._project_state
                                if supervisor_agent is not None
                                else None
                            ),
                            spec_files=_spec_files_from_read(spec_read),
                            planner_context_sources=_planner_context_sources,
                            spec_path=spec_rel_path,
                            session_dir=storage.session_dir,  # P15-ISS-004
                        )
                        _emit_compile_provenance_pair(
                            delegation_id=delegation_id,
                            workspace=ws,
                            session_dir=storage.session_dir,
                            obs_verbosity=_compile_verbosity,
                            input_stage=STAGE_ARCHITECT_INPUT,
                            output_stage=STAGE_ARCHITECT_OUTPUT,
                            provenance=architect_provenance,
                        )
                        if architect_plan:
                            architect_plan_applied = True
                        planner_pass_audit = {
                            "ran": True,
                            "applied": architect_plan_applied,
                            "error": architect_pass_error,
                            "duration_ms": timing.get("planner_pass_ms"),
                            "model_role": (architect_record or {}).get("role"),
                            "model": (architect_record or {}).get("model"),
                        }
                        planner_pass_audit["planner_context_sources"] = (
                            _planner_context_sources
                        )
                        if pipeline_recorder is not None:
                            if architect_pass_error:
                                pipeline_recorder.end(
                                    "planner_pass",
                                    status="error",
                                    detail=architect_pass_error[:200],
                                )
                            else:
                                pipeline_recorder.end("planner_pass", status="ok")
                    else:
                        planner_pass_audit = {
                            "ran": False,
                            "applied": False,
                            "error": None,
                            "reason": architect_reason,
                            "duration_ms": 0,
                            "model_role": "planner_pass",
                            "model": None,
                        }
                        planner_pass_audit["planner_context_sources"] = (
                            _planner_context_sources
                        )
                        if pipeline_recorder is not None:
                            pipeline_recorder.mark(
                                "planner_pass",
                                status="skipped",
                                detail=architect_reason,
                            )
                        _emit_compile_skip(
                            delegation_id=delegation_id,
                            stage=STAGE_ARCHITECT_INPUT,
                            workspace=ws,
                            session_dir=storage.session_dir,
                            obs_verbosity=_compile_verbosity,
                            reason=architect_reason,
                        )

                    builder_llm_enabled = (
                        builder_on
                        and picker_result is not None
                        and context_builder_llm_enabled(ws)
                    )
                    if builder_llm_enabled:
                        if pipeline_recorder is not None:
                            pipeline_recorder.start("builder_llm")
                        (
                            context_package,
                            builder_brief_applied,
                            builder_llm_error,
                            builder_record,
                            builder_provenance,
                        ) = _apply_builder_llm(
                            context_package=context_package,
                            picker_result=picker_result,
                            workspace=ws,
                            task=task,
                            context_summary=context_summary,
                            spec_rel_path=spec_rel_path,
                            host_transcript=host_transcript_text,
                            timing=timing,
                            delegation_id=delegation_id,
                            mcp_session_id=storage.mcp_session_id,
                            rag_refs=rag_retrieval_refs if rag_retrieval_on else None,
                        )
                        _emit_compile_provenance_pair(
                            delegation_id=delegation_id,
                            workspace=ws,
                            session_dir=storage.session_dir,
                            obs_verbosity=_compile_verbosity,
                            input_stage=STAGE_BUILDER_INPUT,
                            output_stage=STAGE_BUILDER_OUTPUT,
                            provenance=builder_provenance,
                        )
                        if pipeline_recorder is not None:
                            if builder_llm_error:
                                pipeline_recorder.end(
                                    "builder_llm", status="error", detail=builder_llm_error[:200]
                                )
                            else:
                                pipeline_recorder.end("builder_llm", status="ok")
                    else:
                        if pipeline_recorder is not None:
                            pipeline_recorder.mark(
                                "builder_llm",
                                status="skipped",
                                detail="disabled",
                            )
                        _emit_compile_skip(
                            delegation_id=delegation_id,
                            stage=STAGE_BUILDER_INPUT,
                            workspace=ws,
                            session_dir=storage.session_dir,
                            obs_verbosity=_compile_verbosity,
                            reason="disabled",
                        )
                    if architect_plan:
                        context_package.brief = _merge_architect_plan(
                            architect_plan, context_package.brief
                        )
                    engine = get_engine(backend)
                    model = engine.model_name
                    try:
                        caps = engine.capabilities()
                        context_package, cap_warnings = apply_backend_capabilities(
                            context_package, caps, workspace=Path(ws)
                        )
                    except (NotImplementedError, AttributeError):
                        caps = None
                    budget = resolve_context_budget_tokens(model=model)
                    if budget is not None:
                        context_package = apply_context_budget(
                            context_package, workspace=Path(ws), budget_tokens=budget
                        )
                    executor_prompt = context_package.brief
                    # P15-001 Slice C: wire builder brief into supervisor
                    # so the decision prompt can check "did executor follow the brief?"
                    if supervisor_agent is not None:
                        supervisor_agent.set_builder_brief(context_package.brief)
                    if delegate_mode == DELEGATE_MODE_IMPLEMENT:
                        _emit_compile_event(
                            delegation_id=delegation_id,
                            stage=STAGE_FINAL_EXECUTOR_PROMPT,
                            text_body=executor_prompt,
                            workspace=ws,
                            session_dir=storage.session_dir,
                            obs_verbosity=_compile_verbosity,
                        )
                    if pipeline_recorder is not None:
                        pipeline_recorder.start("executor")
                        executor_phase_started = True
                    _loop_obs_verbosity = resolve_observability_verbosity(ws)

                    def _ctx_step_fn(timeout_s: float | None) -> ExecutionResult:
                        with role_context(ROLE_EXECUTOR):
                            return engine.run_context(
                                context_package,
                                workspace_path=ws,
                                mcp_session_id=storage.mcp_session_id,
                                host_transcript=host_transcript_text,
                                delegation_id=delegation_id,
                                spec_path=spec_rel_path,
                                timestamp_start=timestamp_start,
                                timeout_s=timeout_s,
                            )

                    result, _executor_turns, effective_target_files, auto_merged_read_paths, context_package, stall_auto_retried = (
                        _run_executor_with_optional_stall_retry(
                            step_fn=_ctx_step_fn,
                            delegation_id=delegation_id,
                            session_dir=storage.session_dir,
                            workspace=ws,
                            obs_verbosity=_loop_obs_verbosity,
                            progress_notify=progress.notify,
                            context_package=context_package,
                            effective_target_files=effective_target_files,
                            auto_merged_read_paths=auto_merged_read_paths,
                            already_retried=stall_auto_retried,
                        )
                    )
                    executor_prompt = result.prompt_used or context_package.brief
                else:
                    # Legacy path: no context package — log raw prompt as mechanical_brief
                    _emit_compile_event(
                        delegation_id=delegation_id,
                        stage=STAGE_MECHANICAL_BRIEF,
                        text_body=prompt or None,
                        workspace=ws,
                        session_dir=storage.session_dir,
                        obs_verbosity=_compile_verbosity,
                        status="ok",
                        detail="no_spec_raw_prompt",
                    )
                    for _skipped_stage in (
                        STAGE_VALIDATION_INPUT,
                        STAGE_ARCHITECT_INPUT,
                        STAGE_BUILDER_INPUT,
                    ):
                        _emit_compile_skip(
                            delegation_id=delegation_id,
                            stage=_skipped_stage,
                            workspace=ws,
                            session_dir=storage.session_dir,
                            obs_verbosity=_compile_verbosity,
                            reason="context_package_disabled",
                        )
                    if pipeline_recorder is not None:
                        pipeline_recorder.mark(
                            "file_picker",
                            status="skipped",
                            detail="context_package_disabled",
                        )
                        pipeline_recorder.mark(
                            "rag_retrieval",
                            status="skipped",
                            detail="context_package_disabled",
                        )
                        pipeline_recorder.mark(
                            "context_assemble",
                            status="skipped",
                            detail="context_package_disabled",
                        )
                        pipeline_recorder.mark(
                            "planner_pass",
                            status="skipped",
                            detail="context_package_disabled",
                        )
                        pipeline_recorder.mark(
                            "builder_llm",
                            status="skipped",
                            detail="context_package_disabled",
                        )
                    engine = get_engine(backend)
                    model = engine.model_name
                    try:
                        caps = engine.capabilities()
                    except (NotImplementedError, AttributeError):
                        caps = None
                    legacy_contract: list[str] | None = None
                    if delegation_policies is not None:
                        legacy_contract = sorted(
                            set(delegation_policies.files_edit)
                            | set(delegation_policies.files_read)
                        )
                    if pipeline_recorder is not None:
                        pipeline_recorder.start("executor")
                        executor_phase_started = True
                    _loop_obs_verbosity = resolve_observability_verbosity(ws)
                    if delegate_mode == DELEGATE_MODE_IMPLEMENT:
                        _emit_compile_event(
                            delegation_id=delegation_id,
                            stage=STAGE_FINAL_EXECUTOR_PROMPT,
                            text_body=prompt,
                            workspace=ws,
                            session_dir=storage.session_dir,
                            obs_verbosity=_compile_verbosity,
                        )

                    def _legacy_step_fn(timeout_s: float | None) -> ExecutionResult:
                        with role_context(ROLE_EXECUTOR):
                            return engine.run(
                                prompt,
                                effective_target_files,
                                workspace_path=ws,
                                mcp_session_id=storage.mcp_session_id,
                                delegation_id=delegation_id,
                                spec_path=spec_rel_path,
                                contract_paths=legacy_contract,
                                timestamp_start=timestamp_start,
                                timeout_s=timeout_s,
                            )

                    result, _executor_turns, effective_target_files, auto_merged_read_paths, _legacy_pkg, stall_auto_retried = (
                        _run_executor_with_optional_stall_retry(
                            step_fn=_legacy_step_fn,
                            delegation_id=delegation_id,
                            session_dir=storage.session_dir,
                            workspace=ws,
                            obs_verbosity=_loop_obs_verbosity,
                            progress_notify=progress.notify,
                            context_package=None,
                            effective_target_files=effective_target_files,
                            auto_merged_read_paths=auto_merged_read_paths,
                            already_retried=stall_auto_retried,
                        )
                    )
                timing["engine_run_ms"] = int((time.perf_counter() - t_engine) * 1000)

                success = result.success
                output = result.output or ""
                files_changed = result.files_changed
                files_unexpected = result.files_unexpected
                tokens = result.tokens or tokens
                model = result.model or model
                error = result.error
                error_class = result.error_class
                stall_info = _stall_from_tokens(tokens)
                if stall_info.get("stall_type"):
                    stall_type = str(stall_info["stall_type"])
                    stall_files_requested = list(stall_info.get("files_requested") or [])
                    success = False
                    supervisor_reason = stall_info.get("supervisor_reason")
                    classification = {
                        "outcome": stall_type,
                        "message": supervisor_reason
                        or error
                        or (
                            "Aider needs additional files. Add them to target_files and retry."
                            if stall_type == OUTCOME_NEEDS_INPUT_FILES
                            else (
                                "Aider left an open question after edits "
                                "(review output; re-delegate with more context if needed)."
                            )
                        ),
                        "files_requested": stall_files_requested,
                        "executor_output_tail": stall_info.get("executor_output_tail")
                        or output[-500:],
                    }
                    if supervisor_reason:
                        classification["supervisor_reason"] = supervisor_reason
                    needs_input_payload = build_needs_input_payload(classification)
                    error_class = stall_type
                    error = classification.get("message")
                elif not success and error:
                    _ec, error_message = classify_delegation_error(error)
                    if not error_class:
                        error_class = _ec
                supervisor_decisions_trace = list((tokens or {}).get("supervisor_decisions") or [])
                if supervisor_decisions_trace:
                    _emit_supervisor_decision_traces(
                        delegation_id=delegation_id,
                        session_dir=storage.session_dir,
                        workspace=ws,
                        decisions=supervisor_decisions_trace,
                        step_index=_executor_turns or 1,
                    )
                executor_reused = result.executor_reused
                executor_recreated = result.executor_recreated
                workspace_snapshot = result.workspace_snapshot
                if result.workspace_snapshot_ms is not None:
                    timing["workspace_snapshot_ms"] = result.workspace_snapshot_ms
                if not success and error and not output:
                    output = error
                if pipeline_recorder is not None and executor_phase_started:
                    pipeline_recorder.end(
                        "executor",
                        status="ok" if success else "error",
                        detail=error[:200] if (error and not success) else None,
                    )

            except UnknownBackendError as exc:
                success = False
                error = str(exc)
                error_class, error_message = classify_delegation_error(error, exc=exc)
                output = error
                if pipeline_recorder is not None and executor_phase_started:
                    pipeline_recorder.end("executor", status="error", detail=error[:200])
            except Exception as exc:
                success = False
                error = f"{type(exc).__name__}: {exc}"
                error_class, error_message = classify_delegation_error(error, exc=exc)
                output = error
                if pipeline_recorder is not None and executor_phase_started:
                    pipeline_recorder.end("executor", status="error", detail=error[:200])

        resolved_model = model or resolve_model_name()

        # Build context_block from executor_prompt (legacy: same as prompt; package: translated prompt)
        if context_package is not None:
            try:
                from core.context.package_blob import persist_context_package_blob

                context_package_hash, _, _ = persist_context_package_blob(
                    storage.session_dir,
                    context_package,
                )
                annotate_trace_header_context_package_hash(
                    session_dir=storage.session_dir,
                    delegation_id=delegation_id,
                    context_package_hash=context_package_hash,
                )
            except Exception:
                context_package_hash = None

        context_block = prompt_metadata(
            executor_prompt,
            context_summary=context_summary,
            transcript_meta=transcript_meta,
        )
        if _executor_turns > 0:
            context_block["executor_turns"] = _executor_turns
        if spec_validation_audit is not None:
            context_block["spec_validation"] = spec_validation_audit
        from core.logging.delegation_log import resolve_clarity_check_result

        clarity_check_result = resolve_clarity_check_result(
            enabled=clarity_pass_on,
            ran=clarity_check_ran,
            passed=clarity_check_passed,
            blocked=clarity_check_blocked,
            error=clarity_check_error,
        )
        if clarity_check_result is not None:
            context_block["clarity_check_result"] = clarity_check_result
        if clarity_check_audit is not None:
            context_block["clarity_check"] = clarity_check_audit
        if clarity_followup_lineage is not None:
            context_block["clarity_followup_lineage"] = clarity_followup_lineage
        from core.logging.delegation_log import supervisor_audit_fields

        context_block.update(supervisor_audit_fields(tokens))
        if context_package is not None:
            read_entries_in_prompt = [
                e
                for e in context_package.entries
                if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT) and e.payload is not None
            ]
            if context_package_hash is not None:
                context_block["context_package_hash"] = context_package_hash
            pkg_meta = context_package.metadata
            if pkg_meta.get("context_builder_enabled"):
                candidate_files = pkg_meta.get("candidate_files") or {}
                context_block["context_builder_enabled"] = True
                context_block["candidate_files"] = candidate_files
                context_block["suggested_edit_paths"] = candidate_files.get(
                    "suggested_edit_paths", []
                )
                context_block["repo_map_count"] = pkg_meta.get("repo_map_count", 0)
                context_block["context_builder_llm_enabled"] = builder_llm_enabled
                if builder_llm_enabled:
                    context_block["builder_brief_applied"] = builder_brief_applied
                    if builder_llm_error:
                        context_block["builder_llm_error"] = builder_llm_error
                if rag_retrieval_on:
                    if builder_history_rag_on:
                        context_block["builder_history_rag_enabled"] = True
                    if workspace_file_hints_on:
                        context_block["workspace_file_hints_enabled"] = True
                    context_block["rag_retrieval_hit_count"] = len(rag_retrieval_refs)
                    context_block["rag_retrieval_delegation_hits"] = len(delegation_rag_refs)
                    context_block["rag_retrieval_file_hits"] = len(workspace_file_rag_refs)
            # Planner pass telemetry should be stable regardless of builder/rag toggles.
            if planner_pass_audit is not None:
                context_block["planner_pass"] = planner_pass_audit
            context_block["planner_pass_enabled"] = architect_enabled
            context_block["planner_plan_applied"] = architect_plan_applied
            if architect_pass_error:
                context_block["planner_pass_error"] = architect_pass_error
            context_block["adapter_in"] = {
                "fnames": sorted(
                    e.path for e in context_package.entries if e.tier == TIER_EDIT_FULL
                ),
                "read_paths_in_prompt": [e.path for e in read_entries_in_prompt],
                "prompt_chars": len(executor_prompt),
                "prompt_tokens_est": estimate_tokens(executor_prompt),
                "prompt_hash": sha256_hex(executor_prompt),
            }
            if cap_warnings:
                context_block["capability_warnings"] = cap_warnings

        if caps is not None:
            context_block["backend_capabilities"] = caps.to_dict()

        if stall_type:
            context_block["stall_type"] = stall_type
        if stall_files_requested:
            context_block["stall_files_requested"] = stall_files_requested
        if stall_auto_retried:
            context_block["auto_retried"] = True

        usage_dict = obs.build_usage_report(
            model=resolved_model,
            prompt=executor_prompt,
            actual_tokens=tokens,
            preflight_tokens_est=int(context_block.get("prompt_tokens_est") or 0),
            preflight_chars=int(context_block.get("prompt_chars") or len(executor_prompt)),
        )
        usage_summary_line = obs.format_usage_run_log_line(usage_dict)
        context_block["token_estimate_preflight"] = usage_dict["preflight_tokens_est"]
        usage_warnings = obs.build_usage_warnings(usage_dict["preflight_tokens_est"])

        timestamp_end = obs.utc_now_iso()
        spec_sha256: str | None = spec_read.sha256 if spec_read else None
        spec_bytes: int | None = spec_read.file_bytes if spec_read else None
        spec_mtime: str | None = spec_read.mtime_iso if spec_read else None
        outcome: str | None = None
        scope_violations: list[str] = []
        reverted_paths: list[str] = []
        revert_skipped: list[str] = []
        post_gateway: dict[str, Any] | None = None
        spec_report_rel_path: str | None = None

        reviewer_applicable = (
            reviewer_pass_on
            and delegate_mode == DELEGATE_MODE_IMPLEMENT
            and success
            and bool(files_changed)
            and not spec_invalid_reason
        )
        if pipeline_recorder is not None:
            if reviewer_applicable:
                pipeline_recorder.start("reviewer_pass")
                try:
                    unified_diff = _collect_reviewer_unified_diff(ws, files_changed)
                except Exception as diff_exc:
                    reviewer_pass_error = str(diff_exc)
                    pipeline_recorder.end(
                        "reviewer_pass",
                        status="error",
                        detail=reviewer_pass_error[:200],
                    )
                else:
                    (
                        reviewer_pass_ran,
                        reviewer_pass_outcome,
                        reviewer_pass_note,
                        reviewer_pass_audit,
                        reviewer_pass_record,
                        _reviewer_prov,
                    ) = _apply_reviewer_pass(
                        spec_read=spec_read,
                        workspace=ws,
                        task=task,
                        files_changed=files_changed,
                        unified_diff=unified_diff,
                        timing=timing,
                        delegation_id=delegation_id,
                    )
                    if reviewer_pass_ran and reviewer_pass_outcome in ("lgtm", "issues"):
                        pipeline_recorder.end("reviewer_pass", status="ok")
                    else:
                        reviewer_pass_error = reviewer_pass_error or (
                            (reviewer_pass_audit or {}).get("error") or "reviewer_pass_failed"
                        )
                        pipeline_recorder.end(
                            "reviewer_pass",
                            status="error",
                            detail=str(reviewer_pass_error)[:200],
                        )
            else:
                pipeline_recorder.mark(
                    "reviewer_pass",
                    status="skipped",
                    detail="disabled_or_not_applicable",
                )

        from core.logging.delegation_log import (
            resolve_reviewer_pass_result,
            resolve_reviewer_policy_fields,
        )

        reviewer_pass_result = resolve_reviewer_pass_result(
            enabled=reviewer_pass_on,
            ran=reviewer_pass_ran,
            outcome=reviewer_pass_outcome,
            error=reviewer_pass_error,
        )
        reviewer_policy_fields = resolve_reviewer_policy_fields(
            enabled=reviewer_pass_on,
            ran=reviewer_pass_ran,
            outcome=reviewer_pass_outcome,
            error=reviewer_pass_error,
        )
        context_block["reviewer_pass_result"] = reviewer_pass_result
        # Explicit reviewer policy visibility fields (P11-ISS-017).
        context_block.update(reviewer_policy_fields)
        if reviewer_pass_audit is not None:
            context_block["reviewer_pass"] = reviewer_pass_audit

        # P12-004: promote reviewer findings to project state
        if (
            supervisor_agent is not None
            and reviewer_pass_ran
            and reviewer_pass_outcome == "issues"
            and reviewer_pass_note
            and supervisor_agent._project_state is not None
        ):
            from core.engine.reviewer_findings_classifier import (
                classify_reviewer_findings,
                should_promote_finding_to_risk,
            )

            findings = classify_reviewer_findings(
                reviewer_pass_note,
                spec_contract=str(spec_read.sections.get("Contract", ""))[:400]
                    if spec_read else None,
                workspace_path=ws,
                delegation_id=delegation_id,
            )

            promoted_count = 0
            suppressed_count = 0
            changed_file_contents = _collect_reviewer_changed_file_contents(
                ws,
                list(files_changed or []),
            )
            for finding in findings:
                supervisor_agent._project_state.add_reviewer_finding(
                    text=finding.text,
                    severity=finding.severity,
                    delegation_id=delegation_id,
                    spec_path=spec_rel_path,
                    files=list(files_changed or [])[:10],
                )
                if should_promote_finding_to_risk(
                    finding,
                    changed_file_contents=changed_file_contents,
                ):
                    supervisor_agent._project_state.add_risk(
                        text=finding.text,
                        severity=finding.severity,
                        source_delegation_id=delegation_id,
                    )
                    promoted_count += 1
                elif finding.severity in ("notable", "critical"):
                    suppressed_count += 1

            _supervisor_event_sink({
                "type": "reviewer_findings_classified",
                "finding_count": len(findings),
                "promoted_to_risks": promoted_count,
                "suppressed_risk_promotions": suppressed_count,
                "severities": [f.severity for f in findings],
                "delegation_id": delegation_id,
            })
            if promoted_count > 0:
                _supervisor_event_sink({
                    "type": "project_state_risks_updated",
                    "new_risks": promoted_count,
                    "total_open_risks": len(supervisor_agent._project_state.open_risks),
                    "delegation_id": delegation_id,
                })

        # P13-016 (ISS-017): when an early-close preloop gate (clarity_check /
        # invalid_spec / review_target_files_error) already closed the lifecycle
        # envelope, the executor loop never started. Skip the host-driven
        # turn/loop closure block entirely — otherwise complete_turn() + finish()
        # would emit synthetic supervisor_turn_end(worker_outcome=failure) and
        # supervisor_loop_end(end_reason=executor_error) markers for a loop that
        # never ran, misrepresenting a pause/back-to-host handoff as a failure.
        if supervisor_agent is not None and not _lifecycle_closed:
            # Translate the reviewer signal into the agent's per-turn check summary, then
            # let the agent emit supervisor_turn_end + supervisor_decision and close the
            # loop. P15-ISS-010 fix: when the supervisor decides `rerun_aider` and turns
            # remain, re-invoke the executor + reviewer with a correction note instead of
            # immediately escalating to the host.
            if architect_plan:
                supervisor_agent.set_plan(architect_plan)

            # Save the base executor prompt so retries can append a correction note.
            _retry_base_prompt = executor_prompt if context_package is not None else prompt
            _retry_context_package = context_package
            _retry_use_pkg = _use_pkg
            _retry_engine = engine if _use_pkg else None

            # ── supervisor retry loop (P15-ISS-010) ──────────────────────────
            # Each iteration: build reviewer checks from the latest reviewer pass,
            # feed result + checks to complete_turn, then inspect the decision.
            # `rerun_aider` + turns remaining → re-run executor + reviewer.
            # `done` / `escalate_host` / no turns → finish().
            _supervisor_retrying = True
            while _supervisor_retrying:
                _reviewer_checks = {
                    "outcome": (
                        "issues"
                        if reviewer_pass_outcome == "issues"
                        else ("lgtm" if reviewer_pass_outcome == "lgtm" else None)
                    ),
                    "note": str(
                        reviewer_pass_note or reviewer_pass_error or ""
                    )[:300],
                }
                _agent_turn_result = (
                    result
                    if result is not None
                    else ExecutionResult(
                        success=success,
                        output=output or "",
                        files_changed=files_changed,
                        model=model,
                        error=error,
                        error_class=error_class,
                    )
                )
                # P13-005: persist reviewer pass result into lifecycle context before finish()
                # so escalation SupervisorState captures it; non-fatal for delegation success.
                if delegate_mode == DELEGATE_MODE_IMPLEMENT:
                    supervisor_agent.update_reviewer_pass_result(reviewer_pass_result)
                _turn_decision = supervisor_agent.complete_turn(
                    _agent_turn_result, _reviewer_checks
                )

                # Decide whether to retry or finish.
                _should_rerun = (
                    _turn_decision.action == "rerun_aider"
                    and delegate_mode == DELEGATE_MODE_IMPLEMENT
                    and supervisor_agent.can_rerun()
                )
                if not _should_rerun:
                    _supervisor_retrying = False
                    break

                # ── rerun path: re-invoke executor with correction note ───────
                try:
                    _correction = supervisor_agent.correction_note(_reviewer_checks)
                except Exception:
                    _correction = ""
                _retry_prompt = (
                    f"{_retry_base_prompt}\n\n{_correction}" if _correction else _retry_base_prompt
                )
                supervisor_agent.begin_turn()
                _executor_turns = 0
                executor_phase_started = False
                try:
                    t_engine = time.perf_counter()
                    if _retry_use_pkg and _retry_engine is not None:
                        # Re-run via legacy engine.run with augmented prompt.
                        # We intentionally don't use run_context on retry: the
                        # context package is already applied; the correction note
                        # just needs to reach the executor as a prompt suffix.
                        if pipeline_recorder is not None:
                            pipeline_recorder.start("executor")
                            executor_phase_started = True

                        def _retry_legacy_step_fn(timeout_s):
                            with role_context(ROLE_EXECUTOR):
                                return _retry_engine.run(
                                    _retry_prompt,
                                    effective_target_files,
                                    workspace_path=ws,
                                    mcp_session_id=storage.mcp_session_id,
                                    delegation_id=delegation_id,
                                    spec_path=spec_rel_path,
                                    contract_paths=legacy_contract,
                                    timestamp_start=timestamp_start,
                                    timeout_s=timeout_s,
                                )

                        result, _executor_turns, effective_target_files, auto_merged_read_paths, _legacy_pkg, stall_auto_retried = (
                            _run_executor_with_optional_stall_retry(
                                step_fn=_retry_legacy_step_fn,
                                delegation_id=delegation_id,
                                session_dir=storage.session_dir,
                                workspace=ws,
                                obs_verbosity=_loop_obs_verbosity,
                                progress_notify=progress.notify,
                                context_package=None,
                                effective_target_files=effective_target_files,
                                auto_merged_read_paths=auto_merged_read_paths,
                                already_retried=stall_auto_retried,
                            )
                        )
                        executor_prompt = _retry_prompt
                    else:
                        # No engine available (review mode or other) — can't retry.
                        _supervisor_retrying = False
                        break

                    timing["engine_run_ms"] = int((time.perf_counter() - t_engine) * 1000)
                    success = result.success
                    output = result.output or ""
                    files_changed = result.files_changed
                    files_unexpected = result.files_unexpected
                    tokens = result.tokens or tokens
                    model = result.model or model
                    error = result.error
                    error_class = result.error_class
                    if not success and error and not output:
                        output = error
                    if pipeline_recorder is not None and executor_phase_started:
                        pipeline_recorder.end(
                            "executor",
                            status="ok" if success else "error",
                            detail=error[:200] if (error and not success) else None,
                        )
                except Exception as exc:
                    success = False
                    error = f"{type(exc).__name__}: {exc}"
                    error_class, error_message = classify_delegation_error(error, exc=exc)
                    output = error
                    if pipeline_recorder is not None and executor_phase_started:
                        pipeline_recorder.end("executor", status="error", detail=error[:200])
                    # On executor exception during retry, fall through to finish().
                    _supervisor_retrying = False
                    break

                # ── re-run reviewer pass on the new result ────────────────────
                reviewer_pass_ran = False
                reviewer_pass_outcome = None
                reviewer_pass_note = None
                reviewer_pass_error = None
                reviewer_pass_audit = None
                reviewer_pass_record = None
                reviewer_applicable = (
                    reviewer_pass_on
                    and delegate_mode == DELEGATE_MODE_IMPLEMENT
                    and success
                    and bool(files_changed)
                    and not spec_invalid_reason
                )
                if reviewer_applicable:
                    if pipeline_recorder is not None:
                        pipeline_recorder.start("reviewer_pass")
                    try:
                        unified_diff = _collect_reviewer_unified_diff(ws, files_changed)
                    except Exception as diff_exc:
                        reviewer_pass_error = str(diff_exc)
                        if pipeline_recorder is not None:
                            pipeline_recorder.end(
                                "reviewer_pass", status="error", detail=reviewer_pass_error[:200]
                            )
                    else:
                        (
                            reviewer_pass_ran,
                            reviewer_pass_outcome,
                            reviewer_pass_note,
                            reviewer_pass_audit,
                            reviewer_pass_record,
                            _reviewer_prov,
                        ) = _apply_reviewer_pass(
                            spec_read=spec_read,
                            workspace=ws,
                            task=task,
                            files_changed=files_changed,
                            unified_diff=unified_diff,
                            timing=timing,
                            delegation_id=delegation_id,
                        )
                        if reviewer_pass_ran and reviewer_pass_outcome in ("lgtm", "issues"):
                            if pipeline_recorder is not None:
                                pipeline_recorder.end("reviewer_pass", status="ok")
                        else:
                            reviewer_pass_error = reviewer_pass_error or (
                                (reviewer_pass_audit or {}).get("error") or "reviewer_pass_failed"
                            )
                            if pipeline_recorder is not None:
                                pipeline_recorder.end(
                                    "reviewer_pass",
                                    status="error",
                                    detail=str(reviewer_pass_error)[:200],
                                )
                else:
                    if pipeline_recorder is not None:
                        pipeline_recorder.mark(
                            "reviewer_pass", status="skipped", detail="disabled_or_not_applicable"
                        )
                reviewer_pass_result = resolve_reviewer_pass_result(
                    enabled=reviewer_pass_on,
                    ran=reviewer_pass_ran,
                    outcome=reviewer_pass_outcome,
                    error=reviewer_pass_error,
                )
                # Loop continues: complete_turn will be called again at top of while.
            # ── end supervisor retry loop ──────────────────────────────────────

            supervisor_agent_result = supervisor_agent.finish()
            supervisor_paused_questions = list(supervisor_agent_result.paused_questions or [])
            context_block["supervisor_agent_loop"] = supervisor_agent.context_block(
                supervisor_agent_result
            )
            # P13-006: agent owns loop phase end
            if delegate_mode == DELEGATE_MODE_IMPLEMENT and not _lifecycle_closed:
                _loop_outcome_status = (
                    "escalated"
                    if supervisor_agent_result.outcome == "escalated"
                    else ("error" if supervisor_agent_result.outcome == "error" else "ok")
                )
                supervisor_agent.emit_lifecycle_phase_end("loop", status=_loop_outcome_status)
            if supervisor_agent_result.outcome == "escalated":
                success = False
                needs_input_payload = build_needs_input_payload(
                    {
                        "outcome": OUTCOME_NEEDS_INPUT_CLARIFICATION,
                        "supervisor_reason": (
                            supervisor_paused_questions[0]
                            if supervisor_paused_questions
                            else "Supervisor requires host clarification."
                        ),
                        "message": (
                            supervisor_paused_questions[0]
                            if supervisor_paused_questions
                            else "Supervisor requires host clarification."
                        ),
                        "files_requested": [],
                        "executor_output_tail": (output or "")[-500:],
                    }
                )
                error_class = "needs_input"
                error = (
                    supervisor_paused_questions[0]
                    if supervisor_paused_questions
                    else "Supervisor requires host clarification."
                )
                error_message = error

        # Explicit clarity loop telemetry (P11-ISS-019).
        if clarity_round_index is not None:
            context_block["clarity_round_index"] = clarity_round_index
        if clarity_round_cap is not None:
            context_block["clarity_round_cap"] = clarity_round_cap
        if clarity_auto_passed is not None:
            context_block["clarity_auto_passed"] = clarity_auto_passed

        # P13-006: agent owns postloop phase start (post_gateway + spec_report + indexing)
        _postloop_started = False
        if (
            supervisor_agent is not None
            and delegate_mode == DELEGATE_MODE_IMPLEMENT
            and not _lifecycle_closed  # P13-008: early-close paths skip postloop
        ):
            supervisor_agent.emit_lifecycle_phase_start("postloop", resumed=False)
            _postloop_started = True

        if (
            spec_path
            and not spec_invalid_reason
            and delegate_mode == DELEGATE_MODE_IMPLEMENT
            and delegation_policies is not None
        ):
            if pipeline_recorder is not None:
                pipeline_recorder.start("post_gateway")
            gateway_result = apply_post_delegation_gateway(
                workspace=ws,
                delegation_id=delegation_id,
                delegate_mode=delegate_mode,
                edit_scope=delegation_policies.edit_scope,
                files_changed=files_changed,
                files_edit=delegation_policies.files_edit,
            )
            scope_violations = gateway_result.scope_violations
            reverted_paths = gateway_result.reverted_paths
            revert_skipped = gateway_result.revert_skipped
            if gateway_result.gateway_applied or scope_violations:
                post_gateway = {
                    "edit_scope": delegation_policies.edit_scope,
                    "violations": scope_violations,
                    "reverted": reverted_paths,
                    "skipped": revert_skipped,
                    "gateway_applied": gateway_result.gateway_applied,
                }
            if pipeline_recorder is not None:
                pipeline_recorder.end("post_gateway", status="ok")

        if spec_invalid_reason:
            # Invalid spec is the canonical terminal outcome even if clarity
            # also flagged blocked in the same preloop run.
            outcome = OUTCOME_INVALID_SPEC
        elif clarity_check_blocked:
            outcome = OUTCOME_NEEDS_INPUT
        elif spec_path:
            if spec_abs_path is not None and spec_abs_path.is_file():
                if pipeline_recorder is not None:
                    pipeline_recorder.start("spec_report")
                report_abs_path = ensure_task_report(spec_abs_path, workspace=ws)
                spec_report_rel_path = str(report_abs_path.resolve().relative_to(Path(ws).resolve()))
                apply_post_delegation_report_updates(
                    report_abs_path,
                    timestamp=timestamp_end,
                    delegation_id=delegation_id,
                    mcp_session_id=storage.mcp_session_id,
                    delegate_mode=delegate_mode,
                    success=success,
                    files_changed=files_changed,
                    output=output,
                    error=error,
                    task_spec=spec_rel_path,
                    usage_summary=usage_summary_line,
                    scope_violations=scope_violations or None,
                    files_unexpected=files_unexpected or None,
                    edit_scope=delegation_policies.edit_scope if delegation_policies else None,
                    capability_warnings=cap_warnings or None,
                    reverted_paths=reverted_paths or None,
                    revert_skipped=revert_skipped or None,
                    reviewer_note=reviewer_pass_note,
                )
                spec_read = read_task_spec(spec_abs_path, workspace=ws)
                spec_sha256 = spec_read.sha256
                spec_bytes = spec_read.file_bytes
                spec_mtime = spec_read.mtime_iso
                outcome = compute_spec_outcome(
                    success=success,
                    files_changed=files_changed,
                    blockers_written=not success,
                    delegate_mode=delegate_mode,
                )
                if stall_type:
                    outcome = OUTCOME_NEEDS_INPUT
                if (
                    delegate_mode == DELEGATE_MODE_IMPLEMENT
                    and delegation_policies is not None
                    and delegation_policies.edit_scope == "strict"
                ):
                    outcome = apply_scope_outcome(
                        outcome,
                        edit_scope=delegation_policies.edit_scope,
                        scope_violations=scope_violations,
                    )
                    if scope_violations:
                        obs.emit(
                            "spec_scope_violation",
                            level="warn",
                            delegation_id=delegation_id,
                            spec_path=spec_rel_path,
                            scope_violations=scope_violations,
                            edit_scope=delegation_policies.edit_scope,
                        )
                if pipeline_recorder is not None:
                    pipeline_recorder.end("spec_report", status="ok")
        elif stall_type:
            outcome = OUTCOME_NEEDS_INPUT

        if supervisor_agent_result is not None and supervisor_agent_result.outcome == "escalated":
            outcome = OUTCOME_NEEDS_INPUT
            from core.session.executor_cache import drop_coder

            if storage.mcp_session_id:
                drop_coder(storage.mcp_session_id)

        _supervisor_end_reason = (
            str(supervisor_agent_result.end_reason or "")
            if supervisor_agent_result is not None
            else ""
        )
        if not success and (
            error_class == "unknown"
            or (error_class is None and _supervisor_end_reason == "unknown")
        ):
            error_class = "unknown"
            if not error_message:
                error_message = (
                    "supervisor_loop_unknown"
                    if _supervisor_end_reason == "unknown"
                    else "executor_unknown_failure"
                )
            if not error:
                error = error_message

        verify_result: VerifyResult | None = None
        verify_enabled = auto_verify_enabled(ws)
        if (
            verify_enabled
            and delegate_mode == DELEGATE_MODE_IMPLEMENT
            and spec_path
            and not spec_invalid_reason
            and success
            and files_changed
        ):
            if pipeline_recorder is not None:
                pipeline_recorder.start("auto_verify")
            t_verify = time.perf_counter()
            verify_result = run_verify_command(
                workspace=Path(ws),
                command=resolve_verify_command(ws),
                timeout_s=resolve_verify_timeout_s(ws),
            )
            timing["verify_ms"] = int((time.perf_counter() - t_verify) * 1000)
            if verify_result.passed is False and outcome == OUTCOME_SUCCESS:
                outcome = apply_verify_outcome(
                    outcome,
                    verify_passed=False,
                    files_changed=files_changed,
                )
            elif verify_result.error:
                obs.emit(
                    "verify_command_failed",
                    level="warn",
                    delegation_id=delegation_id,
                    command=verify_result.command,
                    error=verify_result.error,
                )
            context_block["verify"] = verify_result.to_audit_dict(enabled=True)
            if pipeline_recorder is not None:
                if verify_result.error:
                    pipeline_recorder.end(
                        "auto_verify", status="error", detail=verify_result.error[:200]
                    )
                elif verify_result.passed is False:
                    pipeline_recorder.end(
                        "auto_verify",
                        status="error",
                        detail=f"verify failed (exit_code={verify_result.exit_code})",
                    )
                else:
                    pipeline_recorder.end("auto_verify", status="ok")
        elif pipeline_recorder is not None:
            pipeline_recorder.mark(
                "auto_verify",
                status="skipped",
                detail="disabled_or_not_applicable",
            )

        delegation_pipeline_payload = (
            pipeline_recorder.to_list() if pipeline_recorder is not None else None
        )
        if delegation_pipeline_payload is not None:
            context_block["delegation_pipeline"] = delegation_pipeline_payload

        policies_response: dict[str, Any] | None = None
        if (
            delegate_mode == DELEGATE_MODE_IMPLEMENT
            and delegation_policies is not None
            and not spec_invalid_reason
        ):
            policies_response = delegation_policies.to_response_dict()

        mcp_context_summary = (
            build_mcp_context_summary(context_package, capability_warnings=cap_warnings or None)
            if context_package is not None
            else None
        )
        preflight_token_estimate = (
            usage_dict["preflight_tokens_est"] if context_package is not None else None
        )

        t_post = time.perf_counter()
        duration_ms = int((time.perf_counter() - t0) * 1000)
        timing["post_process_ms"] = int((time.perf_counter() - t_post) * 1000)

        checkpoint_block: dict[str, Any] | None = None
        if workspace_snapshot is not None:
            from core.workspace.checkpoint_summary import resolve_checkpoint_summary
            from core.workspace.history_db import WorkspaceHistoryDB
            from core.workspace.snapshot import is_snapshot_enabled

            if is_snapshot_enabled():
                summary = resolve_checkpoint_summary(
                    task=task,
                    spec_path=spec_rel_path,
                    workspace=ws,
                )
                delta = workspace_snapshot.get("delta") or {}
                actual_usage = (usage_dict.get("actual") or {}) if usage_dict else {}
                tokens_total = actual_usage.get("total")
                db = WorkspaceHistoryDB(ws)
                db.finalize_checkpoint_metadata(
                    delegation_id=delegation_id,
                    checkpoint_summary=summary,
                    delegate_mode=delegate_mode,
                    outcome=outcome,
                    model=resolved_model,
                    duration_ms=duration_ms,
                    tokens_total=tokens_total,
                    error_class=error_class if not success else None,
                    delta_created=len(delta.get("created") or []),
                    delta_modified=len(delta.get("modified") or []),
                    delta_deleted=len(delta.get("deleted") or []),
                    spec_report_path=spec_report_rel_path,
                )
                checkpoint_block = {"summary": summary, "outcome": outcome}

        _checkpoint_summary_for_rag: str | None = None
        if checkpoint_block:
            raw_summary = checkpoint_block.get("summary")
            if isinstance(raw_summary, str):
                _checkpoint_summary_for_rag = raw_summary

        from core.rag.index import index_delegation_after_delegate

        index_delegation_after_delegate(
            workspace=ws,
            delegation_id=delegation_id,
            timestamp_end=timestamp_end,
            task=task,
            delegate_mode=delegate_mode,
            outcome=outcome,
            files_changed=files_changed,
            spec_path=spec_rel_path,
            spec_report_path=spec_report_rel_path,
            checkpoint_summary=_checkpoint_summary_for_rag,
        )

        from core.rag.workspace_indexer import index_workspace_paths_after_delegate

        index_workspace_paths_after_delegate(ws, files_changed)

        # P13-006: agent owns postloop phase end + lifecycle end (non-fatal reviewer)
        if _postloop_started and supervisor_agent is not None and not _lifecycle_closed:
            _postloop_status = "ok"
            _lifecycle_final_outcome = outcome or ("success" if success else "error")
            _close_lifecycle_once(
                _lifecycle_final_outcome,
                phase="postloop",
                phase_status=_postloop_status,
            )

        delegation_diff_payload: dict[str, Any] | None = None
        judgment_checklist_payload: dict[str, Any] | None = None
        if delegate_mode == DELEGATE_MODE_IMPLEMENT and workspace_snapshot is not None:
            from core.workspace.history_query import safe_delegation_diff_dict
            from core.workspace.judgment_checklist import build_judgment_checklist

            delegation_diff_payload = safe_delegation_diff_dict(ws, delegation_id)
            if delegation_diff_payload is not None:
                judgment_checklist_payload = build_judgment_checklist(
                    delegation_diff=delegation_diff_payload,
                    files_unexpected=files_unexpected,
                )

        from core.workspace.prior_attempts import (
            PRIOR_FAILED_ATTEMPTS_REMINDER,
            find_prior_failed_attempts,
        )

        prior_failed_attempts_payload = find_prior_failed_attempts(
            ws,
            spec_path=spec_rel_path or spec_path,
            mcp_session_id=storage.mcp_session_id,
            exclude_delegation_id=delegation_id,
        )
        prior_failed_reminder = (
            PRIOR_FAILED_ATTEMPTS_REMINDER if prior_failed_attempts_payload else None
        )

        model_roles_payload = _build_model_roles_payload(
            delegation_id=delegation_id,
            delegate_mode=delegate_mode,
            resolved_model=resolved_model,
            tokens=tokens,
            timing=timing,
            workspace=ws,
            builder_record=builder_record,
            spec_validation_record=spec_validation_record,
            clarity_check_record=clarity_check_record,
            reviewer_record=reviewer_pass_record,
            architect_record=architect_record,
            supervisor_record=_supervisor_record_from_tokens(tokens),
        )

        suggested_edit_paths_payload: list[str] | None = (
            picker_result.suggested_edit_paths or None if picker_result is not None else None
        )
        server_status_payload = _build_server_status(ws)

        response = _response_payload(
            success=success,
            output=output,
            files_changed=files_changed,
            files_unexpected=files_unexpected,
            session_reused=storage.session_action == "reuse",
            session_reason=(
                "resumed" if _resumed_from_pause_token is not None
                else storage.session_reason
            ),
            session_policy=(
                "resume" if _resumed_from_pause_token is not None
                else storage.session_policy
            ),
            mcp_session_id=storage.mcp_session_id,
            log_path=str(storage.log_path),
            host_kind=host_hint.host_kind,
            host_session_id=host_hint.host_session_id,
            executor_reused=executor_reused,
            executor_recreated=executor_recreated,
            outcome=outcome,
            spec_path=spec_rel_path,
            spec_report_path=spec_report_rel_path,
            spec_sha256=spec_sha256,
            spec_bytes=spec_bytes,
            delegate_mode=delegate_mode,
            spec_files_missing_from_target=spec_files_missing or None,
            contract_warnings=contract_warnings or None,
            delegation_policies=policies_response,
            scope_violations=scope_violations or None,
            reverted_paths=reverted_paths or None,
            revert_skipped=revert_skipped or None,
            usage=usage_dict if usage_report_enabled else None,
            usage_warnings=usage_warnings if usage_report_enabled else None,
            error_class=error_class if not success else None,
            error_message=error_message if not success else None,
            context_package_summary=mcp_context_summary,
            capability_warnings=cap_warnings or None,
            preflight_token_estimate=preflight_token_estimate,
            delegation_diff=delegation_diff_payload,
            judgment_checklist=judgment_checklist_payload,
            prior_failed_attempts=prior_failed_attempts_payload or None,
            prior_failed_attempts_reminder=prior_failed_reminder,
            auto_merged_read_paths=auto_merged_read_paths or None,
            auto_merge_spec_read=auto_merge_spec_read,
            model_roles=model_roles_payload,
            suggested_edit_paths=suggested_edit_paths_payload,
            context_builder_llm_enabled=builder_llm_enabled if picker_result is not None else None,
            builder_brief_applied=builder_brief_applied if builder_llm_enabled else None,
            auto_verify_enabled_flag=verify_enabled if verify_result is not None else None,
            verify_result=verify_result.to_response_dict() if verify_result is not None else None,
            clarification_needed=clarification_needed,
            clarity_questions=clarity_check_questions or None,
            clarity_round_index=clarity_round_index,
            clarity_round_cap=clarity_round_cap,
            clarity_auto_passed=clarity_auto_passed,
            reviewer_mode=reviewer_policy_fields.get("reviewer_mode"),
            reviewer_outcome=reviewer_policy_fields.get("reviewer_outcome"),
            reviewer_action=reviewer_policy_fields.get("reviewer_action"),
            spec_validation_ran=spec_validation_ran,
            spec_validation_passed=spec_validation_passed,
            delegation_pipeline=delegation_pipeline_payload,
            executor_turns=_executor_turns if _executor_turns > 0 else None,
            needs_input=needs_input_payload,
            paused_questions=(
                supervisor_paused_questions if outcome == OUTCOME_NEEDS_INPUT else None
            ),
            auto_retried=stall_auto_retried,
            stall_type=stall_type,
            server_status=server_status_payload,
        )
        if host_policy_overrides:
            response["model_policy_applied"] = summarize_model_policy_applied(
                host_policy_overrides
            )
        if model_policy_warnings:
            response["model_policy_warnings"] = model_policy_warnings
        done_status = "needs_input" if outcome == OUTCOME_NEEDS_INPUT else ("success" if success else "failure")
        progress.notify(f"[done] Delegation complete — {done_status}.", force=True)

        if auto_merged_read_paths:
            mcp_request["auto_merged_read_paths"] = auto_merged_read_paths
            mcp_request["effective_target_files"] = effective_target_files
        if spec_files_missing:
            mcp_request["spec_files_missing_from_target"] = spec_files_missing
        if contract_warnings:
            mcp_request["contract_warnings"] = contract_warnings
        if policies_response is not None:
            mcp_request["delegation_policies"] = policies_response
        if scope_violations:
            mcp_request["scope_violations"] = scope_violations

        reasoning_summary = obs.finalize_reasoning_summary(delegation_id)
        if reasoning_summary:
            context_block["reasoning_summary"] = reasoning_summary
            obs.record_reasoning_in_session(
                storage.mcp_session_id,
                delegation_id,
                reasoning_summary,
                buffer_size=obs.resolve_reasoning_buffer_size(ws),
            )

        if host_policy_overrides:
            context_block["model_policy_applied"] = summarize_model_policy_applied(
                host_policy_overrides
            )
        if model_policy_warnings:
            context_block["model_policy_warnings"] = model_policy_warnings

        _obs_verbosity = resolve_observability_verbosity(ws)
        _trace_ref = (
            f"traces/{delegation_id}.jsonl"
            if _obs_verbosity in ("standard", "full")
            else None
        )

        record = obs.build_delegation_record(
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
            files_requested=list(planner_target_files),
            files_changed=files_changed,
            files_unexpected=files_unexpected,
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
            prompt_full=executor_prompt,
            spec_path=spec_rel_path,
            spec_report_path=spec_report_rel_path,
            spec_sha256=spec_sha256,
            spec_mtime=spec_mtime,
            outcome=outcome,
            delegate_mode=delegate_mode,
            spec_files_missing_from_target=spec_files_missing or None,
            contract_warnings=contract_warnings or None,
            delegation_policies=policies_response,
            scope_violations=scope_violations or None,
            usage=usage_dict,
            error_class=error_class if not success else None,
            error_message=error_message if not success else None,
            workspace_snapshot=workspace_snapshot,
            post_gateway=post_gateway,
            checkpoint=checkpoint_block,
            auto_merged_read_paths=auto_merged_read_paths or None,
            auto_merge_spec_read=auto_merge_spec_read,
            model_roles=model_roles_payload,
            context_refs=(
                context_refs_to_lean_dict(rag_retrieval_refs) if rag_retrieval_on else None
            ),
            trace_ref=_trace_ref,
        )
        log_path = obs.append_delegation_record(record, ws=ws)
        _delegation_record_appended = True  # P13-008: normal completion path
        obs.log_delegation_sent(
            delegation_id=delegation_id,
            success=success,
            duration_ms=duration_ms,
            files_changed=files_changed,
            log_path=log_path,
            error=error,
        )

        pipeline_flags_runtime = {
            "context_builder_llm_enabled": (
                builder_llm_enabled if picker_result is not None else None
            ),
            "builder_brief_applied": builder_brief_applied if builder_llm_enabled else None,
            "spec_validation_ran": spec_validation_ran,
            "spec_validation_passed": spec_validation_passed,
            "auto_verify_enabled": verify_enabled if verify_result is not None else None,
            "rag_retrieval_on": rag_retrieval_on,
        }
        obs.write_training_capture_if_enabled(
            workspace=ws,
            session_dir=storage.session_dir,
            delegation_id=delegation_id,
            timestamp_end=timestamp_end,
            task=task,
            context_package_hash=context_package_hash,
            reasoning_summary=reasoning_summary,
            outcome=outcome,
            verify_result=(
                verify_result.to_response_dict() if verify_result is not None else None
            ),
            success=success,
            model_roles=model_roles_payload,
            pipeline_flags_runtime=pipeline_flags_runtime,
        )

        if cli_artifacts:
            from core.delegation.artifacts import delegation_envelope, full_run_artifacts

            read_entries_in_prompt: list[str] = []
            fnames_for_cli: list[str] = []
            if context_package is not None:
                read_entries_in_prompt = [
                    e.path
                    for e in context_package.entries
                    if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT) and e.payload is not None
                ]
                fnames_for_cli = sorted(
                    e.path for e in context_package.entries if e.tier == TIER_EDIT_FULL
                )
            envelope = delegation_envelope(
                ok=bool(success) and not clarity_check_blocked,
                stop_after="full",
                artifacts=full_run_artifacts(
                    caller_response=response,
                    executor_prompt=executor_prompt,
                    fnames=fnames_for_cli,
                    read_paths_in_prompt=read_entries_in_prompt,
                    capability_warnings=cap_warnings or None,
                ),
                caller_response=response,
                error=error if (not success or clarity_check_blocked) else None,
            )
            return json.dumps(envelope, ensure_ascii=False)

        return json.dumps(response, ensure_ascii=False)
    finally:
        # P13-008 (ISS-009): if the delegation was interrupted (host cancel,
        # uncaught exception) before the normal completion path appended a
        # record, append a minimal "interrupted" record now so delegations.jsonl
        # stays 1:1 with the trace tree. Best-effort: never mask the original
        # exception.
        if (
            _interrupted_record_armed
            and not _delegation_record_appended
            and storage is not None
        ):
            try:
                _close_lifecycle_once(
                    "error",
                    phase_status="error",
                    detail="interrupted",
                )
                _ts_end = obs.utc_now_iso()
                _dur = int((time.perf_counter() - t0) * 1000)
                _interrupted_record = obs.build_delegation_record(
                    delegation_id=delegation_id,
                    timestamp_start=timestamp_start,
                    timestamp_end=_ts_end,
                    duration_ms=_dur,
                    mcp_request=mcp_request,
                    backend=backend,
                    model=model,
                    success=False,
                    error="interrupted before completion",
                    response_to_cursor={
                        "success": False,
                        "output": "interrupted before completion",
                        "files_changed": [],
                        "outcome": "interrupted",
                    },
                    files_requested=list(target_files),
                    files_changed=[],
                    files_unexpected=[],
                    context_block={},
                    context_mode=None,
                    timing=None,
                    tokens=None,
                    project_key=storage.project_key,
                    mcp_session_id=storage.mcp_session_id,
                    session_dir=storage.session_dir,
                    log_path=storage.log_path,
                    session_action=storage.session_action,
                    session_reason=storage.session_reason,
                    session_policy=storage.session_policy,
                    host_kind=None,
                    host_session_id=None,
                    host_transcript_path=None,
                    host_context=None,
                    executor_reused=False,
                    executor_recreated=False,
                    prompt_full=None,
                    spec_path=spec_rel_path,
                    spec_report_path=None,
                    spec_sha256=None,
                    spec_mtime=None,
                    outcome="interrupted",
                    delegate_mode=delegate_mode,
                    spec_files_missing_from_target=None,
                    contract_warnings=None,
                    delegation_policies=None,
                    scope_violations=None,
                    usage=None,
                    error_class="interrupted",
                    error_message="delegation interrupted before completion",
                    workspace_snapshot=None,
                    post_gateway=None,
                    checkpoint=None,
                    auto_merged_read_paths=None,
                    auto_merge_spec_read=None,
                    model_roles=None,
                    context_refs=None,
                    trace_ref=(
                        f"traces/{delegation_id}.jsonl"
                        if _obs_verbosity in ("standard", "full")
                        else None
                    ),
                )
                obs.append_delegation_record(_interrupted_record, ws=ws)
            except Exception:
                # Best-effort: never mask the original exception/cancel.
                pass
        if host_policy_token is not None:
            host_model_policy_var.reset(host_policy_token)
        _delegation_scope.__exit__(None, None, None)
        progress.close()


@mcp.tool(
    name="inspect_context",
    description=(
        "DRY-RUN CONTEXT INSPECTOR: Compile ContextPackage and adapter preview "
        "(fnames, read paths in prompt) without calling the execution backend. "
        "No file edits by default; optional helper LLM flags via CLI only. "
        "Set include_prompt=true for full executor prompt text in adapter_preview. "
        "Use before delegate_to_agent to verify read-deps and edit scope. "
        "Required: task, target_files, context_summary. "
        "Optional spec_path under .mcp-coder/specs/tasks/."
    ),
)
def inspect_context(
    task: str,
    target_files: list[str],
    context_summary: str,
    spec_path: str | None = None,
    include_payloads: bool = False,
    include_adapter_preview: bool = True,
    include_prompt: bool = False,
) -> str:
    """Return assembled context package + adapter preview as JSON (dry-run only)."""
    ws = obs.default_workspace_path()
    result = inspect_context_package(
        workspace=Path(ws),
        task=task,
        target_files=target_files,
        context_summary=context_summary,
        spec_path=spec_path,
        include_payloads=include_payloads,
        include_adapter_preview=include_adapter_preview,
        include_prompt=include_prompt,
        host_transcript=None,
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool(
    name="get_server_status",
    description=(
        "Return MCP server runtime identity + freshness signals (pid, source revision, "
        "process start time, dirty-worktree comparison, stale sibling pids). "
        "Use this to quickly confirm Cursor is connected to the latest local server code."
    ),
)
def get_server_status(workspace_path: str | None = None) -> str:
    ws = workspace_path or obs.default_workspace_path()
    return json.dumps(_build_server_status(ws), ensure_ascii=False)


@mcp.tool(
    name="list_delegations",
    description=(
        "List recent delegation checkpoints from workspace_history.db with "
        "summary labels and delta counts. Optional filters: spec_path, file_path."
    ),
)
def list_delegations_tool(
    limit: int = 20,
    spec_path: str | None = None,
    file_path: str | None = None,
    workspace_path: str | None = None,
) -> str:
    """Browse recent checkpoints (read-only)."""
    from core.workspace.history_query import list_delegations_for_mcp

    ws = workspace_path or obs.default_workspace_path()
    result = list_delegations_for_mcp(
        ws, limit=limit, spec_path=spec_path, file_path=file_path
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool(
    name="get_checkpoint_detail",
    description=(
        "Return checkpoint metadata and created/modified/deleted path lists "
        "without unified diff bodies. Use delegation_id from delegate_to_agent "
        "or latest=true for the most recent checkpoint."
    ),
)
def get_checkpoint_detail(
    delegation_id: str | None = None,
    latest: bool = False,
    workspace_path: str | None = None,
) -> str:
    """Lightweight checkpoint inspect (read-only)."""
    from core.workspace.history_query import checkpoint_detail_for_mcp

    ws = workspace_path or obs.default_workspace_path()
    result = checkpoint_detail_for_mcp(
        ws, delegation_id, latest=latest
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool(
    name="get_file_history",
    description=(
        "Per-file timeline: which delegations touched a path and what changed "
        "each time. Includes unified diff for modified rows when stored."
    ),
)
def get_file_history(
    file_path: str,
    limit: int = 20,
    workspace_path: str | None = None,
) -> str:
    """File change timeline across checkpoints (read-only)."""
    from core.workspace.history_query import file_history_for_mcp

    ws = workspace_path or obs.default_workspace_path()
    result = file_history_for_mcp(ws, file_path, limit=limit)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool(
    name="get_delegation_diff",
    description=(
        "Return unified diffs and file delta summary for a delegation checkpoint "
        "from workspace_history.db. Prefer delegation_id from delegate_to_agent; "
        "use latest=true for the most recent checkpoint. Optional file_path "
        "filters diffs to a single file."
    ),
)
def get_delegation_diff(
    delegation_id: str | None = None,
    latest: bool = False,
    file_path: str | None = None,
    workspace_path: str | None = None,
) -> str:
    """Fetch delegation_diff for a past delegation (read-only)."""
    from core.workspace.history_query import delegation_diff_for_mcp

    ws = workspace_path or obs.default_workspace_path()
    result = delegation_diff_for_mcp(
        ws,
        delegation_id,
        latest=latest,
        file_path=file_path,
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool(
    name="rag_search",
    description=(
        "Keyword search over indexed past delegations (checkpoint summaries, tasks, "
        "spec paths, outcomes). Returns ranked hits with delegation_id — pair with "
        "get_delegation_diff or list_delegations for full detail."
    ),
)
def rag_search_tool(
    query: str,
    limit: int = 5,
    workspace_path: str | None = None,
    spec_path_prefix: str | None = None,
    outcome: str | None = None,
) -> str:
    """Search delegation RAG index (read-only)."""
    from core.rag.search import rag_search_for_mcp

    ws = workspace_path or obs.default_workspace_path()
    result = rag_search_for_mcp(
        ws,
        query,
        limit=limit,
        spec_path_prefix=spec_path_prefix,
        outcome=outcome,
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool(
    name="workspace_search",
    description=(
        "Keyword search over indexed workspace source files (LLM summaries + symbol "
        "outlines in workspace_rag.db). Parity with mcp-coder search files CLI. "
        "Requires workspace_file_rag: true and mcp-coder index-workspace."
    ),
)
def workspace_search_tool(
    query: str,
    limit: int = 5,
    workspace_path: str | None = None,
) -> str:
    """Search workspace-file RAG index (read-only)."""
    from core.rag.workspace_search import workspace_search_for_mcp

    ws = workspace_path or obs.default_workspace_path()
    result = workspace_search_for_mcp(ws, query, limit=limit)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool(
    name="answer_delegation_question",
    description=(
        "Unblock a paused delegation by providing a human answer to an escalated "
        "supervisor question. Call this while delegate_to_agent is running and has "
        "emitted a [gate] notification. "
        "delegation_id: the active delegation ID shown in the notification. "
        "answer: 'yes' or 'no' (or any text — 'yes'/'y'/'true'/'1' = approve)."
    ),
)
def answer_delegation_question(delegation_id: str, answer: str) -> str:
    """Route the human answer to the waiting delegation thread."""
    from core.engine.question_registry import _REGISTRY

    found = _REGISTRY.answer(delegation_id, answer)
    if found:
        return json.dumps({"status": "ok", "delegation_id": delegation_id, "answer": answer})
    return json.dumps({"status": "not_found", "delegation_id": delegation_id})


@mcp.tool(
    name="get_project_cost",
    description=(
        "Return a per-project cost report aggregated from delegation logs. "
        "Shows total USD spent, breakdown by model, by role (executor, planner_pass, "
        "supervisor, clarity_check, reviewer_pass, spec_validation), and by task "
        "(spec_path). Executor tokens are included when captured via litellm callback; "
        "runs where tokens were unavailable appear in uncaptured_roles with 0 cost. "
        "HOST COSTS ARE NOT INCLUDED (cursor, IDE, etc.). "
        "Optional: project_key filters to one epic; limit caps the delegation count. "
        "Returns JSON string."
    ),
)
def get_project_cost(
    project_key: str | None = None,
    limit: int = 50,
) -> str:
    """Aggregate cost data from delegation logs and return JSON report."""
    try:
        from core.logging.cost_report import build_project_cost_report

        ws = obs.default_workspace_path()
        report = build_project_cost_report(ws, project_key=project_key, limit=limit)
        return json.dumps(report, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)


def run_stdio() -> None:
    _log_role_model_startup()
    mcp.run(transport="stdio")


def _log_role_model_startup() -> None:
    """Emit one server log line per role showing the resolved model at startup (P11-ISS-009)."""
    try:
        from core.config.role_models import (
            ROLE_CONTEXT_BUILDER,
            ROLE_EXECUTOR,
            ROLE_PLANNER,
            ROLE_REVIEWER,
            ROLE_SUPERVISOR,
            resolve_role_model_name,
        )
        from core.logging.server_log import server_log_emit

        roles = [ROLE_EXECUTOR, ROLE_PLANNER, ROLE_CONTEXT_BUILDER, ROLE_SUPERVISOR, ROLE_REVIEWER]
        resolved = {role: resolve_role_model_name(role, workspace=".") for role in roles}
        server_log_emit(
            "role_models_resolved",
            level="info",
            models=resolved,
            hint="restart MCP server after .env changes to pick up new models",
        )
    except Exception:
        pass
