from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from core.config.auto_merge import auto_merge_spec_read_enabled
from core.config.auto_verify import (
    auto_verify_enabled,
    resolve_verify_command,
    resolve_verify_timeout_s,
)
from core.config.architect_pass import architect_pass_enabled
from core.config.context_builder import (
    context_builder_enabled,
    context_builder_llm_enabled,
)
from core.config.spec_validation import spec_validation_enabled
from core.config.models import resolve_model_name
from core.config.role_models import (
    ROLE_CONTEXT_BUILDER,
    ROLE_EXECUTOR,
    ROLE_REVIEW,
    resolve_role_model_name,
)
from core.context.assemble import assemble_context
from core.context.file_picker import CandidateFilesResult, pick_candidate_files
from core.context.budget import apply_context_budget, resolve_context_budget_tokens
from core.context.capability_adjust import apply_backend_capabilities
from core.context.helper_llm_pipeline import (
    SPEC_VALIDATION_BLOCK_OUTPUT,
    apply_architect_pass as _shared_apply_architect_pass,
    apply_builder_llm as _shared_apply_builder_llm,
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
    summarize_context_package,
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
from core.engine import get_engine, list_backends
from core.engine.factory import UnknownBackendError
from core.session.policy import resolve_session_policy
from core.session.store import SessionStore
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
from core.pipeline.phases import PipelineRecorder
from core.usage import (
    build_usage_report,
    build_usage_warnings,
    format_usage_run_log_line,
    resolve_usage_report_enabled,
)
from core.usage.role_audit import build_role_usage_record, merge_model_roles

OUTPUT_MAX_CHARS = 16_000


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


def _server_log_warn(event: str, fields: dict[str, Any]) -> None:
    server_log_emit(event, level="warn", **fields)


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
) -> tuple["ContextPackage", bool, str | None, dict[str, Any] | None]:
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
        log_warn=_server_log_warn,
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
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    return _shared_apply_architect_pass(
        context_package=context_package,
        spec_read=spec_read,
        picker_result=picker_result,
        workspace=workspace,
        task=task,
        context_summary=context_summary,
        host_transcript=host_transcript,
        timing=timing,
        delegation_id=delegation_id,
        log_warn=_server_log_warn,
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
]:
    return _shared_apply_spec_validation(
        spec_read=spec_read,
        workspace=workspace,
        task=task,
        context_summary=context_summary,
        host_transcript=host_transcript,
        timing=timing,
        delegation_id=delegation_id,
        log_warn=_server_log_warn,
    )


_SPEC_VALIDATION_BLOCK_OUTPUT = SPEC_VALIDATION_BLOCK_OUTPUT


