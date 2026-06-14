"""Owned helper LLM completion via LlmGateway (P6-008 Route B, P7-001)."""

from __future__ import annotations

import concurrent.futures
import contextvars
import time
from dataclasses import dataclass
from typing import Any

from core.config.providers import apply_provider_env
from core.observability.context import CLI_FALLBACK_ROLE, role_var
from core.observability.gateway import get_llm_gateway


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
    """ThreadPoolExecutor + copy_context + gateway.complete()."""
    apply_provider_env()
    t0 = time.perf_counter()

    def _call() -> OwnedHelperCompletion:
        gw = get_llm_gateway()
        role = role_var.get() or CLI_FALLBACK_ROLE
        result = gw.complete(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            role=role,
        )
        return OwnedHelperCompletion(
            text=result.text,
            model=result.model,
            tokens=result.tokens,
            duration_ms=result.duration_ms,
            error=result.error,
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
