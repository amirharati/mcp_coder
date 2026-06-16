"""P9-012 — generation params + weak-model default-fill + policy_applied logging."""

from __future__ import annotations

import pytest

from core.config.model_registry import (
    ROLE_CONTEXT_BUILDER,
    ROLE_EXECUTOR,
    _default_weak_model,
    policy_applied,
    resolve,
)
from core.observability.trace import (
    build_backend_llm_call_record,
    build_trace_record,
)


# --- env-driven generation params ----------------------------------------


def test_reasoning_effort_from_env(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_REASONING_EFFORT", "high")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.reasoning_effort == "high"
    assert cp.sources["reasoning_effort"] == "env"


def test_thinking_budget_from_env(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "anthropic/claude-sonnet-4-5")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_THINKING_BUDGET", "8000")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.thinking_budget == 8000
    assert cp.sources["thinking_budget"] == "env"


def test_temperature_top_p_max_tokens_from_env(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_TEMPERATURE", "0.3")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_TOP_P", "0.9")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_MAX_TOKENS", "2048")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.temperature == 0.3
    assert cp.top_p == 0.9
    assert cp.max_tokens == 2048


def test_extra_params_json_from_env(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_EXTRA_PARAMS", '{"seed": 42, "logprobs": true}')
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.extra_params == {"seed": 42, "logprobs": True}
    assert cp.sources["extra_params"] == "env"


def test_invalid_reasoning_effort_raises(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_REASONING_EFFORT", "ultra")
    with pytest.raises(ValueError):
        resolve(ROLE_EXECUTOR, include_aider_metadata=False)


def test_invalid_thinking_budget_raises(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_THINKING_BUDGET", "lots")
    with pytest.raises(ValueError):
        resolve(ROLE_EXECUTOR, include_aider_metadata=False)


def test_invalid_extra_params_json_raises(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_EXTRA_PARAMS", "{not json}")
    with pytest.raises(ValueError):
        resolve(ROLE_EXECUTOR, include_aider_metadata=False)


# --- per-role defaults ----------------------------------------------------


def test_context_builder_temperature_default(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/openai/gpt-4o-mini")
    cp = resolve(ROLE_CONTEXT_BUILDER, tmp_path, include_aider_metadata=False)
    assert cp.temperature == 0.2
    assert cp.sources["temperature"] == "default"


def test_env_overrides_role_default(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_TEMPERATURE", "0.7")
    cp = resolve(ROLE_CONTEXT_BUILDER, tmp_path, include_aider_metadata=False)
    assert cp.temperature == 0.7
    assert cp.sources["temperature"] == "env"


# --- weak model -----------------------------------------------------------


def test_default_weak_model_map():
    assert "haiku" in (_default_weak_model("anthropic/claude-sonnet-4-5") or "")
    assert "mini" in (_default_weak_model("openrouter/openai/gpt-4o") or "")
    assert _default_weak_model("some/unknown-model") is None


def test_weak_model_default_fill(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "anthropic/claude-sonnet-4-5")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.weak_model and "haiku" in cp.weak_model
    assert cp.sources["weak_model"] == "registry_default"


def test_weak_model_env_override(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "anthropic/claude-sonnet-4-5")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_WEAK_MODEL", "openrouter/openai/gpt-4o-mini")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.weak_model == "openrouter/openai/gpt-4o-mini"
    assert cp.sources["weak_model"] == "env"


# --- policy_applied shape -------------------------------------------------


def test_policy_applied_omits_none_includes_set(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "anthropic/claude-sonnet-4-5")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_THINKING_BUDGET", "5000")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    pa = policy_applied(cp, ROLE_EXECUTOR)
    assert pa["role"] == ROLE_EXECUTOR
    assert pa["thinking_budget"] == 5000
    assert "weak_model" in pa  # default-filled
    assert "temperature" not in pa  # never set for executor here
    assert pa["sources"]["thinking_budget"] == "env"


# --- trace records carry policy_applied -----------------------------------


def test_backend_record_includes_policy_applied():
    rec = build_backend_llm_call_record(
        delegation_id="d1",
        step_index=0,
        call_index=1,
        call_type="main",
        model="m",
        verbosity="standard",
        policy_applied={"role": "executor", "thinking_budget": 5000},
    )
    assert rec["policy_applied"]["thinking_budget"] == 5000


def test_llm_call_record_includes_policy_applied():
    rec = build_trace_record(
        delegation_id="d1",
        role="context_builder",
        model="m",
        call_index=1,
        duration_ms=10,
        tokens=None,
        verbosity="standard",
        prompt_text=None,
        response_text=None,
        policy_applied={"role": "context_builder", "temperature": 0.2},
    )
    assert rec["policy_applied"]["temperature"] == 0.2


def test_records_omit_policy_applied_when_none():
    rec = build_trace_record(
        delegation_id="d1",
        role="executor",
        model="m",
        call_index=1,
        duration_ms=10,
        tokens=None,
        verbosity="standard",
        prompt_text=None,
        response_text=None,
    )
    assert "policy_applied" not in rec
