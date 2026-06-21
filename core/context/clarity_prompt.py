"""Pre-delegate clarity check prompt (P11-001). Backend-neutral."""

from __future__ import annotations

from typing import Any

_MAX_SECTION_CHARS = 500
_MAX_PROMPT_CHARS = 12000

# After this many blocked rounds on the same spec, auto-pass without running the LLM.
CLARITY_ROUND_CAP = 2

CLARITY_PREAMBLE = """## Role: clarity check

You review a task delegation request before it is executed.
Your job: identify questions that would genuinely help the executor — questions where without an answer the executor would have to guess and might guess wrong.

**Execution is paused until questions are answered.** If you return `## UNCLEAR`, the host will add answers to the `## Q&A` section of the spec file and re-delegate. So only ask questions that are worth a round-trip.

Return `## CLEAR` when the task can be reasonably started — even if some details are unspecified. Executors are good at making sensible decisions during implementation.
Return `## UNCLEAR` when a question is genuinely blocking: without the answer, there's a meaningful chance the executor produces something wrong or incomplete that would need to be thrown away.

Rules:
- Begin your response IMMEDIATELY with exactly one of:
  - `## CLEAR` — task is well-formed; proceed
  - `## UNCLEAR` — execution is paused; list at most 2 specific blocking questions
- After `## UNCLEAR`, list at most 2 questions as markdown bullets (`- `).
- Questions must be genuinely blocking — not just "nice to have" details.
- If a `## Q&A` section is present in the spec, treat those answers as final — do NOT re-ask them.
- When in doubt: return `## CLEAR`. The cost of one wrong assumption is almost always less than a round-trip.
- No preamble, no reasoning narration, no code."""

CLARITY_PREAMBLE_RETRY = """## Role: clarity check (retry — round {round_n})

The host already answered your previous questions in the `## Q&A` section of the spec.
Return `## CLEAR` unless something is **catastrophically** ambiguous — i.e. the executor would produce code that must be completely thrown away.

Rules:
- Begin IMMEDIATELY with `## CLEAR` or `## UNCLEAR`.
- Do NOT re-ask anything already answered in `## Q&A` or `context_summary`.
- After `## UNCLEAR`, list at most 1 new question — it must be genuinely catastrophic.
- When in doubt: `## CLEAR`. The host has already invested time answering.
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

    if prior_blocked_count > 0:
        preamble = CLARITY_PREAMBLE_RETRY.format(round_n=prior_blocked_count + 1)
    else:
        preamble = CLARITY_PREAMBLE

    sections = [preamble]

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
