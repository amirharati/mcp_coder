"""Pre-delegate clarity check prompt (P11-001). Backend-neutral."""

from __future__ import annotations

from typing import Any

_MAX_SECTION_CHARS = 500
_MAX_PROMPT_CHARS = 12000

# After this many blocked rounds on the same spec, auto-pass without running the LLM.
CLARITY_ROUND_CAP = 2


CLARITY_RETRY_CONTEXT = """## Clarity retry context

This is clarity round {round_n}. The host already answered previous questions in
the `## Q&A` section of the spec.

Return `## CLEAR` unless something is **catastrophically** ambiguous — i.e. the
executor would produce code that must be completely thrown away.

Do NOT re-ask anything already answered in `## Q&A` or `context_summary`."""


def _truncate(text: str, max_chars: int = _MAX_SECTION_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 14] + "…[truncated]"


def build_clarity_check_prompt(
    *,
    task: str,
    spec_read: Any,
    context_summary: str = "",
    recent_delegation_titles: list[str],
    prior_blocked_count: int = 0,
) -> str:
    """Assemble the clarity-check LLM prompt.

    `prior_blocked_count` — how many times clarity has already blocked this task.
    When > 0, use the stricter retry preamble and surface Q&A / context_summary answers.
    """
    goal = _truncate((spec_read.sections.get("Goal") or "").strip()) if spec_read else ""
    files = _truncate((spec_read.sections.get("Files") or "").strip()) if spec_read else ""
    qa = _truncate((spec_read.sections.get("Q&A") or "").strip(), 2000) if spec_read else ""

    sections = []
    if prior_blocked_count > 0:
        sections.append(CLARITY_RETRY_CONTEXT.format(round_n=prior_blocked_count + 1))

    task_text = (task or "").strip()
    if task_text:
        sections.append(f"## Task\n{task_text}")

    # Surface Q&A first so the LLM sees what's already answered
    if qa:
        sections.append(f"## Q&A (already answered — do not re-ask)\n{qa}")

    ctx = (context_summary or "").strip()
    if ctx:
        sections.append(f"## context_summary\n{_truncate(ctx, 1000)}")

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
