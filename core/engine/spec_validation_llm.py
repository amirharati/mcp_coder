"""Cheap-LLM pre-delegate spec validation (P4-009).

One-shot model call that checks spec vs host transcript coherence. Fails gracefully
so the delegate pipeline can proceed when the validator errors.
"""

from __future__ import annotations

import concurrent.futures
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config.providers import apply_provider_env
from core.config.models import provider_hint_for_model
from core.config.role_models import ROLE_CONTEXT_BUILDER, resolve_role_model_name
from core.engine.stdio_isolation import isolated_stdio, merged_capture

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

    from aider.models import Model

    messages = [{"role": "user", "content": prompt}]
    t0 = time.perf_counter()

    def _call() -> tuple[str, str, Any]:
        with isolated_stdio() as (stdout_cap, stderr_cap):
            model = Model(resolved)
            reply = model.simple_send_with_retries(messages)
            captured = merged_capture(stdout_cap, stderr_cap)
            text = (reply or "").strip()
            if captured.strip() and not text:
                text = captured.strip()
            return text, captured, model

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            text, captured, model_obj = pool.submit(_call).result()
    except Exception as exc:
        return SpecValidationLlmResult(
            success=False,
            passed=None,
            clarifications=[],
            model=resolved,
            error=f"{type(exc).__name__}: {exc}",
            tokens=_unavailable_tokens(),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    output = text or captured
    if not output.strip():
        return SpecValidationLlmResult(
            success=False,
            passed=None,
            clarifications=[],
            model=resolved,
            error="Empty validation response from model",
            tokens=_unavailable_tokens(),
            duration_ms=duration_ms,
        )

    passed, clarifications, parse_error = parse_spec_validation_output(output)
    if parse_error:
        return SpecValidationLlmResult(
            success=False,
            passed=None,
            clarifications=[],
            model=resolved,
            error=parse_error,
            tokens=_extract_validation_tokens(model_obj),
            duration_ms=duration_ms,
        )

    return SpecValidationLlmResult(
        success=True,
        passed=passed,
        clarifications=clarifications,
        model=resolved,
        error=None,
        tokens=_extract_validation_tokens(model_obj),
        duration_ms=duration_ms,
    )


def _extract_validation_tokens(model_obj: Any) -> dict[str, Any]:
    from core.usage.litellm_tokens import extract_litellm_model_tokens

    return extract_litellm_model_tokens(model_obj, role_source="spec_validation")
