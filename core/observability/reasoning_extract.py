"""Shared reasoning-text extraction from litellm / OpenRouter response shapes.

litellm surfaces provider reasoning inconsistently:
- Direct attr: ``message.reasoning_content`` (DeepSeek, Anthropic via thinking=)
- Dict key: ``message["reasoning"]`` (LLaMA via OpenRouter raw)
- Buried: ``message.provider_specific_fields.reasoning`` (OpenRouter/Anthropic
  when reasoning_effort is set but thinking= is not — litellm drops the top-level
  field and only preserves it under provider_specific_fields)
- List: ``message.reasoning_details`` (OpenRouter ``[{type:"reasoning.text", text:...}]``)

This module gives every extraction point (gateway, litellm_callback,
ObservableModel) one helper so a provider quirk cannot silently drop reasoning
in one path but not another.
"""

from __future__ import annotations

from typing import Any


def _read_reasoning_details(details: Any) -> str | None:
    """Join a ``reasoning_details`` list of ``{type, text}`` blocks."""
    if not details:
        return None
    parts: list[str] = []
    if isinstance(details, list):
        for d in details:
            text = d.get("text") if isinstance(d, dict) else getattr(d, "text", None)
            if isinstance(text, str) and text:
                parts.append(text)
    joined = "\n".join(parts)
    return joined or None


def extract_reasoning_text(message: Any) -> str | None:
    """Read reasoning text from a litellm/OpenRouter message object or dict.

    Returns the reasoning text (str) or None when no reasoning is present.
    """
    if message is None:
        return None
    try:
        if isinstance(message, dict):
            reasoning = message.get("reasoning_content") or message.get("reasoning")
            if not reasoning:
                psf = message.get("provider_specific_fields") or {}
                if isinstance(psf, dict):
                    reasoning = psf.get("reasoning_content") or psf.get("reasoning")
            if not reasoning:
                reasoning = _read_reasoning_details(message.get("reasoning_details"))
        else:
            reasoning = getattr(message, "reasoning_content", None) or getattr(
                message, "reasoning", None
            )
            if not reasoning:
                psf = getattr(message, "provider_specific_fields", None) or {}
                if isinstance(psf, dict):
                    reasoning = psf.get("reasoning_content") or psf.get("reasoning")
            if not reasoning:
                reasoning = _read_reasoning_details(
                    getattr(message, "reasoning_details", None)
                )
        return reasoning if isinstance(reasoning, str) and reasoning else None
    except (AttributeError, TypeError):
        return None
