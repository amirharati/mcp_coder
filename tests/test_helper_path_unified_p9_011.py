"""P9-011 — workspace_summarizer + spec_review now route through LlmGateway.

These previously called aider Model().simple_send_with_retries() directly and
emitted no llm_call trace event. After P9-011 they must use the gateway path
(run_owned_helper_completion), giving uniform logging.
"""

from __future__ import annotations

from unittest.mock import patch

import core.engine.spec_review as spec_review_mod
import core.engine.workspace_summarizer_llm as wsl
from core.engine.owned_helper_llm import OwnedHelperCompletion


def _fake_completion(text: str, error: str | None = None) -> OwnedHelperCompletion:
    return OwnedHelperCompletion(
        text=text,
        model="test-model",
        tokens={"input": 10, "output": 5, "total": 15, "source": "gateway"},
        duration_ms=7,
        error=error,
    )


# --- workspace_summarizer -------------------------------------------------


def test_summarizer_uses_gateway(monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "provider_hint_for_model", lambda _m: None)
    fake = _fake_completion("Parses config files and returns a dict.")
    with patch(
        "core.engine.owned_helper_llm.run_owned_helper_completion",
        return_value=fake,
    ) as mock_call:
        result = wsl.run_workspace_file_summarizer_llm(
            rel_path="a.py",
            source="def f():\n    return 1\n",
            workspace_path=tmp_path,
        )
    assert mock_call.called, "summarizer must go through the gateway helper"
    assert result.success
    assert result.summary == "Parses config files and returns a dict."
    assert result.tokens["source"] == "gateway"


def test_summarizer_maps_gateway_error(monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "provider_hint_for_model", lambda _m: None)
    fake = _fake_completion("", error="litellm.RateLimitError: slow down")
    with patch(
        "core.engine.owned_helper_llm.run_owned_helper_completion",
        return_value=fake,
    ):
        result = wsl.run_workspace_file_summarizer_llm(
            rel_path="a.py",
            source="x = 1",
            workspace_path=tmp_path,
        )
    assert result.success is False
    assert "RateLimitError" in (result.error or "")


def test_summarizer_no_direct_aider_model(monkeypatch, tmp_path):
    """Regression: summarizer must not import/construct aider Model directly."""
    monkeypatch.setattr(wsl, "provider_hint_for_model", lambda _m: None)
    fake = _fake_completion("Summary.")
    with patch(
        "core.engine.owned_helper_llm.run_owned_helper_completion",
        return_value=fake,
    ):
        # If it still called aider Model, this would attempt a real network call;
        # the gateway mock guarantees we never reach aider.
        result = wsl.run_workspace_file_summarizer_llm(
            rel_path="a.py", source="x = 1", workspace_path=tmp_path
        )
    assert result.success


# --- spec_review ----------------------------------------------------------


def test_spec_review_uses_gateway():
    fake = _fake_completion("Questions: None\nReadiness: READY_TO_IMPLEMENT")
    with patch(
        "core.engine.owned_helper_llm.run_owned_helper_completion",
        return_value=fake,
    ) as mock_call:
        result = spec_review_mod.run_spec_review("Review this spec.", model_name="test-model")
    assert mock_call.called
    assert result.success
    assert "READY_TO_IMPLEMENT" in result.output


def test_spec_review_maps_gateway_error():
    fake = _fake_completion("", error="boom")
    with patch(
        "core.engine.owned_helper_llm.run_owned_helper_completion",
        return_value=fake,
    ):
        result = spec_review_mod.run_spec_review("Review this spec.", model_name="test-model")
    assert result.success is False
    assert result.error == "boom"
