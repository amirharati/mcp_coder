"""Integration tests: delegate_to_agent context package path vs legacy path."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.context.package import TIER_EDIT_FULL, TIER_READ_FULL, ContextPackage
from core.engine.base import ExecutionResult
from server.mcp_server import delegate_to_agent


STEP_B_SPEC = """\
---
spec_id: step-b
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


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-b.md").write_text(STEP_B_SPEC, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("def api(): return 1", encoding="utf-8")
    return ws


def _make_mock_engine(fake_result: ExecutionResult, captured: dict) -> object:
    def _run_context(self_ref, package, *, workspace_path, mcp_session_id=None, host_transcript=None):
        captured["package"] = package
        captured["called"] = "run_context"
        fake_result.prompt_used = "## Task\ntest"
        return fake_result

    def _run(self_ref, prompt, target_files, *, workspace_path, mcp_session_id=None):
        captured["called"] = "run"
        return fake_result

    return type(
        "MockEngine",
        (),
        {
            "model_name": "mock-model",
            "backend_id": "aider",
            "run": _run,
            "run_context": _run_context,
        },
    )()


# ---------------------------------------------------------------------------
# Context package path active when spec + implement + env default
# ---------------------------------------------------------------------------


def test_run_context_called_when_spec_and_implement(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="done", files_changed=["pkg/cli.py"])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
            mode="implement",
        )

    assert captured.get("called") == "run_context", "run_context must be called on package path"
    payload = json.loads(raw)
    assert payload["success"] is True


def test_run_context_package_has_read_entry(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    pkg: ContextPackage = captured["package"]
    paths = {e.path: e for e in pkg.entries}
    assert "pkg/core.py" in paths, "read contract path must be in package even if not in target_files"
    assert paths["pkg/core.py"].tier == TIER_READ_FULL
    assert paths["pkg/core.py"].payload == "def api(): return 1"


def test_translate_does_not_put_read_path_in_fnames(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    from core.engine.aider_engine import translate_context_package

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    pkg: ContextPackage = captured["package"]
    req = translate_context_package(pkg)
    assert "pkg/core.py" not in req.fnames, "read path must NOT be in fnames"
    assert "pkg/cli.py" in req.fnames or req.fnames == [], (
        "cli.py is missing on disk (missing_paths); fnames may be empty or contain it if it exists"
    )
    assert "def api(): return 1" in req.prompt, "read payload must appear in prompt"


def test_response_has_context_package_summary(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    assert "context_package_summary" in payload
    summary = payload["context_package_summary"]
    assert summary["compiler_version"] == "0.2.0"
    assert "read_paths" in summary
    assert "pkg/core.py" in summary["read_paths"]


def test_jsonl_has_context_package_and_adapter_in(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())

    ctx = record["context"]
    assert "context_package" in ctx, "JSONL context must include context_package"
    assert "adapter_in" in ctx, "JSONL context must include adapter_in"
    assert "fnames" in ctx["adapter_in"]
    assert "read_paths_in_prompt" in ctx["adapter_in"]
    assert "pkg/core.py" in ctx["adapter_in"]["read_paths_in_prompt"]


# ---------------------------------------------------------------------------
# Legacy path when MCP_CODER_USE_CONTEXT_PACKAGE=0
# ---------------------------------------------------------------------------


def test_legacy_run_called_when_env_disabled(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    assert captured.get("called") == "run", "legacy engine.run must be called when env=0"
    payload = json.loads(raw)
    assert "context_package_summary" not in payload
    assert payload["success"] is True


def test_legacy_run_called_without_spec_path(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="No spec",
            target_files=["pkg/cli.py"],
            context_summary="context",
        )

    assert captured.get("called") == "run", "no spec_path → must use legacy run"
    payload = json.loads(raw)
    assert "context_package_summary" not in payload
