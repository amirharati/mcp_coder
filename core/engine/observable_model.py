"""ObservableModel — Aider Model subclass for inner-loop LLM capture (P8-001)."""

from __future__ import annotations

import time
from typing import Any, Iterator

from aider.models import Model

from core.observability.context import (
    _backend_call_active,
    delegation_id_var,
    step_index_var,
)
from core.usage.litellm_tokens import _coerce_int, _tokens_from_usage_mapping


def extract_thinking_from_response(result: Any) -> tuple[str | None, int]:
    """Extract normalized thinking text and token count from a litellm ModelResponse."""
    thinking_text: str | None = None
    thinking_tokens = 0

    if result is None:
        return None, 0

    try:
        choices = getattr(result, "choices", None)
        if not choices and isinstance(result, dict):
            choices = result.get("choices")
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            if message is None and isinstance(first, dict):
                message = first.get("message")
            if message is not None:
                if isinstance(message, dict):
                    reasoning = message.get("reasoning_content")
                    thinking_blocks = message.get("thinking_blocks")
                else:
                    reasoning = getattr(message, "reasoning_content", None)
                    thinking_blocks = getattr(message, "thinking_blocks", None)
                if isinstance(reasoning, str) and reasoning.strip():
                    thinking_text = reasoning.strip()
                elif thinking_blocks:
                    parts: list[str] = []
                    for block in thinking_blocks:
                        if isinstance(block, dict):
                            text = block.get("thinking") or block.get("text")
                        else:
                            text = getattr(block, "thinking", None) or getattr(
                                block, "text", None
                            )
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
                    if parts:
                        thinking_text = "\n".join(parts)
    except (AttributeError, IndexError, TypeError):
        pass

    usage_raw = getattr(result, "usage", None)
    if usage_raw is None and isinstance(result, dict):
        usage_raw = result.get("usage")
    if usage_raw is not None:
        if isinstance(usage_raw, dict):
            details = usage_raw.get("completion_tokens_details") or {}
            reasoning = (
                usage_raw.get("reasoning_tokens")
                or (details.get("reasoning_tokens") if isinstance(details, dict) else None)
            )
        else:
            details = getattr(usage_raw, "completion_tokens_details", None)
            reasoning = getattr(usage_raw, "reasoning_tokens", None)
            if details is not None and reasoning is None:
                reasoning = getattr(details, "reasoning_tokens", None)
        coerced = _coerce_int(reasoning)
        if coerced is not None:
            thinking_tokens = coerced

    return thinking_text, thinking_tokens


def _extract_response_text(result: Any) -> str | None:
    if result is None:
        return None
    try:
        choices = getattr(result, "choices", None)
        if not choices and isinstance(result, dict):
            choices = result.get("choices")
        if not choices:
            return None
        first = choices[0]
        message = getattr(first, "message", None)
        if message is None and isinstance(first, dict):
            message = first.get("message")
        if message is None:
            return None
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)
        return content if isinstance(content, str) else None
    except (AttributeError, IndexError, TypeError):
        return None


def _extract_prompt_text(messages: Any) -> str | None:
    if not isinstance(messages, list):
        return None
    parts: list[str] = []
    for message in messages:
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                parts.append(content)
    if parts:
        return "\n\n".join(parts)
    return None


def _extract_usage(result: Any) -> dict[str, Any] | None:
    usage_raw = getattr(result, "usage", None)
    if usage_raw is None and isinstance(result, dict):
        usage_raw = result.get("usage")
    return _tokens_from_usage_mapping(usage_raw)


def _record_backend_call(
    *,
    call_type: str,
    model: str | None,
    duration_ms: int,
    messages: Any,
    result: Any,
) -> None:
    try:
        from core.observability import get_observability

        thinking_text, thinking_tokens = extract_thinking_from_response(result)
        get_observability().record_backend_llm_call(
            call_type=call_type,
            model=model,
            step_index=step_index_var.get(),
            thinking_text=thinking_text,
            thinking_tokens=thinking_tokens or None,
            usage=_extract_usage(result),
            duration_ms=duration_ms,
            prompt_text=_extract_prompt_text(messages),
            response_text=_extract_response_text(result),
        )
    except Exception:
        pass


def _is_streaming_result(result: Any) -> bool:
    if result is None:
        return False
    if hasattr(result, "choices"):
        return False
    return hasattr(result, "__iter__") and not isinstance(result, (str, bytes, dict))


class _StreamCaptureWrapper:
    """Transparent iterator wrapper that records backend_llm_call on exhaustion."""

    def __init__(
        self,
        inner: Iterator[Any],
        *,
        model: str | None,
        messages: Any,
        t0: float,
    ) -> None:
        self._inner = iter(inner)
        self._model = model
        self._messages = messages
        self._t0 = t0
        self._chunks: list[Any] = []
        self._recorded = False

    def __iter__(self) -> "_StreamCaptureWrapper":
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self._inner)
            self._chunks.append(chunk)
            return chunk
        except StopIteration:
            if not self._recorded:
                self._recorded = True
                self._finalize()
            raise

    def _finalize(self) -> None:
        duration_ms = int((time.perf_counter() - self._t0) * 1000)
        assembled = _assemble_stream_response(self._chunks)
        _record_backend_call(
            call_type="executor_turn",
            model=self._model,
            duration_ms=duration_ms,
            messages=self._messages,
            result=assembled,
        )


def _assemble_stream_response(chunks: list[Any]) -> Any:
    """Best-effort assembly of streaming chunks into a pseudo-ModelResponse."""
    if not chunks:
        return None

    content_parts: list[str] = []
    thinking_parts: list[str] = []
    usage: Any = None
    model: str | None = None

    for chunk in chunks:
        if chunk is None:
            continue
        if getattr(chunk, "model", None):
            model = str(chunk.model)
        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage is not None:
            usage = chunk_usage

        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        first = choices[0]
        delta = getattr(first, "delta", None)
        if delta is None and isinstance(first, dict):
            delta = first.get("delta")
        if delta is None:
            continue
        if isinstance(delta, dict):
            piece = delta.get("content")
            reasoning = delta.get("reasoning_content")
        else:
            piece = getattr(delta, "content", None)
            reasoning = getattr(delta, "reasoning_content", None)
        if isinstance(piece, str) and piece:
            content_parts.append(piece)
        if isinstance(reasoning, str) and reasoning:
            thinking_parts.append(reasoning)

    from types import SimpleNamespace

    message = SimpleNamespace(
        content="".join(content_parts) if content_parts else None,
        reasoning_content="\n".join(thinking_parts) if thinking_parts else None,
    )
    return SimpleNamespace(
        model=model,
        usage=usage,
        choices=[SimpleNamespace(message=message)],
    )


class ObservableModel(Model):
    """Aider Model subclass that records every send_completion() as backend_llm_call."""

    def send_completion(
        self,
        messages,
        functions,
        stream,
        temperature=None,
    ):
        t0 = time.perf_counter()
        active_token = _backend_call_active.set(True)
        model_name = getattr(self, "name", None) or str(getattr(self, "model", "")) or None
        try:
            hash_obj, result = super().send_completion(
                messages, functions, stream, temperature
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)

            if stream or _is_streaming_result(result):
                wrapped = _StreamCaptureWrapper(
                    result,
                    model=model_name,
                    messages=messages,
                    t0=t0,
                )
                return hash_obj, wrapped

            _record_backend_call(
                call_type="executor_turn",
                model=model_name,
                duration_ms=duration_ms,
                messages=messages,
                result=result,
            )
            return hash_obj, result
        finally:
            _backend_call_active.reset(active_token)
