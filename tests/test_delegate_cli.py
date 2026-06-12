"""Tests for mcp-coder delegate CLI (prepare + artifact envelope)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.cli.delegate import main_delegate
from core.delegation.prepare import prepare_delegation_context
from core.engine.base import ExecutionResult

STEP_SPEC = """\
---
spec_id: step-cli
files_edit:
  - pkg/models.py
files_read:
  - pkg/loader.py
edit_scope: discover
---

# Step

## Goal

Add comment.

## Files

### Edit

- `pkg/models.py`

### Read

- `pkg/loader.py`
"""


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-cli.md").write_text(STEP_SPEC, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "models.py").write_text("class Model:\n    pass\n", encoding="utf-8")
    (pkg / "loader.py").write_text("def load():\n    return []\n", encoding="utf-8")
    return ws


def test_prepare_stop_after_context_envelope(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = prepare_delegation_context(
        workspace=ws,
        task="Add comment",
        target_files=["pkg/models.py"],
        spec_path="tasks/step-cli.md",
    )
    assert result["ok"] is True
    assert result["stop_after"] == "context"
    assert "executor_in" in result["artifacts"]
    assert result["artifacts"]["executor_in"]["prompt"]
    assert "pkg/models.py" in result["artifacts"]["executor_in"]["fnames"]
    assert "helper_phases" in result["artifacts"]


def test_delegate_cli_stop_after_context(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)
    code = main_delegate(
        [
            "--task",
            "Add comment",
            "--target-files",
            "pkg/models.py",
            "--spec",
            "tasks/step-cli.md",
            "--stop-after",
            "context",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stop_after"] == "context"
    assert payload["artifacts"]["executor_in"]["prompt"]


def test_delegate_cli_full_run_envelope(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["pkg/models.py"],
        model="test-model",
        prompt_used="executor prompt used",
    )
    engine = MagicMock()
    engine.model_name = "test-model"
    engine.capabilities.return_value = MagicMock(supports_read_only_in_chat=True)
    engine.run_context.return_value = fake

    with patch("server.mcp_server.get_engine", return_value=engine):
        code = main_delegate(
            [
                "--workspace",
                str(ws),
                "--task",
                "Add comment",
                "--target-files",
                "pkg/models.py",
                "--context-summary",
                "ctx",
                "--spec",
                "tasks/step-cli.md",
            ]
        )
    assert code == 0
