"""Cheap-LLM pre-delegate spec validation (P4-009).

One-shot model call that checks spec vs host transcript coherence. Fails gracefully
so the delegate pipeline can proceed when the validator errors.
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
_VALIDATION_OK_RE = re.compile(r"^##\s+Validation\s+OK\s*$", re.MULTILINE | re.IGNORECASE)
_CLARIFICATIONS_RE = re.compile(
    r"^##\s+Clarifications\s+needed\s*$", re.MULTILINE | re.IGNORECASE
)
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")

_MAX_CLARIFICATIONS = 5


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


def _parse_clarification_bullets(body: str) -> list[str]:
    items: list[str] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line.strip())
        if not m:
            continue
        item = m.group(1).strip()
        if item:
            items.append(item)
        if len(items) >= _MAX_CLARIFICATIONS:
            break
    return items


def parse_spec_validation_output(raw_output: str) -> tuple[bool | None, list[str], str | None]:
    """Parse model output. Returns (passed, clarifications, error)."""
    narrative = _strip_code_fences(raw_output)
    narrative = _strip_reasoning_preamble(narrative)
    if not narrative:
        return None, [], "no markdown heading in validation response"

    lower = narrative.lower()
    if any(m in lower for m in _ERROR_MARKERS):
        return None, [], narrative[:2000]

    if _VALIDATION_OK_RE.search(narrative):
        return True, [], None

    clar_match = _CLARIFICATIONS_RE.search(narrative)
    if clar_match is None:
        return None, [], "missing Validation OK or Clarifications needed heading"

    body = narrative[clar_match.end() :].strip()
    clarifications = _parse_clarification_bullets(body)
    if not clarifications:
        return None, [], "Clarifications needed heading without bullet questions"
    return False, clarifications, None


@dataclass
class SpecValidationLlmResult:
    success: bool
    passed: bool | None
    clarifications: list[str]
    model: str
    error: str | None = None
    tokens: dict[str, Any] = field(default_factory=lambda: {"source": "unavailable"})
    duration_ms: int = 0
    raw_output: str = ""


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


def run_spec_validation_llm(
    prompt: str,
    *,
    workspace_path: str | Path,
) -> SpecValidationLlmResult:
    """One-shot spec validation call. On parse/LLM failure returns success=False (pass-through)."""
    apply_provider_env()
    resolved = resolve_role_model_name(ROLE_CONTEXT_BUILDER, workspace_path)

    config_error = provider_hint_for_model(resolved)
    if config_error:
        return SpecValidationLlmResult(
            success=False,
            passed=None,
            clarifications=[],
            model=resolved,
            error=config_error,
            tokens=_unavailable_tokens(),
        )

    messages = [{"role": "user", "content": prompt}]
    completion = run_owned_helper_completion(
        messages,
        model=resolved,
        system_prompt=build_role_rules("spec_validation"),
    )
    if completion.error:
        return SpecValidationLlmResult(
            success=False,
            passed=None,
            clarifications=[],
            model=resolved,
            error=completion.error,
            tokens=completion.tokens,
            duration_ms=completion.duration_ms,
        )

    output = completion.text
    duration_ms = completion.duration_ms
    tokens = completion.tokens

    if not output.strip():
        return SpecValidationLlmResult(
            success=False,
            passed=None,
            clarifications=[],
            model=resolved,
            error="Empty validation response from model",
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    passed, clarifications, parse_error = parse_spec_validation_output(output)
    if parse_error:
        return SpecValidationLlmResult(
            success=False,
            passed=None,
            clarifications=[],
            model=resolved,
            error=parse_error,
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    return SpecValidationLlmResult(
        success=True,
        passed=passed,
        clarifications=clarifications,
        model=resolved,
        error=None,
        tokens=tokens,
        duration_ms=duration_ms,
        raw_output=output,
    )
