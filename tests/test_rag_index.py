"""Delegation RAG index (P3-002-lite)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

from core.config.rag import rag_enabled
from core.engine.base import ExecutionResult
from core.rag.db import DelegationRagDB
from core.rag.index import (
    backfill_from_history,
    build_searchable_text,
    index_delegation_after_delegate,
    make_task_preview,
)
from core.rag.search import rag_search_for_mcp
from core.storage.paths import delegation_rag_db_path, project_key
from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution
from server.mcp_server import delegate_to_agent


def _write_spec(ws: Path, rel: str, body: str) -> None:
    path = ws / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _seed_snapshot(
    ws: Path,
    home: Path,
    monkeypatch,
    *,
    summary: str = "calculate_total CLI helper",
    spec_rel: str = "tasks/tip-calc.md",
    delegation_id: str | None = None,
    timestamp_end: str = "2026-06-01T00:00:00Z",
) -> str:
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    _write_spec(
        ws,
        f".mcp-coder/specs/{spec_rel}",
        f"---\nspec_id: tip\n---\n\n## Goal\n\n{summary}\n",
    )
    did = delegation_id or str(uuid.uuid4())
    (ws / "core.py").write_text("v1\n", encoding="utf-8")
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=did,
        mcp_session_id="sess-rag",
        timestamp_start="2026-06-01T00:00:00Z",
        spec_path=spec_rel,
        contract_paths=["core.py"],
    )
    (ws / "core.py").write_text("v1\nv2\n", encoding="utf-8")
    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["core.py"],
        edit_paths_rel=["core.py"],
        before_git=None,
        before_mtimes=None,
        delegation_id=did,
    )
    db = WorkspaceHistoryDB(ws)
    with db._connect() as conn:
        conn.execute(
            "UPDATE snapshots SET timestamp_end = ? WHERE delegation_id = ?",
            (timestamp_end, did),
        )
        conn.commit()
    db.finalize_checkpoint_metadata(
        delegation_id=did,
        checkpoint_summary=summary,
        delegate_mode="implement",
        outcome="success",
        model="test",
        duration_ms=10,
        tokens_total=50,
        error_class=None,
        delta_created=0,
        delta_modified=1,
        delta_deleted=0,
        spec_report_path="reports/tip-calc.md",
    )
    return did


def test_schema_init_creates_fts5(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    db = DelegationRagDB(ws)
    db._connect().close()

    conn = sqlite3.connect(str(delegation_rag_db_path(ws)))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"
        )
    }
    conn.close()
    assert "delegation_index" in tables
    assert "delegation_fts" in tables
    assert "delegation_index_ai" in tables


def test_upsert_replaces_same_delegation_id(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    did = "fixed-id-1234"
    index_delegation_after_delegate(
        workspace=ws,
        delegation_id=did,
        timestamp_end="2026-06-01T00:00:00Z",
        task="first task",
        delegate_mode="implement",
        outcome="success",
        files_changed=["a.py"],
        checkpoint_summary="first summary",
    )
    index_delegation_after_delegate(
        workspace=ws,
        delegation_id=did,
        timestamp_end="2026-06-02T00:00:00Z",
        task="updated calculate_total CLI",
        delegate_mode="implement",
        outcome="failure",
        files_changed=["b.py"],
        checkpoint_summary="updated summary",
    )

    conn = sqlite3.connect(str(delegation_rag_db_path(ws)))
    row = conn.execute(
        "SELECT checkpoint_summary, searchable_text FROM delegation_index WHERE delegation_id = ?",
        (did,),
    ).fetchone()
    conn.close()
    assert row[0] == "updated summary"
    assert "calculate_total" in row[1]
    assert "b.py" in row[1]


def test_build_searchable_text_skips_empty():
    text = build_searchable_text(
        checkpoint_summary="CLI",
        task_preview=None,
        spec_path="tasks/x.md",
        files_changed=["a.py", "b.py"],
        outcome="success",
        delegate_mode="implement",
    )
    assert "CLI" in text
    assert "a.py b.py" in text
    assert "implement" in text


def test_disabled_config_skips_upsert(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".mcp-coder").mkdir()
    (ws / ".mcp-coder" / "config.yaml").write_text("rag_enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    assert rag_enabled(ws) is False
    index_delegation_after_delegate(
        workspace=ws,
        delegation_id="x",
        timestamp_end="2026-06-01T00:00:00Z",
        task="task",
        delegate_mode="implement",
        outcome="success",
        files_changed=[],
    )
    assert not delegation_rag_db_path(ws).is_file()


def test_backfill_from_history(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed_snapshot(ws, home, monkeypatch)

    count = backfill_from_history(ws)
    assert count == 1
    assert DelegationRagDB(ws).has_delegation(did)

    # Idempotent
    assert backfill_from_history(ws) == 0


def test_backfill_cli(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed_snapshot(ws, home, monkeypatch, summary="CLI backfill test")

    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "main.py", "rag", "index", "--workspace", str(ws)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert DelegationRagDB(ws).row_count() >= 1


def test_workspace_isolation_two_db_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    index_delegation_after_delegate(
        workspace=ws1,
        delegation_id="only-ws1",
        timestamp_end="2026-06-01T00:00:00Z",
        task="ws1 task",
        delegate_mode="implement",
        outcome="success",
        files_changed=[],
        checkpoint_summary="ws1 only",
    )

    assert project_key(ws1) != project_key(ws2)
    assert delegation_rag_db_path(ws1) != delegation_rag_db_path(ws2)
    assert DelegationRagDB(ws1).has_delegation("only-ws1")
    assert not DelegationRagDB(ws2).has_delegation("only-ws1")


def test_post_delegate_hook_indexes_row(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    fake_result = ExecutionResult(
        success=True,
        output="done",
        files_changed=["hello.py"],
        model="gpt-4o",
        tokens={"source": "unavailable"},
    )
    mock_engine = type(
        "MockEngine",
        (),
        {"model_name": "gpt-4o", "backend_id": "aider", "run": lambda *a, **k: fake_result},
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="calculate_total for tip calculator CLI",
            target_files=["hello.py"],
            context_summary="ctx",
            backend="aider",
        )

    payload = json.loads(raw)
    assert payload["success"] is True

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    did = record["delegation_id"]
    assert DelegationRagDB(workspace).has_delegation(did)


def test_index_failure_does_not_fail_delegate(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)

    fake_result = ExecutionResult(
        success=True,
        output="done",
        files_changed=[],
        model="gpt-4o",
        tokens={"source": "unavailable"},
    )
    mock_engine = type(
        "MockEngine",
        (),
        {"model_name": "gpt-4o", "backend_id": "aider", "run": lambda *a, **k: fake_result},
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        with patch(
            "core.rag.index.DelegationRagDB.upsert",
            side_effect=RuntimeError("rag boom"),
        ):
            raw = delegate_to_agent(
                task="should still succeed",
                target_files=["a.py"],
                context_summary="ctx",
                backend="aider",
            )

    assert json.loads(raw)["success"] is True


def test_make_task_preview_redacts_and_truncates():
    long_task = "x" * 600 + " sk-abcdefghijklmnopqrstuvwxyz123456"
    preview = make_task_preview(long_task)
    assert len(preview) <= 500
    assert "sk-***" in preview or "sk-" not in preview
