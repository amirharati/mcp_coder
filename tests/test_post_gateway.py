"""Post-delegation strict gateway + auto-revert (P3-322c)."""

from __future__ import annotations

import sqlite3
import uuid

from core.specs.delegation_policies import EDIT_SCOPE_DISCOVER, EDIT_SCOPE_STRICT
from core.specs.modes import DELEGATE_MODE_IMPLEMENT, DELEGATE_MODE_REVIEW
from core.specs.outcome import OUTCOME_SCOPE_VIOLATION, apply_scope_outcome
from core.storage.paths import workspace_history_db_path
from core.workspace.gateway import apply_post_delegation_gateway
from core.workspace.snapshot import (
    begin_delegation_snapshot,
    is_snapshot_enabled,
    resolve_delegation_attribution,
)


def _commit_delegation(
    ws,
    home,
    monkeypatch,
    *,
    delegation_id: str,
    contract_paths: list[str],
    mutate,
) -> None:
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-gw",
        timestamp_start="2026-06-08T00:00:00Z",
        spec_path="tasks/foo.md",
        contract_paths=contract_paths,
    )
    mutate(ws)
    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=contract_paths,
        edit_paths_rel=contract_paths,
        before_git=None,
        before_mtimes=None,
        delegation_id=delegation_id,
    )


def test_strict_violation_reverts_created_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())

    _commit_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["app/cli.py"],
        mutate=lambda w: (
            (w / "app").mkdir(exist_ok=True),
            (w / "app" / "cli.py").write_text("ok\n", encoding="utf-8"),
            (w / "app" / "extra.py").write_text("bad\n", encoding="utf-8"),
        ),
    )
    assert (ws / "app" / "extra.py").is_file()

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=delegation_id,
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["app/cli.py", "app/extra.py"],
        files_edit=["app/cli.py"],
    )

    assert result.gateway_applied is True
    assert result.scope_violations == ["app/extra.py"]
    assert result.reverted_paths == ["app/extra.py"]
    assert result.revert_skipped == []
    assert not (ws / "app" / "extra.py").exists()
    assert (ws / "app" / "cli.py").read_text(encoding="utf-8") == "ok\n"


def test_strict_all_changes_in_files_edit_no_revert(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())

    _commit_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["a.py"],
        mutate=lambda w: (w / "a.py").write_text("v2\n", encoding="utf-8"),
    )

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=delegation_id,
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["a.py"],
        files_edit=["a.py"],
    )

    assert result.gateway_applied is False
    assert result.scope_violations == []
    assert result.reverted_paths == []
    assert (ws / "a.py").read_text(encoding="utf-8") == "v2\n"


def test_discover_mode_gateway_noop(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())

    _commit_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["a.py"],
        mutate=lambda w: (w / "extra.py").write_text("x\n", encoding="utf-8"),
    )

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=delegation_id,
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_DISCOVER,
        files_changed=["a.py", "extra.py"],
        files_edit=["a.py"],
    )

    assert result.gateway_applied is False
    assert result.scope_violations == []
    assert (ws / "extra.py").is_file()


def test_review_mode_gateway_noop(tmp_path, monkeypatch):
    result = apply_post_delegation_gateway(
        workspace=tmp_path,
        delegation_id="del-1",
        delegate_mode=DELEGATE_MODE_REVIEW,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["other.py"],
        files_edit=["a.py"],
    )
    assert result.gateway_applied is False
    assert result.scope_violations == []


def test_snapshot_disabled_no_revert(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", "1")
    assert is_snapshot_enabled() is False

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "bad.py").write_text("x\n", encoding="utf-8")

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=str(uuid.uuid4()),
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["bad.py"],
        files_edit=["a.py"],
    )

    assert result.gateway_applied is False
    assert result.scope_violations == ["bad.py"]
    assert result.reverted_paths == []
    assert result.revert_skipped == ["bad.py"]
    assert (ws / "bad.py").is_file()


