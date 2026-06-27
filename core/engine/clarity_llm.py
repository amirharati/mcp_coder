"""Cheap-LLM pre-delegate clarity check (P11-001).

One-shot model call that checks whether a task is specific enough to execute.
Fails gracefully so the delegate pipeline can proceed when the checker errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config.providers import apply_provider_env
from core.config.models import provider_hint_for_model
from core.config.role_models import ROLE_CONTEXT_BUILDER, resolve_role_model_name
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

_HEADING_RE = re.compile(r"^##\s+\S", re.MULTILINE)
_CODE_FENCE_LINE_RE = re.compile(r"^```\w*\s*$", re.MULTILINE)
_CLEAR_RE = re.compile(r"^##\s+CLEAR\s*$", re.MULTILINE | re.IGNORECASE)
_UNCLEAR_RE = re.compile(r"^##\s+UNCLEAR\s*$", re.MULTILINE | re.IGNORECASE)
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")

_MAX_QUESTIONS = 5


def _strip_code_fences(text: str) -> str:
    m = _CODE_FENCE_LINE_RE.search(text)
    if m is None:
        return text
    return text[: m.start()].rstrip()


def _strip_reasoning_preamble(text: str) -> str:
    m = _HEADING_RE.search(text)
    if m is None:
        return ""
    return text[m.start() :].strip()


def _parse_question_bullets(body: str) -> list[str]:
    items: list[str] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line.strip())
        if not m:
            continue
        item = m.group(1).strip()
        if item:
            items.append(item)
        if len(items) >= _MAX_QUESTIONS:
            break
    return items


def parse_clarity_check_output(raw_output: str) -> tuple[bool | None, list[str], str | None]:
    """Parse model output. Returns (passed, questions, error)."""
    narrative = _strip_code_fences(raw_output)
    narrative = _strip_reasoning_preamble(narrative)
    if not narrative:
        return None, [], "no markdown heading in clarity response"

    lower = narrative.lower()
    if any(m in lower for m in _ERROR_MARKERS):
        return None, [], narrative[:2000]

    if _CLEAR_RE.search(narrative):
        return True, [], None

    unclear_match = _UNCLEAR_RE.search(narrative)
    if unclear_match is None:
        return None, [], "missing CLEAR or UNCLEAR heading"

    body = narrative[unclear_match.end() :].strip()
    questions = _parse_question_bullets(body)
    if not questions:
        return None, [], "UNCLEAR heading without bullet questions"
    return False, questions, None


@dataclass
class ClarityCheckResult:
    success: bool
    passed: bool | None
    questions: list[str]
    model: str
    error: str | None = None
    tokens: dict[str, Any] = field(default_factory=lambda: {"source": "unavailable"})
    duration_ms: int = 0
    raw_output: str = ""


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


def run_clarity_check_llm(
    prompt: str,
    *,
    workspace_path: str | Path,
) -> ClarityCheckResult:
    """One-shot clarity check call. On parse/LLM failure returns success=False (pass-through)."""
    apply_provider_env()
    resolved = resolve_role_model_name(ROLE_CONTEXT_BUILDER, workspace_path)

    config_error = provider_hint_for_model(resolved)
    if config_error:
        return ClarityCheckResult(
            success=False,
            passed=None,
            questions=[],
            model=resolved,
            error=config_error,
            tokens=_unavailable_tokens(),
        )

    messages = [{"role": "user", "content": prompt}]
    completion = run_owned_helper_completion(
        messages,
        model=resolved,
        system_prompt=build_role_rules("clarity"),
    )
    if completion.error:
        return ClarityCheckResult(
            success=False,
            passed=None,
            questions=[],
            model=resolved,
            error=completion.error,
            tokens=completion.tokens,
            duration_ms=completion.duration_ms,
        )

    output = completion.text
    duration_ms = completion.duration_ms
    tokens = completion.tokens

    if not output.strip():
        return ClarityCheckResult(
            success=False,
            passed=None,
            questions=[],
            model=resolved,
            error="Empty clarity response from model",
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    passed, questions, parse_error = parse_clarity_check_output(output)
    if parse_error:
        return ClarityCheckResult(
            success=False,
            passed=None,
            questions=[],
            model=resolved,
            error=parse_error,
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    return ClarityCheckResult(
        success=True,
        passed=passed,
        questions=questions,
        model=resolved,
        error=None,
        tokens=tokens,
        duration_ms=duration_ms,
        raw_output=output,
    )
