from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
from typing import Any

from core.config.aider_runtime import (
    create_delegation_io,
    delegation_coder_kwargs,
    delegation_timeout_seconds,
    infer_run_success,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context.package import ContextPackage
from core.delegation.errors import (
    block_webbrowser_open,
    classify_delegation_error,
    sanitize_delegation_output,
)
from core.config.models import provider_hint_for_model, resolve_model_name
from core.config.providers import apply_provider_env
from core.engine.base import BackendRunRequest, ExecutionEngine, ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES, BackendCapabilities
from core.engine.factory import register_engine
from core.engine.git_diff import (
    compute_files_unexpected,
    files_touched_since_snapshot,
    snapshot_git_dirty,
    snapshot_mtimes,
)
from core.engine.stdio_isolation import isolated_stdio, merged_capture

BACKEND_ID = "aider"

_READ_CONTEXT_HEADER = (
    "\n\n---\n\n## Read context (read-only — do not edit unless spec allows)\n"
)


def translate_context_package(
    package: "ContextPackage",
    *,
    host_transcript: str | None = None,
) -> BackendRunRequest:
    """Translate a ContextPackage into an Aider-specific BackendRunRequest.

    fnames = edit-full paths only.
    read-full / read-excerpt payloads are injected as a fenced read context block.
    """
    # Local imports avoid circular dependency (core.engine.__init__ ← aider_engine ← core.context)
    from core.context.package import TIER_EDIT_FULL, TIER_READ_EXCERPT, TIER_READ_FULL
    from core.context.summary import assemble_prompt

    read_entries = [
        e
        for e in package.entries
        if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT) and e.payload is not None
    ]

    read_block = ""
    if read_entries:
        parts = [_READ_CONTEXT_HEADER]
        for entry in read_entries:
            parts.append(f"\n### `{entry.path}` ({entry.tier})\n```python\n{entry.payload}\n```")
        read_block = "".join(parts)

    if host_transcript and host_transcript.strip():
        base = assemble_prompt(
            "",
            "",
            host_transcript=host_transcript,
            spec_block=package.brief,
        )
    else:
        base = package.brief

    prompt = base + read_block

    fnames = sorted(e.path for e in package.entries if e.tier == TIER_EDIT_FULL)

    return BackendRunRequest(prompt=prompt, fnames=fnames, edit_paths=list(fnames))


def _extract_tokens(coder: Any, run_result: Any) -> dict[str, Any]:
    for obj in (run_result, coder):
        if obj is None:
            continue
        for attr in ("total_tokens", "tokens_sent", "tokens_received"):
            if hasattr(obj, attr):
                val = getattr(obj, attr)
                if val is not None:
                    return {
                        "input": getattr(obj, "tokens_sent", None),
                        "output": getattr(obj, "tokens_received", None),
                        "total": val,
                        "source": "aider_coder",
                    }
        if hasattr(obj, "usage") and obj.usage:
            usage = obj.usage
            if isinstance(usage, dict):
                return {
                    "input": usage.get("input_tokens") or usage.get("prompt_tokens"),
                    "output": usage.get("output_tokens") or usage.get("completion_tokens"),
                    "total": usage.get("total_tokens"),
                    "source": "aider_usage",
                }
    return {
        "input": None,
        "output": None,
        "total": None,
        "source": "unavailable",
    }


