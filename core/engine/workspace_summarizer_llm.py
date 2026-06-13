"""One-shot per-file workspace summary via context_builder role (P5-003)."""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config.providers import apply_provider_env
from core.config.models import provider_hint_for_model
from core.config.role_models import ROLE_CONTEXT_BUILDER, resolve_role_model_name
from core.engine.stdio_isolation import isolated_stdio, merged_capture
from core.usage.litellm_tokens import extract_litellm_model_tokens

SUMMARY_INPUT_MAX_CHARS = 8000
SUMMARY_OUTPUT_MAX_CHARS = 600

_ERROR_MARKERS = (
    "litellm.",
    "notfounderror",
    "authenticationerror",
    "ratelimiterror",
    "openrouterexception",
    "openaierror",
)


@dataclass
class WorkspaceSummaryResult:
    success: bool
    summary: str
    model: str
    error: str | None = None
    tokens: dict[str, Any] | None = None
    duration_ms: int = 0


def build_workspace_summary_prompt(*, rel_path: str, source: str) -> str:
    """Prompt for a 1–3 sentence plain-text file summary."""
    return (
        "Describe what this source file does in 1-3 plain sentences.\n"
        "No markdown headings, no bullet lists, no code fences.\n"
        f"File path: {rel_path}\n\n"
        "Source:\n"
        f"{source}"
    )


def _clean_summary(text: str) -> str:
    summary = " ".join(text.strip().split())
    if len(summary) > SUMMARY_OUTPUT_MAX_CHARS:
        summary = summary[: SUMMARY_OUTPUT_MAX_CHARS - 1] + "…"
    return summary


def run_workspace_file_summarizer_llm(
    *,
    rel_path: str,
    source: str,
    workspace_path: str | Path,
) -> WorkspaceSummaryResult:
    """Summarize one file. On failure returns empty summary with success=False."""
    apply_provider_env()
    resolved = resolve_role_model_name(ROLE_CONTEXT_BUILDER, workspace_path)

    config_error = provider_hint_for_model(resolved)
    if config_error:
        return WorkspaceSummaryResult(
            success=False,
            summary="",
            model=resolved,
            error=config_error,
        )

    truncated = source[:SUMMARY_INPUT_MAX_CHARS]
    if len(source) > SUMMARY_INPUT_MAX_CHARS:
        truncated += "\n…[truncated]"
    prompt = build_workspace_summary_prompt(rel_path=rel_path, source=truncated)

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
        return WorkspaceSummaryResult(
            success=False,
            summary="",
            model=resolved,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    output = text or captured
    if not output.strip():
        return WorkspaceSummaryResult(
            success=False,
            summary="",
            model=resolved,
            error="Empty summary response from model",
            duration_ms=duration_ms,
        )

    lower = output.lower()
    if any(m in lower for m in _ERROR_MARKERS):
        return WorkspaceSummaryResult(
            success=False,
            summary="",
            model=resolved,
            error=output.strip()[:2000],
            duration_ms=duration_ms,
        )

    summary = _clean_summary(output)
    tokens = extract_litellm_model_tokens(model_obj, role_source="workspace_summarizer")
    return WorkspaceSummaryResult(
        success=True,
        summary=summary,
        model=resolved,
        error=None,
        tokens=tokens,
        duration_ms=duration_ms,
    )
