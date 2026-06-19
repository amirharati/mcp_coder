from __future__ import annotations

import concurrent.futures
import contextvars
import os
from pathlib import Path
from typing import Any

from core.config.aider_runtime import (
    OUTCOME_NEEDS_INPUT_CLARIFICATION,
    OUTCOME_NEEDS_INPUT_FILES,
    STALL_OUTPUT_TAIL_CHARS,
    _executor_output_tail,
    classify_executor_outcome,
    create_delegation_io,
    delegation_coder_kwargs,
    delegation_timeout_seconds,
    executor_pull_hint_enabled,
    infer_run_success,
    supervised_execution_enabled,
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
from core.engine.git_diff import snapshot_git_dirty, snapshot_mtimes
from core.engine.interception_profile import AIDER_INTERCEPTION_PROFILE, InterceptionProfile
from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution
from core.engine.stdio_isolation import isolated_stdio, merged_capture

BACKEND_ID = "aider"

EXECUTOR_PULL_HINT_BLOCK = (
    "If you need additional context, use /read <path> to add files as read-only.\n"
    "Do not ask to add files to the chat.\n"
    "Do not expand edit scope beyond the spec Files contract."
)


def _merge_executor_pull_hint(existing_prefix: str | None) -> str:
    existing = (existing_prefix or "").strip()
    if not existing:
        return EXECUTOR_PULL_HINT_BLOCK
    return f"{existing}\n\n---\n\n{EXECUTOR_PULL_HINT_BLOCK}"


def _apply_executor_pull_hint(model: Any, *, workspace_path: str) -> bool:
    """Append pull-hint block to model.system_prompt_prefix when enabled."""
    if not executor_pull_hint_enabled(workspace_path):
        return False
    try:
        model.system_prompt_prefix = _merge_executor_pull_hint(
            getattr(model, "system_prompt_prefix", None)
        )
        return True
    except Exception:
        return False


def _supervisor_metadata_from_io(io: Any) -> dict[str, Any]:
    """Attach supervisor audit fields from SupervisedIO when present."""
    decisions = getattr(io, "supervisor_decisions", None)
    if not decisions:
        return {}
    payload: dict[str, Any] = {
        "supervisor_decisions": list(decisions),
        "supervisor_decisions_count": int(getattr(io, "supervisor_decisions_count", 0) or 0),
        "supervisor_aborts_count": int(getattr(io, "supervisor_aborts_count", 0) or 0),
    }
    last = decisions[-1]
    payload["supervisor_last_decision"] = str(last.get("decision") or "")
    supervisor = getattr(io, "_supervisor", None)
    if supervisor is not None and hasattr(supervisor, "usage_record"):
        payload["supervisor_usage"] = supervisor.usage_record
    return payload


def _extract_architect_plan(brief: str | None) -> str | None:
    text = (brief or "").strip()
    if not text or "## Architect plan" not in text:
        return None
    start = text.find("## Architect plan")
    end = text.find("\n---\n", start)
    if end == -1:
        return text[start:].strip()
    return text[start:end].strip()


def _build_spec_contract(contract_paths: list[str] | None) -> str | None:
    paths = sorted({p.replace("\\", "/").lstrip("./") for p in (contract_paths or []) if p})
    if not paths:
        return None
    return "### Allowed paths\n" + "\n".join(f"- `{p}`" for p in paths)


def _apply_executor_model_params(model: Any, params: Any) -> None:
    """Apply registry CallParams to an aider Model for the executor role (P9-012).

    Uses Aider's own setters so the provider-specific translation (reasoning_effort
    vs thinking budget) is delegated to Aider/litellm. Best-effort: a setter failing
    must not abort a delegation.
    """
    try:
        if params.reasoning_effort:
            model.set_reasoning_effort(params.reasoning_effort)
        elif params.thinking_budget:
            model.set_thinking_tokens(params.thinking_budget)
    except Exception:
        pass

    if params.extra_params:
        try:
            if not model.extra_params:
                model.extra_params = {}
            for key, value in params.extra_params.items():
                if (
                    isinstance(value, dict)
                    and isinstance(model.extra_params.get(key), dict)
                ):
                    model.extra_params[key] = {**model.extra_params[key], **value}
                else:
                    model.extra_params[key] = value
        except Exception:
            pass

    if params.weak_model:
        try:
            model.get_weak_model(params.weak_model)
        except Exception:
            pass

    if params.system_prompt_prefix:
        try:
            model.system_prompt_prefix = params.system_prompt_prefix
        except Exception:
            pass


_READ_CONTEXT_HEADER = (
    "\n\n---\n\n## Read context (read-only — do not edit unless spec allows)\n"
)

_REPO_MAP_HEADER = (
    "\n\n---\n\n## Repo map (symbols only — do not edit unless spec allows)\n"
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
    from core.context.package import (
        TIER_EDIT_FULL,
        TIER_MAP_ONLY,
        TIER_READ_EXCERPT,
        TIER_READ_FULL,
    )
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

    map_entries = [
        e for e in package.entries if e.tier == TIER_MAP_ONLY and e.payload is not None
    ]
    map_block = ""
    if map_entries:
        parts = [_REPO_MAP_HEADER]
        for entry in map_entries:
            parts.append(f"\n### `{entry.path}` (map-only)\n{entry.payload}\n")
        map_block = "".join(parts)

    if host_transcript and host_transcript.strip():
        base = assemble_prompt(
            "",
            "",
            host_transcript=host_transcript,
            spec_block=package.brief,
        )
    else:
        base = package.brief

    prompt = base + read_block + map_block

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

    @property
    def interception_profile(self) -> InterceptionProfile:
        return AIDER_INTERCEPTION_PROFILE

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
        delegation_id: str | None = None,
        spec_path: str | None = None,
        contract_paths: list[str] | None = None,
        timestamp_start: str | None = None,
        timeout_s: float | None = None,
        spec_contract: str | None = None,
        architect_plan: str | None = None,
    ) -> ExecutionResult:
        """Core Aider execution shared by run() and run_context().

        fnames_rel: paths to open in Aider Coder (for edits).
        edit_paths_rel: paths used for cache key, git snapshot, and audit.
        """
        from aider.coders import Coder

        from core.engine.observable_model import ObservableModel

        prev_cwd = os.getcwd()
        executor_reused = False
        executor_recreated = False
        before_git: set[str] | None = None
        before_mtimes: dict[str, float | None] | None = None
        snapshot_session = None
        contract = contract_paths or edit_paths_rel
        policy_token = None
        supervised_on = supervised_execution_enabled(workspace_path)
        effective_spec_contract = spec_contract or _build_spec_contract(contract)
        try:
            os.chdir(workspace_path)
            resolved_files = [
                str(Path(workspace_path) / f) if not Path(f).is_absolute() else f
                for f in fnames_rel
            ]
            model = ObservableModel(self._model_name)

            from core.config.model_registry import ROLE_EXECUTOR, policy_applied, resolve
            from core.observability.context import model_policy_var

            exec_params = resolve(ROLE_EXECUTOR, workspace_path)
            _apply_executor_model_params(model, exec_params)
            pull_hint_applied = _apply_executor_pull_hint(model, workspace_path=workspace_path)
            policy_token = model_policy_var.set(policy_applied(exec_params, ROLE_EXECUTOR))
            from core.logging.delegation_log import executor_options_audit_var

            executor_options_audit_var.set(
                {
                    "system_prefix_applied": bool(exec_params.system_prompt_prefix),
                    "edit_format": exec_params.edit_format,
                    "executor_pull_hint_applied": pull_hint_applied,
                }
            )
            before_git = snapshot_git_dirty(workspace_path)
            before_mtimes = snapshot_mtimes(workspace_path, edit_paths_rel)
            snapshot_session = begin_delegation_snapshot(
                workspace_path=workspace_path,
                delegation_id=delegation_id,
                mcp_session_id=mcp_session_id,
                timestamp_start=timestamp_start,
                spec_path=spec_path,
                contract_paths=contract,
            )

            def _make_coder() -> tuple[Any, Any, Any]:
                if supervised_on:
                    supervisor_holder: dict[str, Any] = {}

                    def _io_factory(buffer: Any) -> Any:
                        from core.engine.supervised_io import SupervisedIO
                        from core.engine.supervisor import DelegationSupervisor

                        target_set = {
                            p.replace("\\", "/").lstrip("./") for p in edit_paths_rel if p
                        }
                        contract_set = {
                            p.replace("\\", "/").lstrip("./") for p in (contract or []) if p
                        }
                        supervisor = DelegationSupervisor(
                            workspace_path=workspace_path,
                            delegation_id=delegation_id,
                            spec_contract=effective_spec_contract,
                            architect_plan=architect_plan,
                            output_tail_provider=lambda: _executor_output_tail(
                                buffer.getvalue() if hasattr(buffer, "getvalue") else "",
                                max_chars=STALL_OUTPUT_TAIL_CHARS,
                            ),
                        )
                        supervisor_holder["supervisor"] = supervisor
                        return SupervisedIO(
                            output=buffer,
                            supervisor=supervisor,
                            target_files=target_set,
                            contract_paths=contract_set,
                        )

                    io, out_buffer = create_delegation_io(io_factory=_io_factory)
                    if supervisor_holder.get("supervisor") is not None:
                        pass  # supervisor attached via SupervisedIO
                else:
                    io, out_buffer = create_delegation_io()
                coder = Coder.create(
                    main_model=model,
                    io=io,
                    fnames=resolved_files,
                    **delegation_coder_kwargs(exec_params.edit_format),
                )
                return coder, io, out_buffer

            def _run_coder() -> Any:
                # Lazy import: top-level import loads core.session.__init__ → policy →
                # delegation_log before mcp_server finishes importing logging (P2-210 cycle).
                from core.engine.supervised_io import SupervisorAbort
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
                        coder, io, out_buffer = _make_coder()
                        executor_reused_local = False
                        executor_recreated_local = False

                    try:
                        partial = coder.run(prompt)
                    except SupervisorAbort as exc:
                        captured = merged_capture(out_buffer, stdout_cap, stderr_cap)
                        raise exc
                    captured = merged_capture(out_buffer, stdout_cap, stderr_cap)
                    return coder, io, partial, captured, executor_reused_local, executor_recreated_local

            timeout_s = timeout_s if timeout_s is not None else delegation_timeout_seconds()
            ctx = contextvars.copy_context()
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = pool.submit(ctx.run, _run_coder)
            pool_shutdown = False
            try:
                coder, io, partial, captured, executor_reused, executor_recreated = (
                    future.result(timeout=timeout_s)
                )
            except concurrent.futures.TimeoutError:
                future.cancel()
                pool.shutdown(wait=False, cancel_futures=True)
                pool_shutdown = True
                from core.logging.server_log import server_log_emit

                server_log_emit(
                    "delegation_timeout",
                    level="error",
                    model=self._model_name,
                    timeout_s=timeout_s,
                )
                (
                    files_changed_t,
                    files_unexpected_t,
                    workspace_snapshot_t,
                    _used_git_t,
                    snapshot_ms_t,
                ) = resolve_delegation_attribution(
                    workspace_path=workspace_path,
                    snapshot_session=snapshot_session,
                    contract_paths=contract,
                    edit_paths_rel=edit_paths_rel,
                    before_git=before_git,
                    before_mtimes=before_mtimes,
                    delegation_id=delegation_id,
                )
                return ExecutionResult(
                    success=False,
                    output="Delegation timed out; engine did not complete within the allowed time.",
                    files_changed=files_changed_t,
                    files_unexpected=files_unexpected_t,
                    model=self._model_name,
                    error="Delegation timed out.",
                    error_class="timeout",
                    tokens={"source": "unavailable"},
                    workspace_snapshot=workspace_snapshot_t,
                    workspace_snapshot_ms=snapshot_ms_t or None,
                )
            except Exception as exc:
                from core.engine.supervised_io import SupervisorAbort

                if isinstance(exc, SupervisorAbort):
                    if not pool_shutdown:
                        pool.shutdown(wait=False, cancel_futures=True)
                        pool_shutdown = True
                    (
                        files_changed_a,
                        files_unexpected_a,
                        workspace_snapshot_a,
                        _used_git_a,
                        snapshot_ms_a,
                    ) = resolve_delegation_attribution(
                        workspace_path=workspace_path,
                        snapshot_session=snapshot_session,
                        contract_paths=contract,
                        edit_paths_rel=edit_paths_rel,
                        before_git=before_git,
                        before_mtimes=before_mtimes,
                        delegation_id=delegation_id,
                    )
                    output_tail = _executor_output_tail(
                        exc.reasoning,
                        max_chars=STALL_OUTPUT_TAIL_CHARS,
                    )
                    tokens_abort: dict[str, Any] = {
                        "source": "unavailable",
                        "stall_type": OUTCOME_NEEDS_INPUT_CLARIFICATION,
                        "supervisor_reason": exc.reasoning,
                        "supervisor_decisions_count": exc.decisions_count,
                        "supervisor_aborts_count": exc.aborts_count,
                        "supervisor_decisions": exc.decisions,
                        "executor_output_tail": output_tail,
                    }
                    return ExecutionResult(
                        success=False,
                        output=exc.reasoning,
                        files_changed=files_changed_a,
                        files_unexpected=files_unexpected_a,
                        model=self._model_name,
                        error=exc.reasoning,
                        error_class=OUTCOME_NEEDS_INPUT_CLARIFICATION,
                        tokens=tokens_abort,
                        workspace_snapshot=workspace_snapshot_a,
                        workspace_snapshot_ms=snapshot_ms_a or None,
                    )
                if not pool_shutdown:
                    pool.shutdown(wait=False, cancel_futures=True)
                    pool_shutdown = True
                raise
            else:
                pool.shutdown(wait=True)
                pool_shutdown = True

            partial_str = str(partial) if partial is not None else ""
            output = "\n".join(s for s in (captured.strip(), partial_str.strip()) if s)

            (
                files_changed,
                files_unexpected,
                workspace_snapshot,
                _used_git,
                snapshot_ms,
            ) = resolve_delegation_attribution(
                workspace_path=workspace_path,
                snapshot_session=snapshot_session,
                contract_paths=contract,
                edit_paths_rel=edit_paths_rel,
                before_git=before_git,
                before_mtimes=before_mtimes,
                delegation_id=delegation_id,
            )
            from core.usage.aider_tokens import resolve_executor_tokens

            tokens = resolve_executor_tokens(
                coder_tokens=_extract_tokens(coder, partial),
                output=output,
            )
            supervisor_meta = _supervisor_metadata_from_io(io)
            if supervisor_meta:
                tokens.update(supervisor_meta)
            classification = classify_executor_outcome(
                io=io,
                output=output,
                partial_response=partial_str,
            )
            success, error = infer_run_success(
                io=io,
                output=output,
                partial_response=partial_str,
            )
            error_class: str | None = None
            if classification["outcome"] in (
                OUTCOME_NEEDS_INPUT_FILES,
                OUTCOME_NEEDS_INPUT_CLARIFICATION,
            ):
                error_class = classification["outcome"]
                tokens["stall_type"] = classification["outcome"]
                tokens["files_requested"] = list(classification.get("files_requested") or [])
                if classification.get("executor_output_tail"):
                    tokens["executor_output_tail"] = classification["executor_output_tail"]
            elif not success and error:
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
                workspace_snapshot=workspace_snapshot,
                workspace_snapshot_ms=snapshot_ms or None,
            )
        except Exception as exc:
            (
                files_changed,
                files_unexpected,
                workspace_snapshot,
                _used_git,
                snapshot_ms,
            ) = resolve_delegation_attribution(
                workspace_path=workspace_path,
                snapshot_session=snapshot_session,
                contract_paths=contract,
                edit_paths_rel=edit_paths_rel,
                before_git=before_git,
                before_mtimes=before_mtimes,
                delegation_id=delegation_id,
            )
            err_text = f"{type(exc).__name__}: {exc}"
            error_class, _short = classify_delegation_error(err_text, exc=exc)
            return ExecutionResult(
                success=False,
                output=sanitize_delegation_output(err_text, error_class=error_class),
                files_changed=files_changed,
                files_unexpected=files_unexpected,
                model=self._model_name,
                error=err_text,
                error_class=error_class,
                tokens={"source": "unavailable"},
                workspace_snapshot=workspace_snapshot,
                workspace_snapshot_ms=snapshot_ms or None,
            )
        finally:
            os.chdir(prev_cwd)
            if policy_token is not None:
                from core.observability.context import model_policy_var

                model_policy_var.reset(policy_token)

    def run(
        self,
        prompt: str,
        target_files: list[str],
        *,
        workspace_path: str,
        mcp_session_id: str | None = None,
        delegation_id: str | None = None,
        spec_path: str | None = None,
        contract_paths: list[str] | None = None,
        timestamp_start: str | None = None,
        timeout_s: float | None = None,
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
            delegation_id=delegation_id,
            spec_path=spec_path,
            contract_paths=contract_paths or target_files,
            timestamp_start=timestamp_start,
            timeout_s=timeout_s,
        )

    def run_context(
        self,
        package: "ContextPackage",
        *,
        workspace_path: str,
        mcp_session_id: str | None = None,
        host_transcript: str | None = None,
        delegation_id: str | None = None,
        spec_path: str | None = None,
        timestamp_start: str | None = None,
        timeout_s: float | None = None,
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

        from core.context.package import TIER_EDIT_FULL, TIER_READ_EXCERPT, TIER_READ_FULL

        req = translate_context_package(package, host_transcript=host_transcript)
        pkg_key = compute_context_package_cache_key(package)
        if package.policies is not None:
            contract_paths = sorted(
                set(package.policies.files_edit) | set(package.policies.files_read)
            )
        else:
            contract_paths = sorted(
                e.path
                for e in package.entries
                if e.tier in (TIER_EDIT_FULL, TIER_READ_FULL, TIER_READ_EXCERPT)
            )
        result = self._execute_delegation(
            prompt=req.prompt,
            fnames_rel=req.fnames,
            edit_paths_rel=req.edit_paths,
            workspace_path=workspace_path,
            mcp_session_id=mcp_session_id,
            context_package_key=pkg_key,
            delegation_id=delegation_id,
            spec_path=spec_path,
            contract_paths=contract_paths,
            timestamp_start=timestamp_start,
            timeout_s=timeout_s,
            architect_plan=_extract_architect_plan(package.brief),
        )
        result.prompt_used = req.prompt
        return result
