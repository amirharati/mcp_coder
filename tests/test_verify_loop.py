"""Post-delegate verify loop (P4-010)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.auto_verify import (
    DEFAULT_VERIFY_COMMAND,
    auto_verify_enabled,
    resolve_verify_command,
    resolve_verify_timeout_s,
)
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.specs.outcome import (
    OUTCOME_FAILED,
    OUTCOME_PARTIAL,
    OUTCOME_SUCCESS,
    apply_verify_outcome,
)
from core.verify.runner import VerifyResult, run_verify_command
from server.mcp_server import delegate_to_agent

STEP_SPEC = """\
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


def _write_workspace_config(workspace: Path, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-b.md").write_text(STEP_SPEC, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("def api(): return 1\n", encoding="utf-8")
    (pkg / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
    return ws


def _make_mock_engine(fake_result: ExecutionResult) -> object:
    def _run_context(self_ref, package, *, workspace_path, mcp_session_id=None,
                     host_transcript=None, **kwargs):
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


# --- config ---


def test_auto_verify_default_off(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_AUTO_VERIFY", raising=False)
    assert auto_verify_enabled(tmp_path) is False


def test_auto_verify_env_enables(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_AUTO_VERIFY", "1")
    assert auto_verify_enabled(tmp_path) is True


def test_auto_verify_yaml_disables_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_AUTO_VERIFY", "1")
    _write_workspace_config(tmp_path, "auto_verify: false\n")
    assert auto_verify_enabled(tmp_path) is False


def test_resolve_verify_command_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_VERIFY_COMMAND", raising=False)
    assert resolve_verify_command(tmp_path) == DEFAULT_VERIFY_COMMAND


def test_resolve_verify_command_yaml_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_VERIFY_COMMAND", "pytest -x")
    _write_workspace_config(tmp_path, 'verify_command: "python -m pytest -q"\n')
    assert resolve_verify_command(tmp_path) == "python -m pytest -q"


def test_resolve_verify_timeout_yaml_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_VERIFY_TIMEOUT_S", "60")
    _write_workspace_config(tmp_path, "verify_timeout_s: 180\n")
    assert resolve_verify_timeout_s(tmp_path) == 180


# --- runner ---


def test_run_verify_command_exit_zero(tmp_path, monkeypatch):
    proc = MagicMock(returncode=0, stdout="ok\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: proc)
    result = run_verify_command(
        workspace=tmp_path, command="pytest -q", timeout_s=30
    )
    assert result.passed is True
    assert result.exit_code == 0
    assert result.ran is True


def test_run_verify_command_exit_nonzero(tmp_path, monkeypatch):
    proc = MagicMock(returncode=1, stdout="", stderr="FAILED\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: proc)
    result = run_verify_command(
        workspace=tmp_path, command="pytest -q", timeout_s=30
    )
    assert result.passed is False
    assert result.exit_code == 1


def test_run_verify_command_timeout(tmp_path, monkeypatch):
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="pytest -q", timeout=30)

    monkeypatch.setattr(subprocess, "run", _timeout)
    result = run_verify_command(
        workspace=tmp_path, command="pytest -q", timeout_s=30
    )
    assert result.passed is None
    assert result.error == "timeout"


# --- outcome helper ---


@pytest.mark.parametrize(
    ("outcome", "verify_passed", "files", "expected"),
    [
        (OUTCOME_SUCCESS, False, ["a.py"], OUTCOME_PARTIAL),
        (OUTCOME_SUCCESS, True, ["a.py"], OUTCOME_SUCCESS),
        (OUTCOME_PARTIAL, False, [], OUTCOME_PARTIAL),
        (OUTCOME_FAILED, False, ["a.py"], OUTCOME_FAILED),
        (OUTCOME_SUCCESS, None, ["a.py"], OUTCOME_SUCCESS),
    ],
)
def test_apply_verify_outcome(outcome, verify_passed, files, expected):
    assert apply_verify_outcome(
        outcome, verify_passed=verify_passed, files_changed=files
    ) == expected


# --- integration ---


def test_delegate_verify_off_not_called(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_AUTO_VERIFY", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True, output="done", files_changed=["pkg/cli.py"], model="m"
    )
    engine = _make_mock_engine(fake)

    with patch("server.mcp_server.run_verify_command") as verify:
        with patch("server.mcp_server.get_engine", return_value=engine):
            raw = delegate_to_agent(
                task="Implement CLI",
                target_files=["pkg/cli.py"],
                context_summary="",
                spec_path="tasks/step-b.md",
                mode="implement",
            )
        verify.assert_not_called()

    payload = json.loads(raw)
    assert "verify_result" not in payload
    assert "auto_verify_enabled" not in payload


def test_delegate_verify_on_fail_partial(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_AUTO_VERIFY", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True, output="done", files_changed=["pkg/cli.py"], model="m"
    )
    engine = _make_mock_engine(fake)
    verify = VerifyResult(
        ran=True,
        passed=False,
        command="pytest -q",
        exit_code=1,
        duration_ms=50,
        stderr_tail="1 failed",
    )

    with patch("server.mcp_server.run_verify_command", return_value=verify):
        with patch("server.mcp_server.get_engine", return_value=engine):
            raw = delegate_to_agent(
                task="Implement CLI",
                target_files=["pkg/cli.py"],
                context_summary="",
                spec_path="tasks/step-b.md",
                mode="implement",
            )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["outcome"] == OUTCOME_PARTIAL
    assert payload["auto_verify_enabled"] is True
    assert payload["verify_result"]["passed"] is False
    assert payload["verify_result"]["exit_code"] == 1


def test_delegate_verify_on_pass_success(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_AUTO_VERIFY", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True, output="done", files_changed=["pkg/cli.py"], model="m"
    )
    engine = _make_mock_engine(fake)
    verify = VerifyResult(
        ran=True,
        passed=True,
        command="pytest -q",
        exit_code=0,
        duration_ms=40,
    )

    with patch("server.mcp_server.run_verify_command", return_value=verify):
        with patch("server.mcp_server.get_engine", return_value=engine):
            raw = delegate_to_agent(
                task="Implement CLI",
                target_files=["pkg/cli.py"],
                context_summary="",
                spec_path="tasks/step-b.md",
                mode="implement",
            )

    payload = json.loads(raw)
    assert payload["outcome"] == OUTCOME_SUCCESS
    assert payload["verify_result"]["passed"] is True


def test_delegate_review_skips_verify(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_AUTO_VERIFY", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="READY", model="m")

    with patch("server.mcp_server.run_verify_command") as verify:
        with patch("server.mcp_server.run_spec_review", return_value=fake):
            raw = delegate_to_agent(
                task="Review spec",
                target_files=[],
                context_summary="",
                spec_path="tasks/step-b.md",
                mode="review",
            )
        verify.assert_not_called()

    payload = json.loads(raw)
    assert "verify_result" not in payload
