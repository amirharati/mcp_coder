"""Builder LLM prompt assembly (P4-001b). Backend-neutral — no Aider APIs.

Concatenates the mechanical brief, picker audit, prior-delegation history, and
optional host transcript into one prompt for the cheap context-builder model.
Budget-aware: history sections (never contract paths) are truncated to fit an
optional per-role token budget.
"""

from __future__ import annotations

from typing import Any

from core.context.builder_history import BuilderHistoryContext
from core.context.file_picker import CandidateFilesResult
from core.context.summary import estimate_tokens

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
) -> str:
    """Assemble the builder prompt. History is truncated (not contract) to fit budget."""
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
    if budget_tokens is not None and not history.is_empty():
        effective_history = _truncate_history_to_budget(
            history,
            fixed_tokens=estimate_tokens(fixed_text),
            budget_tokens=budget_tokens,
        )

    history_text = _history_section(effective_history)

    ordered = [
        BUILDER_PREAMBLE,
        "## Mechanical brief\n" + mechanical_brief.strip(),
        _picker_section(picker_result),
        _suggested_edits_section(picker_result),
        history_text,
        _transcript_section(host_transcript),
        _planner_section(context_summary, task, mechanical_brief),
    ]
    return "\n\n".join(s for s in ordered if s)