@register_engine(BACKEND_ID)
class AiderEngine(ExecutionEngine):
    """Aider adapter with optional in-process Coder reuse per mcp_session_id."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or resolve_model_name()

    @property
    def backend_id(self) -> str:
        return BACKEND_ID

    @property
    def model_name(self) -> str:
        return self._model_name

    def capabilities(self) -> BackendCapabilities:
        return AIDER_CAPABILITIES

    def _execute_delegation(
        self,
        *,
        prompt: str,
        fnames_rel: list[str],
        edit_paths_rel: list[str],
        workspace_path: str,
        mcp_session_id: str | None,
        context_package_key: str | None = None,
    ) -> ExecutionResult:
        """Core Aider execution shared by run() and run_context().

        fnames_rel: paths to open in Aider Coder (for edits).
        edit_paths_rel: paths used for cache key, git snapshot, and audit.
        """
        from aider.coders import Coder
        from aider.models import Model

        prev_cwd = os.getcwd()
        executor_reused = False
        executor_recreated = False
        before_git: set[str] | None = None
        before_mtimes: dict[str, float | None] | None = None
        try:
            os.chdir(workspace_path)
            resolved_files = [
                str(Path(workspace_path) / f) if not Path(f).is_absolute() else f
                for f in fnames_rel
            ]
            model = Model(self._model_name)
            before_git = snapshot_git_dirty(workspace_path)
            before_mtimes = snapshot_mtimes(workspace_path, edit_paths_rel)

            def _make_coder() -> tuple[Any, Any, Any]:
                io, out_buffer = create_delegation_io()
                coder = Coder.create(
                    main_model=model,
                    io=io,
                    fnames=resolved_files,
                    **delegation_coder_kwargs(),
                )
                return coder, io, out_buffer

            def _run_coder() -> Any:
                # Lazy import: top-level import loads core.session.__init__ → policy →
                # delegation_log before mcp_server finishes importing logging (P2-210 cycle).
                from core.session.executor_cache import get_or_create_coder

                with block_webbrowser_open(), isolated_stdio() as (stdout_cap, stderr_cap):
                    if mcp_session_id:
                        (coder, io, out_buffer), executor_reused_local, executor_recreated_local = (
                            get_or_create_coder(
                                mcp_session_id,
                                edit_paths_rel,
                                _make_coder,
                                context_package_key=context_package_key,
                            )
                        )
                    else:
                        io, out_buffer = create_delegation_io()
                        coder = Coder.create(
                            main_model=model,
                            io=io,
                            fnames=resolved_files,
                            **delegation_coder_kwargs(),
                        )
                        executor_reused_local = False
                        executor_recreated_local = False

                    partial = coder.run(prompt)
                    captured = merged_capture(out_buffer, stdout_cap, stderr_cap)
                    return coder, io, partial, captured, executor_reused_local, executor_recreated_local

            timeout_s = delegation_timeout_seconds()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_coder)
                try:
                    coder, io, partial, captured, executor_reused, executor_recreated = (
                        future.result(timeout=timeout_s)
                    )
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    from core.logging.server_log import server_log_emit

                    server_log_emit(
                        "delegation_timeout",
                        level="error",
                        model=self._model_name,
                        timeout_s=timeout_s,
                    )
                    files_changed_t, used_git_t = files_touched_since_snapshot(
                        workspace_path,
                        before_git,
                        target_files=edit_paths_rel,
                        before_mtimes=before_mtimes,
                    )
                    return ExecutionResult(
                        success=False,
                        output="Delegation timed out; engine did not complete within the allowed time.",
                        files_changed=files_changed_t,
                        files_unexpected=compute_files_unexpected(
                            files_changed_t, edit_paths_rel, used_git=used_git_t
                        ),
                        model=self._model_name,
                        error="Delegation timed out.",
                        error_class="timeout",
                        tokens={"source": "unavailable"},
                    )

            partial_str = str(partial) if partial is not None else ""
            output = "\n".join(s for s in (captured.strip(), partial_str.strip()) if s)

            files_changed, used_git = files_touched_since_snapshot(
                workspace_path,
                before_git,
                target_files=edit_paths_rel,
                before_mtimes=before_mtimes,
            )
            files_unexpected = compute_files_unexpected(
                files_changed, edit_paths_rel, used_git=used_git
            )
            tokens = _extract_tokens(coder, partial)
            if tokens.get("source") == "unavailable" and output:
                from core.usage.aider_tokens import parse_aider_output_tokens

                parsed = parse_aider_output_tokens(output)
                if parsed:
                    tokens = parsed
            success, error = infer_run_success(
                io=io,
                output=output,
                partial_response=partial_str,
            )
            error_class: str | None = None
            if not success and error:
                error_class, _short = classify_delegation_error(error)
                output = sanitize_delegation_output(output, error_class=error_class)
            return ExecutionResult(
                success=success,
                output=output,
                files_changed=files_changed,
                files_unexpected=files_unexpected,
                model=self._model_name,
                error=error,
                error_class=error_class,
                tokens=tokens,
                executor_reused=executor_reused,
                executor_recreated=executor_recreated,
            )
        except Exception as exc:
            files_changed, used_git = files_touched_since_snapshot(
                workspace_path,
                before_git,
                target_files=edit_paths_rel,
                before_mtimes=before_mtimes,
            )
            err_text = f"{type(exc).__name__}: {exc}"
            error_class, _short = classify_delegation_error(err_text, exc=exc)
            return ExecutionResult(
                success=False,
                output=sanitize_delegation_output(err_text, error_class=error_class),
                files_changed=files_changed,
                files_unexpected=compute_files_unexpected(
                    files_changed, edit_paths_rel, used_git=used_git
                ),
                model=self._model_name,
                error=err_text,
                error_class=error_class,
                tokens={"source": "unavailable"},
            )
        finally:
            os.chdir(prev_cwd)

    def run(
        self,
        prompt: str,
        target_files: list[str],
        *,
        workspace_path: str,
        mcp_session_id: str | None = None,
    ) -> ExecutionResult:
        apply_provider_env()
        config_error = provider_hint_for_model(self._model_name)
        if config_error:
            return ExecutionResult(
                success=False,
                output="",
                files_changed=[],
                model=self._model_name,
                error=config_error,
                tokens={"source": "unavailable"},
            )
        return self._execute_delegation(
            prompt=prompt,
            fnames_rel=target_files,
            edit_paths_rel=target_files,
            workspace_path=workspace_path,
            mcp_session_id=mcp_session_id,
        )

    def run_context(
        self,
        package: "ContextPackage",
        *,
        workspace_path: str,
        mcp_session_id: str | None = None,
        host_transcript: str | None = None,
    ) -> ExecutionResult:
        apply_provider_env()
        config_error = provider_hint_for_model(self._model_name)
        if config_error:
            return ExecutionResult(
                success=False,
                output="",
                files_changed=[],
                model=self._model_name,
                error=config_error,
                tokens={"source": "unavailable"},
            )
        from core.context.package_cache import compute_context_package_cache_key

        req = translate_context_package(package, host_transcript=host_transcript)
        pkg_key = compute_context_package_cache_key(package)
        result = self._execute_delegation(
            prompt=req.prompt,
            fnames_rel=req.fnames,
            edit_paths_rel=req.edit_paths,
            workspace_path=workspace_path,
            mcp_session_id=mcp_session_id,
            context_package_key=pkg_key,
        )
        result.prompt_used = req.prompt
        return result
