"""P9-011 — model registry front door + unified helper path."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config.model_registry import (
    ROLE_ARCHITECT,
    ROLE_CONTEXT_BUILDER,
    ROLE_EXECUTOR,
    ROLES,
    CallParams,
    _aider_defaults,
    policy_applied,
    resolve,
)
from core.config.models import resolve_model_name
from core.config.role_models import (
    resolve_role_budget_tokens,
    resolve_role_model_name,
)


def test_resolve_executor_model_matches_resolve_model_name(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    cp = resolve(ROLE_EXECUTOR)
    assert cp.model == resolve_model_name()
    assert cp.sources["model"] == "role_models"


def test_resolve_context_builder_matches_role_models(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/google/gemini-2.5-flash")
    cp = resolve(ROLE_CONTEXT_BUILDER, tmp_path)
    assert cp.model == resolve_role_model_name(ROLE_CONTEXT_BUILDER, tmp_path)


def test_resolve_budget_matches_role_models(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_BUDGET_TOKENS", "1234")
    cp = resolve(ROLE_CONTEXT_BUILDER, tmp_path)
    assert cp.budget_tokens == resolve_role_budget_tokens(ROLE_CONTEXT_BUILDER, tmp_path)
    assert cp.budget_tokens == 1234
    assert cp.sources["budget_tokens"] == "role_models"


def test_generation_fields_unset_without_env(monkeypatch):
    # With no MCP_CODER_EXECUTOR_* env vars set, generation params stay unset.
    # (weak_model is now default-filled by the registry — see P9-012 tests.)
    for var in (
        "MCP_CODER_EXECUTOR_REASONING_EFFORT",
        "MCP_CODER_EXECUTOR_THINKING_BUDGET",
        "MCP_CODER_EXECUTOR_TEMPERATURE",
        "MCP_CODER_EXECUTOR_TOP_P",
        "MCP_CODER_EXECUTOR_MAX_TOKENS",
        "MCP_CODER_EXECUTOR_EXTRA_PARAMS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.reasoning_effort is None
    assert cp.thinking_budget is None
    assert cp.temperature is None
    assert cp.top_p is None
    assert cp.max_tokens is None
    assert cp.extra_params == {}
    assert cp.drop_params is True


def test_helper_label_roles_alias_to_underlying_model(monkeypatch, tmp_path):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/google/gemini-2.5-flash")
    # workspace_summarizer + architect + spec_validation resolve via context_builder.
    for role in ("workspace_summarizer", "architect", "spec_validation"):
        cp = resolve(role, tmp_path)
        assert cp.model == resolve_role_model_name(ROLE_CONTEXT_BUILDER, tmp_path)


def test_overrides_apply_and_record_source(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    cp = resolve(ROLE_EXECUTOR, overrides={"temperature": 0.5})
    assert cp.temperature == 0.5
    assert cp.sources["temperature"] == "override"


def test_aider_defaults_known_model_returns_metadata():
    info = _aider_defaults("anthropic/claude-sonnet-4-5")
    assert info.get("edit_format")  # diff/whole/etc.


def test_aider_defaults_never_raises_on_garbage():
    assert _aider_defaults("totally/unknown-model-xyz") == {} or isinstance(
        _aider_defaults("totally/unknown-model-xyz"), dict
    )


def test_callparams_is_dataclass_with_expected_shape():
    cp = CallParams()
    assert cp.drop_params is True
    assert cp.extra_params == {}
    assert cp.sources == {}


def test_all_roles_resolvable(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    for role in ROLES:
        cp = resolve(role, include_aider_metadata=False)
        assert cp.model, f"role {role} resolved empty model"


def test_policy_applied_executor_ignored_fields_and_note():
    cp = CallParams(temperature=0.5, top_p=0.9, max_tokens=1024)
    out = policy_applied(cp, ROLE_EXECUTOR)
    assert out["ignored"] == ["max_tokens", "temperature", "top_p"] or out["ignored"] == [
        "temperature",
        "top_p",
        "max_tokens",
    ]
    assert "MCP_CODER_EXECUTOR_EXTRA_PARAMS" in out["note"]


def test_policy_applied_non_executor_no_ignored():
    cp = CallParams(temperature=0.2)
    out = policy_applied(cp, ROLE_ARCHITECT)
    assert "ignored" not in out
    assert "note" not in out
