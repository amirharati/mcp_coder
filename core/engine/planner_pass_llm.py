"""Cheap-LLM planner pass (P11-008 rename from architect_pass_llm).

One-shot model call that returns a short "## Planner plan" section. Fails
gracefully so delegations continue with the mechanical/builder brief.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config.models import provider_hint_for_model
from core.config.providers import apply_provider_env
from core.config.role_models import ROLE_PLANNER, resolve_role_model_name
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
_PLANNER_HEADER_RE = re.compile(r"^##\s+Planner\s+plan\s*$", re.IGNORECASE)
_MAX_PLAN_CHARS = 3000


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


def _finalize_planner_plan(raw_output: str) -> tuple[str, str | None]:
    narrative = _strip_code_fences(raw_output).strip()
    if not narrative:
        return "", "planner plan empty after stripping code fences"
    lines = narrative.splitlines()
    if not lines or not _PLANNER_HEADER_RE.match(lines[0].strip()):
        return "", "planner response must start with '## Planner plan'"
    lower = narrative.lower()
    if any(m in lower for m in _ERROR_MARKERS):
        return "", narrative[:2000]
    if len(narrative) > _MAX_PLAN_CHARS:
        narrative = narrative[: _MAX_PLAN_CHARS - 20] + "\n…[truncated]"
    return narrative, None


@dataclass
class PlannerPassLlmResult:
    success: bool
    plan: str
    model: str
    error: str | None = None
    tokens: dict[str, Any] = field(default_factory=lambda: {"source": "unavailable"})
    duration_ms: int = 0
    raw_output: str = ""


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


def run_planner_pass_llm(
    prompt: str,
    *,
    workspace_path: str | Path,
) -> PlannerPassLlmResult:
    """One-shot planner model call. On failures, returns success=False."""
    apply_provider_env()
    resolved = resolve_role_model_name(ROLE_PLANNER, workspace_path)

    config_error = provider_hint_for_model(resolved)
    if config_error:
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error=config_error,
            tokens=_unavailable_tokens(),
        )

    messages = [{"role": "user", "content": prompt}]
    completion = run_owned_helper_completion(messages, model=resolved)
    if completion.error:
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error=completion.error,
            tokens=completion.tokens,
            duration_ms=completion.duration_ms,
        )

    output = completion.text
    duration_ms = completion.duration_ms
    tokens = completion.tokens

    if not output.strip():
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error="Empty planner response from model",
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    clean = _strip_reasoning_preamble(output)
    if not clean:
        lower = output.lower()
        if any(m in lower for m in _ERROR_MARKERS):
            return PlannerPassLlmResult(
                success=False,
                plan="",
                model=resolved,
                error=output.strip()[:2000],
                tokens=tokens,
                duration_ms=duration_ms,
                raw_output=output,
            )
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error=(
                "Planner response contained no markdown headings (reasoning leak?): "
                f"{output.strip()[:200]}"
            ),
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    plan, finalize_error = _finalize_planner_plan(clean)
    if finalize_error:
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error=finalize_error,
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    return PlannerPassLlmResult(
        success=True,
        plan=plan,
        model=resolved,
        error=None,
        tokens=tokens,
        duration_ms=duration_ms,
        raw_output=output,
    )
