"""Dry-run context compiler inspection (no execution backend)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.config.architect_pass import architect_pass_enabled
from core.config.auto_merge import auto_merge_spec_read_enabled
from core.config.context_builder import (
    context_builder_enabled,
    context_builder_llm_enabled,
)
from core.config.rag import (
    builder_history_rag_enabled,
    workspace_file_hints_enabled,
)
from core.config.models import resolve_model_name
from core.config.spec_validation import spec_validation_enabled
from core.context.assemble import assemble_context
from core.context.budget import apply_context_budget, resolve_context_budget_tokens
from core.context.helper_llm_pipeline import (
    apply_architect_pass,
    apply_builder_llm,
    apply_spec_validation,
    merge_architect_plan,
)
from core.context.package import (
    COMPILER_VERSION,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
    summarize_context_package,
)
from core.context.summary import estimate_tokens, sha256_hex
from core.context.file_picker import CandidateFilesResult, pick_candidate_files
from core.context.capability_adjust import apply_backend_capabilities
from core.engine import get_engine
from core.engine.aider_engine import translate_context_package
from core.specs.delegation_policies import (
    DelegationPolicies,
    PolicyValidationError,
    load_delegation_policies,
)
from core.specs.read_deps_merge import resolve_spec_read_deps
from core.specs.paths import normalize_spec_path_arg, resolve_spec_path
from core.specs.read import read_task_spec


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _resolve_spec(
    workspace: Path,
    spec_path: str | Path,
) -> tuple[str | None, DelegationPolicies | None, str | None]:
    """Mirror delegate spec validation. Returns (spec_rel_path, policies, error)."""
    ws = str(workspace.resolve())
    try:
        spec_rel_path = normalize_spec_path_arg(str(spec_path))
        spec_abs_path = resolve_spec_path(ws, spec_rel_path)
    except ValueError as exc:
        return None, None, str(exc)

    if not spec_abs_path.is_file():
        return (
            spec_rel_path,
            None,
            (
                f"Step task spec not found: {spec_rel_path}. "
                f"Copy .mcp-coder/spec-template.md to {spec_rel_path} "
                "(one file per step; link epic: in front matter). "
                "For multi-step work, also create .mcp-coder/specs/epics/<slug>.md "
                "from spec-epic-template.md."
            ),
        )

    spec_read = read_task_spec(spec_abs_path, workspace=ws)
    try:
        policies = load_delegation_policies(
            spec_read.front_matter,
            spec_read.sections.get("Files", ""),
        )
    except PolicyValidationError as exc:
        return spec_rel_path, None, str(exc)

    return spec_rel_path, policies, None


def _entry_dict(entry: PathEntry, *, include_payloads: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "path": entry.path,
        "tier": entry.tier,
        "bytes": entry.bytes,
        "excerpt_path": entry.excerpt_path,
    }
    if include_payloads:
        data["payload"] = entry.payload
    return data


def _package_dict(package: ContextPackage, *, include_payloads: bool) -> dict[str, Any]:
    return {
        "brief": package.brief,
        "entries": [_entry_dict(e, include_payloads=include_payloads) for e in package.entries],
        "metadata": dict(package.metadata),
        "summary": summarize_context_package(package),
    }


def _adapter_preview_dict(
    package: ContextPackage,
    *,
    host_transcript: str | None,
    include_prompt: bool = False,
) -> dict[str, Any]:
    req = translate_context_package(package, host_transcript=host_transcript)
    read_paths_in_prompt = [
        e.path
        for e in package.entries
        if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT) and e.payload is not None
    ]
    preview: dict[str, Any] = {
        "fnames": req.fnames,
        "read_paths_in_prompt": read_paths_in_prompt,
        "prompt_chars": len(req.prompt),
        "prompt_tokens_est": estimate_tokens(req.prompt),
        "prompt_hash": sha256_hex(req.prompt),
    }
    if include_prompt:
        preview["prompt"] = req.prompt
    return preview


def _helper_phase_model(record: dict[str, Any] | None) -> str | None:
    if record is None:
        return None
    model = record.get("model")
    return str(model) if model else None


def _should_run_helper(
    *,
    requested: bool,
    workspace_enabled: bool,
    force_helpers: bool,
    respect_workspace_flags: bool,
) -> bool:
    if not requested:
        return False
    if force_helpers:
        return True
    if respect_workspace_flags:
        return workspace_enabled
    return True


def inspect_context_package(
    *,
    workspace: Path,
    task: str,
    target_files: list[str],
    context_summary: str | None = None,
    spec_path: str | Path | None = None,
    include_payloads: bool = False,
    include_adapter_preview: bool = True,
    include_prompt: bool = False,
    host_transcript: str | None = None,
    run_builder_llm: bool = False,
    run_architect: bool = False,
    run_spec_validation: bool = False,
    respect_workspace_flags: bool = True,
    force_helpers: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Compile ContextPackage (+ optional adapter preview) without calling the backend."""
    ws = workspace.resolve()
    ws_str = str(ws)

    spec_rel_path: str | None = None
    delegation_policies: DelegationPolicies | None = None
    spec_read = None

    if spec_path is not None:
        spec_rel_path, delegation_policies, spec_error = _resolve_spec(ws, spec_path)
        if spec_error:
            return {"ok": False, "error": spec_error}
        if spec_rel_path is not None:
            spec_abs = resolve_spec_path(ws_str, spec_rel_path)
            if spec_abs.is_file():
                spec_read = read_task_spec(spec_abs, workspace=ws_str)

    effective_target_files = list(target_files)
    auto_merged_read_paths: list[str] = []
    auto_merge_spec_read: bool | None = None
    spec_files_missing: list[str] = []
    contract_warnings: list[str] = []
    if delegation_policies is not None and delegation_policies.all_paths:
        merge_enabled = auto_merge_spec_read_enabled(ws)
        auto_merge_spec_read = merge_enabled
        merge_result, spec_files_missing, contract_warnings = resolve_spec_read_deps(
            files_edit=delegation_policies.files_edit,
            files_read=delegation_policies.files_read,
            all_paths=delegation_policies.all_paths,
            target_files=target_files,
            auto_merge_enabled=merge_enabled,
        )
        effective_target_files = merge_result.effective_target_files
        auto_merged_read_paths = merge_result.auto_merged_read_paths

    helper_phases: dict[str, Any] = {
        "spec_validation": {
            "ran": False,
            "passed": None,
            "clarification_needed": None,
            "would_block_delegate": False,
            "error": None,
            "model": None,
        },
        "rag_retrieval": {
            "ran": False,
            "hit_count": 0,
            "error": None,
        },
        "architect_pass": {
            "ran": False,
            "applied": False,
            "error": None,
            "model": None,
        },
        "builder_llm": {
            "ran": False,
            "applied": False,
            "error": None,
            "model": None,
        },
    }

    env_builder = _env_truthy("MCP_CODER_INSPECT_RUN_BUILDER_LLM")
    effective_run_builder = run_builder_llm or env_builder

    want_spec_validation = _should_run_helper(
        requested=run_spec_validation,
        workspace_enabled=spec_validation_enabled(ws),
        force_helpers=force_helpers,
        respect_workspace_flags=respect_workspace_flags,
    )
    if want_spec_validation and spec_read is not None and host_transcript and host_transcript.strip():
        (
            blocked,
            clarifications,
            ran,
            passed,
            val_error,
            _audit,
            val_record,
        ) = apply_spec_validation(
            spec_read=spec_read,
            workspace=ws_str,
            task=task,
            context_summary=context_summary or "",
            host_transcript=host_transcript,
        )
        helper_phases["spec_validation"] = {
            "ran": ran,
            "passed": passed,
            "clarification_needed": clarifications,
            "would_block_delegate": blocked,
            "error": val_error,
            "model": _helper_phase_model(val_record),
        }

    # Same picker path as delegate (dry-run parity, P4-001a)
    picker_result: CandidateFilesResult | None = None
    rag_retrieval_refs: list[Any] = []
    delegation_rag_refs: list[Any] = []
    workspace_file_rag_refs: list[Any] = []
    rag_retrieval_on = False
    workspace_file_hints_on = False
    builder_history_rag_on = False

    if delegation_policies is not None and context_builder_enabled(ws):
        from core.rag.builder_retrieval import (
            rag_retrieval_should_run,
            run_builder_workspace_file_retrieval,
            run_merged_builder_rag_retrieval,
        )

        rag_should_run, _ = rag_retrieval_should_run(
            ws, builder_on=True, implement_mode=True
        )
        workspace_rag_paths_for_picker: list[str] = []
        if workspace_file_hints_enabled(ws):
            workspace_file_hints_on = True
            try:
                spec_sections_pre = spec_read.sections if spec_read is not None else None
                workspace_file_rag_refs = run_builder_workspace_file_retrieval(
                    ws_str,
                    task=task,
                    spec_sections=spec_sections_pre,
                )
                workspace_rag_paths_for_picker = [ref.id for ref in workspace_file_rag_refs]
            except Exception:
                workspace_file_rag_refs = []
                workspace_rag_paths_for_picker = []
        if builder_history_rag_enabled(ws):
            builder_history_rag_on = True
        if rag_should_run:
            rag_retrieval_on = True

        spec_text: str | None = None
        if spec_rel_path is not None:
            spec_abs = resolve_spec_path(ws_str, spec_rel_path)
            if spec_abs.is_file():
                spec_text = read_task_spec(spec_abs, workspace=ws_str).raw_text
        picker_result = pick_candidate_files(
            workspace=ws,
            task=task,
            spec_text=spec_text,
            policies=delegation_policies,
            target_files=effective_target_files,
            workspace_rag_paths=workspace_rag_paths_for_picker or None,
        )

        if rag_retrieval_on:
            try:
                spec_sections = spec_read.sections if spec_read is not None else None
                (
                    delegation_rag_refs,
                    workspace_file_rag_refs,
                    rag_retrieval_refs,
                ) = run_merged_builder_rag_retrieval(
                    ws_str,
                    task=task,
                    spec_sections=spec_sections,
                )
                helper_phases["rag_retrieval"] = {
                    "ran": True,
                    "hit_count": len(rag_retrieval_refs),
                    "delegation_hits": len(delegation_rag_refs),
                    "file_hits": len(workspace_file_rag_refs),
                    "error": None,
                }
            except Exception as exc:
                rag_retrieval_refs = []
                helper_phases["rag_retrieval"] = {
                    "ran": True,
                    "hit_count": 0,
                    "delegation_hits": 0,
                    "file_hits": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }

    package = assemble_context(
        workspace=ws,
        spec_path=spec_rel_path,
        target_files=effective_target_files,
        task=task,
        context_summary=context_summary,
        policies=delegation_policies,
        picker_result=picker_result,
        include_repo_map=picker_result is not None,
    )

    architect_plan: str | None = None
    want_architect = _should_run_helper(
        requested=run_architect,
        workspace_enabled=architect_pass_enabled(ws),
        force_helpers=force_helpers,
        respect_workspace_flags=respect_workspace_flags,
    )
    if want_architect and spec_read is not None:
        architect_plan, arch_error, arch_record = apply_architect_pass(
            context_package=package,
            spec_read=spec_read,
            picker_result=picker_result,
            workspace=ws_str,
            task=task,
            context_summary=context_summary or "",
            host_transcript=host_transcript,
        )
        helper_phases["architect_pass"] = {
            "ran": True,
            "applied": architect_plan is not None,
            "error": arch_error,
            "model": _helper_phase_model(arch_record),
        }

    want_builder = (
        effective_run_builder
        and picker_result is not None
        and _should_run_helper(
            requested=True,
            workspace_enabled=context_builder_llm_enabled(ws),
            force_helpers=force_helpers,
            respect_workspace_flags=respect_workspace_flags,
        )
    )
    if want_builder:
        package, builder_applied, builder_error, builder_record = apply_builder_llm(
            context_package=package,
            picker_result=picker_result,
            workspace=ws_str,
            task=task,
            context_summary=context_summary or "",
            spec_rel_path=spec_rel_path,
            host_transcript=host_transcript,
            rag_refs=rag_retrieval_refs if rag_retrieval_on else None,
        )
        helper_phases["builder_llm"] = {
            "ran": True,
            "applied": builder_applied,
            "error": builder_error,
            "model": _helper_phase_model(builder_record),
        }
        package.metadata["builder_brief_applied"] = builder_applied
        if builder_error:
            package.metadata["builder_llm_error"] = builder_error
        elif "builder_llm_error" in package.metadata:
            package.metadata.pop("builder_llm_error", None)

    if architect_plan:
        package.brief = merge_architect_plan(architect_plan, package.brief)

    cap_warnings: list[str] = []
    if backend:
        try:
            caps = get_engine(backend).capabilities()
            package, cap_warnings = apply_backend_capabilities(
                package, caps, workspace=ws
            )
        except (NotImplementedError, AttributeError, Exception):
            cap_warnings = []

    # Apply budget pass (mirrors delegate pipeline for dry-run parity)
    budget_model = resolve_model_name()
    if backend:
        try:
            budget_model = get_engine(backend).model_name
        except Exception:
            pass
    budget = resolve_context_budget_tokens(model=budget_model)
    if budget is not None:
        package = apply_context_budget(package, workspace=ws, budget_tokens=budget)

    result: dict[str, Any] = {
        "ok": True,
        "compiler_version": package.metadata.get("compiler_version", COMPILER_VERSION),
        "context_package": _package_dict(package, include_payloads=include_payloads),
        "helper_phases": helper_phases,
        "context_refs": [],
    }
    if rag_retrieval_on:
        from core.rag.retrieval import context_refs_to_dict

        result["context_refs"] = context_refs_to_dict(rag_retrieval_refs)
    if cap_warnings:
        result["capability_warnings"] = cap_warnings

    if delegation_policies is not None and delegation_policies.all_paths:
        if auto_merged_read_paths:
            result["auto_merged_read_paths"] = auto_merged_read_paths
        if auto_merge_spec_read is not None:
            result["auto_merge_spec_read"] = auto_merge_spec_read
        if spec_files_missing:
            result["spec_files_missing_from_target"] = spec_files_missing
        if contract_warnings:
            result["contract_warnings"] = contract_warnings

    if include_adapter_preview:
        result["adapter_preview"] = _adapter_preview_dict(
            package,
            host_transcript=host_transcript,
            include_prompt=include_prompt,
        )

    return result
