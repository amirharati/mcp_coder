"""Cheap-LLM context builder call (P4-001b).

One-shot model call that returns an enhanced executor brief. No Coder, no file
changes. Mirrors core/engine/spec_review.py. Fails gracefully so the delegate
pipeline can fall back to the mechanical brief.
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
    raw_output: str = ""


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

    messages = [{"role": "user", "content": prompt}]

    completion = run_owned_helper_completion(
        messages,
        model=resolved,
        system_prompt=build_role_rules("builder"),
    )
    if completion.error:
        return BuilderLlmResult(
            success=False,
            brief="",
            model=resolved,
            error=completion.error,
            tokens=completion.tokens,
            duration_ms=completion.duration_ms,
        )

    text = completion.text
    duration_ms = completion.duration_ms
    tokens = completion.tokens
    output = text

    if not output.strip():
        return BuilderLlmResult(
            success=False,
            brief="",
            model=resolved,
            error="Empty builder response from model",
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
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
                tokens=tokens,
                duration_ms=duration_ms,
                raw_output=output,
            )
        return BuilderLlmResult(
            success=False,
            brief="",
            model=resolved,
            error=(
                "Builder response contained no markdown headings (reasoning leak?): "
                f"{output.strip()[:200]}"
            ),
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    narrative, finalize_error = _finalize_builder_brief(clean)
    if finalize_error:
        return BuilderLlmResult(
            success=False,
            brief="",
            model=resolved,
            error=finalize_error,
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    return BuilderLlmResult(
        success=True,
        brief=narrative,
        model=resolved,
        error=None,
        tokens=tokens,
        duration_ms=duration_ms,
        raw_output=output,
    )
