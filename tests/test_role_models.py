"""Per-role model registry + audit (P4-004)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.config.models import resolve_model_name
from core.config.role_models import (
    ROLE_CONTEXT_BUILDER,
    ROLE_CRITIC,
    ROLE_EXECUTOR,
    ROLE_REVIEW,
    resolve_role_budget_tokens,
    resolve_role_model_name,
    role_config_keys,
)
from core.engine.base import ExecutionResult
from core.logging.delegation_log import build_delegation_record
from core.observability.context import delegation_context, role_context
from core.observability.litellm_callback import litellm_success_handler, reset_callback_state_for_tests
from core.usage.role_audit import build_role_usage_record, merge_model_roles
from server.mcp_server import _build_model_roles_payload, delegate_to_agent


def _write_workspace_config(workspace: Path, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def test_context_builder_default_falls_back_to_executor(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    assert resolve_role_model_name(ROLE_CONTEXT_BUILDER, tmp_path) == resolve_model_name()


def test_context_builder_default_model_env_before_executor(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_MODEL", raising=False)
    monkeypatch.setenv(
        "MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL",
        "openrouter/test/default-builder",
    )
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    assert resolve_role_model_name(ROLE_CONTEXT_BUILDER, tmp_path) == (
        "openrouter/test/default-builder"
    )


def test_context_builder_env_overrides_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/env-builder")
    assert resolve_role_model_name(ROLE_CONTEXT_BUILDER, tmp_path) == (
        "openrouter/test/env-builder"
    )


def test_context_builder_yaml_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/env-builder")
    _write_workspace_config(tmp_path, "context_builder_model: openrouter/test/yaml-builder\n")
    assert resolve_role_model_name(ROLE_CONTEXT_BUILDER, tmp_path) == (
        "openrouter/test/yaml-builder"
    )


def test_context_builder_empty_env_falls_through(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "")
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    assert resolve_role_model_name(ROLE_CONTEXT_BUILDER, tmp_path) == resolve_model_name()


def test_critic_defaults_to_executor(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CRITIC_MODEL", raising=False)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    assert resolve_role_model_name(ROLE_CRITIC, tmp_path) == resolve_model_name()


def test_executor_delegates_to_resolve_model_name(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    assert resolve_role_model_name(ROLE_EXECUTOR, tmp_path) == resolve_model_name()


def test_role_config_keys_context_builder():
    yaml_key, env_var = role_config_keys(ROLE_CONTEXT_BUILDER)
    assert yaml_key == "context_builder_model"
    assert env_var == "MCP_CODER_CONTEXT_BUILDER_MODEL"


def test_resolve_role_budget_tokens_yaml_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_BUDGET_TOKENS", "8000")
    _write_workspace_config(tmp_path, "context_builder_budget_tokens: 12000\n")
    assert resolve_role_budget_tokens(ROLE_CONTEXT_BUILDER, tmp_path) == 12000


def test_resolve_role_budget_tokens_unset_returns_none(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_BUDGET_TOKENS", raising=False)
    assert resolve_role_budget_tokens(ROLE_CONTEXT_BUILDER, tmp_path) is None


def test_build_role_usage_record_includes_cost_for_known_model():
    record = build_role_usage_record(
        role=ROLE_REVIEW,
        model="openrouter/google/gemini-2.5-flash",
        input_tokens=1200,
        output_tokens=80,
        total_tokens=1280,
        duration_ms=450,
        source="aider_message",
    )
    assert record["role"] == ROLE_REVIEW
    assert record["model"] == "openrouter/google/gemini-2.5-flash"
    assert record["tokens"]["total"] == 1280
    assert record["duration_ms"] == 450
    assert record["cost_est_usd"]["source"] == "static_rates"
    assert record["cost_est_usd"]["total"] > 0


def test_build_role_usage_record_unknown_model_cost():
    record = build_role_usage_record(
        role=ROLE_REVIEW,
        model="unknown/model-xyz",
        input_tokens=100,
        output_tokens=50,
        source="builder_llm",
    )
    assert record["cost_est_usd"]["source"] == "unknown_model"


def test_merge_model_roles_keyed_by_role():
    review = build_role_usage_record(role=ROLE_REVIEW, model="m1")
    executor = build_role_usage_record(role=ROLE_EXECUTOR, model="m2", source="executor")
    merged = merge_model_roles(review, None, executor)
    assert merged is not None
    assert set(merged) == {ROLE_REVIEW, ROLE_EXECUTOR}
    assert merged[ROLE_REVIEW]["model"] == "m1"


def test_delegation_record_includes_model_roles():
    roles = merge_model_roles(
        build_role_usage_record(role=ROLE_REVIEW, model="openrouter/test/review")
    )
    record = build_delegation_record(
        delegation_id="id",
        timestamp_start="t0",
        timestamp_end="t1",
        duration_ms=1,
        mcp_request={},
        backend="aider",
        model="openrouter/test/review",
        success=True,
        error=None,
        response_to_cursor={},
        files_requested=[],
        files_changed=[],
        context_block={},
        timing={},
        tokens={"source": "review"},
        project_key="p",
        mcp_session_id="s",
        session_dir="/tmp",
        log_path="/tmp/log",
        session_action="new",
        session_reason="",
        session_policy="new",
        model_roles=roles,
    )
    assert record["model_roles"]["review"]["model"] == "openrouter/test/review"
    assert record["context_refs"] == []


TASK_SPEC = """---
spec_id: widget-step
epic: widget
revision: 1
status: draft
---

