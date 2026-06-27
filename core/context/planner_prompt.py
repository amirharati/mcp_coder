"""Planner pass prompt assembly (P11-008 rename from architect_prompt)."""

from __future__ import annotations

import re

from core.context.file_picker import CandidateFilesResult
from core.specs.read import SpecReadResult

_MAX_TRANSCRIPT_CHARS = 6000
_MAX_PATHS_CHARS = 4000

_PATHS_HEADING_RE = re.compile(r"^##\s+Paths\b", re.IGNORECASE | re.MULTILINE)


def _spec_summary(spec_read: SpecReadResult) -> str:
    parts = ["## Task spec summary"]
    goal = (spec_read.sections.get("Goal") or "").strip()
    if goal:
        parts.append("### Goal\n" + goal)
    constraints = (spec_read.sections.get("Constraints") or "").strip()
    if constraints:
        parts.append("### Constraints\n" + constraints)
    files = (spec_read.sections.get("Files") or "").strip()
    if files:
        parts.append("### Files\n" + files)
    if len(parts) == 1 and spec_read.prompt_block:
        parts.append(spec_read.prompt_block.strip())
    return "\n\n".join(parts)


def _paths_from_brief(mechanical_brief: str) -> str:
    m = _PATHS_HEADING_RE.search(mechanical_brief or "")
    if m is None:
        text = mechanical_brief.strip()
        return text[:_MAX_PATHS_CHARS]
    paths = mechanical_brief[m.start() :].strip()
    return paths[:_MAX_PATHS_CHARS]


def _picker_section(picker_result: CandidateFilesResult | None) -> str:
    if picker_result is None:
        return ""
    audit = picker_result.to_audit_dict()
    parts = ["## Candidate file audit"]
    ranked = audit.get("ranked_paths") or []
    if ranked:
        parts.append("Ranked paths:")
        parts.extend(f"- {p}" for p in ranked)
    suggested = audit.get("suggested_edit_paths") or []
    if suggested:
        parts.append("\nSuggested edit paths (audit only):")
        parts.extend(f"- {p}" for p in suggested)
    discovered = audit.get("discovered_read") or []
    if discovered:
        parts.append("\nDiscovered reads:")
        parts.extend(f"- {p}" for p in discovered)
    return "\n".join(parts)


def _transcript_tail(host_transcript: str | None) -> str:
    if not host_transcript or not host_transcript.strip():
        return ""
    text = host_transcript.strip()
    if len(text) > _MAX_TRANSCRIPT_CHARS:
        text = "…[truncated]\n" + text[-_MAX_TRANSCRIPT_CHARS:]
    return "## Recent host conversation\n" + text


def build_planner_pass_prompt(
    *,
    spec_read: SpecReadResult,
    mechanical_brief: str,
    picker_result: CandidateFilesResult | None,
    host_transcript: str | None,
    task: str,
    context_summary: str,
    project_state_section: str | None = None,
) -> str:
    """Assemble planner pass prompt from spec + planner + picker context."""
    parts = [
        _spec_summary(spec_read),
        "## Mechanical brief paths\n" + _paths_from_brief(mechanical_brief),
        _picker_section(picker_result),
    ]
    if project_state_section:
        parts.append(project_state_section)
    task_text = task.strip()
    if task_text:
        parts.append("## Delegate task\n" + task_text)
    summary_text = (context_summary or "").strip()
    if summary_text:
        parts.append("## Planner context\n" + summary_text)
    transcript = _transcript_tail(host_transcript)
    if transcript:
        parts.append(transcript)
    return "\n\n".join(p for p in parts if p)


# Backward-compat alias — old callers still work
def build_architect_pass_prompt(
    *,
    spec_read: SpecReadResult,
    mechanical_brief: str,
    picker_result: CandidateFilesResult | None,
    host_transcript: str | None,
    task: str,
    context_summary: str,
) -> str:
    """Deprecated alias for build_planner_pass_prompt (P11-008)."""
    return build_planner_pass_prompt(
        spec_read=spec_read,
        mechanical_brief=mechanical_brief,
        picker_result=picker_result,
        host_transcript=host_transcript,
        task=task,
        context_summary=context_summary,
        project_state_section=None,
    )
