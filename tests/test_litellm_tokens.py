"""Unit tests for helper-LLM LiteLLM token extraction (BL-335)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.engine.architect_pass_llm import _extract_architect_tokens
from core.engine.context_builder_llm import _extract_builder_tokens
from core.engine.spec_validation_llm import _extract_validation_tokens
from core.usage.litellm_tokens import extract_litellm_model_tokens


@pytest.mark.parametrize(
    ("extractor", "role_source"),
    [
        (_extract_builder_tokens, "context_builder_llm"),
        (_extract_architect_tokens, "architect_pass"),
        (_extract_validation_tokens, "spec_validation"),
    ],
)
def test_extract_tokens_from_model_attrs(extractor, role_source):
    model = SimpleNamespace(total_tokens=150, tokens_sent=100, tokens_received=50)
    tokens = extractor(model)
    assert tokens == {
        "input": 100,
        "output": 50,
        "total": 150,
        "source": role_source,
    }


@pytest.mark.parametrize(
    ("extractor", "role_source"),
    [
        (_extract_builder_tokens, "context_builder_llm"),
        (_extract_architect_tokens, "architect_pass"),
        (_extract_validation_tokens, "spec_validation"),
    ],
)
def test_extract_tokens_from_usage_dict(extractor, role_source):
    model = SimpleNamespace(
        total_tokens=None,
        tokens_sent=None,
        tokens_received=None,
        usage={
            "prompt_tokens": 2400,
            "completion_tokens": 53,
            "total_tokens": 2453,
        },
    )
    tokens = extractor(model)
    assert tokens["input"] == 2400
    assert tokens["output"] == 53
    assert tokens["total"] == 2453
    assert tokens["source"] == role_source


def test_extract_tokens_from_last_response_usage_object():
    usage = SimpleNamespace(prompt_tokens=1200, completion_tokens=200, total_tokens=1400)
    model = SimpleNamespace(
        total_tokens=None,
        tokens_sent=None,
        tokens_received=None,
        usage=None,
        last_response=SimpleNamespace(usage=usage),
    )
    tokens = extract_litellm_model_tokens(model, role_source="context_builder_llm")
    assert tokens["input"] == 1200
    assert tokens["output"] == 200
    assert tokens["total"] == 1400
    assert tokens["source"] == "context_builder_llm"


def test_extract_tokens_unavailable_when_model_empty():
    model = SimpleNamespace(total_tokens=None, tokens_sent=None, tokens_received=None)
    tokens = extract_litellm_model_tokens(model, role_source="context_builder_llm")
    assert tokens["input"] is None
    assert tokens["output"] is None
    assert tokens["total"] is None
    assert tokens["source"] == "unavailable"


def test_extract_tokens_unavailable_for_none_model():
    tokens = _extract_builder_tokens(None)
    assert tokens["source"] == "unavailable"
    assert tokens["total"] is None
