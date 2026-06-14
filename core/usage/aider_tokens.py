"""Parse token usage from Aider stdout (P2-ISS-003 last-resort fallback).

Token precedence for executor delegations (P8-005):
1. ``litellm_callback`` accumulator / ``backend_llm_call`` trace (authoritative inner-loop capture)
2. Aider ``Coder`` attrs on the run result (``aider_coder`` / ``aider_usage``)
3. ``parse_aider_output_tokens`` stdout line parse (``aider_output_parse``) — compatibility only

``model_roles`` overlay in ``mcp_server`` prefers callback accumulation over engine
``ExecutionResult.tokens``. Engine-level resolution uses :func:`resolve_executor_tokens`.
"""

from __future__ import annotations

import re
from typing import Any

_TOKENS_LINE_RE = re.compile(
    r"Tokens:\s*([\d.]+)\s*([kKmM])?\s*sent,\s*([\d.]+)\s*([kKmM])?\s*received",
    re.IGNORECASE,
)


def _parse_token_count(raw: str, suffix: str | None) -> int:
    value = float(raw)
    if suffix is None:
        return int(value)
    suffix_lower = suffix.lower()
    if suffix_lower == "k":
        return int(value * 1000)
    if suffix_lower == "m":
        return int(value * 1_000_000)
    return int(value)


def parse_aider_output_tokens(text: str) -> dict[str, Any] | None:
    """Parse 'Tokens: 2.4k sent, 53 received' from Aider stdout.

    Last-resort fallback only — returns None when the summary line is absent.
    """
    if not text:
        return None
    match = _TOKENS_LINE_RE.search(text)
    if not match:
        return None
    input_tokens = _parse_token_count(match.group(1), match.group(2))
    output_tokens = _parse_token_count(match.group(3), match.group(4))
    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": input_tokens + output_tokens,
        "source": "aider_output_parse",
    }


def resolve_executor_tokens(
    *,
    coder_tokens: dict[str, Any],
    output: str,
) -> dict[str, Any]:
    """Resolve executor token dict from engine attrs, with stdout parse as last resort."""
    if coder_tokens.get("source") != "unavailable":
        return coder_tokens
    parsed = parse_aider_output_tokens(output)
    if parsed:
        return parsed
    return coder_tokens
