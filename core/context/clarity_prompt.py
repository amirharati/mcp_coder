"""Pre-delegate clarity check prompt (P11-001). Backend-neutral."""

from __future__ import annotations

from typing import Any

_MAX_SECTION_CHARS = 500
_MAX_PROMPT_CHARS = 12000

CLARITY_PREAMBLE = """## Role: clarity checker

You review a task delegation request before it is executed.
Your ONLY job: decide whether the task is clear enough for a developer to START working on it.

**Default to `## CLEAR`.** Most well-formed requests pass, even if some details are unspecified — those can be decided during implementation. The bar is "can a competent developer reasonably interpret and start this?" not "is every edge case defined?".

Only return `## UNCLEAR` if the task is genuinely unexecutable without more information — e.g. the target file or feature is completely unknown, the instruction directly contradicts itself, or there is no way to know whether the output is correct.

Rules:
- Begin your response IMMEDIATELY with exactly one of:
  - `## CLEAR` — task is specific enough to start; details can emerge during implementation
  - `## UNCLEAR` — task cannot be reasonably started without answers to specific questions
- After `## UNCLEAR`, list at most 2 specific blocking questions as markdown bullets (`- `).
- Questions must be truly blocking (executor cannot make any reasonable assumption), not just "nice to know".
- When in doubt: return `## CLEAR`.
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
