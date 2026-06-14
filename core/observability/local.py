"""Local filesystem-backed observability (delegates to core.logging and core.usage)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.logging.delegation_log import (
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
from core.observability.base import ObservabilityBackend
from core.observability.litellm_callback import (
    finalize_delegation_reasoning_summary,
    get_accumulated_usage,
    overlay_model_roles_from_callback,
    register_litellm_callbacks,
)
from core.observability.reasoning_buffer import (
    ReasoningBufferEntry,
    get_prior_reasoning,
    record_session_reasoning,
)
from core.pipeline.phases import PipelineRecorder
from core.usage import (
    build_usage_report,
    build_usage_warnings,
    format_usage_run_log_line,
    resolve_usage_report_enabled,
)
from core.usage.role_audit import build_role_usage_record, merge_model_roles


class LocalObservability(ObservabilityBackend):
    """Default observability backend — JSONL logs, SQLite-adjacent paths, usage telemetry."""

    def __init__(self) -> None:
        register_litellm_callbacks()

    def get_role_tokens(
        self, delegation_id: str, role: str
    ) -> dict[str, Any] | None:
        """Return callback-accumulated tokens for a delegation role."""
        return get_accumulated_usage(delegation_id, role)

    def overlay_model_roles_tokens(
        self,
        model_roles: dict[str, Any] | None,
        *,
        delegation_id: str,
        executor_fallback_tokens: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Merge LiteLLM callback tokens into model_roles when live attrs are missing."""
        return overlay_model_roles_from_callback(
            model_roles,
            delegation_id=delegation_id,
            executor_fallback_tokens=executor_fallback_tokens,
        )

    def finalize_reasoning_summary(self, delegation_id: str) -> str | None:
        return finalize_delegation_reasoning_summary(delegation_id)

    def record_reasoning_in_session(
        self,
        mcp_session_id: str,
        delegation_id: str,
        reasoning_summary: str,
        *,
        buffer_size: int,
    ) -> None:
        record_session_reasoning(
            mcp_session_id,
            delegation_id,
            reasoning_summary,
            max_entries=buffer_size,
        )

    def get_prior_reasoning_for_builder(
        self,
        mcp_session_id: str,
        *,
        exclude_delegation_id: str | None = None,
    ) -> list[ReasoningBufferEntry]:
        return get_prior_reasoning(
            mcp_session_id,
            exclude_delegation_id=exclude_delegation_id,
        )

    def capture_reasoning_enabled(self, workspace: str | Path) -> bool:
        from core.config.observability import capture_reasoning_enabled

        return capture_reasoning_enabled(workspace)

    def resolve_reasoning_buffer_size(self, workspace: str | Path) -> int:
        from core.config.observability import resolve_reasoning_buffer_size

        return resolve_reasoning_buffer_size(workspace)

    def capture_for_training_enabled(self, workspace: str | Path) -> bool:
        from core.config.observability import capture_for_training_enabled

        return capture_for_training_enabled(workspace)

    def resolve_observability_retention(self, workspace: str | Path) -> str:
        from core.config.observability import resolve_observability_retention

        return resolve_observability_retention(workspace)

    def write_training_capture_if_enabled(
        self,
        *,
        workspace: str | Path,
        session_dir: str | Path,
        delegation_id: str,
        timestamp_end: str,
        task: str,
        context_package_hash: str | None,
        reasoning_summary: str | None,
        outcome: str | None,
        verify_result: dict[str, Any] | None,
        success: bool,
        model_roles: dict[str, Any] | None,
        pipeline_flags_runtime: dict[str, Any] | None = None,
    ) -> Path | None:
        from core.observability.training_capture import write_training_capture_if_enabled

        return write_training_capture_if_enabled(
            workspace=workspace,
            session_dir=session_dir,
            delegation_id=delegation_id,
            timestamp_end=timestamp_end,
            task=task,
            context_package_hash=context_package_hash,
            reasoning_summary=reasoning_summary,
            outcome=outcome,
            verify_result=verify_result,
            success=success,
            model_roles=model_roles,
            pipeline_flags_runtime=pipeline_flags_runtime,
        )

    def emit(self, event: str, *, level: str = "info", **fields: Any) -> None:
        server_log_emit(event, level=level, **fields)

    def warn(self, event: str, fields: dict[str, Any]) -> None:
        server_log_emit(event, level="warn", **fields)

    def log_host_resolved(
        self,
        *,
        hint_host_kind: str | None,
        host_session_id: str | None,
        transcript_path: str | None,
        resolve_error: str | None = None,
        host_resolve_ms: int | None = None,
    ) -> None:
        log_host_resolved(
            hint_host_kind=hint_host_kind,
            host_session_id=host_session_id,
            transcript_path=transcript_path,
            resolve_error=resolve_error,
            host_resolve_ms=host_resolve_ms,
        )

    def log_delegation_received(
        self,
        *,
        delegation_id: str,
        target_files: list[str],
        backend: str,
        task_preview: str,
    ) -> None:
        log_delegation_received(
            delegation_id=delegation_id,
            target_files=target_files,
            backend=backend,
            task_preview=task_preview,
        )

    def log_delegation_sent(
        self,
        *,
        delegation_id: str,
        success: bool,
        duration_ms: int,
        files_changed: list[str],
        log_path: Path,
        error: str | None = None,
    ) -> None:
        log_delegation_sent(
            delegation_id=delegation_id,
            success=success,
            duration_ms=duration_ms,
            files_changed=files_changed,
            log_path=log_path,
            error=error,
        )

    def build_delegation_record(
        self,
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
        context_mode: str = "fallback",
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
    ) -> dict[str, Any]:
        return build_delegation_record(
            delegation_id=delegation_id,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            duration_ms=duration_ms,
            mcp_request=mcp_request,
            backend=backend,
            model=model,
            success=success,
            error=error,
            response_to_cursor=response_to_cursor,
            files_requested=files_requested,
            files_changed=files_changed,
            files_unexpected=files_unexpected,
            context_block=context_block,
            context_mode=context_mode,
            timing=timing,
            tokens=tokens,
            project_key=project_key,
            mcp_session_id=mcp_session_id,
            session_dir=session_dir,
            log_path=log_path,
            session_action=session_action,
            session_reason=session_reason,
            session_policy=session_policy,
            host_kind=host_kind,
            host_session_id=host_session_id,
            host_transcript_path=host_transcript_path,
            host_context=host_context,
            executor_reused=executor_reused,
            executor_recreated=executor_recreated,
            prompt_full=prompt_full,
            spec_path=spec_path,
            spec_report_path=spec_report_path,
            spec_sha256=spec_sha256,
            spec_mtime=spec_mtime,
            outcome=outcome,
            delegate_mode=delegate_mode,
            spec_files_missing_from_target=spec_files_missing_from_target,
            contract_warnings=contract_warnings,
            delegation_policies=delegation_policies,
            scope_violations=scope_violations,
            usage=usage,
            error_class=error_class,
            error_message=error_message,
            workspace_snapshot=workspace_snapshot,
            post_gateway=post_gateway,
            checkpoint=checkpoint,
            auto_merged_read_paths=auto_merged_read_paths,
            auto_merge_spec_read=auto_merge_spec_read,
            model_roles=model_roles,
            context_refs=context_refs,
            trace_ref=trace_ref,
        )

    def append_delegation_record(
        self, record: dict[str, Any], *, ws: str | None = None
    ) -> Path:
        return append_delegation_record(record, ws=ws)

    def resolve_usage_report_enabled(self, workspace: str | Path) -> bool:
        return resolve_usage_report_enabled(workspace)

    def build_usage_report(
        self,
        *,
        model: str,
        prompt: str,
        actual_tokens: dict[str, Any] | None,
        preflight_tokens_est: int | None = None,
        preflight_chars: int | None = None,
    ) -> dict[str, Any]:
        return build_usage_report(
            model=model,
            prompt=prompt,
            actual_tokens=actual_tokens,
            preflight_tokens_est=preflight_tokens_est,
            preflight_chars=preflight_chars,
        )

    def format_usage_run_log_line(self, usage: dict[str, Any]) -> str:
        return format_usage_run_log_line(usage)

    def build_usage_warnings(self, preflight_tokens_est: int) -> list[str]:
        return build_usage_warnings(preflight_tokens_est)

    def build_role_usage_record(
        self,
        *,
        role: str,
        model: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        duration_ms: int | None = None,
        source: str = "unavailable",
    ) -> dict[str, Any]:
        return build_role_usage_record(
            role=role,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            source=source,
        )

    def merge_model_roles(
        self, *records: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return merge_model_roles(*records)

    def new_pipeline_recorder(self) -> PipelineRecorder:
        return PipelineRecorder()

    def default_workspace_path(self) -> str:
        return workspace_path()

    def new_delegation_id(self) -> str:
        return new_delegation_id()

    def utc_now_iso(self) -> str:
        return utc_now_iso()

    def should_log_full_prompt(self) -> bool:
        return should_log_full_prompt()

    def record_llm_call(
        self,
        *,
        role: str,
        model: str | None,
        messages: list[dict[str, Any]],
        response_obj: Any,
        duration_ms: int,
    ) -> dict[str, Any]:
        from core.observability.litellm_callback import record_owned_completion

        return record_owned_completion(
            role=role,
            model=model,
            messages=messages,
            response_obj=response_obj,
            duration_ms=duration_ms,
        )
