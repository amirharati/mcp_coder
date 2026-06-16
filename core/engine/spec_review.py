"""Spec review delegations — LLM feedback without Aider Coder / file edits."""

from __future__ import annotations

from core.config.models import provider_hint_for_model, resolve_model_name
from core.config.review_model import resolve_review_model_name
from core.config.providers import apply_provider_env
from core.config.role_models import ROLE_REVIEW
from core.engine.base import ExecutionResult
from core.observability.context import role_context

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
    workspace_path: str | None = None,
) -> ExecutionResult:
    """One-shot model call for spec review (no Coder, no file changes)."""
    apply_provider_env()
    if model_name is not None:
        resolved = model_name
    elif workspace_path:
        resolved = resolve_review_model_name(workspace_path)
    else:
        resolved = resolve_model_name()
    config_error = provider_hint_for_model(resolved)
    if config_error:
        return ExecutionResult(
            success=False,
            output="",
            model=resolved,
            error=config_error,
            tokens={"source": "unavailable"},
        )

    from core.engine.owned_helper_llm import run_owned_helper_completion

    full_prompt = wrap_review_prompt(prompt)
    messages = [{"role": "user", "content": full_prompt}]

    with role_context(ROLE_REVIEW):
        completion = run_owned_helper_completion(messages, model=resolved)

    if completion.error:
        return ExecutionResult(
            success=False,
            output="",
            model=resolved,
            error=completion.error,
            tokens={"source": "unavailable"},
        )

    output = completion.text
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
