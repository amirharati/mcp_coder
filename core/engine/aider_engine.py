from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
from typing import Any

from core.config.aider_runtime import (
    create_delegation_io,
    delegation_coder_kwargs,
    infer_run_success,
)
from core.config.models import provider_hint_for_model, resolve_model_name
from core.config.providers import apply_provider_env
from core.engine.base import ExecutionEngine, ExecutionResult
from core.engine.factory import register_engine
from core.engine.git_diff import (
    compute_files_unexpected,
    files_touched_since_snapshot,
    snapshot_git_dirty,
    snapshot_mtimes,
)
from core.engine.stdio_isolation import isolated_stdio, merged_capture
from core.session.executor_cache import get_or_create_coder

BACKEND_ID = "aider"


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
    return {"source": "unavailable"}


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
                for f in target_files
            ]
            model = Model(self._model_name)
            before_git = snapshot_git_dirty(workspace_path)
            before_mtimes = snapshot_mtimes(workspace_path, target_files)

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
                with isolated_stdio() as (stdout_cap, stderr_cap):
                    if mcp_session_id:
                        (coder, io, out_buffer), executor_reused_local, executor_recreated_local = (
                            get_or_create_coder(
                                mcp_session_id,
                                target_files,
                                _make_coder,
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

            # Run Aider in a dedicated thread to isolate its synchronous Playwright 
            # calls from FastMCP's asyncio event loop.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_coder)
                coder, io, partial, captured, executor_reused, executor_recreated = future.result()

            partial_str = str(partial) if partial is not None else ""
            output = "\n".join(s for s in (captured.strip(), partial_str.strip()) if s)

            files_changed, used_git = files_touched_since_snapshot(
                workspace_path,
                before_git,
                target_files=target_files,
                before_mtimes=before_mtimes,
            )
            files_unexpected = compute_files_unexpected(
                files_changed, target_files, used_git=used_git
            )
            tokens = _extract_tokens(coder, partial)
            success, error = infer_run_success(
                io=io,
                output=output,
                partial_response=partial_str,
            )
            return ExecutionResult(
                success=success,
                output=output,
                files_changed=files_changed,
                files_unexpected=files_unexpected,
                model=self._model_name,
                error=error,
                tokens=tokens,
                executor_reused=executor_reused,
                executor_recreated=executor_recreated,
            )
        except Exception as exc:
            files_changed, used_git = files_touched_since_snapshot(
                workspace_path,
                before_git,
                target_files=target_files,
                before_mtimes=before_mtimes,
            )
            return ExecutionResult(
                success=False,
                output="",
                files_changed=files_changed,
                files_unexpected=compute_files_unexpected(
                    files_changed, target_files, used_git=used_git
                ),
                model=self._model_name,
                error=f"{type(exc).__name__}: {exc}",
                tokens={"source": "unavailable"},
            )
        finally:
            os.chdir(prev_cwd)
