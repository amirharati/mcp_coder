"""Post-executor tier-1 reviewer prompt (P11-005). Backend-neutral."""

from __future__ import annotations

_MAX_ACCEPTANCE_CHARS = 1200
_MAX_DIFF_CHARS = 7000
_MAX_PROMPT_CHARS = 10000

REVIEWER_PREAMBLE = """## Role: junior code reviewer

You review a small code change after an executor run.
Your ONLY job: spot obvious problems in the diff — bugs, import/typing mistakes, naming, missing docstrings or tests.
You do NOT edit files, re-run the executor, or propose architecture redesign.

Rules:
- Begin your response IMMEDIATELY with exactly one of:
  - `## LGTM` followed by one short sentence
  - `## ISSUES` followed by up to 3 markdown bullets (`- `)
- No preamble, no reasoning narration, no code blocks."""


def _truncate(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 14] + "…[truncated]"


def build_reviewer_prompt(
    *,
    task: str,
    acceptance: str,
    files_changed: list[str],
    unified_diff: str,
) -> str:
    """Assemble the tier-1 reviewer LLM prompt."""
    sections = [REVIEWER_PREAMBLE]

    task_text = (task or "").strip()
    if task_text:
        sections.append(f"## Task\n{task_text}")

    acceptance_text = _truncate(acceptance, _MAX_ACCEPTANCE_CHARS)
    if acceptance_text:
        sections.append(f"## Acceptance\n{acceptance_text}")

    paths = [p.strip() for p in files_changed if (p or "").strip()]
    if paths:
        bullets = "\n".join(f"- `{p}`" for p in paths)
        sections.append(f"## Files changed\n{bullets}")

    diff_text = _truncate(unified_diff, _MAX_DIFF_CHARS)
    if diff_text:
        sections.append(f"## Unified diff\n```diff\n{diff_text}\n```")
    else:
        sections.append("## Unified diff\n(no diff available)")

    prompt = "\n\n".join(sections)
    if len(prompt) > _MAX_PROMPT_CHARS:
        return prompt[: _MAX_PROMPT_CHARS - 14] + "…[truncated]"
    return prompt
