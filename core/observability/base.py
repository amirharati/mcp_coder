"""Observability adapter seam — abstract backend for logging and telemetry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.pipeline.phases import PipelineRecorder


class ObservabilityBackend(ABC):
    """Adapter interface for delegation logging, server events, usage, and pipeline timing."""

    @abstractmethod
    def emit(self, event: str, *, level: str = "info", **fields: Any) -> None:
        """Emit a structured server audit event."""

    @abstractmethod
    def warn(self, event: str, fields: dict[str, Any]) -> None:
        """Emit a server audit event at warn level (pipeline helper callback shape)."""

    @abstractmethod
    def log_host_resolved(
        self,
        *,
        hint_host_kind: str | None,
        host_session_id: str | None,
        transcript_path: str | None,
        resolve_error: str | None = None,
        host_resolve_ms: int | None = None,
    ) -> None:
        """Log host session resolution for a delegation."""

    @abstractmethod
    def log_delegation_received(
        self,
        *,
        delegation_id: str,
        target_files: list[str],
        backend: str,
        task_preview: str,
    ) -> None:
        """Log inbound delegation request."""

    @abstractmethod
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
        """Log outbound delegation completion (brief stderr trace)."""

    @abstractmethod
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
        """Build a delegation JSONL record dict."""

    @abstractmethod
    def append_delegation_record(
        self, record: dict[str, Any], *, ws: str | None = None
    ) -> Path:
        """Append a delegation record to JSONL session log(s)."""

    @abstractmethod
    def resolve_usage_report_enabled(self, workspace: str | Path) -> bool:
        """Return whether usage telemetry is enabled for the workspace."""

    @abstractmethod
    def build_usage_report(
        self,
        *,
        model: str,
        prompt: str,
        actual_tokens: dict[str, Any] | None,
        preflight_tokens_est: int | None = None,
        preflight_chars: int | None = None,
    ) -> dict[str, Any]:
        """Build usage dict for JSONL, MCP response, and spec report."""

    @abstractmethod
    def format_usage_run_log_line(self, usage: dict[str, Any]) -> str:
        """Format one-line markdown usage summary for spec report Run log."""

    @abstractmethod
    def build_usage_warnings(self, preflight_tokens_est: int) -> list[str]:
        """Return soft warnings when preflight exceeds configured threshold."""

    @abstractmethod
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
        """Build one auditable model_roles entry for a single LLM role call."""

    @abstractmethod
    def merge_model_roles(
        self, *records: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Merge role usage records keyed by role."""

    @abstractmethod
    def get_role_tokens(
        self, delegation_id: str, role: str
    ) -> dict[str, Any] | None:
        """Return callback-accumulated token usage for a delegation role."""

    @abstractmethod
    def overlay_model_roles_tokens(
        self,
        model_roles: dict[str, Any] | None,
        *,
        delegation_id: str,
        executor_fallback_tokens: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Merge LiteLLM callback tokens into model_roles when live attrs are missing."""

    @abstractmethod
    def finalize_reasoning_summary(self, delegation_id: str) -> str | None:
        """Finalize executor reasoning text captured during a delegation."""

    @abstractmethod
    def record_reasoning_in_session(
        self,
        mcp_session_id: str,
        delegation_id: str,
        reasoning_summary: str,
        *,
        buffer_size: int,
    ) -> None:
        """Store reasoning summary in the in-memory session hot buffer."""

    @abstractmethod
    def get_prior_reasoning_for_builder(
        self,
        mcp_session_id: str,
        *,
        exclude_delegation_id: str | None = None,
    ) -> list[Any]:
        """Prior-session reasoning entries for builder brief injection."""

    @abstractmethod
    def capture_reasoning_enabled(self, workspace: str | Path) -> bool:
        """Return whether executor reasoning capture is enabled."""

    @abstractmethod
    def resolve_reasoning_buffer_size(self, workspace: str | Path) -> int:
        """Return max prior reasoning entries kept per MCP session."""

    @abstractmethod
    def capture_for_training_enabled(self, workspace: str | Path) -> bool:
        """Return whether opt-in training tuple export is enabled."""

    @abstractmethod
    def resolve_observability_retention(self, workspace: str | Path) -> str:
        """Return observability retention policy stub (session | N_days | forever)."""

    @abstractmethod
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
        """Write training tuple when capture_for_training is enabled."""

    @abstractmethod
    def new_pipeline_recorder(self) -> PipelineRecorder:
        """Return a fresh pipeline phase recorder."""

    @abstractmethod
    def default_workspace_path(self) -> str:
        """Resolve default workspace path (env MCP_CODER_WORKSPACE or cwd)."""

    @abstractmethod
    def new_delegation_id(self) -> str:
        """Generate a new delegation UUID."""

    @abstractmethod
    def utc_now_iso(self) -> str:
        """Return current UTC timestamp in ISO-8601 Z format."""

    @abstractmethod
    def should_log_full_prompt(self) -> bool:
        """Return whether full executor prompt should be stored in JSONL."""

    @abstractmethod
    def record_llm_call(
        self,
        *,
        role: str,
        model: str | None,
        messages: list[dict[str, Any]],
        response_obj: Any,
        duration_ms: int,
    ) -> dict[str, Any]:
        """
        Synchronously record token usage and write llm_call trace event.
        Uses contextvars (delegation_id, session_dir, workspace) already set by mcp_server.
        Returns token dict: {"input": int|None, "output": int|None, "total": int|None, "source": str}.
        Must never raise — observability must not break completions.
        """

    @abstractmethod
    def record_backend_llm_call(
        self,
        *,
        call_type: str,
        model: str | None,
        step_index: int | None = None,
        thinking_text: str | None = None,
        thinking_tokens: int | None = None,
        usage: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        prompt_text: str | None = None,
        response_text: str | None = None,
    ) -> None:
        """Record an Aider inner-loop LLM completion as backend_llm_call trace event."""

    @abstractmethod
    def record_proxy_llm_call(
        self,
        *,
        delegation_id: str | None,
        step_index: int | None = None,
        call_index: int | None = None,
        session_dir: str | Path | None = None,
        workspace: str | Path | None = None,
        model: str | None,
        request_received_at: str,
        response_received_at: str,
        wire_latency_ms: int,
        status_code: int,
        raw_request: str | None = None,
        raw_response: str | None = None,
        attribution_source: str = "none",
    ) -> None:
        """Record a proxy-captured raw HTTP LLM call as proxy_llm_call trace event."""
