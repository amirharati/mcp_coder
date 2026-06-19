"""P10-001 — Executor option wiring v0.

Tests for:
  - MCP_CODER_EXECUTOR_SYSTEM_PREFIX wired through model_registry resolve()
  - MCP_CODER_EXECUTOR_EDIT_FORMAT wired through model_registry resolve()
  - policy_applied() includes system_prompt_prefix and edit_format
  - _apply_executor_model_params sets model.system_prompt_prefix
  - delegation_coder_kwargs passes edit_format kwarg when set
  - delegation_coder_kwargs omits edit_format when None (default path unchanged)
  - build_delegation_record includes system_prefix_applied and edit_format in context
  - contextvar path: executor_options_audit_var → build_delegation_record
  - default (no env vars): byte-compatible behavior
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config.aider_runtime import delegation_coder_kwargs
from core.config.model_registry import (
    ROLE_EXECUTOR,
    CallParams,
    policy_applied,
    resolve,
)
from core.engine.aider_engine import _apply_executor_model_params
from core.logging.delegation_log import (
    build_delegation_record,
    executor_options_audit_var,
)
from core.storage.session_paths import prepare_delegation_storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeModel:
    """Minimal stand-in for aider.models.Model."""

    def __init__(self) -> None:
        self.system_prompt_prefix: str | None = None
        self.extra_params: dict = {}
        self.weak_model_name: str | None = None

    # aider API stubs
    def set_reasoning_effort(self, effort: str) -> None:
        pass

    def set_thinking_tokens(self, budget: int) -> None:
        pass

    def get_weak_model(self, name: str) -> None:
        self.weak_model_name = name


def _storage(tmp_path: Path, monkeypatch) -> object:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    monkeypatch.delenv("MCP_CODER_MIRROR_LOGS_TO_WORKSPACE", raising=False)
    return prepare_delegation_storage(workspace)


# ---------------------------------------------------------------------------
# model_registry: env var wiring
# ---------------------------------------------------------------------------


def test_system_prefix_resolved_from_env(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_SYSTEM_PREFIX", "Respect the spec Files contract.")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.system_prompt_prefix == "Respect the spec Files contract."
    assert cp.sources["system_prompt_prefix"] == "env"


def test_system_prefix_absent_when_env_unset(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.delenv("MCP_CODER_EXECUTOR_SYSTEM_PREFIX", raising=False)
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.system_prompt_prefix is None
    assert "system_prompt_prefix" not in cp.sources


def test_edit_format_resolved_from_env(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_EDIT_FORMAT", "whole")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.edit_format == "whole"
    assert cp.sources["edit_format"] == "env"


def test_edit_format_env_overrides_aider_default(monkeypatch):
    """Env var wins over Aider's own model-native edit_format."""
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_EDIT_FORMAT", "diff")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=True)
    assert cp.edit_format == "diff"
    assert cp.sources["edit_format"] == "env"


def test_edit_format_absent_by_default(monkeypatch):
    """Without env override, edit_format may be None or set from Aider — never 'env'."""
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.delenv("MCP_CODER_EXECUTOR_EDIT_FORMAT", raising=False)
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    assert cp.edit_format is None
    assert cp.sources.get("edit_format") != "env"


# ---------------------------------------------------------------------------
# policy_applied: includes new fields when resolved
# ---------------------------------------------------------------------------


