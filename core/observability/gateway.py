"""LlmGateway — single proxy for all owned litellm.completion calls (P7-001, D-P7-1)."""

from __future__ import annotations

import concurrent.futures
import contextvars
import time
from dataclasses import dataclass
from typing import Any

from core.engine.stdio_isolation import isolated_stdio, merged_capture
from core.observability.base import ObservabilityBackend

# Used by litellm_callback.py to skip accumulation for gateway-managed calls.
_gateway_call_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_gateway_call_active", default=False
)

_active_gateway: "LlmGateway | None" = None


@dataclass
class GatewayCompletion:
    text: str
    model: str
    tokens: dict[str, Any]
    duration_ms: int
    reasoning_text: str | None = None
    error: str | None = None


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


def _extract_text_and_reasoning(response_obj: Any) -> tuple[str, str | None]:
    if response_obj is None:
        return "", None
    try:
        choices = getattr(response_obj, "choices", None)
        if not choices:
            return "", None
        first = choices[0]
        message = getattr(first, "message", None)
        if message is None and isinstance(first, dict):
            message = first.get("message")
        if message is None:
            return "", None
        if isinstance(message, dict):
            content = message.get("content")
            reasoning = message.get("reasoning_content")
        else:
            content = getattr(message, "content", None)
            reasoning = getattr(message, "reasoning_content", None)
        text = (content or "").strip() if isinstance(content, str) else ""
        reasoning_text = reasoning if isinstance(reasoning, str) else None
        return text, reasoning_text
    except (AttributeError, IndexError, TypeError):
        return "", None


class LlmGateway:
    """Wraps litellm.completion; records tokens + trace synchronously via backend."""

    def __init__(self, backend: ObservabilityBackend) -> None:
        self._backend = backend
        self._call_index = 0

    def _build_extra_headers(self) -> dict[str, str]:
        from core.observability.context import (
            delegation_id_var,
            session_dir_var,
            step_index_var,
            workspace_var,
        )

        self._call_index += 1
        headers: dict[str, str] = {"X-Mcp-Call-Index": str(self._call_index)}
        delegation_id = delegation_id_var.get()
        if delegation_id:
            headers["X-Mcp-Delegation-Id"] = delegation_id
        step_index = step_index_var.get()
        if step_index is not None:
            headers["X-Mcp-Step-Index"] = str(step_index)
        session_dir = session_dir_var.get()
        if session_dir:
            headers["X-Mcp-Session-Dir"] = session_dir
        workspace = workspace_var.get()
        if workspace:
            headers["X-Mcp-Workspace"] = workspace
        return headers

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
        role: str,
    ) -> GatewayCompletion:
        """Execute litellm.completion and record via backend; never raises."""
        t0 = time.perf_counter()

        def _call() -> GatewayCompletion:
            active_token = _gateway_call_active.set(True)
            try:
                with isolated_stdio() as (stdout_cap, stderr_cap):
                    import litellm

                    litellm.suppress_debug_info = True
                    response = litellm.completion(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        extra_headers=self._build_extra_headers(),
                    )
                    captured = merged_capture(stdout_cap, stderr_cap)
                    text, reasoning_text = _extract_text_and_reasoning(response)
                    if captured.strip() and not text:
                        text = captured.strip()

                    duration_ms = int((time.perf_counter() - t0) * 1000)
                    try:
                        tokens = self._backend.record_llm_call(
                            role=role,
                            model=model,
                            messages=messages,
                            response_obj=response,
                            duration_ms=duration_ms,
                        )
                    except Exception:
                        tokens = _unavailable_tokens()

                    return GatewayCompletion(
                        text=text,
                        model=model,
                        tokens=tokens,
                        duration_ms=duration_ms,
                        reasoning_text=reasoning_text,
                    )
            except Exception as exc:
                return GatewayCompletion(
                    text="",
                    model=model,
                    tokens=_unavailable_tokens(),
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    error=f"{type(exc).__name__}: {exc}",
                )
            finally:
                _gateway_call_active.reset(active_token)

        try:
            ctx = contextvars.copy_context()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(ctx.run, _call).result()
        except Exception as exc:
            return GatewayCompletion(
                text="",
                model=model,
                tokens=_unavailable_tokens(),
                duration_ms=int((time.perf_counter() - t0) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            )


class NullLlmGateway(LlmGateway):
    """No-op gateway for tests — no litellm calls, no I/O, returns empty completion."""

    def __init__(self) -> None:
        pass

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
        role: str,
    ) -> GatewayCompletion:
        return GatewayCompletion(
            text="",
            model=model,
            tokens={"input": None, "output": None, "total": None, "source": "null_gateway"},
            duration_ms=0,
        )


def set_llm_gateway(gw: LlmGateway) -> None:
    """Register the process-level gateway. Call once at server startup."""
    global _active_gateway
    _active_gateway = gw


def get_llm_gateway() -> LlmGateway:
    """Return the active gateway. Raises RuntimeError if not set."""
    if _active_gateway is None:
        raise RuntimeError(
            "LlmGateway not initialised. Call set_llm_gateway() at startup "
            "before any owned LLM completion."
        )
    return _active_gateway


def reset_llm_gateway() -> None:
    """Clear the process-level gateway (tests only)."""
    global _active_gateway
    _active_gateway = None
