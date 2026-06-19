"""Host model_policy per delegation (P11-007)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.config.host_model_policy import (
    normalize_host_model_policy,
    pick_host_override,
    summarize_model_policy_applied,
)
from core.config.model_registry import ROLE_EXECUTOR, resolve
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.observability.context import host_model_policy_var, role_context
from core.observability.gateway import (
    LlmGateway,
    get_llm_gateway,
    reset_llm_gateway,
    set_llm_gateway,
)
from core.observability.local import LocalObservability
from server.mcp_server import delegate_to_agent

STEP_SPEC_ARCH_ON = """\
---
spec_id: step-b
architect_pass: true
files_edit:
  - pkg/cli.py
files_read:
  - pkg/core.py
edit_scope: discover
---

# Step task spec

## Goal

CLI uses core.

## Files

### Edit
- `pkg/cli.py`

### Read
- `pkg/core.py`
"""


def _write_workspace_config(workspace, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def _setup_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-b.md").write_text(STEP_SPEC_ARCH_ON, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("def api(): return 1\n", encoding="utf-8")
    (pkg / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
    return ws


def _make_mock_engine(fake_result: ExecutionResult) -> object:
    def _run_context(
        self_ref, package, *, workspace_path, mcp_session_id=None, host_transcript=None, **kwargs
    ):
        return fake_result

    def _run(self_ref, prompt, target_files, *, workspace_path, mcp_session_id=None, **kwargs):
        return fake_result

    def _capabilities(self_ref):
        return AIDER_CAPABILITIES

    return type(
        "MockEngine",
        (),
        {
            "model_name": "mock-model",
            "backend_id": "aider",
            "run": _run,
            "run_context": _run_context,
            "capabilities": _capabilities,
        },
    )()


def test_normalize_model_policy_executor_and_reviewer():
    overrides, warnings = normalize_host_model_policy(
        {
            "executor": {"model": "openrouter/openai/gpt-4o-mini", "thinking_budget": 8000},
            "reviewer": {"temperature": 0.1},
        }
    )
    assert warnings == []
    assert overrides["executor"]["model"] == "openrouter/openai/gpt-4o-mini"
    assert overrides["executor"]["thinking_budget"] == 8000
    assert overrides["review"]["temperature"] == 0.1
    summary = summarize_model_policy_applied(overrides)
    assert "executor" in summary["roles"]
    assert "model" in summary["roles"]["executor"]


def test_normalize_model_policy_unknown_role_warns():
    overrides, warnings = normalize_host_model_policy(
        {"planner": {"model": "x"}, "executor": {"model": "y"}}
    )
    assert overrides["executor"]["model"] == "y"
    assert any("unknown" in w for w in warnings)


def test_normalize_model_policy_invalid_field_warns():
    overrides, warnings = normalize_host_model_policy(
        {"executor": {"model": "", "bogus": 1, "temperature": "hot"}}
    )
    assert overrides == {}
    assert len(warnings) >= 2


def test_model_registry_host_policy_precedence_over_env(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("MCP_CODER_EXECUTOR_THINKING_BUDGET", "1000")
    cp = resolve(
        ROLE_EXECUTOR,
        host_policy_override={"thinking_budget": 8000},
        include_aider_metadata=False,
    )
    assert cp.thinking_budget == 8000
    assert cp.sources["thinking_budget"] == "host_policy"


def test_model_registry_runtime_override_beats_host_policy(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    cp = resolve(
        ROLE_EXECUTOR,
        overrides={"thinking_budget": 999},
        host_policy_override={"thinking_budget": 8000},
        include_aider_metadata=False,
    )
    assert cp.thinking_budget == 999
    assert cp.sources["thinking_budget"] == "override"


def test_delegate_model_policy_executor_override_applied(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)
    _write_workspace_config(ws, "auto_merge_spec_read: false\n")

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
            model_policy={"executor": {"thinking_budget": 7777}},
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["model_policy_applied"]["roles"]["executor"] == ["thinking_budget"]
    assert host_model_policy_var.get() is None

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["mcp_request"]["model_policy_applied"]["roles"]["executor"] == [
        "thinking_budget"
    ]
    assert record["context"]["model_policy_applied"]["roles"]["executor"] == ["thinking_budget"]


def test_delegate_model_policy_invalid_nonfatal_with_warning(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="ctx",
            spec_path="tasks/step-b.md",
            mode="implement",
            model_policy={"executor": "not-a-dict", "unknown_role": {"model": "x"}},
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    warnings = payload["model_policy_warnings"]
    assert any("must be a dict" in w for w in warnings)
    assert any("unknown" in w for w in warnings)


def test_gateway_uses_host_policy_model_for_helper_role(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    obs = LocalObservability()
    set_llm_gateway(LlmGateway(obs))

    normalized, _ = normalize_host_model_policy(
        {"reviewer": {"model": "openrouter/host/reviewer-model", "temperature": 0.0}}
    )
    token = host_model_policy_var.set(normalized)

    response = SimpleNamespace(
        model="openrouter/host/reviewer-model",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
    )

    try:
        with patch("litellm.completion", return_value=response) as completion:
            with role_context("review"):
                result = get_llm_gateway().complete(
                    model="openrouter/default/review",
                    messages=[{"role": "user", "content": "ping"}],
                    role="review",
                )
        assert result.model == "openrouter/host/reviewer-model"
        assert completion.call_args.kwargs["model"] == "openrouter/host/reviewer-model"
    finally:
        host_model_policy_var.reset(token)
        reset_llm_gateway()


def test_pick_host_override_architect_pass_alias():
    normalized = {"architect": {"thinking_budget": 4000}}
    picked = pick_host_override(normalized, "architect_pass")
    assert picked == {"thinking_budget": 4000}
