"""CLI history list|diff|revert (P3-322d)."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution


def _seed(ws, home, monkeypatch) -> str:
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    did = str(uuid.uuid4())
    (ws / "m.py").write_text("v1\n", encoding="utf-8")
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=did,
        mcp_session_id="sess-cli",
        timestamp_start="2026-06-08T00:00:00Z",
        spec_path="tasks/t.md",
        contract_paths=["m.py"],
    )
    (ws / "m.py").write_text("v1\nv2\n", encoding="utf-8")
    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["m.py"],
        edit_paths_rel=["m.py"],
        before_git=None,
        before_mtimes=None,
        delegation_id=did,
    )
    return did


def test_history_list_cli(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed(ws, home, monkeypatch)
    repo = Path(__file__).resolve().parents[1]

    proc = subprocess.run(
        [sys.executable, "main.py", "history", "list", "--workspace", str(ws)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert did[:8] in proc.stdout


def test_history_diff_cli_prints_hunk(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed(ws, home, monkeypatch)
    repo = Path(__file__).resolve().parents[1]

    proc = subprocess.run(
        [
            sys.executable,
            "main.py",
            "history",
            "diff",
            did,
            "--workspace",
            str(ws),
            "--path",
            "m.py",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "@@" in proc.stdout
    assert "v2" in proc.stdout


def test_history_revert_cli_restores_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed(ws, home, monkeypatch)
    assert (ws / "m.py").read_text(encoding="utf-8") == "v1\nv2\n"
    repo = Path(__file__).resolve().parents[1]

    proc = subprocess.run(
        [
            sys.executable,
            "main.py",
            "history",
            "revert",
            did,
            "--workspace",
            str(ws),
            "--paths",
            "m.py",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (ws / "m.py").read_text(encoding="utf-8") == "v1\n"