## Goal

Build widget.

## Scope

One module.

## Files

- `widget.py`

## Constraints

- none

## Done when

- [ ] widget exists
"""


def _setup_review_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    task = ws / ".mcp-coder" / "specs" / "tasks" / "widget-step.md"
    task.parent.mkdir(parents=True)
    task.write_text(TASK_SPEC, encoding="utf-8")
    return ws


def test_review_delegate_jsonl_has_model_roles(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup_review_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_REVIEW_MODEL", "openrouter/test/review-model")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="**Questions:** None\nREADY_TO_IMPLEMENT",
        model="openrouter/test/review-model",
        tokens={"source": "review", "total": None},
    )

    with patch("server.mcp_server.run_spec_review", return_value=fake):
        raw = delegate_to_agent(
            task="Review this spec before we implement.",
            target_files=[],
            context_summary="",
            spec_path="tasks/widget-step.md",
            mode="review",
        )

    payload = json.loads(raw)
    assert "model_roles" in payload
    assert payload["model_roles"]["review"]["role"] == ROLE_REVIEW
    assert payload["model_roles"]["review"]["model"] == "openrouter/test/review-model"

    from core.logging.delegation_log import delegation_log_path

    log_path = delegation_log_path(str(ws))
    line = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    record = json.loads(line)
    assert record["model_roles"]["review"]["model"] == "openrouter/test/review-model"


def test_build_model_roles_payload_executor_tokens_from_callback():
    reset_callback_state_for_tests()
    delegation_id = "executor-tokens-test"
    with delegation_context(delegation_id):
        with role_context(ROLE_EXECUTOR):
            usage = SimpleNamespace(prompt_tokens=900, completion_tokens=100, total_tokens=1000)
            litellm_success_handler(
                {},
                SimpleNamespace(model="openrouter/openai/gpt-4o-mini", usage=usage),
                None,
                None,
            )

    roles = _build_model_roles_payload(
        delegation_id=delegation_id,
        delegate_mode="implement",
        resolved_model="openrouter/openai/gpt-4o-mini",
        tokens={"source": "unavailable"},
        timing={"engine_run_ms": 1200},
        workspace="/tmp/ws",
    )
    assert roles is not None
    assert roles[ROLE_EXECUTOR]["tokens"]["input"] == 900
    assert roles[ROLE_EXECUTOR]["tokens"]["output"] == 100
    assert roles[ROLE_EXECUTOR]["tokens"]["total"] == 1000
    assert roles[ROLE_EXECUTOR]["cost_est_usd"]["total"] > 0
