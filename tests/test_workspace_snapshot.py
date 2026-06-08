"""Workspace hash snapshot + manifest attribution (P3-322a)."""

from __future__ import annotations

import subprocess
import uuid

from core.engine.git_diff import compute_files_unexpected
from core.storage.paths import workspace_history_db_path
from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.manifest import diff_manifests
from core.workspace.snapshot import (
    begin_delegation_snapshot,
    is_snapshot_enabled,
    resolve_delegation_attribution,
)
from core.workspace.walk import walk_workspace


def _git_init_commit(repo: str, files: dict[str, str]) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    for name, content in files.items():
        path = f"{repo}/{name}"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        subprocess.run(["git", "add", name], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)


def test_p2_iss_002_non_git_unexpected_paths(tmp_path, monkeypatch):
    """P2-ISS-002: non-git workspace reports all created files + unexpected outside contract."""
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    ws = tmp_path / "ws"
    (ws / "app").mkdir(parents=True)

    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=None,
        mcp_session_id=None,
        timestamp_start=None,
        spec_path=None,
    )
    assert session is not None

    (ws / "app" / "cli.py").write_text("", encoding="utf-8")
    (ws / "app" / "app").mkdir()
    (ws / "app" / "app" / "cli.py").write_text("x\n", encoding="utf-8")
    (ws / "app" / "app" / "core.py").write_text("y\n", encoding="utf-8")
    (ws / "app" / "app" / "__init__.py").write_text("", encoding="utf-8")

    files_changed, files_unexpected, meta, _used_git, _ms = resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["app/cli.py"],
        edit_paths_rel=["app/cli.py"],
        before_git=None,
        before_mtimes=None,
    )

    assert meta is not None
    assert meta["attribution_source"] == "manifest"
    assert sorted(files_changed) == sorted(
        [
            "app/cli.py",
            "app/app/cli.py",
            "app/app/core.py",
            "app/app/__init__.py",
        ]
    )
    assert sorted(files_unexpected) == sorted(
        ["app/app/cli.py", "app/app/core.py", "app/app/__init__.py"]
    )
    assert sorted(meta["delta"]["created"]) == sorted(files_changed)


def test_modify_and_delete_in_delta(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "keep.py").write_text("old\n", encoding="utf-8")
    (ws / "gone.py").write_text("bye\n", encoding="utf-8")

    before = walk_workspace(str(ws))
    (ws / "keep.py").write_text("new\n", encoding="utf-8")
    (ws / "gone.py").unlink()

    after = walk_workspace(str(ws))
    delta = diff_manifests(before, after)

    assert delta.modified == ["keep.py"]
    assert delta.deleted == ["gone.py"]
    assert delta.created == []


def test_skip_rules_exclude_node_modules_and_mcp_coder(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "node_modules").mkdir()
    (ws / "node_modules" / "foo.js").write_text("x", encoding="utf-8")
    (ws / ".mcp-coder").mkdir()
    (ws / ".mcp-coder" / "config.yaml").write_text("x: 1\n", encoding="utf-8")
    (ws / "src.py").write_text("ok\n", encoding="utf-8")

    manifest = walk_workspace(str(ws))
    assert "src.py" in manifest
    assert "node_modules/foo.js" not in manifest
    assert ".mcp-coder/config.yaml" not in manifest


def test_git_preexisting_dirty_not_in_delta(tmp_path, monkeypatch):
    """Manifest delta includes only files changed during delegation."""
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    _git_init_commit(str(tmp_path), {"a.py": "v1\n", "stale.py": "old\n"})
    (tmp_path / "stale.py").write_text("already dirty\n", encoding="utf-8")

    session = begin_delegation_snapshot(
        workspace_path=str(tmp_path),
        delegation_id=None,
        mcp_session_id=None,
        timestamp_start=None,
        spec_path=None,
    )
    (tmp_path / "a.py").write_text("v2\n", encoding="utf-8")

    files_changed, _, meta, _used_git, _ms = resolve_delegation_attribution(
        workspace_path=str(tmp_path),
        snapshot_session=session,
        contract_paths=["a.py"],
        edit_paths_rel=["a.py"],
        before_git=None,
        before_mtimes=None,
    )

    assert files_changed == ["a.py"]
    assert meta is not None
    assert "stale.py" not in meta["delta"]["modified"]


def test_sqlite_file_deltas_match_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())

    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-1",
        timestamp_start="2026-06-08T00:00:00Z",
        spec_path="tasks/foo.md",
    )
    (ws / "new.py").write_text("hello\n", encoding="utf-8")

    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["new.py"],
        edit_paths_rel=["new.py"],
        before_git=None,
        before_mtimes=None,
        delegation_id=delegation_id,
    )

    db_path = workspace_history_db_path(ws)
    assert db_path.is_file()

    db = WorkspaceHistoryDB(ws)
    rows = db.get_file_deltas(delegation_id)
    assert len(rows) == 1
    assert rows[0]["path"] == "new.py"
    assert rows[0]["change_type"] == "created"


def test_disable_snapshot_legacy_mtime_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", "1")
    assert is_snapshot_enabled() is False

    ws = tmp_path / "ws"
    ws.mkdir()
    f = ws / "a.py"
    f.write_text("v1\n", encoding="utf-8")

    from core.engine.git_diff import snapshot_mtimes

    before_mtimes = snapshot_mtimes(str(ws), ["a.py"])
    f.write_text("v2\n", encoding="utf-8")

    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=None,
        mcp_session_id=None,
        timestamp_start=None,
        spec_path=None,
    )
    assert session is None

    files_changed, files_unexpected, meta, used_git, _ms = resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["a.py"],
        edit_paths_rel=["a.py"],
        before_git=None,
        before_mtimes=before_mtimes,
    )

    assert meta is None
    assert used_git is False
    assert files_changed == ["a.py"]
    assert files_unexpected == []


def test_compute_files_unexpected_manifest_mode():
    unexpected = compute_files_unexpected(
        ["src/a.py", "src/extra.py"],
        ["src/a.py", "./src/b.py"],
        attribution_source="manifest",
    )
    assert unexpected == ["src/extra.py"]