def test_missing_blob_revert_skipped(tmp_path, monkeypatch):
    """Modified violation cannot revert when prev_hash blob was removed."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "allowed.py").write_text("ok\n", encoding="utf-8")
    (ws / "violation.py").write_text("old\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    _commit_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["allowed.py", "violation.py"],
        mutate=lambda w: (w / "violation.py").write_text("new\n", encoding="utf-8"),
    )

    conn = sqlite3.connect(str(workspace_history_db_path(ws)))
    conn.execute("DELETE FROM blobs")
    conn.commit()
    conn.close()

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=delegation_id,
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["violation.py"],
        files_edit=["allowed.py"],
    )

    assert result.scope_violations == ["violation.py"]
    assert result.reverted_paths == []
    assert result.revert_skipped == ["violation.py"]
    assert (ws / "violation.py").read_text(encoding="utf-8") == "new\n"


def test_strict_modified_violation_restored(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "allowed.py").write_text("a\n", encoding="utf-8")
    (ws / "violation.py").write_text("old\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    _commit_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["allowed.py", "violation.py"],
        mutate=lambda w: (w / "violation.py").write_text("new\n", encoding="utf-8"),
    )
    assert (ws / "violation.py").read_text(encoding="utf-8") == "new\n"

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=delegation_id,
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["violation.py"],
        files_edit=["allowed.py"],
    )

    assert result.reverted_paths == ["violation.py"]
    assert (ws / "violation.py").read_text(encoding="utf-8") == "old\n"


def test_p2_iss_002_strict_auto_revert(tmp_path, monkeypatch):
    """Non-git strict: unexpected app/app/* paths reverted; outcome scope_violation."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    (ws / "app").mkdir(parents=True)
    delegation_id = str(uuid.uuid4())

    _commit_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["app/cli.py"],
        mutate=lambda w: (
            (w / "app" / "cli.py").write_text("", encoding="utf-8"),
            (w / "app" / "app").mkdir(exist_ok=True),
            (w / "app" / "app" / "cli.py").write_text("x\n", encoding="utf-8"),
            (w / "app" / "app" / "core.py").write_text("y\n", encoding="utf-8"),
            (w / "app" / "app" / "__init__.py").write_text("", encoding="utf-8"),
        ),
    )

    files_changed = [
        "app/cli.py",
        "app/app/cli.py",
        "app/app/core.py",
        "app/app/__init__.py",
    ]
    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=delegation_id,
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=files_changed,
        files_edit=["app/cli.py"],
    )

    assert result.scope_violations == [
        "app/app/__init__.py",
        "app/app/cli.py",
        "app/app/core.py",
    ]
    assert result.reverted_paths == result.scope_violations
    assert not (ws / "app" / "app" / "cli.py").exists()
    assert not (ws / "app" / "app" / "core.py").exists()
    assert not (ws / "app" / "app" / "__init__.py").exists()
    assert (ws / "app" / "cli.py").is_file()

    outcome = apply_scope_outcome(
        "success",
        edit_scope=EDIT_SCOPE_STRICT,
        scope_violations=result.scope_violations,
    )
    assert outcome == OUTCOME_SCOPE_VIOLATION


# P15-032 acceptance: T5–T6


def test_p15_032_t5_gateway_skips_revert_for_files_read(tmp_path, monkeypatch):
    """files_read-listed path changed but not reverted under strict."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())

    _commit_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["a.ts", "b.ts"],
        mutate=lambda w: (
            (w / "a.ts").write_text("edit-a\n", encoding="utf-8"),
            (w / "b.ts").write_text("edit-b\n", encoding="utf-8"),
        ),
    )

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=delegation_id,
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["a.ts", "b.ts"],
        files_edit=["a.ts"],
        files_read=["b.ts"],
    )

    assert "b.ts" not in result.reverted_paths
    assert result.scope_violations == []
    assert (ws / "b.ts").read_text(encoding="utf-8") == "edit-b\n"


def test_p15_032_t6_gateway_reverts_out_of_contract_path(tmp_path, monkeypatch):
    """Path not in files_edit or files_read is reverted under strict."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())

    _commit_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["a.ts", "b.ts"],
        mutate=lambda w: (
            (w / "a.ts").write_text("edit-a\n", encoding="utf-8"),
            (w / "b.ts").write_text("edit-b\n", encoding="utf-8"),
            (w / "c.ts").write_text("bad\n", encoding="utf-8"),
        ),
    )

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id=delegation_id,
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["a.ts", "b.ts", "c.ts"],
        files_edit=["a.ts"],
        files_read=["b.ts"],
    )

    assert "c.ts" in result.scope_violations
    assert "c.ts" in result.reverted_paths
    assert "b.ts" not in result.reverted_paths
    assert not (ws / "c.ts").exists()
    assert (ws / "b.ts").read_text(encoding="utf-8") == "edit-b\n"
