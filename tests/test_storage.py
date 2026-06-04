"""Tests for core.storage.paths and session preparation."""

from __future__ import annotations

import json

from core.storage.paths import mcp_coder_home, project_key, sessions_root, ensure_mcp_coder_home
from core.storage.session_paths import prepare_delegation_storage


def test_ensure_mcp_coder_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    assert not home.exists()
    created = ensure_mcp_coder_home()
    assert created == home.resolve()
    assert (home / "projects").is_dir()


def test_project_key_stable(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    assert project_key(ws) == project_key(ws.resolve())


def test_prepare_delegation_storage(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    storage = prepare_delegation_storage(workspace)
    assert storage.project_key == project_key(workspace)
    assert storage.session_dir.is_dir()
    assert (storage.session_dir / "session.json").is_file()
    assert storage.log_path.parent == storage.session_dir

    session = json.loads((storage.session_dir / "session.json").read_text(encoding="utf-8"))
    assert session["mcp_session_id"] == storage.mcp_session_id
    assert session["host_kind"] is None
    assert session["session_policy"] == "always_new"

    assert mcp_coder_home() == home.resolve()
    assert sessions_root(workspace) == home / "projects" / storage.project_key / "sessions"

    pointer = workspace / ".mcp-coder" / "session.json"
    assert pointer.is_file()
    ptr = json.loads(pointer.read_text(encoding="utf-8"))
    assert ptr["project_key"] == storage.project_key
    assert ptr["sessions_root"] == str(sessions_root(workspace))
