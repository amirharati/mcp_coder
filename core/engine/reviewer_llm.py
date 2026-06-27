"""Cheap-LLM post-executor tier-1 reviewer (P11-005).

One-shot model call that scans files_changed + acceptance context.
Fails gracefully so the delegate pipeline can proceed when the reviewer errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.config.models import provider_hint_for_model
from core.config.providers import apply_provider_env
from core.config.role_models import ROLE_REVIEW, resolve_role_model_name
from core.context.role_rules import build_role_rules
from core.engine.owned_helper_llm import run_owned_helper_completion

_ERROR_MARKERS = (
    "litellm.",
    "notfounderror",
    "authenticationerror",
    "ratelimiterror",
    "openrouterexception",
    "openaierror",
)

_HEADING_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]+\S|(?:[-*][ \t]*)?(?:#{1,6}[ \t]*)?(?:\*\*)?(?:LGTM|ISSUES?)(?:\*\*)?[ \t]*(?:[:\-–—][ \t]*)?)",
    re.MULTILINE | re.IGNORECASE,
)
_CODE_FENCE_LINE_RE = re.compile(r"^\s*```")
_LGTM_RE = re.compile(
    r"^[ \t]*(?:[-*][ \t]*)?(?:#{1,6}[ \t]*)?(?:\*\*)?LGTM(?:\*\*)?[ \t]*(?:[:\-–—][ \t]*)?(.*)$",
    re.MULTILINE | re.IGNORECASE,
)
_ISSUES_RE = re.compile(
    r"^[ \t]*(?:[-*][ \t]*)?(?:#{1,6}[ \t]*)?(?:\*\*)?ISSUES?(?:\*\*)?[ \t]*(?:[:\-–—][ \t]*)?(.*)$",
    re.MULTILINE | re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")

_MAX_ISSUES = 3
_MAX_NOTE_CHARS = 500


def _strip_code_fences(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return text
    cleaned: list[str] = []
    in_fence = False
    saw_fence = False
    for line in lines:
        if _CODE_FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            saw_fence = True
            continue
        if not in_fence:
            cleaned.append(line)
    if not saw_fence:
        return text
    return "\n".join(cleaned).strip()


def _strip_reasoning_preamble(text: str) -> str:
    m = _HEADING_RE.search(text)
    if m is None:
        return ""
    return text[m.start() :].strip()


def _parse_issue_bullets(body: str) -> list[str]:
    items: list[str] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line.strip())
        if not m:
            continue
        item = m.group(1).strip()
        if item:
            items.append(item)
        if len(items) >= _MAX_ISSUES:
            break
    return items


def _clamp_note(text: str) -> str:
    text = text.strip()
    if len(text) <= _MAX_NOTE_CHARS:
        return text
    return text[: _MAX_NOTE_CHARS - 3] + "..."


def parse_reviewer_output(
    raw_output: str,
) -> tuple[Literal["lgtm", "issues"] | None, str, str | None]:
    """Parse model output. Returns (outcome, note, error)."""
    narrative = _strip_code_fences(raw_output)
    narrative = _strip_reasoning_preamble(narrative)
    if not narrative:
        return None, "", "no markdown heading in reviewer response"

    lower = narrative.lower()
    if any(m in lower for m in _ERROR_MARKERS):
        return None, "", narrative[:2000]

    lgtm_match = _LGTM_RE.search(narrative)
    if lgtm_match is not None:
        body = narrative[lgtm_match.end() :].strip()
        inline_note = lgtm_match.group(1).strip()
        first_line = inline_note or (body.splitlines()[0].strip() if body else "")
        return "lgtm", _clamp_note(first_line), None

    issues_match = _ISSUES_RE.search(narrative)
    if issues_match is None:
        return None, "", "missing LGTM or ISSUES heading"

    inline_body = issues_match.group(1).strip()
    body = "\n".join(
        part for part in (inline_body, narrative[issues_match.end() :].strip()) if part
    )
    bullets = _parse_issue_bullets(body)
    if not bullets:
        return None, "", "ISSUES heading without bullet points"
    note = _clamp_note("\n".join(f"- {b}" for b in bullets))
    return "issues", note, None


@dataclass
class ReviewerResult:
    success: bool
    outcome: Literal["lgtm", "issues"] | None
    note: str
    model: str
    error: str | None = None
    tokens: dict[str, Any] = field(default_factory=lambda: {"source": "unavailable"})
    duration_ms: int = 0
    raw_output: str = ""


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


def run_reviewer_llm(
    prompt: str,
    *,
    workspace_path: str | Path,
) -> ReviewerResult:
    """One-shot reviewer call. On parse/LLM failure returns success=False (pass-through)."""
    apply_provider_env()
    resolved = resolve_role_model_name(ROLE_REVIEW, workspace_path)

    config_error = provider_hint_for_model(resolved)
    if config_error:
        return ReviewerResult(
            success=False,
            outcome=None,
            note="",
            model=resolved,
            error=config_error,
            tokens=_unavailable_tokens(),
        )

    messages = [{"role": "user", "content": prompt}]
    completion = run_owned_helper_completion(
        messages,
        model=resolved,
        system_prompt=build_role_rules("reviewer"),
    )
    if completion.error:
        return ReviewerResult(
            success=False,
            outcome=None,
            note="",
            model=resolved,
            error=completion.error,
            tokens=completion.tokens,
            duration_ms=completion.duration_ms,
        )

    output = completion.text
    duration_ms = completion.duration_ms
    tokens = completion.tokens

    if not output.strip():
        return ReviewerResult(
            success=False,
            outcome=None,
            note="",
            model=resolved,
            error="Empty reviewer response from model",
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    outcome, note, parse_error = parse_reviewer_output(output)
    if parse_error:
        return ReviewerResult(
            success=False,
            outcome=None,
            note="",
            model=resolved,
            error=parse_error,
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    return ReviewerResult(
        success=True,
        outcome=outcome,
        note=note,
        model=resolved,
        error=None,
        tokens=tokens,
        duration_ms=duration_ms,
        raw_output=output,
    )
