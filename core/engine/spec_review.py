"""Spec review delegations — LLM feedback without Aider Coder / file edits."""

from __future__ import annotations

import concurrent.futures
from typing import Any

from core.config.models import provider_hint_for_model, resolve_model_name
from core.config.providers import apply_provider_env
from core.engine.base import ExecutionResult
from core.engine.stdio_isolation import isolated_stdio, merged_capture

REVIEW_PREAMBLE = """## Delegation mode: review

You are reviewing a task spec **before** implementation. Do **not** edit or create any files.

Respond with:
1. **Questions** — ambiguities needing planner/human input (or "None")
2. **Suggestions** — optional scope/constraint improvements (or "None")
3. **Readiness** — end with `READY_TO_IMPLEMENT` if clear enough to implement as written, otherwise `NEEDS_SPEC_UPDATE`

Do not ask to add files to chat; use only the spec and context below."""


def wrap_review_prompt(prompt: str) -> str:
    body = prompt.strip()
    if not body:
        return REVIEW_PREAMBLE
    return f"{REVIEW_PREAMBLE}\n\n---\n\n{body}"


def run_spec_review(
    prompt: str,
    *,
    model_name: str | None = None,
) -> ExecutionResult:
    """One-shot model call for spec review (no Coder, no file changes)."""
    apply_provider_env()
    resolved = model_name or resolve_model_name()
    config_error = provider_hint_for_model(resolved)
    if config_error:
        return ExecutionResult(
            success=False,
            output="",
            model=resolved,
            error=config_error,
            tokens={"source": "unavailable"},
        )

    from aider.models import Model

    full_prompt = wrap_review_prompt(prompt)
    messages = [{"role": "user", "content": full_prompt}]

    def _call() -> tuple[str, str]:
        with isolated_stdio() as (stdout_cap, stderr_cap):
            model = Model(resolved)
            reply = model.simple_send_with_retries(messages)
            captured = merged_capture(stdout_cap, stderr_cap)
            text = (reply or "").strip()
            if captured.strip() and not text:
                text = captured.strip()
            return text, captured

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            text, captured = pool.submit(_call).result()
    except Exception as exc:
        return ExecutionResult(
            success=False,
            output="",
            model=resolved,
            error=f"{type(exc).__name__}: {exc}",
            tokens={"source": "unavailable"},
        )

    output = text or captured
    if not output.strip():
        return ExecutionResult(
            success=False,
            output=output,
            model=resolved,
            error="Empty review response from model",
            tokens={"source": "unavailable"},
        )

    lower = output.lower()
    error_markers = (
        "litellm.",
        "notfounderror",
        "authenticationerror",
        "ratelimiterror",
        "openrouterexception",
        "openaierror",
    )
    if any(m in lower for m in error_markers):
        return ExecutionResult(
            success=False,
            output=output,
            model=resolved,
            error=output.strip()[:2000],
            tokens={"source": "unavailable"},
        )

    return ExecutionResult(
        success=True,
        output=output,
        files_changed=[],
        model=resolved,
        tokens={"source": "review", "total": None},
    )
