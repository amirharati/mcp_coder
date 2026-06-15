"""Attribution header injection for proxy path (P9-003)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.observability.context import (
    bind_delegation_trace_scope,
    delegation_context,
    executor_step_context,
)
from core.observability.gateway import LlmGateway, NullLlmGateway, reset_llm_gateway
from core.observability.local import LocalObservability


@pytest.fixture(autouse=True)
def _reset_gateway():
    reset_llm_gateway()
    yield
    reset_llm_gateway()


def test_llm_gateway_injects_attribution_headers():
    captured: list[dict] = []

    def fake_completion(**kwargs):
        captured.append(kwargs)
        from types import SimpleNamespace

        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=None,
        )

    gw = LlmGateway(LocalObservability())
    with patch("litellm.completion", side_effect=fake_completion):
        with delegation_context("delegation-abc"):
            bind_delegation_trace_scope(workspace="/tmp/ws", session_dir="/tmp/session")
            with executor_step_context(4):
                gw.complete(
                    model="openrouter/test/model",
                    messages=[{"role": "user", "content": "hi"}],
                    role="context_builder",
                )
                gw.complete(
                    model="openrouter/test/model",
                    messages=[{"role": "user", "content": "again"}],
                    role="context_builder",
                )

    assert len(captured) == 2
    headers_one = captured[0]["extra_headers"]
    headers_two = captured[1]["extra_headers"]
    assert headers_one["X-Mcp-Delegation-Id"] == "delegation-abc"
    assert headers_one["X-Mcp-Step-Index"] == "4"
    assert headers_one["X-Mcp-Call-Index"] == "1"
    assert headers_two["X-Mcp-Call-Index"] == "2"


def test_observable_model_injects_attribution_headers(observable_model_module):
    ObservableModel = observable_model_module.ObservableModel
    model = ObservableModel("openrouter/test/model")
    captured: list[dict] = []

    def fake_send(self, messages, functions, stream, temperature=None):
        captured.append(dict(self.extra_params or {}))
        return ("hash", None)

    with patch.object(observable_model_module.Model, "send_completion", fake_send):
        with delegation_context("delegation-xyz"):
            bind_delegation_trace_scope(workspace="/tmp/ws", session_dir="/tmp/session")
            with executor_step_context(7):
                model.send_completion([{"role": "user", "content": "a"}], None, False)
                model.send_completion([{"role": "user", "content": "b"}], None, False)

    assert captured[0]["extra_headers"]["X-Mcp-Delegation-Id"] == "delegation-xyz"
    assert captured[0]["extra_headers"]["X-Mcp-Step-Index"] == "7"
    assert captured[0]["extra_headers"]["X-Mcp-Call-Index"] == "1"
    assert captured[1]["extra_headers"]["X-Mcp-Call-Index"] == "2"


@pytest.fixture
def observable_model_module(monkeypatch):
    import importlib
    import sys

    pytest.importorskip("aider")
    import aider.models as real_models

    monkeypatch.setitem(sys.modules, "aider.models", real_models)
    import core.engine.observable_model as observable_model

    importlib.reload(observable_model)
    return observable_model
