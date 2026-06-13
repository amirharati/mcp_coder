"""Workspace-file RAG corpus (P5-003)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.cli.index_workspace import main_index_workspace
from core.cli.search import main_search
from core.config.rag import workspace_file_rag_enabled
from core.engine.workspace_summarizer_llm import WorkspaceSummaryResult
from core.rag.retrieval import CORPUS_WORKSPACE_FILES, retrieve
from core.rag.workspace_db import WorkspaceRagDB
from core.rag.workspace_indexer import index_workspace
from core.rag.workspace_search import workspace_search, workspace_search_for_mcp
from core.storage.paths import delegation_rag_db_path, workspace_rag_db_path


def _mock_summarizer(rel_path: str, source: str, workspace_path: Path | str):
    summaries = {
        "core/logging/delegation_log.py": (
            "Delegation audit trail JSONL logging for delegate_to_agent records."
        ),
        "core/rag/retrieval.py": (
            "Phase 5 retrieval contract wrapping delegation and workspace FTS search."
        ),
    }
    summary = summaries.get(rel_path, f"Module at {rel_path}.")
    return WorkspaceSummaryResult(success=True, summary=summary, model="mock-model")


@pytest.fixture
def ws_workspace(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = ws / ".mcp-coder"
    cfg.mkdir()
    (cfg / "config.yaml").write_text("workspace_file_rag: true\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    return ws


def _write_py(ws: Path, rel: str, body: str) -> None:
    path = ws / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_workspace_rag_db_path_sibling_to_delegation(ws_workspace):
    ws = ws_workspace
    assert workspace_rag_db_path(ws).parent == delegation_rag_db_path(ws).parent
    assert workspace_rag_db_path(ws).name == "workspace_rag.db"


def test_workspace_file_rag_default_true(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_WORKSPACE_FILE_RAG", raising=False)
    assert workspace_file_rag_enabled(tmp_path) is True


def test_index_and_search_by_summary_keyword(ws_workspace):
    ws = ws_workspace
    _write_py(
        ws,
        "core/logging/delegation_log.py",
        'def build_delegation_record():\n    """JSONL audit trail."""\n    pass\n',
    )
    _write_py(ws, "core/other.py", "x = 1\n")

    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        result = index_workspace(ws, limit=10)

    assert result.indexed >= 1
    db = WorkspaceRagDB(ws)
    assert db.row_count() >= 1

    hits = workspace_search(ws, "delegation audit trail", limit=5)
    assert len(hits) >= 1
    paths = [h.path for h in hits]
    assert "core/logging/delegation_log.py" in paths


def test_changed_only_reindexes_on_sha_change(ws_workspace):
    ws = ws_workspace
    rel = "pkg/module.py"
    _write_py(ws, rel, "def alpha():\n    return 1\n")

    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        first = index_workspace(ws, paths=[rel])
    assert first.indexed == 1

    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        second = index_workspace(ws, changed_only=True, paths=[rel])
    assert second.indexed == 0
    assert second.skipped_unchanged == 1

    _write_py(ws, rel, "def alpha():\n    return 2\n")

    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        third = index_workspace(ws, changed_only=True, paths=[rel])
    assert third.indexed == 1
    assert third.skipped_unchanged == 0


def test_retrieve_workspace_files_context_ref_shape(ws_workspace):
    ws = ws_workspace
    _write_py(
        ws,
        "core/logging/delegation_log.py",
        "def build_delegation_record():\n    pass\n",
    )
    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        index_workspace(ws, paths=["core/logging/delegation_log.py"])

    refs = retrieve(ws, "delegation audit", corpus=CORPUS_WORKSPACE_FILES, k=5)
    assert len(refs) >= 1
    ref = refs[0]
    assert ref.kind == "workspace_file"
    assert ref.corpus == CORPUS_WORKSPACE_FILES
    assert ref.id == "core/logging/delegation_log.py"
    assert ref.sha256
    assert ref.snippet


def test_disabled_toggle_no_index_or_search(ws_workspace):
    ws = ws_workspace
    (ws / ".mcp-coder" / "config.yaml").write_text(
        "workspace_file_rag: false\n", encoding="utf-8"
    )
    _write_py(ws, "core/logging/delegation_log.py", "def f(): pass\n")

    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        result = index_workspace(ws)
    assert result.indexed == 0
    assert workspace_search(ws, "delegation") == []
    mcp = workspace_search_for_mcp(ws, "delegation")
    assert mcp["found"] is False


def test_cli_search_files_plain(ws_workspace, monkeypatch, capsys):
    ws = ws_workspace
    _write_py(
        ws,
        "core/logging/delegation_log.py",
        "def build_delegation_record():\n    pass\n",
    )
    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        index_workspace(ws, paths=["core/logging/delegation_log.py"])

    rc = main_search(
        [
            "files",
            "delegation audit trail",
            "--workspace",
            str(ws),
            "--format",
            "plain",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "core/logging/delegation_log.py" in out
    assert "delegation" in out.lower()
    assert "{" not in out


def test_cli_json_matches_mcp_ranking(ws_workspace, monkeypatch, capsys):
    ws = ws_workspace
    _write_py(
        ws,
        "core/logging/delegation_log.py",
        "def build_delegation_record():\n    pass\n",
    )
    _write_py(ws, "core/rag/retrieval.py", "def retrieve():\n    pass\n")
    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        index_workspace(ws, limit=10)

    mcp_payload = workspace_search_for_mcp(ws, "retrieval contract", limit=5)
    assert mcp_payload["found"] is True

    rc = main_search(["files", "retrieval contract", "--workspace", str(ws), "--json"])
    assert rc == 0
    cli_payload = json.loads(capsys.readouterr().out)
    mcp_ids = [h["path"] for h in mcp_payload["hits"]]
    cli_ids = [h["path"] for h in cli_payload["hits"]]
    assert mcp_ids == cli_ids


def test_index_workspace_cli_json(ws_workspace, capsys):
    ws = ws_workspace
    _write_py(ws, "pkg/a.py", "def a(): pass\n")
    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        rc = main_index_workspace(["--workspace", str(ws), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["indexed"] >= 1


def test_summarizer_failure_still_indexes_symbols(ws_workspace):
    ws = ws_workspace
    _write_py(
        ws,
        "core/token_util.py",
        "def refresh_token():\n    return 'ok'\n",
    )

    def _fail(**kwargs):
        return WorkspaceSummaryResult(
            success=False, summary="", model="mock", error="llm down"
        )

    with patch("core.rag.workspace_indexer.run_workspace_file_summarizer_llm", side_effect=_fail):
        result = index_workspace(ws, paths=["core/token_util.py"])

    assert result.indexed == 1
    hits = workspace_search(ws, "refresh_token", limit=5)
    assert any(h.path == "core/token_util.py" for h in hits)