def test_policy_applied_includes_system_prompt_prefix(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_SYSTEM_PREFIX", "do not commit")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    pa = policy_applied(cp, ROLE_EXECUTOR)
    assert pa["system_prompt_prefix"] == "do not commit"


def test_policy_applied_includes_edit_format(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_EDIT_FORMAT", "whole")
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    pa = policy_applied(cp, ROLE_EXECUTOR)
    assert pa["edit_format"] == "whole"


def test_policy_applied_omits_unset_fields(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.delenv("MCP_CODER_EXECUTOR_SYSTEM_PREFIX", raising=False)
    monkeypatch.delenv("MCP_CODER_EXECUTOR_EDIT_FORMAT", raising=False)
    cp = resolve(ROLE_EXECUTOR, include_aider_metadata=False)
    pa = policy_applied(cp, ROLE_EXECUTOR)
    assert "system_prompt_prefix" not in pa


# ---------------------------------------------------------------------------
# _apply_executor_model_params: sets model.system_prompt_prefix
# ---------------------------------------------------------------------------


def test_apply_executor_model_params_sets_prefix():
    model = _FakeModel()
    params = CallParams(system_prompt_prefix="Follow the Files contract.")
    _apply_executor_model_params(model, params)
    assert model.system_prompt_prefix == "Follow the Files contract."


def test_apply_executor_model_params_no_prefix_no_change():
    model = _FakeModel()
    params = CallParams(system_prompt_prefix=None)
    _apply_executor_model_params(model, params)
    assert model.system_prompt_prefix is None


# ---------------------------------------------------------------------------
# delegation_coder_kwargs: passes edit_format kwarg
# ---------------------------------------------------------------------------


def test_delegation_coder_kwargs_includes_edit_format():
    kwargs = delegation_coder_kwargs(edit_format="whole")
    assert kwargs["edit_format"] == "whole"


def test_delegation_coder_kwargs_omits_edit_format_by_default():
    kwargs = delegation_coder_kwargs()
    assert "edit_format" not in kwargs


def test_delegation_coder_kwargs_omits_edit_format_when_none():
    kwargs = delegation_coder_kwargs(edit_format=None)
    assert "edit_format" not in kwargs


def test_delegation_coder_kwargs_default_path_unchanged():
    """Without edit_format, the returned kwargs must match the previous stable set."""
    kwargs = delegation_coder_kwargs()
    expected_keys = {
        "auto_commits",
        "dirty_commits",
        "use_git",
        "suggest_shell_commands",
        "stream",
        "auto_lint",
        "show_diffs",
        "detect_urls",
    }
    assert set(kwargs.keys()) == expected_keys
    assert kwargs["auto_commits"] is False
    assert kwargs["show_diffs"] is False


# ---------------------------------------------------------------------------
# build_delegation_record: audit fields in context block
# ---------------------------------------------------------------------------


def _base_record_kwargs(storage) -> dict:
    return dict(
        delegation_id="p10-001-test",
        timestamp_start="2026-06-18T00:00:00.000Z",
        timestamp_end="2026-06-18T00:00:01.000Z",
        duration_ms=1000,
        mcp_request={"task": "t"},
        backend="aider",
        model="openrouter/openai/gpt-4o-mini",
        success=True,
        error=None,
        response_to_cursor={"success": True},
        files_requested=["a.py"],
        files_changed=["a.py"],
        context_block={"prompt_chars": 10},
        timing={"engine_run_ms": 900},
        tokens={"source": "unavailable"},
        project_key=storage.project_key,
        mcp_session_id=storage.mcp_session_id,
        session_dir=storage.session_dir,
        log_path=storage.log_path,
        session_action="new",
        session_reason="policy_always_new",
        session_policy="always_new",
    )


def test_delegation_record_has_system_prefix_applied_field(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch)
    record = build_delegation_record(
        **_base_record_kwargs(storage),
        system_prefix_applied=True,
    )
    assert record["context"]["system_prefix_applied"] is True


def test_delegation_record_has_edit_format_field(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch)
    record = build_delegation_record(
        **_base_record_kwargs(storage),
        edit_format_applied="whole",
    )
    assert record["context"]["edit_format"] == "whole"


def test_delegation_record_default_system_prefix_false(tmp_path, monkeypatch):
    """Backward-compat: system_prefix_applied defaults to False for old callers."""
    storage = _storage(tmp_path, monkeypatch)
    # Ensure contextvar is empty
    executor_options_audit_var.set({})
    record = build_delegation_record(**_base_record_kwargs(storage))
    assert record["context"]["system_prefix_applied"] is False
    assert "edit_format" not in record["context"]


def test_delegation_record_via_contextvar(tmp_path, monkeypatch):
    """Audit data flows from contextvar when not passed as explicit params."""
    storage = _storage(tmp_path, monkeypatch)
    executor_options_audit_var.set(
        {"system_prefix_applied": True, "edit_format": "diff"}
    )
    try:
        record = build_delegation_record(**_base_record_kwargs(storage))
        assert record["context"]["system_prefix_applied"] is True
        assert record["context"]["edit_format"] == "diff"
    finally:
        executor_options_audit_var.set({})


def test_explicit_params_take_priority_over_contextvar(tmp_path, monkeypatch):
    """Explicit params win over contextvar."""
    storage = _storage(tmp_path, monkeypatch)
    executor_options_audit_var.set(
        {"system_prefix_applied": False, "edit_format": "diff"}
    )
    try:
        record = build_delegation_record(
            **_base_record_kwargs(storage),
            system_prefix_applied=True,
            edit_format_applied="whole",
        )
        assert record["context"]["system_prefix_applied"] is True
        assert record["context"]["edit_format"] == "whole"
    finally:
        executor_options_audit_var.set({})
