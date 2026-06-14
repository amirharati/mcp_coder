"""Shared helper-LLM pipeline for delegate and inspect-context (P4.5-004).

Backend-neutral: only mutates ContextPackage.brief and returns audit metadata.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from core.config.role_models import ROLE_CONTEXT_BUILDER, resolve_role_budget_tokens
from core.observability.context import role_context
from core.usage.role_audit import build_role_usage_record

if TYPE_CHECKING:
    from core.context.file_picker import CandidateFilesResult
    from core.context.package import ContextPackage
    from core.rag.retrieval import ContextRef

BUILDER_BRIEF_HEADER = "## Builder brief"

SPEC_VALIDATION_BLOCK_OUTPUT = (
    "Spec validation blocked delegation. Answer clarifications in Cursor, "
    "update spec if needed, then retry delegate_to_agent."
)

LogWarnFn = Callable[[str, dict[str, Any]], None]


def _helper_provenance(
    *,
    input_prompt: str,
    output_text: str | None = None,
    error_text: str | None = None,
    raw_output: str | None = None,
) -> dict[str, Any]:
    """Minimal provenance bundle for compile_event emission (P7-003)."""
    prov: dict[str, Any] = {"input_prompt": input_prompt}
    if output_text:
        prov["output_text"] = output_text
    elif error_text:
        prov["output_text"] = error_text
    elif raw_output:
        prov["output_text"] = raw_output
    return prov


def merge_brief(mechanical_brief: str, llm_brief: str) -> str:
    """Prepend LLM narrative; keep mechanical brief (incl. accurate ## Paths) below."""
    return (
        f"{BUILDER_BRIEF_HEADER}\n\n"
        f"{llm_brief.strip()}\n\n"
        "---\n\n"
        f"{mechanical_brief.strip()}"
    )


def merge_architect_plan(architect_plan: str, brief: str) -> str:
    """Prepend architect plan above whatever brief is currently assembled."""
    return f"{architect_plan.strip()}\n\n---\n\n{brief.strip()}"


def apply_builder_llm(
    *,
    context_package: ContextPackage,
    picker_result: CandidateFilesResult | None,
    workspace: str,
    task: str,
    context_summary: str,
    spec_rel_path: str | None,
    host_transcript: str | None,
    timing: dict[str, int | float] | None = None,
    delegation_id: str | None = None,
    mcp_session_id: str | None = None,
    log_warn: LogWarnFn | None = None,
    rag_refs: list["ContextRef"] | None = None,
) -> tuple[ContextPackage, bool, str | None, dict[str, Any] | None, dict[str, Any]]:
    """Run the cheap-LLM brief pass; fall back to the mechanical brief on failure.

    Returns (package, builder_brief_applied, builder_llm_error, builder_record, provenance).
    Only ContextPackage.brief is ever mutated (D-P4-10).
    """
    from core.context.builder_history import BuilderHistoryContext, gather_builder_history
    from core.context.builder_prompt import build_builder_llm_prompt
    from core.engine.context_builder_llm import run_context_builder_llm
    from core.observability import get_observability

    mechanical_brief = context_package.brief
    t_builder = time.perf_counter()

    history = gather_builder_history(Path(workspace), spec_path=spec_rel_path)
    obs = get_observability()
    prior_reasoning = []
    if (
        mcp_session_id
        and delegation_id
        and obs.capture_reasoning_enabled(workspace)
    ):
        prior_reasoning = obs.get_prior_reasoning_for_builder(
            mcp_session_id,
            exclude_delegation_id=delegation_id,
        )
    history = BuilderHistoryContext(
        same_spec=history.same_spec,
        project_recent=history.project_recent,
        prior_reasoning=prior_reasoning,
    )
    budget_tokens = resolve_role_budget_tokens(ROLE_CONTEXT_BUILDER, workspace)
    prompt = build_builder_llm_prompt(
        mechanical_brief=mechanical_brief,
        picker_result=picker_result,
        package_metadata=context_package.metadata,
        history=history,
        host_transcript=host_transcript,
        context_summary=context_summary,
        task=task,
        budget_tokens=budget_tokens,
        rag_refs=rag_refs,
    )

    with role_context(ROLE_CONTEXT_BUILDER):
        llm_result = run_context_builder_llm(prompt, workspace_path=workspace)
    if timing is not None:
        timing["context_builder_llm_ms"] = int((time.perf_counter() - t_builder) * 1000)

    builder_record = build_role_usage_record(
        role=ROLE_CONTEXT_BUILDER,
        model=llm_result.model,
        input_tokens=llm_result.tokens.get("input"),
        output_tokens=llm_result.tokens.get("output"),
        total_tokens=llm_result.tokens.get("total"),
        duration_ms=llm_result.duration_ms,
        source=str(llm_result.tokens.get("source") or "context_builder_llm"),
    )

    if llm_result.success:
        context_package.brief = merge_brief(mechanical_brief, llm_result.brief)
        provenance = _helper_provenance(
            input_prompt=prompt,
            output_text=llm_result.brief,
            raw_output=llm_result.raw_output,
        )
        return context_package, True, None, builder_record, provenance

    if log_warn is not None:
        log_warn(
            "context_builder_llm_failed",
            {
                "delegation_id": delegation_id,
                "model": llm_result.model,
                "error": llm_result.error,
            },
        )
    provenance = _helper_provenance(
        input_prompt=prompt,
        error_text=llm_result.error,
        raw_output=llm_result.raw_output,
    )
    return context_package, False, llm_result.error, builder_record, provenance


def apply_architect_pass(
    *,
    context_package: ContextPackage,
    spec_read: Any,
    picker_result: CandidateFilesResult | None,
    workspace: str,
    task: str,
    context_summary: str,
    host_transcript: str | None,
    timing: dict[str, int | float] | None = None,
    delegation_id: str | None = None,
    log_warn: LogWarnFn | None = None,
) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, Any]]:
    """Run architect pass and return (architect_plan, error, model_record, provenance)."""
    from core.context.architect_prompt import build_architect_pass_prompt
    from core.engine.architect_pass_llm import run_architect_pass_llm

    t_arch = time.perf_counter()
    prompt = build_architect_pass_prompt(
        spec_read=spec_read,
        mechanical_brief=context_package.brief,
        picker_result=picker_result,
        host_transcript=host_transcript,
        task=task,
        context_summary=context_summary,
    )
    with role_context("architect_pass"):
        llm_result = run_architect_pass_llm(prompt, workspace_path=workspace)
    if timing is not None:
        timing["architect_pass_ms"] = int((time.perf_counter() - t_arch) * 1000)

    architect_record = build_role_usage_record(
        role="architect_pass",
        model=llm_result.model,
        input_tokens=llm_result.tokens.get("input"),
        output_tokens=llm_result.tokens.get("output"),
        total_tokens=llm_result.tokens.get("total"),
        duration_ms=llm_result.duration_ms,
        source=str(llm_result.tokens.get("source") or "architect_pass"),
    )

    if llm_result.success:
        provenance = _helper_provenance(
            input_prompt=prompt,
            output_text=llm_result.plan,
            raw_output=llm_result.raw_output,
        )
        return llm_result.plan, None, architect_record, provenance

    if log_warn is not None:
        log_warn(
            "architect_pass_failed",
            {
                "delegation_id": delegation_id,
                "model": llm_result.model,
                "error": llm_result.error,
            },
        )
    provenance = _helper_provenance(
        input_prompt=prompt,
        error_text=llm_result.error,
        raw_output=llm_result.raw_output,
    )
    return None, llm_result.error, architect_record, provenance


