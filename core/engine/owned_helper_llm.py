"""Owned helper LLM completion via litellm.completion (P6-008, Route B)."""

from __future__ import annotations

import concurrent.futures
import contextvars
import time
from dataclasses import dataclass
from typing import Any

from core.config.providers import apply_provider_env
from core.engine.stdio_isolation import isolated_stdio, merged_capture
from core.observability.context import CLI_FALLBACK_ROLE, role_var
from core.observability.owned_completion import record_owned_completion


@dataclass
class OwnedHelperCompletion:
    text: str
    model: str
    tokens: dict[str, Any]
    duration_ms: int
    error: str | None = None


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


def run_owned_helper_completion(
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int = 4096,
) -> OwnedHelperCompletion:
    """ThreadPoolExecutor + copy_context + litellm.completion + record_owned_completion."""
    apply_provider_env()
    t0 = time.perf_counter()

    def _call() -> OwnedHelperCompletion:
        with isolated_stdio() as (stdout_cap, stderr_cap):
            import litellm

            litellm.suppress_debug_info = True
            response = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
            )
            captured = merged_capture(stdout_cap, stderr_cap)
            try:
                text = (response.choices[0].message.content or "").strip()
            except (AttributeError, IndexError, TypeError):
                text = ""
            if captured.strip() and not text:
                text = captured.strip()

            duration_ms = int((time.perf_counter() - t0) * 1000)
            role = role_var.get() or CLI_FALLBACK_ROLE
            tokens = record_owned_completion(
                role=role,
                model=model,
                messages=messages,
                response_obj=response,
                duration_ms=duration_ms,
            )
            return OwnedHelperCompletion(
                text=text,
                model=model,
                tokens=tokens,
                duration_ms=duration_ms,
            )

    try:
        _ctx = contextvars.copy_context()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_ctx.run, _call).result()
    except Exception as exc:
        return OwnedHelperCompletion(
            text="",
            model=model,
            tokens=_unavailable_tokens(),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )
