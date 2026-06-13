"""LiteLLM success_callback token accumulator (P6-002)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.config.role_models import ROLE_CONTEXT_BUILDER, ROLE_EXECUTOR
from core.observability.context import CLI_FALLBACK_ROLE, delegation_context, role_context
from core.observability.litellm_callback import (
    get_accumulated_usage,
    get_cli_accumulated_usage,
    litellm_success_handler,
    overlay_model_roles_from_callback,
    overlay_role_record_from_callback,
    register_litellm_callbacks,
    reset_callback_state_for_tests,
)
from core.usage.role_audit import build_role_usage_record


@pytest.fixture(autouse=True)
def _reset_callback_state():
    reset_callback_state_for_tests()
    yield
    reset_callback_state_for_tests()


def test_register_litellm_callbacks_idempotent():
    register_litellm_callbacks()
    import litellm

    count = len(litellm.success_callback)
    register_litellm_callbacks()
    assert len(litellm.success_callback) == count


def test_success_handler_accumulates_tokens_under_delegation_and_role():
    delegation_id = "delegation-abc"
    with delegation_context(delegation_id):
        with role_context(ROLE_CONTEXT_BUILDER):
            usage = SimpleNamespace(prompt_tokens=2400, completion_tokens=53, total_tokens=2453)
            response = SimpleNamespace(model="openrouter/google/gemini-2.5-flash", usage=usage)
            litellm_success_handler(
                {"model": "openrouter/google/gemini-2.5-flash"},
                response,
                None,
                None,
            )

    acc = get_accumulated_usage(delegation_id, ROLE_CONTEXT_BUILDER)
    assert acc is not None
    assert acc["input"] == 2400
    assert acc["output"] == 53
    assert acc["total"] == 2453
    assert acc["source"] == "litellm_callback"


def test_success_handler_without_delegation_uses_cli_fallback():
    with role_context(CLI_FALLBACK_ROLE):
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14)
        response = SimpleNamespace(model="openrouter/openai/gpt-4o-mini", usage=usage)
        litellm_success_handler({}, response, None, None)

    acc = get_cli_accumulated_usage()
    assert acc is not None
    assert acc["input"] == 10
    assert acc["output"] == 4
    assert acc["total"] == 14


def test_overlay_role_record_fills_unavailable_tokens():
    delegation_id = "delegation-overlay"
    with delegation_context(delegation_id):
        with role_context(ROLE_EXECUTOR):
            usage = SimpleNamespace(prompt_tokens=8000, completion_tokens=1200, total_tokens=9200)
            response = SimpleNamespace(model="openrouter/openai/gpt-4o-mini", usage=usage)
            litellm_success_handler({}, response, None, None)

    record = build_role_usage_record(
        role=ROLE_EXECUTOR,
        model="openrouter/openai/gpt-4o-mini",
        source="executor",
    )
    assert record["tokens"]["input"] is None

    updated = overlay_role_record_from_callback(
        record, delegation_id=delegation_id, role=ROLE_EXECUTOR
    )
    assert updated is not None
    assert updated["tokens"]["input"] == 8000
    assert updated["tokens"]["output"] == 1200
    assert updated["tokens"]["total"] == 9200
    assert updated["cost_est_usd"]["total"] > 0


def test_overlay_model_roles_merges_helper_and_executor():
    delegation_id = "delegation-merge"
    with delegation_context(delegation_id):
        with role_context(ROLE_CONTEXT_BUILDER):
            usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=120)
            litellm_success_handler(
                {},
                SimpleNamespace(model="openrouter/google/gemini-2.5-flash", usage=usage),
                None,
                None,
            )
        with role_context(ROLE_EXECUTOR):
            usage = SimpleNamespace(prompt_tokens=500, completion_tokens=50, total_tokens=550)
            litellm_success_handler(
                {},
                SimpleNamespace(model="openrouter/openai/gpt-4o-mini", usage=usage),
                None,
                None,
            )

    roles = {
        ROLE_CONTEXT_BUILDER: build_role_usage_record(
            role=ROLE_CONTEXT_BUILDER,
            model="openrouter/google/gemini-2.5-flash",
            source="context_builder_llm",
        ),
        ROLE_EXECUTOR: build_role_usage_record(
            role=ROLE_EXECUTOR,
            model="openrouter/openai/gpt-4o-mini",
            source="executor",
        ),
    }
    merged = overlay_model_roles_from_callback(roles, delegation_id=delegation_id)
    assert merged is not None
    assert merged[ROLE_CONTEXT_BUILDER]["tokens"]["input"] == 100
    assert merged[ROLE_EXECUTOR]["tokens"]["input"] == 500
    assert merged[ROLE_EXECUTOR]["cost_est_usd"]["total"] > 0
