"""Pre-delegate clarity check prompt (P11-001). Backend-neutral."""

from __future__ import annotations

from typing import Any

_MAX_SECTION_CHARS = 500
_MAX_PROMPT_CHARS = 12000

CLARITY_PREAMBLE = """## Role: clarity checker

You review a task delegation request before it is executed.
Your ONLY job: judge whether the task and spec have enough detail to proceed without stalling.
You do NOT implement anything and you do NOT edit files.

Rules:
- Begin your response IMMEDIATELY with exactly one of:
  - `## CLEAR` — task is specific enough to execute
  - `## UNCLEAR` — task is ambiguous or missing required decisions
- After `## UNCLEAR`, list 2–3 specific actionable questions as markdown bullets (`- `).
- Questions must target what the executor would stall on (missing file paths, ambiguous scope, conflicting instructions, missing acceptance criteria).
- No preamble, no reasoning narration, no code."""


def _truncate(text: str, max_chars: int = _MAX_SECTION_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 14] + "…[truncated]"


def build_clarity_check_prompt(
    *,
    task: str,
    spec_read: Any,
    recent_delegation_titles: list[str],
) -> str:
    """Assemble the clarity-check LLM prompt."""
    goal = _truncate((spec_read.sections.get("Goal") or "").strip()) if spec_read else ""
    files = _truncate((spec_read.sections.get("Files") or "").strip()) if spec_read else ""
    has_spec_sections = bool(goal or files)

    sections = [CLARITY_PREAMBLE]
    task_text = (task or "").strip()
    if task_text:
        sections.append(f"## Task\n{task_text}")

    if has_spec_sections:
        if goal:
            sections.append(f"## Spec: Goal\n{goal}")
        if files:
            sections.append(f"## Spec: Files\n{files}")

    titles = [t.strip() for t in recent_delegation_titles if (t or "").strip()]
    if titles:
        bullets = "\n".join(f"- {t}" for t in titles[:3])
        sections.append(f"## Recent delegations\n{bullets}")

    prompt = "\n\n".join(sections)
    if len(prompt) > _MAX_PROMPT_CHARS:
        return prompt[: _MAX_PROMPT_CHARS - 14] + "…[truncated]"
    return prompt
