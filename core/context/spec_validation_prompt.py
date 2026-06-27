"""Pre-delegate spec validation prompt (P4-009). Backend-neutral."""

from __future__ import annotations

from core.specs.read import SpecReadResult

_TRANSCRIPT_TAIL_CHARS = 8000


def _truncate_transcript_tail(text: str, max_chars: int = _TRANSCRIPT_TAIL_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return "…[truncated]\n" + text[-max_chars:]


def _spec_section(spec_read: SpecReadResult) -> str:
    parts = ["## Task spec"]
    goal = (spec_read.sections.get("Goal") or "").strip()
    if goal:
        parts.append("### Goal\n" + goal)
    constraints = (spec_read.sections.get("Constraints") or "").strip()
    if constraints:
        parts.append("### Constraints\n" + constraints)
    files = (spec_read.sections.get("Files") or "").strip()
    if files:
        parts.append("### Files\n" + files)
    if spec_read.prompt_block and not goal and not constraints and not files:
        parts.append(spec_read.prompt_block.strip())
    return "\n\n".join(parts)


def build_spec_validation_prompt(
    *,
    spec_read: SpecReadResult,
    host_transcript: str,
    task: str,
    context_summary: str,
) -> str:
    """Assemble the spec-validation LLM prompt."""
    sections = [
        _spec_section(spec_read),
    ]
    task_text = (task or "").strip()
    if task_text:
        sections.append(f"## Delegate task\n{task_text}")
    summary = (context_summary or "").strip()
    if summary:
        sections.append(f"## Planner context summary\n{summary}")
    transcript = _truncate_transcript_tail((host_transcript or "").strip())
    if transcript:
        sections.append("## Recent host conversation\n" + transcript)
    return "\n\n".join(sections)