def apply_spec_validation(
    *,
    spec_read: Any,
    workspace: str,
    task: str,
    context_summary: str,
    host_transcript: str,
    timing: dict[str, int | float] | None = None,
    delegation_id: str | None = None,
    log_warn: LogWarnFn | None = None,
) -> tuple[
    bool,
    list[str] | None,
    bool,
    bool | None,
    str | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any],
]:
    """Run pre-delegate spec validation LLM.

    Returns (blocked, clarifications, ran, passed, error, audit_dict, model_record, provenance).
    On LLM/parse failure: not blocked, ran=False, audit includes error.
    """
    from core.context.spec_validation_prompt import build_spec_validation_prompt
    from core.engine.spec_validation_llm import run_spec_validation_llm

    t_val = time.perf_counter()
    prompt = build_spec_validation_prompt(
        spec_read=spec_read,
        host_transcript=host_transcript,
        task=task,
        context_summary=context_summary,
    )
    with role_context("spec_validation"):
        llm_result = run_spec_validation_llm(prompt, workspace_path=workspace)
    if timing is not None:
        timing["spec_validation_ms"] = int((time.perf_counter() - t_val) * 1000)

    model_record = build_role_usage_record(
        role="spec_validation",
        model=llm_result.model,
        input_tokens=llm_result.tokens.get("input"),
        output_tokens=llm_result.tokens.get("output"),
        total_tokens=llm_result.tokens.get("total"),
        duration_ms=llm_result.duration_ms,
        source=str(llm_result.tokens.get("source") or "spec_validation"),
    )

    if not llm_result.success or llm_result.passed is None:
        if log_warn is not None:
            log_warn(
                "spec_validation_failed",
                {
                    "delegation_id": delegation_id,
                    "model": llm_result.model,
                    "error": llm_result.error,
                },
            )
        audit: dict[str, Any] = {
            "ran": False,
            "passed": None,
            "clarifications_count": 0,
            "duration_ms": llm_result.duration_ms,
        }
        if llm_result.error:
            audit["error"] = llm_result.error
        provenance = _helper_provenance(
            input_prompt=prompt,
            error_text=llm_result.error,
            raw_output=llm_result.raw_output,
        )
        return False, None, False, None, llm_result.error, audit, model_record, provenance

    if llm_result.passed is True:
        audit = {
            "ran": True,
            "passed": True,
            "clarifications_count": 0,
            "duration_ms": llm_result.duration_ms,
        }
        provenance = _helper_provenance(
            input_prompt=prompt,
            raw_output=llm_result.raw_output,
            output_text=llm_result.raw_output,
        )
        return False, None, True, True, None, audit, model_record, provenance

    clarifications = llm_result.clarifications
    audit = {
        "ran": True,
        "passed": False,
        "clarifications_count": len(clarifications),
        "duration_ms": llm_result.duration_ms,
    }
    output_text = llm_result.raw_output or "\n".join(f"- {c}" for c in clarifications)
    provenance = _helper_provenance(
        input_prompt=prompt,
        output_text=output_text,
        raw_output=llm_result.raw_output,
    )
    return True, clarifications, True, False, None, audit, model_record, provenance
