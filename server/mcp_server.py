from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from core.config.models import resolve_model_name
from core.context.assemble import assemble_context
from core.context.budget import apply_context_budget, resolve_context_budget_tokens
from core.context.capability_adjust import apply_backend_capabilities
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
    compute_scope_violations,
    load_delegation_policies,
)
from core.specs.files_contract import build_contract_warnings, paths_missing_from_target
from core.specs.modes import DELEGATE_MODE_IMPLEMENT, DELEGATE_MODE_REVIEW, normalize_delegate_mode
from core.specs.outcome import (
    OUTCOME_INVALID_SPEC,
    apply_scope_outcome,
    compute_spec_outcome,
)
from core.specs.paths import normalize_spec_path_arg, resolve_spec_path
from core.specs.read import read_task_spec
from core.specs.write import apply_post_delegation_report_updates
from core.usage import (
    build_usage_report,
    build_usage_warnings,
    format_usage_run_log_line,
    resolve_usage_report_enabled,
)

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
    usage: dict[str, Any] | None = None,
    usage_warnings: list[str] | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    context_package_summary: dict[str, Any] | None = None,
    capability_warnings: list[str] | None = None,
    preflight_token_estimate: int | None = None,
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
        "MCP appends audit to specs/reports/<same-name>.md. Returns success, output, files_changed, outcome. "
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

    spec_files_missing: list[str] = []
    contract_warnings: list[str] = []
    if (
        delegate_mode == DELEGATE_MODE_IMPLEMENT
        and delegation_policies is not None
        and not spec_invalid_reason
    ):
        if delegation_policies.all_paths:
            spec_files_missing = paths_missing_from_target(
                delegation_policies.all_paths, target_files
            )
            contract_warnings = build_contract_warnings(spec_files_missing)
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

    if spec_invalid_reason:
        success = False
        error = spec_invalid_reason
        output = spec_invalid_reason
    elif review_target_files_error:
        success = False
        error = review_target_files_error
        output = review_target_files_error
    else:
        try:
            t_engine = time.perf_counter()
            if delegate_mode == DELEGATE_MODE_REVIEW:
                result = run_spec_review(prompt)
            elif _use_pkg:
                context_package = assemble_context(
                    workspace=Path(ws),
                    spec_path=spec_rel_path,
                    target_files=target_files,
                    task=task,
                    context_summary=context_summary,
                    policies=delegation_policies,
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
                result = engine.run_context(
                    context_package,
                    workspace_path=ws,
                    mcp_session_id=storage.mcp_session_id,
                    host_transcript=host_transcript_text,
                )
                executor_prompt = result.prompt_used or context_package.brief
            else:
                engine = get_engine(backend)
                model = engine.model_name
                try:
                    caps = engine.capabilities()
                except (NotImplementedError, AttributeError):
                    caps = None
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
            if not success and error and not output:
                output = error

        except UnknownBackendError as exc:
            success = False
            error = str(exc)
            error_class, error_message = classify_delegation_error(error, exc=exc)
            output = error
        except Exception as exc:
            success = False
            error = f"{type(exc).__name__}: {exc}"
            error_class, error_message = classify_delegation_error(error, exc=exc)
            output = error

    resolved_model = model or resolve_model_name()

    # Build context_block from executor_prompt (legacy: same as prompt; package: translated prompt)
    context_block = prompt_metadata(
        executor_prompt,
        context_summary=context_summary,
        transcript_meta=transcript_meta,
    )
    if context_package is not None:
        read_entries_in_prompt = [
            e
            for e in context_package.entries
            if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT) and e.payload is not None
        ]
        context_block["context_package"] = summarize_context_package(context_package)
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
    spec_report_rel_path: str | None = None
    if spec_path:
        if spec_invalid_reason:
            outcome = OUTCOME_INVALID_SPEC
        elif spec_abs_path is not None and spec_abs_path.is_file():
            report_abs_path = ensure_task_report(spec_abs_path, workspace=ws)
            spec_report_rel_path = str(report_abs_path.resolve().relative_to(Path(ws).resolve()))
            # Compute scope violations before writing report so the report reflects them.
            if (
                delegate_mode == DELEGATE_MODE_IMPLEMENT
                and delegation_policies is not None
                and delegation_policies.edit_scope == "strict"
            ):
                scope_violations = compute_scope_violations(
                    files_changed, delegation_policies.files_edit
                )
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
        usage=usage_dict if usage_report_enabled else None,
        usage_warnings=usage_warnings if usage_report_enabled else None,
        error_class=error_class if not success else None,
        error_message=error_message if not success else None,
        context_package_summary=mcp_context_summary,
        capability_warnings=cap_warnings or None,
        preflight_token_estimate=preflight_token_estimate,
    )
    if spec_files_missing:
        mcp_request["spec_files_missing_from_target"] = spec_files_missing
    if contract_warnings:
        mcp_request["contract_warnings"] = contract_warnings
    if policies_response is not None:
        mcp_request["delegation_policies"] = policies_response
    if scope_violations:
        mcp_request["scope_violations"] = scope_violations
    duration_ms = int((time.perf_counter() - t0) * 1000)
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


@mcp.tool(
    name="inspect_context",
    description=(
        "DRY-RUN CONTEXT INSPECTOR: Compile ContextPackage and adapter preview "
        "(fnames, read paths in prompt) without calling the execution backend. "
        "No file edits, no LLM call, no JSONL delegation log. "
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
        host_transcript=None,
    )
    return json.dumps(result, ensure_ascii=False)


def run_stdio() -> None:
    mcp.run(transport="stdio")
