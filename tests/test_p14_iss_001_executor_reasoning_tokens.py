"""P14-ISS-001: executor llm_call summary must carry reasoning/cached tokens.

`build_executor_llm_trace_record` previously copied only input/output/total
from the `tokens` dict, silently dropping `reasoning_tokens`/`cached_tokens`
even when the backend captured them. The helper path (build_trace_record)
already copied them. This test pins parity between the two paths.
"""

from __future__ import annotations

from core.config.observability import VERBOSITY_FULL
from core.observability.trace import build_executor_llm_trace_record


def test_executor_trace_copies_reasoning_and_cached_tokens():
    rec = build_executor_llm_trace_record(
        delegation_id="d-001",
        step_index=1,
        model="openrouter/deepseek/deepseek-v4-pro",
        verbosity=VERBOSITY_FULL,
        duration_ms=1234,
        tokens={
            "input": 1200,
            "output": 800,
            "total": 2000,
            "reasoning_tokens": 4908,
            "cached_tokens": 344,
        },
    )

    assert rec["tokens"]["input"] == 1200
    assert rec["tokens"]["output"] == 800
    assert rec["tokens"]["total"] == 2000
    # P14-ISS-001: reasoning_tokens must be surfaced on the executor summary.
    assert rec["tokens"]["reasoning_tokens"] == 4908
    assert rec["tokens"]["cached_tokens"] == 344
    # Top-level alias for quick log scans, parity with helper path.
    assert rec["thinking_tokens"] == 4908


def test_executor_trace_omits_reasoning_keys_when_none():
    """Backward compat: when reasoning/cached tokens are None, neither key
    is added (no null emission on the executor path — only the helper path
    emits explicit null per P14-ISS-002)."""
    rec = build_executor_llm_trace_record(
        delegation_id="d-002",
        step_index=1,
        model="openrouter/openai/gpt-4o-mini",
        verbosity=VERBOSITY_FULL,
        tokens={"input": 10, "output": 20, "total": 30},
    )

    assert rec["tokens"]["input"] == 10
    assert rec["tokens"]["output"] == 20
    assert rec["tokens"]["total"] == 30
    assert "reasoning_tokens" not in rec["tokens"]
    assert "cached_tokens" not in rec["tokens"]
    assert "thinking_tokens" not in rec


def test_executor_trace_omits_tokens_block_when_no_tokens():
    rec = build_executor_llm_trace_record(
        delegation_id="d-003",
        step_index=1,
        model="openrouter/openai/gpt-4o-mini",
        verbosity=VERBOSITY_FULL,
        tokens=None,
    )
    assert "tokens" not in rec
    assert "thinking_tokens" not in rec
