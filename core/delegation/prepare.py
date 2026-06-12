"""Delegate-faithful pre-executor context preparation (no backend run)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config.architect_pass import architect_pass_enabled
from core.config.context_builder import context_builder_enabled, context_builder_llm_enabled
from core.config.spec_validation import spec_validation_enabled
from core.context.inspect import inspect_context_package
from core.context.transcript_policy import POLICY_DUMP, resolve_host_transcript_policy
from core.delegation.artifacts import delegation_envelope, prepare_artifacts
from core.host import get_host_provider
from core.host.cursor_transcript import load_cursor_transcript
from core.logging.delegation_log import CONTEXT_MODE_HOST_TRANSCRIPT


def resolve_host_transcript_text(workspace: Path) -> tuple[str | None, str]:
    """Load host transcript when workspace policy is dump (same as delegate)."""
    ws = str(workspace.resolve())
    policy = resolve_host_transcript_policy(ws)
    if policy != POLICY_DUMP:
        return None, "none"
    try:
        hint = get_host_provider().resolve_active_session(ws)
    except Exception:
        return None, "resolve_error"
    if not hint.host_transcript_path or hint.resolve_error:
        return None, "unavailable"
    result = load_cursor_transcript(hint.host_transcript_path)
    if result.text:
        return result.text, CONTEXT_MODE_HOST_TRANSCRIPT
    return None, "empty"


def prepare_delegation_context(
    *,
    workspace: Path,
    task: str,
    target_files: list[str],
    context_summary: str | None = None,
    spec_path: str | Path | None = None,
    backend: str = "aider",
    include_payloads: bool = False,
) -> dict[str, Any]:
    """Compile context the same way as delegate pre-executor (config-driven helpers)."""
    ws = workspace.resolve()
    host_transcript, _host_mode = resolve_host_transcript_text(ws)

    inspect_result = inspect_context_package(
        workspace=ws,
        task=task,
        target_files=target_files,
        context_summary=context_summary,
        spec_path=spec_path,
        include_payloads=include_payloads,
        include_adapter_preview=True,
        include_prompt=True,
        host_transcript=host_transcript,
        run_spec_validation=spec_validation_enabled(ws),
        run_architect=architect_pass_enabled(ws),
        run_builder_llm=context_builder_enabled(ws) and context_builder_llm_enabled(ws),
        respect_workspace_flags=True,
        force_helpers=False,
        backend=backend,
    )

    if not inspect_result.get("ok"):
        return delegation_envelope(
            ok=False,
            stop_after="context",
            artifacts={},
            error=str(inspect_result.get("error") or "prepare failed"),
        )

    sv = (inspect_result.get("helper_phases") or {}).get("spec_validation") or {}
    if sv.get("would_block_delegate"):
        return delegation_envelope(
            ok=False,
            stop_after="context",
            artifacts=prepare_artifacts(
                inspect_result=inspect_result,
                executor_prompt="",
                capability_warnings=inspect_result.get("capability_warnings"),
            ),
            error="spec_validation would block delegate",
        )

    cap_warnings = list(inspect_result.get("capability_warnings") or [])
    adapter_preview = inspect_result.get("adapter_preview") or {}
    executor_prompt = str(adapter_preview.get("prompt") or "")

    artifacts = prepare_artifacts(
        inspect_result=inspect_result,
        executor_prompt=executor_prompt,
        capability_warnings=cap_warnings or None,
    )

    return delegation_envelope(
        ok=True,
        stop_after="context",
        artifacts=artifacts,
    )