def _build_model_roles_payload(
    *,
    delegate_mode: str,
    resolved_model: str,
    tokens: dict[str, Any],
    timing: dict[str, int | float],
    workspace: str,
    builder_record: dict[str, Any] | None = None,
    spec_validation_record: dict[str, Any] | None = None,
    architect_record: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Per-role audit block for JSONL + MCP response (D-P4-8 Stage 1)."""
    engine_ms = timing.get("engine_run_ms")
    duration_ms = int(engine_ms) if engine_ms is not None else None

    if delegate_mode == DELEGATE_MODE_REVIEW:
        roles = merge_model_roles(
            build_role_usage_record(
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
        roles = merge_model_roles(
            build_role_usage_record(
                role=ROLE_EXECUTOR,
                model=resolve_role_model_name(ROLE_EXECUTOR, workspace),
                source="executor",
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
    spec_validation_ran: bool | None = None,
    spec_validation_passed: bool | None = None,
    delegation_pipeline: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
    if spec_validation_ran is not None:
        payload["spec_validation_ran"] = spec_validation_ran
    if spec_validation_passed is not None:
        payload["spec_validation_passed"] = spec_validation_passed
    if delegation_pipeline is not None:
        payload["delegation_pipeline"] = delegation_pipeline
    return payload


@mcp.tool(
    name="delegate_to_agent",
    description=(
        "IMPLEMENTATION DELEGATE: Run Aider to edit files on disk. Use this instead of "
        "writing code yourself when the user asks to build, create, or change project files "
        "(web pages, scripts, multi-file features). Required: task, target_files (repo-relative), "
        "context_summary (decisions from chat—the delegate cannot see history). "
        "Optional spec_path: step task under .mcp-coder/specs/tasks/ (e.g. tasks/my-epic-02-cli.md). "
        "mode: implement (default) edits target_files; review asks questions only (target_files must be []). "
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
    ws = workspace_path()
    usage_report_enabled = resolve_usage_report_enabled(ws)
    ensure_workspace_spec_layout(ws)

    spec_rel_path: str | None = None
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

    pipeline_recorder: PipelineRecorder | None = None
    if (
        delegate_mode == DELEGATE_MODE_IMPLEMENT
        and spec_read is not None
        and not spec_invalid_reason
    ):
        pipeline_recorder = PipelineRecorder()
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
    error_class: str | None = None
    error_message: str | None = None
    files_changed: list[str] = []
    files_unexpected: list[str] = []
    output = ""
    tokens: dict[str, Any] = {"source": "unavailable"}
    executor_reused = False
    executor_recreated = False
    workspace_snapshot: dict[str, Any] | None = None
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
                server_log_emit(
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
    architect_plan_applied = False
    architect_pass_error: str | None = None
    architect_record: dict[str, Any] | None = None
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

    if (
        pipeline_recorder is not None
        and not review_target_files_error
        and spec_validation_enabled(ws)
    ):
        if host_transcript_text and host_transcript_text.strip():
            pipeline_recorder.start("spec_validation")
            (
                spec_validation_blocked,
                clarification_needed,
                spec_validation_ran,
                spec_validation_passed,
                _spec_val_err,
                spec_validation_audit,
                spec_validation_record,
            ) = _apply_spec_validation(
                spec_read=spec_read,
                workspace=ws,
                task=task,
                context_summary=context_summary,
                host_transcript=host_transcript_text,
                timing=timing,
                delegation_id=delegation_id,
            )
            if spec_validation_blocked:
                pipeline_recorder.end("spec_validation", status="blocked")
            elif _spec_val_err:
                pipeline_recorder.end(
                    "spec_validation", status="error", detail=_spec_val_err[:200]
                )
            else:
                pipeline_recorder.end("spec_validation", status="ok")
        else:
            pipeline_recorder.mark(
                "spec_validation",
                status="skipped",
                detail="empty_host_transcript",
            )
    elif pipeline_recorder is not None and not review_target_files_error:
        pipeline_recorder.mark(
            "spec_validation",
            status="skipped",
            detail="disabled",
        )

    if spec_invalid_reason:
        success = False
        error = spec_invalid_reason
        output = spec_invalid_reason
    elif review_target_files_error:
        success = False
        error = review_target_files_error
        output = review_target_files_error
    elif spec_validation_blocked:
        success = False
        error = None
        output = _SPEC_VALIDATION_BLOCK_OUTPUT
    else:
        executor_phase_started = False
        try:
            t_engine = time.perf_counter()
            if delegate_mode == DELEGATE_MODE_REVIEW:
                result = run_spec_review(prompt, workspace_path=ws)
            elif _use_pkg:
                builder_on = context_builder_enabled(ws)
                if builder_on and delegation_policies is not None:
                    if pipeline_recorder is not None:
                        pipeline_recorder.start("file_picker")
                    try:
                        picker_result = pick_candidate_files(
                            workspace=Path(ws),
                            task=task,
                            spec_text=spec_read.raw_text if spec_read else None,
                            policies=delegation_policies,
                            target_files=effective_target_files,
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

                architect_enabled = architect_pass_enabled(ws)
                if architect_enabled:
                    if pipeline_recorder is not None:
                        pipeline_recorder.start("architect_pass")
                    (
                        architect_plan,
                        architect_pass_error,
                        architect_record,
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
                    )
                    if architect_plan:
                        architect_plan_applied = True
                    if pipeline_recorder is not None:
                        if architect_pass_error:
                            pipeline_recorder.end(
                                "architect_pass",
                                status="error",
                                detail=architect_pass_error[:200],
                            )
                        else:
                            pipeline_recorder.end("architect_pass", status="ok")
                elif pipeline_recorder is not None:
                    pipeline_recorder.mark(
                        "architect_pass",
                        status="skipped",
                        detail="disabled",
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
                    )
                    if pipeline_recorder is not None:
                        if builder_llm_error:
                            pipeline_recorder.end(
                                "builder_llm", status="error", detail=builder_llm_error[:200]
                            )
                        else:
                            pipeline_recorder.end("builder_llm", status="ok")
                elif pipeline_recorder is not None:
                    pipeline_recorder.mark(
                        "builder_llm",
                        status="skipped",
                        detail="disabled",
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
                if pipeline_recorder is not None:
                    pipeline_recorder.start("executor")
                    executor_phase_started = True
                result = engine.run_context(
                    context_package,
                    workspace_path=ws,
                    mcp_session_id=storage.mcp_session_id,
                    host_transcript=host_transcript_text,
                    delegation_id=delegation_id,
                    spec_path=spec_rel_path,
                    timestamp_start=timestamp_start,
                )
                executor_prompt = result.prompt_used or context_package.brief
            else:
                if pipeline_recorder is not None:
                    pipeline_recorder.mark(
                        "file_picker",
                        status="skipped",
                        detail="context_package_disabled",
                    )
                    pipeline_recorder.mark(
                        "context_assemble",
                        status="skipped",
                        detail="context_package_disabled",
                    )
                    pipeline_recorder.mark(
                        "architect_pass",
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
                result = engine.run(
                    prompt,
                    effective_target_files,
                    workspace_path=ws,
                    mcp_session_id=storage.mcp_session_id,
                    delegation_id=delegation_id,
                    spec_path=spec_rel_path,
                    contract_paths=legacy_contract,
                    timestamp_start=timestamp_start,
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
            if not success and error:
                _ec, error_message = classify_delegation_error(error)
                if not error_class:
                    error_class = _ec
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
    context_block = prompt_metadata(
        executor_prompt,
        context_summary=context_summary,
        transcript_meta=transcript_meta,
    )
    if spec_validation_audit is not None:
        context_block["spec_validation"] = spec_validation_audit
    if context_package is not None:
        read_entries_in_prompt = [
            e
            for e in context_package.entries
            if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT) and e.payload is not None
        ]
        context_block["context_package"] = summarize_context_package(context_package)
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
            context_block["architect_pass_enabled"] = architect_enabled
            context_block["architect_plan_applied"] = architect_plan_applied
            if architect_pass_error:
                context_block["architect_pass_error"] = architect_pass_error
            if builder_llm_enabled:
                context_block["builder_brief_applied"] = builder_brief_applied
                if builder_llm_error:
                    context_block["builder_llm_error"] = builder_llm_error
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

    usage_dict = build_usage_report(
        model=resolved_model,
        prompt=executor_prompt,
        actual_tokens=tokens,
        preflight_tokens_est=int(context_block.get("prompt_tokens_est") or 0),
        preflight_chars=int(context_block.get("prompt_chars") or len(executor_prompt)),
    )
    usage_summary_line = format_usage_run_log_line(usage_dict)
    context_block["token_estimate_preflight"] = usage_dict["preflight_tokens_est"]
    usage_warnings = build_usage_warnings(usage_dict["preflight_tokens_est"])

    timestamp_end = utc_now_iso()
    spec_sha256: str | None = spec_read.sha256 if spec_read else None
    spec_bytes: int | None = spec_read.file_bytes if spec_read else None
    spec_mtime: str | None = spec_read.mtime_iso if spec_read else None
    outcome: str | None = None
    scope_violations: list[str] = []
    reverted_paths: list[str] = []
    revert_skipped: list[str] = []
    post_gateway: dict[str, Any] | None = None
    spec_report_rel_path: str | None = None

    if (
        spec_path
        and not spec_invalid_reason
        and delegate_mode == DELEGATE_MODE_IMPLEMENT
        and delegation_policies is not None
    ):
        if pipeline_recorder is not None and not spec_validation_blocked:
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
        if pipeline_recorder is not None and not spec_validation_blocked:
            pipeline_recorder.end("post_gateway", status="ok")

    if spec_validation_blocked:
        outcome = OUTCOME_NEEDS_INPUT
    elif spec_path:
        if spec_invalid_reason:
            outcome = OUTCOME_INVALID_SPEC
        elif spec_abs_path is not None and spec_abs_path.is_file():
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
                    server_log_emit(
                        "spec_scope_violation",
                        level="warn",
                        delegation_id=delegation_id,
                        spec_path=spec_rel_path,
                        scope_violations=scope_violations,
                        edit_scope=delegation_policies.edit_scope,
                    )
            if pipeline_recorder is not None:
                pipeline_recorder.end("spec_report", status="ok")

    verify_result: VerifyResult | None = None
    verify_enabled = auto_verify_enabled(ws)
    if (
        verify_enabled
        and delegate_mode == DELEGATE_MODE_IMPLEMENT
        and spec_path
        and not spec_invalid_reason
        and success
        and files_changed
        and not spec_validation_blocked
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
            server_log_emit(
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
    elif pipeline_recorder is not None and not spec_validation_blocked:
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
        delegate_mode=delegate_mode,
        resolved_model=resolved_model,
        tokens=tokens,
        timing=timing,
        workspace=ws,
        builder_record=builder_record,
        spec_validation_record=spec_validation_record,
        architect_record=architect_record,
    )

    suggested_edit_paths_payload: list[str] | None = (
        picker_result.suggested_edit_paths or None if picker_result is not None else None
    )

    response = _response_payload(
        success=success,
        output=output,
        files_changed=files_changed,
        files_unexpected=files_unexpected,
        session_reused=storage.session_action == "reuse",
        session_reason=storage.session_reason,
        session_policy=storage.session_policy,
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
        spec_validation_ran=spec_validation_ran,
        spec_validation_passed=spec_validation_passed,
        delegation_pipeline=delegation_pipeline_payload,
    )
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
        prompt_full=executor_prompt if should_log_full_prompt() else None,
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
            ok=bool(success) and not spec_validation_blocked,
            stop_after="full",
            artifacts=full_run_artifacts(
                caller_response=response,
                executor_prompt=executor_prompt,
                fnames=fnames_for_cli,
                read_paths_in_prompt=read_entries_in_prompt,
                capability_warnings=cap_warnings or None,
            ),
            caller_response=response,
            error=error if (not success or spec_validation_blocked) else None,
        )
        return json.dumps(envelope, ensure_ascii=False)

    return json.dumps(response, ensure_ascii=False)


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
    ws = workspace_path()
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
    from core.logging.delegation_log import workspace_path as default_workspace
    from core.workspace.history_query import list_delegations_for_mcp

    ws = workspace_path or default_workspace()
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
    from core.logging.delegation_log import workspace_path as default_workspace
    from core.workspace.history_query import checkpoint_detail_for_mcp

    ws = workspace_path or default_workspace()
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
    from core.logging.delegation_log import workspace_path as default_workspace
    from core.workspace.history_query import file_history_for_mcp

    ws = workspace_path or default_workspace()
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
    from core.logging.delegation_log import workspace_path as default_workspace
    from core.workspace.history_query import delegation_diff_for_mcp

    ws = workspace_path or default_workspace()
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
    from core.logging.delegation_log import workspace_path as default_workspace
    from core.rag.search import rag_search_for_mcp

    ws = workspace_path or default_workspace()
    result = rag_search_for_mcp(
        ws,
        query,
        limit=limit,
        spec_path_prefix=spec_path_prefix,
        outcome=outcome,
    )
    return json.dumps(result, ensure_ascii=False)


def run_stdio() -> None:
    mcp.run(transport="stdio")
