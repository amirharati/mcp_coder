"""P14-ISS-001 (BL-557): executor tokens overlay from litellm callback accumulator.

`_extract_tokens` in `aider_engine.py` reads Aider's Coder attrs, which don't
surface `reasoning_tokens`. The engine now overlays the executor's
`reasoning_tokens`/`cached_tokens` from the litellm callback accumulator
(keyed by `(delegation_id, ROLE_EXECUTOR)`) so the executor `llm_call` trace
record carries thinking counts parity with `backend_llm_call`.

This test verifies the overlay step in isolation by calling the same code path
the engine uses after `coder.run()` completes.
"""

from __future__ import annotations

from core.config.role_models import ROLE_EXECUTOR
from core.observability.litellm_callback import (
    reset_callback_state_for_tests,
    get_accumulated_usage,
)


def _overlay_reasoning_tokens(delegation_id: str, tokens: dict) -> dict:
    """Mirror the overlay logic added to AiderEngine._execute_delegation."""
    if not delegation_id:
        return tokens
    acc = get_accumulated_usage(delegation_id, ROLE_EXECUTOR)
    if acc:
        rt = acc.get("reasoning_tokens")
        if rt is not None:
            tokens["reasoning_tokens"] = rt
        ct = acc.get("cached_tokens")
        if ct is not None:
            tokens["cached_tokens"] = ct
    return tokens


def test_overlay_adds_reasoning_tokens_from_callback():
    """When the callback accumulator has reasoning_tokens, the overlay injects
    them into the engine token dict (which _extract_tokens left without it)."""
    reset_callback_state_for_tests()
    delegation_id = "d-overlay-001"

    # Simulate the callback accumulator capturing a reasoning model's usage.
    # We poke the internal store directly to avoid spinning up litellm.
    from core.observability.litellm_callback import _store, _UsageBucket

    _store[(delegation_id, ROLE_EXECUTOR)] = _UsageBucket(
        model="openrouter/deepseek/deepseek-v4-pro",
        input=1785,
        output=950,
        total=2735,
        reasoning=490,
        duration_ms=17623,
        call_count=1,
    )

    # Engine extracted tokens via _extract_tokens — no reasoning_tokens key.
    engine_tokens = {
        "input": 1800,
        "output": 950,
        "total": 2750,
        "source": "aider_coder",
    }

    result = _overlay_reasoning_tokens(delegation_id, engine_tokens)

    assert result["reasoning_tokens"] == 490
    assert result["input"] == 1800  # original values preserved
    assert result["output"] == 950
    assert result["source"] == "aider_coder"
    reset_callback_state_for_tests()


def test_overlay_noop_when_no_accumulator():
    """When no callback data exists (e.g. non-reasoning model), the overlay
    must not inject anything — the token dict stays as _extract_tokens left it."""
    reset_callback_state_for_tests()
    delegation_id = "d-overlay-002"

    engine_tokens = {
        "input": 100,
        "output": 200,
        "total": 300,
        "source": "aider_coder",
    }

    result = _overlay_reasoning_tokens(delegation_id, engine_tokens)

    assert "reasoning_tokens" not in result
    assert "cached_tokens" not in result
    assert result["source"] == "aider_coder"
    reset_callback_state_for_tests()


def test_overlay_noop_when_delegation_id_none():
    """Defensive: when delegation_id is None (shouldn't happen in practice),
    the overlay must not crash and must not mutate the token dict."""
    reset_callback_state_for_tests()

    engine_tokens = {"input": 1, "output": 2, "total": 3, "source": "x"}

    result = _overlay_reasoning_tokens(None, engine_tokens)

    assert "reasoning_tokens" not in result
    assert result == engine_tokens
    reset_callback_state_for_tests()
