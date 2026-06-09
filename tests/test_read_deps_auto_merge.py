"""Tests for P3-311 auto-merge spec read-deps (D-P3-7)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.config.auto_merge import auto_merge_spec_read_enabled
from core.context.inspect import inspect_context_package
from core.engine.base import ExecutionResult
from core.specs.read_deps_merge import merge_spec_read_into_target, resolve_spec_read_deps
from server.mcp_server import delegate_to_agent

EDIT_READ_SPEC_BODY = """---
spec_id: cli-step
epic: expense
status: open
---

# Step 2 CLI

## Goal

Add CLI.

## Scope

CLI only.

## Files

### Edit

- `expense_splitter/cli.py`

### Read (include in target_files)

- `expense_splitter/splitter.py` — public API from step 1

## Constraints

- none

## Done when

- [ ] CLI works
"""

EDIT_ONLY_OMIT_SPEC = """---
spec_id: edit-omit
files_edit:
  - expense_splitter/cli.py
  - expense_splitter/util.py
files_read:
  - expense_splitter/splitter.py
edit_scope: discover
---

# Step

## Goal

Edit two files.

## Files

### Edit

- `expense_splitter/cli.py`
- `expense_splitter/util.py`

### Read

- `expense_splitter/splitter.py`
"""


def _setup_ws(tmp_path: Path, spec_body: str = EDIT_READ_SPEC_BODY, spec_name: str = "step.md") -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    task = ws / ".mcp-coder" / "specs" / "tasks" / spec_name
    task.parent.mkdir(parents=True)
    task.write_text(spec_body, encoding="utf-8")
    pkg = ws / "expense_splitter"
    pkg.mkdir()
    (pkg / "splitter.py").write_text("def split(): pass\n", encoding="utf-8")
    return ws


# ---------------------------------------------------------------------------
# Merge helper unit tests
# ---------------------------------------------------------------------------


def test_merge_appends_read_paths_not_edit():
    result = merge_spec_read_into_target(
        files_read=["pkg/read.py", "./pkg/other.py"],
        files_edit=["pkg/edit.py"],
        target_files=["pkg/edit.py"],
        enabled=True,
    )
    assert result.auto_merged_read_paths == ["pkg/other.py", "pkg/read.py"]
    assert result.effective_target_files == ["pkg/edit.py", "pkg/other.py", "pkg/read.py"]


def test_merge_does_not_add_edit_paths():
    result = merge_spec_read_into_target(
        files_read=["pkg/read.py"],
        files_edit=["pkg/edit.py", "pkg/missing_edit.py"],
        target_files=["pkg/edit.py"],
        enabled=True,
    )
    assert "pkg/missing_edit.py" not in result.effective_target_files
    assert result.auto_merged_read_paths == ["pkg/read.py"]


def test_merge_disabled_returns_planner_targets_only():
    result = merge_spec_read_into_target(
        files_read=["pkg/read.py"],
        files_edit=["pkg/edit.py"],
        target_files=["pkg/edit.py"],
        enabled=False,
    )
    assert result.auto_merged_read_paths == []
    assert result.effective_target_files == ["pkg/edit.py"]


def test_resolve_spec_read_deps_warns_edit_only_when_merge_on():
    _, missing, warnings = resolve_spec_read_deps(
        files_edit=["a/edit.py", "a/other_edit.py"],
        files_read=["a/read.py"],
        all_paths=["a/edit.py", "a/other_edit.py", "a/read.py"],
        target_files=["a/edit.py"],
        auto_merge_enabled=True,
    )
    assert missing == ["a/other_edit.py"]
    assert warnings == ["Spec Files lists paths not in target_files: a/other_edit.py"]


def test_resolve_spec_read_deps_warns_all_paths_when_merge_off():
    _, missing, warnings = resolve_spec_read_deps(
        files_edit=["a/edit.py"],
        files_read=["a/read.py"],
        all_paths=["a/edit.py", "a/read.py"],
        target_files=["a/edit.py"],
        auto_merge_enabled=False,
    )
    assert missing == ["a/read.py"]
    assert "a/read.py" in warnings[0]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_default_merge_on(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    assert auto_merge_spec_read_enabled(ws) is True


def test_config_opt_out_via_yaml(tmp_path):
    ws = tmp_path / "workspace"
    cfg = ws / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("auto_merge_spec_read: false\n", encoding="utf-8")
    assert auto_merge_spec_read_enabled(ws) is False


def test_config_yaml_wins_over_env(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    cfg = ws / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("auto_merge_spec_read: false\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_AUTO_MERGE_SPEC_READ", "1")
    assert auto_merge_spec_read_enabled(ws) is False


def test_config_env_when_no_yaml(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_AUTO_MERGE_SPEC_READ", "0")
    assert auto_merge_spec_read_enabled(ws) is False


# ---------------------------------------------------------------------------
# Delegate integration
# ---------------------------------------------------------------------------


def test_delegate_merge_on_no_read_contract_warning(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup_ws(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["expense_splitter/cli.py"], model="m")
    captured: dict = {}

    def _run_context(self_ref, package, **kwargs):
        captured["package"] = package
        fake.prompt_used = "prompt"
        return fake

    engine = type(
        "E",
        (),
        {
            "model_name": "m",
            "run_context": _run_context,
            "capabilities": lambda self: __import__(
                "core.engine.capabilities", fromlist=["AIDER_CAPABILITIES"]
            ).AIDER_CAPABILITIES,
        },
    )()

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["expense_splitter/cli.py"],
            context_summary="step 1 done",
            spec_path="tasks/step.md",
            mode="implement",
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["auto_merged_read_paths"] == ["expense_splitter/splitter.py"]
    assert payload["auto_merge_spec_read"] is True
    assert "contract_warnings" not in payload
    assert "spec_files_missing_from_target" not in payload

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["auto_merged_read_paths"] == ["expense_splitter/splitter.py"]
    assert record["mcp_request"]["target_files"] == ["expense_splitter/cli.py"]
    assert "expense_splitter/splitter.py" in record["mcp_request"]["effective_target_files"]
    assert "expense_splitter/splitter.py" in record["context"]["adapter_in"]["read_paths_in_prompt"]


def test_delegate_legacy_run_receives_merged_target_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup_ws(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)

    captured: dict = {}
    fake = ExecutionResult(success=True, output="ok", files_changed=[], model="m")

    def _run(self_ref, prompt, target_files, **kwargs):
        captured["target_files"] = target_files
        return fake

    engine = type("E", (), {"model_name": "m", "run": _run, "capabilities": lambda self: None})()

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["expense_splitter/cli.py"],
            context_summary="",
            spec_path="tasks/step.md",
        )

    payload = json.loads(raw)
    assert payload["auto_merged_read_paths"] == ["expense_splitter/splitter.py"]
    assert captured["target_files"] == [
        "expense_splitter/cli.py",
        "expense_splitter/splitter.py",
    ]


def test_delegate_edit_omit_still_warns_with_merge_on(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup_ws(tmp_path, EDIT_ONLY_OMIT_SPEC, "edit-omit.md")
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[], model="m")
    engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Edit files",
            target_files=["expense_splitter/cli.py"],
            context_summary="",
            spec_path="tasks/edit-omit.md",
        )

    payload = json.loads(raw)
    assert payload["auto_merged_read_paths"] == ["expense_splitter/splitter.py"]
    assert payload["spec_files_missing_from_target"] == ["expense_splitter/util.py"]
    assert any("util.py" in w for w in payload["contract_warnings"])
    assert not any("splitter.py" in w for w in payload["contract_warnings"])


def test_delegate_opt_out_restores_read_warn(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup_ws(tmp_path)
    cfg = ws / ".mcp-coder"
    cfg.mkdir(exist_ok=True)
    (cfg / "config.yaml").write_text("auto_merge_spec_read: false\n", encoding="utf-8")

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[], model="m")
    engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["expense_splitter/cli.py"],
            context_summary="",
            spec_path="tasks/step.md",
        )

    payload = json.loads(raw)
    assert payload.get("auto_merge_spec_read") is False
    assert "auto_merged_read_paths" not in payload
    assert payload["spec_files_missing_from_target"] == ["expense_splitter/splitter.py"]
    assert any("splitter.py" in w for w in payload["contract_warnings"])


def test_inspect_context_parity_with_delegate(tmp_path):
    ws = _setup_ws(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="Implement CLI",
        target_files=["expense_splitter/cli.py"],
        context_summary="step 1",
        spec_path="tasks/step.md",
    )
    assert result["ok"] is True
    assert result["auto_merged_read_paths"] == ["expense_splitter/splitter.py"]
    assert result["auto_merge_spec_read"] is True
    assert "contract_warnings" not in result
    assert "expense_splitter/splitter.py" in result["adapter_preview"]["read_paths_in_prompt"]
