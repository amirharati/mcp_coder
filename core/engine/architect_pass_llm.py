"""Cheap-LLM architect pass (P4-020).

One-shot model call that returns a short "## Architect plan" section. Fails
gracefully so delegations continue with the mechanical/builder brief.
"""

from __future__ import annotations

import concurrent.futures
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config.models import provider_hint_for_model
from core.config.providers import apply_provider_env
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
_ARCHITECT_HEADER_RE = re.compile(r"^##\s+Architect\s+plan\s*$", re.IGNORECASE)
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


def _finalize_architect_plan(raw_output: str) -> tuple[str, str | None]:
    narrative = _strip_code_fences(raw_output).strip()
    if not narrative:
        return "", "architect plan empty after stripping code fences"
    lines = narrative.splitlines()
    if not lines or not _ARCHITECT_HEADER_RE.match(lines[0].strip()):
        return "", "architect response must start with '## Architect plan'"
    lower = narrative.lower()
    if any(m in lower for m in _ERROR_MARKERS):
        return "", narrative[:2000]
    if len(narrative) > _MAX_PLAN_CHARS:
        narrative = narrative[: _MAX_PLAN_CHARS - 20] + "\n…[truncated]"
    return narrative, None


@dataclass
class ArchitectPassLlmResult:
    success: bool
    plan: str
    model: str
    error: str | None = None
    tokens: dict[str, Any] = field(default_factory=lambda: {"source": "unavailable"})
    duration_ms: int = 0


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


def run_architect_pass_llm(
    prompt: str,
    *,
    workspace_path: str | Path,
) -> ArchitectPassLlmResult:
    """One-shot architect model call. On failures, returns success=False."""
    apply_provider_env()
    resolved = resolve_role_model_name(ROLE_CONTEXT_BUILDER, workspace_path)

    config_error = provider_hint_for_model(resolved)
    if config_error:
        return ArchitectPassLlmResult(
            success=False,
            plan="",
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
        return ArchitectPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error=f"{type(exc).__name__}: {exc}",
            tokens=_unavailable_tokens(),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    output = text or captured
    if not output.strip():
        return ArchitectPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error="Empty architect response from model",
            tokens=_unavailable_tokens(),
            duration_ms=duration_ms,
        )

    clean = _strip_reasoning_preamble(output)
    if not clean:
        lower = output.lower()
        if any(m in lower for m in _ERROR_MARKERS):
            return ArchitectPassLlmResult(
                success=False,
                plan="",
                model=resolved,
                error=output.strip()[:2000],
                tokens=_unavailable_tokens(),
                duration_ms=duration_ms,
            )
        return ArchitectPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error=(
                "Architect response contained no markdown headings (reasoning leak?): "
                f"{output.strip()[:200]}"
            ),
            tokens=_unavailable_tokens(),
            duration_ms=duration_ms,
        )

    plan, finalize_error = _finalize_architect_plan(clean)
    if finalize_error:
        return ArchitectPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error=finalize_error,
            tokens=_extract_architect_tokens(model_obj),
            duration_ms=duration_ms,
        )

    return ArchitectPassLlmResult(
        success=True,
        plan=plan,
        model=resolved,
        error=None,
        tokens=_extract_architect_tokens(model_obj),
        duration_ms=duration_ms,
    )


def _extract_architect_tokens(model_obj: Any) -> dict[str, Any]:
    from core.usage.litellm_tokens import extract_litellm_model_tokens

    return extract_litellm_model_tokens(model_obj, role_source="architect_pass")
