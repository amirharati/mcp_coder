"""No-op observability backend for tests and future remote/product backends."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.observability.base import ObservabilityBackend
from core.pipeline.phases import PipelineRecorder


class NullObservability(ObservabilityBackend):
    """Discard all observability side effects; return empty values of correct types."""

    def emit(self, event: str, *, level: str = "info", **fields: Any) -> None:
        pass

    def warn(self, event: str, fields: dict[str, Any]) -> None:
        pass

    def log_host_resolved(
        self,
        *,
        hint_host_kind: str | None,
        host_session_id: str | None,
        transcript_path: str | None,
        resolve_error: str | None = None,
        host_resolve_ms: int | None = None,
    ) -> None:
        pass

    def log_delegation_received(
        self,
        *,
        delegation_id: str,
        target_files: list[str],
        backend: str,
        task_preview: str,
    ) -> None:
        pass

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
        pass

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
    ) -> dict[str, Any]:
        return {"delegation_id": delegation_id, "type": "delegation"}

    def append_delegation_record(
        self, record: dict[str, Any], *, ws: str | None = None
    ) -> Path:
        raw = record.get("log_path")
        return Path(raw) if raw else Path("/dev/null")

    def resolve_usage_report_enabled(self, workspace: str | Path) -> bool:
        return False

    def build_usage_report(
        self,
        *,
        model: str,
        prompt: str,
        actual_tokens: dict[str, Any] | None,
        preflight_tokens_est: int | None = None,
        preflight_chars: int | None = None,
    ) -> dict[str, Any]:
        return {}

    def format_usage_run_log_line(self, usage: dict[str, Any]) -> str:
        return ""

    def build_usage_warnings(self, preflight_tokens_est: int) -> list[str]:
        return []

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
        return {}

    def merge_model_roles(
        self, *records: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return {}

    def new_pipeline_recorder(self) -> PipelineRecorder:
        return PipelineRecorder()

    def default_workspace_path(self) -> str:
        return ""

    def new_delegation_id(self) -> str:
        return "00000000-0000-0000-0000-000000000000"

    def utc_now_iso(self) -> str:
        return "1970-01-01T00:00:00.000Z"

    def should_log_full_prompt(self) -> bool:
        return False
