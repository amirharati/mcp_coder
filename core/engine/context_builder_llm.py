"""Cheap-LLM context builder call (P4-001b).

One-shot model call that returns an enhanced executor brief. No Coder, no file
changes. Mirrors core/engine/spec_review.py. Fails gracefully so the delegate
pipeline can fall back to the mechanical brief.
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

# Matches "## Heading" lines — the expected start of a valid builder brief.
_HEADING_RE = re.compile(r"^##\s+\S", re.MULTILINE)

# Line that opens or closes a markdown code fence (optional language tag).
_CODE_FENCE_LINE_RE = re.compile(r"^```\w*\s*$", re.MULTILINE)

_BUILDER_BRIEF_HEADER_RE = re.compile(r"^##\s+Builder brief\s*$", re.MULTILINE | re.IGNORECASE)

_MAX_NARRATIVE_CHARS = 4000


def _strip_code_fences(text: str) -> str:
    """Return text before the first line that is only ``` (optional language tag)."""
    m = _CODE_FENCE_LINE_RE.search(text)
    if m is None:
        return text
    return text[: m.start()].rstrip()


def _strip_redundant_builder_header(text: str) -> str:
    """Remove leading '## Builder brief' line if present (_merge_brief adds it)."""
    lines = text.splitlines()
    if lines and _BUILDER_BRIEF_HEADER_RE.match(lines[0].strip()):
        return "\n".join(lines[1:]).lstrip("\n")
    return text


def _finalize_builder_brief(raw_output: str) -> tuple[str, str | None]:
    """Validate and clean preamble-stripped output. Returns (narrative_brief, error)."""
    narrative = _strip_code_fences(raw_output)
    narrative = _strip_redundant_builder_header(narrative).strip()

    if not narrative:
        return "", "brief empty after stripping code fences"

    lower = narrative.lower()
    if any(m in lower for m in _ERROR_MARKERS):
        return "", narrative[:2000]

    if len(narrative) > _MAX_NARRATIVE_CHARS:
        narrative = narrative[: _MAX_NARRATIVE_CHARS - 20] + "\n…[truncated]"

    return narrative, None


def _strip_reasoning_preamble(text: str) -> str:
    """Drop leading reasoning/thinking prose before the first markdown ## heading.

    Models with extended thinking (e.g. Gemini Flash) sometimes emit a reasoning
    narration before the actual markdown output. We strip everything before the
    first '## ' heading so the executor only sees clean brief content.

    Returns empty string when no heading is found — caller treats this as failure.
    """
    m = _HEADING_RE.search(text)
    if m is None:
        return ""
    stripped = text[m.start():].strip()
    return stripped


@dataclass
class BuilderLlmResult:
    success: bool
    brief: str
    model: str
    error: str | None = None
    tokens: dict[str, Any] = field(default_factory=lambda: {"source": "unavailable"})
    duration_ms: int = 0


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


def run_context_builder_llm(
    prompt: str,
    *,
    workspace_path: str | Path,
) -> BuilderLlmResult:
    """One-shot builder model call. On any failure returns success=False."""
    apply_provider_env()
    resolved = resolve_role_model_name(ROLE_CONTEXT_BUILDER, workspace_path)

    config_error = provider_hint_for_model(resolved)
    if config_error:
        return BuilderLlmResult(
            success=False,
            brief="",
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
        return BuilderLlmResult(
            success=False,
            brief="",
            model=resolved,
            error=f"{type(exc).__name__}: {exc}",
            tokens=_unavailable_tokens(),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    output = text or captured

    if not output.strip():
        return BuilderLlmResult(
            success=False,
            brief="",
            model=resolved,
            error="Empty builder response from model",
            tokens=_unavailable_tokens(),
            duration_ms=duration_ms,
        )

    clean = _strip_reasoning_preamble(output)

    if not clean:
        # No markdown headings — API error text or reasoning-only leak.
        lower = output.lower()
        if any(m in lower for m in _ERROR_MARKERS):
            return BuilderLlmResult(
                success=False,
                brief="",
                model=resolved,
                error=output.strip()[:2000],
                tokens=_unavailable_tokens(),
                duration_ms=duration_ms,
            )
        return BuilderLlmResult(
            success=False,
            brief="",
            model=resolved,
            error=(
                "Builder response contained no markdown headings (reasoning leak?): "
                f"{output.strip()[:200]}"
            ),
            tokens=_unavailable_tokens(),
            duration_ms=duration_ms,
        )

    narrative, finalize_error = _finalize_builder_brief(clean)
    if finalize_error:
        return BuilderLlmResult(
            success=False,
            brief="",
            model=resolved,
            error=finalize_error,
            tokens=_unavailable_tokens(),
            duration_ms=duration_ms,
        )

    return BuilderLlmResult(
        success=True,
        brief=narrative,
        model=resolved,
        error=None,
        tokens=_extract_builder_tokens(model_obj),
        duration_ms=duration_ms,
    )


def _extract_builder_tokens(model_obj: Any) -> dict[str, Any]:
    from core.usage.litellm_tokens import extract_litellm_model_tokens

    return extract_litellm_model_tokens(model_obj, role_source="context_builder_llm")
