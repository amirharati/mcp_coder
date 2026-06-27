"""P11-003 — executor-pull hint v0 (prompt-level only)."""

from __future__ import annotations

from core.config.aider_runtime import executor_pull_hint_enabled
from core.config.model_registry import CallParams
from core.context.role_rules import SHARED_RULES, build_role_rules
from core.engine.aider_engine import (
    _apply_executor_system_prefix,
    _apply_executor_model_params,
    _merge_executor_system_prefix,
)
from core.logging.delegation_log import (
    build_delegation_record,
    executor_options_audit_var,
)
from core.storage.session_paths import prepare_delegation_storage


class _FakeModel:
    def __init__(self) -> None:
        self.system_prompt_prefix: str | None = None
        self.extra_params: dict = {}

    def set_reasoning_effort(self, effort: str) -> None:
        pass

    def set_thinking_tokens(self, budget: int) -> None:
        pass

    def get_weak_model(self, name: str) -> None:
        pass


def _storage(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    monkeypatch.delenv("MCP_CODER_MIRROR_LOGS_TO_WORKSPACE", raising=False)
    return prepare_delegation_storage(workspace)


def _base_record_kwargs(storage) -> dict:
    return dict(
        delegation_id="p11-003-test",
        timestamp_start="2026-06-19T00:00:00.000Z",
        timestamp_end="2026-06-19T00:00:01.000Z",
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


def test_executor_pull_hint_default_on(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_EXECUTOR_PULL_HINT", raising=False)
    assert executor_pull_hint_enabled(tmp_path) is True


def test_executor_pull_hint_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_EXECUTOR_PULL_HINT", "1")
    assert executor_pull_hint_enabled(tmp_path) is True


def test_merge_pull_hint_only_when_no_existing_prefix():
    assert _merge_executor_system_prefix(None) == build_role_rules("executor")
    assert _merge_executor_system_prefix("") == build_role_rules("executor")


def test_merge_pull_hint_after_existing_prefix():
    merged = _merge_executor_system_prefix("Custom executor prefix.")
    assert merged.startswith("Custom executor prefix.")
    assert "\n\n---\n\n" in merged
    assert merged.endswith(build_role_rules("executor"))


def test_apply_pull_hint_on_sets_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_EXECUTOR_PULL_HINT", "1")
    model = _FakeModel()
    applied = _apply_executor_system_prefix(model, workspace_path=tmp_path)
    assert applied is True
    assert model.system_prompt_prefix == build_role_rules("executor")
    for shared in SHARED_RULES:
        assert shared in model.system_prompt_prefix


def test_apply_pull_hint_merges_with_existing_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_EXECUTOR_PULL_HINT", "1")
    model = _FakeModel()
    _apply_executor_model_params(
        model,
        CallParams(system_prompt_prefix="Respect the spec Files contract."),
    )
    applied = _apply_executor_system_prefix(model, workspace_path=tmp_path)
    assert applied is True
    assert model.system_prompt_prefix.startswith("Respect the spec Files contract.")
    assert build_role_rules("executor") in model.system_prompt_prefix
    assert model.system_prompt_prefix.index("Respect") < model.system_prompt_prefix.index("/read")


def test_apply_system_prefix_ignores_legacy_pull_hint_toggle(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_EXECUTOR_PULL_HINT", "0")
    model = _FakeModel()
    _apply_executor_model_params(
        model,
        CallParams(system_prompt_prefix="Respect the spec Files contract."),
    )
    applied = _apply_executor_system_prefix(model, workspace_path=tmp_path)
    assert applied is True
    assert model.system_prompt_prefix.startswith("Respect the spec Files contract.")
    assert build_role_rules("executor") in model.system_prompt_prefix


def test_delegation_record_executor_pull_hint_via_contextvar(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch)
    executor_options_audit_var.set({"executor_pull_hint_applied": True})
    try:
        record = build_delegation_record(**_base_record_kwargs(storage))
        assert record["context"]["executor_pull_hint_applied"] is True
    finally:
        executor_options_audit_var.set({})


def test_delegation_record_executor_pull_hint_default_false(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch)
    executor_options_audit_var.set({})
    record = build_delegation_record(**_base_record_kwargs(storage))
    assert record["context"]["executor_pull_hint_applied"] is False
