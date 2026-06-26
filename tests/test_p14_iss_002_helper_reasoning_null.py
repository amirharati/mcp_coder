"""P14-ISS-002: helper llm_call events always emit reasoning_tokens (null
when the provider returned none).

Previously `build_trace_record` only added `reasoning_tokens` to the tokens
payload when it was not None. A reasoning-capable model that chose not to
think on a trivial prompt produced a trace with the field absent —
indistinguishable from "capture path broken". The fix: always emit
`reasoning_tokens` (null when absent), keep `thinking_tokens` alias only
when the count is a real integer.
"""

from __future__ import annotations

from core.config.observability import VERBOSITY_FULL
from core.observability.trace import build_trace_record


def test_helper_trace_emits_null_reasoning_tokens_when_absent():
    rec = build_trace_record(
        delegation_id="d-001",
        role="planner",
        model="openrouter/anthropic/claude-sonnet-4.5",
        call_index=0,
        duration_ms=42,
        tokens={"input": 1, "output": 2, "total": 3, "reasoning_tokens": None},
        verbosity=VERBOSITY_FULL,
        prompt_text="hi",
        response_text="ok",
    )

    # P14-ISS-002: reasoning_tokens is always present (null when absent).
    assert "reasoning_tokens" in rec["tokens"]
    assert rec["tokens"]["reasoning_tokens"] is None
    # thinking_tokens alias only when a real count exists.
    assert "thinking_tokens" not in rec


def test_helper_trace_emits_reasoning_tokens_when_present():
    rec = build_trace_record(
        delegation_id="d-002",
        role="planner",
        model="openrouter/deepseek/deepseek-v4-pro",
        call_index=0,
        duration_ms=42,
        tokens={"input": 1, "output": 2, "total": 3, "reasoning_tokens": 5},
        verbosity=VERBOSITY_FULL,
        prompt_text="hi",
        response_text="ok",
    )

    assert rec["tokens"]["reasoning_tokens"] == 5
    assert rec["thinking_tokens"] == 5


def test_helper_trace_emits_null_reasoning_tokens_when_key_missing():
    """When the tokens dict has no reasoning_tokens key at all (older capture
    path), still emit explicit null so consumers can detect the field."""
    rec = build_trace_record(
        delegation_id="d-003",
        role="planner",
        model="openrouter/openai/gpt-4o-mini",
        call_index=0,
        duration_ms=42,
        tokens={"input": 1, "output": 2, "total": 3},
        verbosity=VERBOSITY_FULL,
        prompt_text="hi",
        response_text="ok",
    )

    assert "reasoning_tokens" in rec["tokens"]
    assert rec["tokens"]["reasoning_tokens"] is None
    assert "thinking_tokens" not in rec


def test_helper_trace_cached_tokens_still_optional():
    """cached_tokens stays opt-in (only emitted when not None), unlike
    reasoning_tokens which is always present."""
    rec = build_trace_record(
        delegation_id="d-004",
        role="planner",
        model="openrouter/openai/gpt-4o-mini",
        call_index=0,
        duration_ms=42,
        tokens={"input": 1, "output": 2, "total": 3, "reasoning_tokens": None},
        verbosity=VERBOSITY_FULL,
        prompt_text="hi",
        response_text="ok",
    )

    assert "cached_tokens" not in rec["tokens"]
