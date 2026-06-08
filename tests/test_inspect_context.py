"""Tests for inspect_context dry-run (CLI + MCP + shared inspect module)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from core.cli.inspect_context import main_inspect_context
from core.context.inspect import inspect_context_package
from server.mcp_server import inspect_context


STEP_5B_SPEC = """\
---
spec_id: step-5b
files_edit:
  - expense_splitter/models.py
files_read:
  - expense_splitter/loader.py
edit_scope: discover
---

# Step 5b

## Goal

Add comment above Expense.

## Files

### Edit

- `expense_splitter/models.py`

### Read

- `expense_splitter/loader.py`
"""


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-5b.md").write_text(STEP_5B_SPEC, encoding="utf-8")

    pkg = ws / "expense_splitter"
    pkg.mkdir()
    (pkg / "models.py").write_text("class Expense:\n    pass\n", encoding="utf-8")
    (pkg / "loader.py").write_text("def load():\n    return []\n", encoding="utf-8")
    return ws


def test_read_dep_omitted_from_target_files(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="Add comment above Expense",
        target_files=["expense_splitter/models.py"],
        context_summary="Step 5b read-context test",
        spec_path="tasks/step-5b.md",
    )

    assert result["ok"] is True
    assert result["compiler_version"] == "0.3.0"
    assert result["spec_files_missing_from_target"] == ["expense_splitter/loader.py"]
    assert any("loader.py" in w for w in result["contract_warnings"])

    preview = result["adapter_preview"]
    assert "expense_splitter/models.py" in preview["fnames"]
    assert "expense_splitter/loader.py" not in preview["fnames"]
    assert "expense_splitter/loader.py" in preview["read_paths_in_prompt"]
    assert preview["prompt_chars"] > 0
    assert preview["prompt_tokens_est"] > 0
    assert preview["prompt_hash"]


def test_no_spec_path_no_contract_warnings(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="Read models",
        target_files=["expense_splitter/models.py"],
        context_summary="hint only",
    )

    assert result["ok"] is True
    assert "contract_warnings" not in result
    assert "spec_files_missing_from_target" not in result
    paths = [e["path"] for e in result["context_package"]["entries"]]
    assert "expense_splitter/models.py" in paths


def test_invalid_spec_path_returns_error(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        context_summary="",
        spec_path="tasks/missing.md",
    )

    assert result["ok"] is False
    assert "error" in result
    assert "spec-template.md" in result["error"]


def test_cli_invalid_spec_exit_code_one(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    code = main_inspect_context(
        [
            "--task",
            "t",
            "--target-files",
            "expense_splitter/models.py",
            "--spec",
            "tasks/missing.md",
        ]
    )
    assert code == 1


def test_include_payloads_false_omits_payload_key(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        context_summary="",
        spec_path="tasks/step-5b.md",
        include_payloads=False,
    )

    assert result["ok"] is True
    for entry in result["context_package"]["entries"]:
        assert "payload" not in entry


def test_include_payloads_true_includes_payload(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        context_summary="",
        spec_path="tasks/step-5b.md",
        include_payloads=True,
    )

    assert result["ok"] is True
    by_path = {e["path"]: e for e in result["context_package"]["entries"]}
    assert "def load" in (by_path["expense_splitter/loader.py"].get("payload") or "")
    assert "class Expense" in (by_path["expense_splitter/models.py"].get("payload") or "")


def test_mcp_tool_returns_parseable_json(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    raw = inspect_context(
        task="Add comment",
        target_files=["expense_splitter/models.py"],
        context_summary="ctx",
        spec_path="tasks/step-5b.md",
    )
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert "adapter_preview" in payload
    assert payload["context_package"]["summary"]["compiler_version"] == "0.3.0"


def test_no_engine_called(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    def _boom(*args, **kwargs):
        raise AssertionError("get_engine must not be called during inspect")

    with patch("server.mcp_server.get_engine", side_effect=_boom):
        result = inspect_context_package(
            workspace=ws,
            task="t",
            target_files=["expense_splitter/models.py"],
            context_summary="",
            spec_path="tasks/step-5b.md",
        )
    assert result["ok"] is True


def test_no_adapter_preview_when_disabled(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        context_summary="",
        spec_path="tasks/step-5b.md",
        include_adapter_preview=False,
    )

    assert result["ok"] is True
    assert "adapter_preview" not in result


def test_cli_success_exit_code_zero(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    code = main_inspect_context(
        [
            "--task",
            "Add comment",
            "--target-files",
            "expense_splitter/models.py",
            "--context-summary",
            "ctx",
            "--spec",
            "tasks/step-5b.md",
            "--pretty",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True


def test_cli_target_files_comma_separated(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py", "expense_splitter/loader.py"],
        context_summary="",
        spec_path="tasks/step-5b.md",
    )
    assert result["ok"] is True
    assert "contract_warnings" not in result


def test_main_py_inspect_context_subcommand(tmp_path):
    ws = _setup_workspace(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            "main.py",
            "inspect-context",
            "--workspace",
            str(ws),
            "--task",
            "t",
            "--target-files",
            "expense_splitter/models.py",
            "--spec",
            "tasks/step-5b.md",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
