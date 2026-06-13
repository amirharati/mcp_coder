"""Builder LLM prompt assembly (P4-001b). Backend-neutral — no Aider APIs.

Concatenates the mechanical brief, picker audit, prior-delegation history, and
optional host transcript into one prompt for the cheap context-builder model.
Budget-aware: history sections (never contract paths) are truncated to fit an
optional per-role token budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.context.builder_history import BuilderHistoryContext
from core.context.file_picker import CandidateFilesResult
from core.context.summary import estimate_tokens

if TYPE_CHECKING:
    from core.rag.retrieval import ContextRef

BUILDER_PREAMBLE = """## Role: context builder

You assemble an executor-facing brief for a code delegation. You do NOT edit files.

Rules:
- Begin your response IMMEDIATELY with the line `## Builder brief` — no preamble, no
  reasoning narration, no "The user wants..." sentences before it.
- Output markdown only (no code fences wrapping the whole response).
- Do NOT paste file contents, code blocks, or ``` fences. Narrative bullets only.
- Do NOT repeat the ## Builder brief header — the pipeline adds it.
- Max ~400 words of guidance (executor has full file payloads separately).
- Preserve spec Goal and Constraints intent; do not contradict files_edit contract.
- Reference only paths from the candidate file list or spec contract.
- Summarize prior delegation outcomes when relevant (APIs shipped, failures to avoid).
- Do not invent file paths or APIs not supported by the inputs.
- Keep under ~800 words unless history is dense."""


def _picker_section(picker_result: CandidateFilesResult | None) -> str:
    if picker_result is None:
        return ""
    audit = picker_result.to_audit_dict()
    lines = ["## Candidate files (from rules picker)"]
    ranked = audit.get("ranked_paths") or []
    if ranked:
        lines.append("Ranked paths:")
        lines.extend(f"- {p}" for p in ranked)
    discovered = audit.get("discovered_read") or []
    if discovered:
        lines.append("\nDiscovered reads (symbol scan):")
        lines.extend(f"- {p}" for p in discovered)
    symbols = audit.get("symbol_queries") or []
    if symbols:
        lines.append("\nSymbols searched: " + ", ".join(symbols))
    if picker_result.path_sources:
        lines.append("\nPath sources:")
        for path in ranked:
            src = picker_result.path_sources.get(path)
            if src:
                lines.append(f"- {path}: {src}")
    return "\n".join(lines)


def _suggested_edits_section(picker_result: CandidateFilesResult | None) -> str:
    if picker_result is None or not picker_result.suggested_edit_paths:
        return ""
    paths = ", ".join(picker_result.suggested_edit_paths)
    return (
        "## Suggested edit paths (audit only, not in contract)\n"
        f"{paths}\n"
        "These are NOT in files_edit — do not instruct edits to them unless the "
        "spec contract is updated."
    )


def _format_history_row(row: dict[str, Any]) -> str:
    did = str(row.get("delegation_id") or "")[:8]
    outcome = row.get("outcome") or "?"
    mode = row.get("delegate_mode") or "?"
    created = row.get("created_count")
    modified = row.get("modified_count")
    summary = (row.get("checkpoint_summary") or "").strip()
    head = (
        f"- [{did}] mode={mode} outcome={outcome} "
        f"(+{created or 0}/~{modified or 0})"
    )
    if summary:
        head += f": {summary}"
    return head


def _history_section(history: BuilderHistoryContext) -> str:
    if history.is_empty():
        return ""
    parts: list[str] = ["## Prior delegations"]
    if history.same_spec:
        parts.append("Same spec (most recent first):")
        parts.extend(_format_history_row(r) for r in history.same_spec)
    if history.project_recent:
        parts.append("\nProject-wide (recent):")
        parts.extend(_format_history_row(r) for r in history.project_recent)
    return "\n".join(parts)


def _prior_reasoning_section(entries: list[Any]) -> str:
    if not entries:
        return ""
    parts: list[str] = ["## Prior reasoning"]
    for entry in entries:
        delegation_id = getattr(entry, "delegation_id", None) or entry.get("delegation_id", "")
        summary = getattr(entry, "reasoning_summary", None) or entry.get("reasoning_summary", "")
        if not summary:
            continue
        short_id = str(delegation_id)[:8]
        parts.append(f"- **{short_id}…**: {summary}")
    return "\n".join(parts) if len(parts) > 1 else ""


def _truncate_prior_reasoning_to_budget(
    entries: list[Any],
    *,
    fixed_tokens: int,
    budget_tokens: int,
) -> list[Any]:
    """Drop oldest prior-reasoning entries until the section fits the budget."""
    items = list(entries)
    while items:
        section = _prior_reasoning_section(items)
        if fixed_tokens + estimate_tokens(section) <= budget_tokens:
            break
        items.pop(0)
    return items


def dedupe_rag_refs_against_history(
    rag_refs: list["ContextRef"] | None,
    history: BuilderHistoryContext,
) -> list["ContextRef"]:
    """Drop delegation RAG refs whose id already appears in recency history."""
    if not rag_refs:
        return []
    seen_ids: set[str] = set()
    for row in history.same_spec + history.project_recent:
        did = row.get("delegation_id")
        if isinstance(did, str) and did:
            seen_ids.add(did)
    return [ref for ref in rag_refs if ref.id not in seen_ids]


def dedupe_file_refs_against_picker(
    file_refs: list["ContextRef"] | None,
    picker_result: CandidateFilesResult | None,
) -> list["ContextRef"]:
    """Drop workspace-file refs whose path is already in picker ranked paths."""
    if not file_refs or picker_result is None:
        return file_refs or []
    ranked = set(picker_result.ranked_paths)
    return [ref for ref in file_refs if ref.id not in ranked]


def _split_rag_refs(
    rag_refs: list["ContextRef"] | None,
) -> tuple[list["ContextRef"], list["ContextRef"]]:
    if not rag_refs:
        return [], []
    delegation = [r for r in rag_refs if r.kind == "delegation"]
    workspace_files = [r for r in rag_refs if r.kind == "workspace_file"]
    return delegation, workspace_files


def _format_rag_ref_line(ref: "ContextRef") -> str:
    did = ref.id[:8]
    spec = ref.metadata.get("spec_path") or "?"
    outcome = ref.metadata.get("outcome") or "?"
    score = ref.score if ref.score is not None else 0.0
    snippet = (ref.snippet or "").strip()
    head = f"- [{did}] spec={spec} outcome={outcome} score={score:.2f}"
    if snippet:
        head += f": {snippet}"
    return head


def _rag_section(rag_refs: list["ContextRef"]) -> str:
    if not rag_refs:
        return ""
    lines = ["## Relevant prior work"]
    lines.extend(_format_rag_ref_line(ref) for ref in rag_refs)
    return "\n".join(lines)


def _format_workspace_file_ref_line(ref: "ContextRef") -> str:
    path = ref.id
    score = ref.score if ref.score is not None else 0.0
    snippet = (ref.snippet or "").strip()
    head = f"- {path} (score {score:.2f})"
    if snippet:
        head += f": {snippet}"
    return head


def _workspace_files_section(file_refs: list["ContextRef"]) -> str:
    if not file_refs:
        return ""
    lines = ["## Related files (by summary)"]
    lines.extend(_format_workspace_file_ref_line(ref) for ref in file_refs)
    return "\n".join(lines)


def _combined_rag_sections(
    delegation_refs: list["ContextRef"],
    file_refs: list["ContextRef"],
) -> str:
    parts = [_rag_section(delegation_refs), _workspace_files_section(file_refs)]
    return "\n\n".join(p for p in parts if p)


def _truncate_rag_to_budget(
    delegation_refs: list["ContextRef"],
    file_refs: list["ContextRef"],
    *,
    fixed_tokens: int,
    budget_tokens: int,
) -> tuple[list["ContextRef"], list["ContextRef"]]:
    """Drop lowest-score refs (files first, then delegations) until sections fit."""
    d_refs = sorted(delegation_refs, key=lambda r: r.score or 0.0, reverse=True)
    f_refs = sorted(file_refs, key=lambda r: r.score or 0.0, reverse=True)
    while d_refs or f_refs:
        section = _combined_rag_sections(d_refs, f_refs)
        if fixed_tokens + estimate_tokens(section) <= budget_tokens:
            break
        if f_refs:
            f_refs.pop()
        elif d_refs:
            d_refs.pop()
    return d_refs, f_refs


def _transcript_section(host_transcript: str | None) -> str:
    if not host_transcript or not host_transcript.strip():
        return ""
    return "## Recent host conversation\n" + host_transcript.strip()


def _planner_section(context_summary: str, task: str, mechanical_brief: str) -> str:
    parts: list[str] = []
    task_text = task.strip()
    if task_text and task_text not in mechanical_brief:
        parts.append(f"## Task\n{task_text}")
    summary = (context_summary or "").strip()
    if summary and summary not in mechanical_brief:
        parts.append(f"## Planner context\n{summary}")
    return "\n\n".join(parts)


def _truncate_history_to_budget(
    history: BuilderHistoryContext,
    *,
    fixed_tokens: int,
    budget_tokens: int,
) -> BuilderHistoryContext:
    """Drop history rows (project first, then same_spec) until the section fits."""
    same_spec = list(history.same_spec)
    project = list(history.project_recent)

    def _fits() -> bool:
        section = _history_section(
            BuilderHistoryContext(same_spec=same_spec, project_recent=project)
        )
        return fixed_tokens + estimate_tokens(section) <= budget_tokens

    while not _fits() and project:
        project.pop()
    while not _fits() and same_spec:
        same_spec.pop()

    return BuilderHistoryContext(same_spec=same_spec, project_recent=project)


def build_builder_llm_prompt(
    *,
    mechanical_brief: str,
    picker_result: CandidateFilesResult | None,
    package_metadata: dict[str, Any],
    history: BuilderHistoryContext,
    host_transcript: str | None,
    context_summary: str,
    task: str,
    budget_tokens: int | None = None,
    rag_refs: list["ContextRef"] | None = None,
) -> str:
    """Assemble the builder prompt. History is truncated (not contract) to fit budget."""
    delegation_refs, file_refs = _split_rag_refs(rag_refs)
    delegation_refs = dedupe_rag_refs_against_history(delegation_refs, history)
    file_refs = dedupe_file_refs_against_picker(file_refs, picker_result)
    fixed_sections = [
        BUILDER_PREAMBLE,
        "## Mechanical brief\n" + mechanical_brief.strip(),
        _picker_section(picker_result),
        _suggested_edits_section(picker_result),
        _transcript_section(host_transcript),
        _planner_section(context_summary, task, mechanical_brief),
    ]
    fixed_text = "\n\n".join(s for s in fixed_sections if s)

    effective_history = history
    prior_reasoning = list(history.prior_reasoning)
    if budget_tokens is not None and prior_reasoning:
        prior_reasoning = _truncate_prior_reasoning_to_budget(
            prior_reasoning,
            fixed_tokens=estimate_tokens(fixed_text),
            budget_tokens=budget_tokens,
        )

    if budget_tokens is not None and not history.is_empty():
        fixed_with_reasoning = fixed_text
        if prior_reasoning:
            reasoning_text = _prior_reasoning_section(prior_reasoning)
            fixed_with_reasoning = fixed_text + ("\n\n" + reasoning_text if reasoning_text else "")
        effective_history = _truncate_history_to_budget(
            history,
            fixed_tokens=estimate_tokens(fixed_with_reasoning),
            budget_tokens=budget_tokens,
        )
    elif budget_tokens is not None and prior_reasoning:
        effective_history = history

    history_text = _history_section(effective_history)
    prior_reasoning_text = _prior_reasoning_section(prior_reasoning)
    history_tokens = estimate_tokens(history_text)
    prior_reasoning_tokens = estimate_tokens(prior_reasoning_text)
    effective_delegation_refs = delegation_refs
    effective_file_refs = file_refs
    if budget_tokens is not None and (delegation_refs or file_refs):
        effective_delegation_refs, effective_file_refs = _truncate_rag_to_budget(
            delegation_refs,
            file_refs,
            fixed_tokens=estimate_tokens(fixed_text)
            + history_tokens
            + prior_reasoning_tokens,
            budget_tokens=budget_tokens,
        )
    rag_text = _combined_rag_sections(effective_delegation_refs, effective_file_refs)

    ordered = [
        BUILDER_PREAMBLE,
        "## Mechanical brief\n" + mechanical_brief.strip(),
        _picker_section(picker_result),
        _suggested_edits_section(picker_result),
        prior_reasoning_text,
        history_text,
        rag_text,
        _transcript_section(host_transcript),
        _planner_section(context_summary, task, mechanical_brief),
    ]
    return "\n\n".join(s for s in ordered if s)
