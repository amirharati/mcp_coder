"""Unit tests for helper-LLM LiteLLM token extraction (BL-335)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.config.role_models import ROLE_CONTEXT_BUILDER
from core.usage.litellm_tokens import extract_litellm_model_tokens


@pytest.mark.parametrize(
    "role_source",
    [
        "context_builder_llm",
        "architect_pass",
        "spec_validation",
    ],
)
def test_extract_tokens_from_model_attrs(role_source):
    model = SimpleNamespace(total_tokens=150, tokens_sent=100, tokens_received=50)
    tokens = extract_litellm_model_tokens(model, role_source=role_source)
    assert tokens == {
        "input": 100,
        "output": 50,
        "total": 150,
        "source": role_source,
    }


@pytest.mark.parametrize(
    "role_source",
    [
        "context_builder_llm",
        "architect_pass",
        "spec_validation",
    ],
)
def test_extract_tokens_from_usage_dict(role_source):
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
    tokens = extract_litellm_model_tokens(model, role_source=role_source)
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
    tokens = extract_litellm_model_tokens(None, role_source="context_builder_llm")
    assert tokens["source"] == "unavailable"
    assert tokens["total"] is None


def test_extract_tokens_from_callback_accumulator_fallback():
    from core.observability.context import delegation_context, role_context
    from core.observability.litellm_callback import litellm_success_handler, reset_callback_state_for_tests

    reset_callback_state_for_tests()
    delegation_id = "delegation-fallback"
    with delegation_context(delegation_id):
        with role_context(ROLE_CONTEXT_BUILDER):
            usage = SimpleNamespace(prompt_tokens=321, completion_tokens=9, total_tokens=330)
            litellm_success_handler(
                {},
                SimpleNamespace(model="openrouter/test/model", usage=usage),
                None,
                None,
            )
            model = SimpleNamespace(total_tokens=None, tokens_sent=None, tokens_received=None)
            tokens = extract_litellm_model_tokens(model, role_source="context_builder_llm")
    assert tokens["input"] == 321
    assert tokens["output"] == 9
    assert tokens["total"] == 330
    assert tokens["source"] == "litellm_callback"
