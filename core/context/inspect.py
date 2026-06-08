"""Dry-run context compiler inspection (no execution backend)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.context.assemble import assemble_context
from core.context.budget import apply_context_budget, resolve_context_budget_tokens
from core.context.package import (
    COMPILER_VERSION,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
    summarize_context_package,
)
from core.context.summary import estimate_tokens, sha256_hex
from core.config.models import resolve_model_name
from core.engine.aider_engine import translate_context_package
from core.specs.delegation_policies import (
    DelegationPolicies,
    PolicyValidationError,
    load_delegation_policies,
)
from core.specs.files_contract import build_contract_warnings, paths_missing_from_target
from core.specs.paths import normalize_spec_path_arg, resolve_spec_path
from core.specs.read import read_task_spec


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
) -> dict[str, Any]:
    req = translate_context_package(package, host_transcript=host_transcript)
    read_paths_in_prompt = [
        e.path
        for e in package.entries
        if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT) and e.payload is not None
    ]
    return {
        "fnames": req.fnames,
        "read_paths_in_prompt": read_paths_in_prompt,
        "prompt_chars": len(req.prompt),
        "prompt_tokens_est": estimate_tokens(req.prompt),
        "prompt_hash": sha256_hex(req.prompt),
    }


def inspect_context_package(
    *,
    workspace: Path,
    task: str,
    target_files: list[str],
    context_summary: str | None = None,
    spec_path: str | Path | None = None,
    include_payloads: bool = False,
    include_adapter_preview: bool = True,
    host_transcript: str | None = None,
) -> dict[str, Any]:
    """Compile ContextPackage (+ optional adapter preview) without calling the backend."""
    ws = workspace.resolve()

    spec_rel_path: str | None = None
    delegation_policies: DelegationPolicies | None = None

    if spec_path is not None:
        spec_rel_path, delegation_policies, spec_error = _resolve_spec(ws, spec_path)
        if spec_error:
            return {"ok": False, "error": spec_error}

    package = assemble_context(
        workspace=ws,
        spec_path=spec_rel_path,
        target_files=target_files,
        task=task,
        context_summary=context_summary,
        policies=delegation_policies,
    )

    # Apply budget pass (mirrors delegate pipeline for dry-run parity)
    budget_model = resolve_model_name()
    budget = resolve_context_budget_tokens(model=budget_model)
    if budget is not None:
        package = apply_context_budget(package, workspace=ws, budget_tokens=budget)

    result: dict[str, Any] = {
        "ok": True,
        "compiler_version": package.metadata.get("compiler_version", COMPILER_VERSION),
        "context_package": _package_dict(package, include_payloads=include_payloads),
    }

    if delegation_policies is not None and delegation_policies.all_paths:
        spec_files_missing = paths_missing_from_target(
            delegation_policies.all_paths,
            target_files,
        )
        contract_warnings = build_contract_warnings(spec_files_missing)
        if spec_files_missing:
            result["spec_files_missing_from_target"] = spec_files_missing
        if contract_warnings:
            result["contract_warnings"] = contract_warnings

    if include_adapter_preview:
        result["adapter_preview"] = _adapter_preview_dict(
            package,
            host_transcript=host_transcript,
        )

    return result
