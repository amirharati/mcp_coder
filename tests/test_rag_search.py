"""Delegation RAG search (P3-002-lite)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from core.rag.index import index_delegation_after_delegate
from core.rag.search import rag_search, rag_search_for_mcp
from server.mcp_server import rag_search_tool
def _index(
    ws: Path,
    *,
    did: str,
    summary: str,
    task: str,
    timestamp_end: str,
    outcome: str = "success",
) -> None:
    index_delegation_after_delegate(
        workspace=ws,
        delegation_id=did,
        timestamp_end=timestamp_end,
        task=task,
        delegate_mode="implement",
        outcome=outcome,
        files_changed=["tip_calc/core.py"],
        spec_path="tasks/tip-calc.md",
        checkpoint_summary=summary,
    )


def test_search_keyword_hit(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    _index(
        ws,
        did=str(uuid.uuid4()),
        summary="Introduce calculate_total for CLI",
        task="Wire calculate_total into CLI entrypoint",
        timestamp_end="2026-06-01T00:00:00Z",
    )

    hits = rag_search(ws, "calculate_total CLI")
    assert len(hits) >= 1
    assert any("calculate_total" in (h.checkpoint_summary or "") for h in hits)


def test_recency_newer_ranks_higher(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    old_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())
    _index(
        ws,
        did=old_id,
        summary="calculate_total helper old",
        task="calculate_total old",
        timestamp_end="2020-01-01T00:00:00Z",
    )
    _index(
        ws,
        did=new_id,
        summary="calculate_total helper new",
        task="calculate_total new",
        timestamp_end="2026-06-08T00:00:00Z",
    )

    hits = rag_search(ws, "calculate_total", limit=5)
    assert len(hits) >= 2
    ids = [h.delegation_id for h in hits]
    assert ids.index(new_id) < ids.index(old_id)


def test_mcp_rag_search_json(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    _index(
        ws,
        did=str(uuid.uuid4()),
        summary="tip calculator CLI imports",
        task="Fix CLI imports",
        timestamp_end="2026-06-05T00:00:00Z",
    )

    raw = rag_search_tool(query="tip calculator CLI", limit=5, workspace_path=str(ws))
    payload = json.loads(raw)
    assert payload["found"] is True
    assert payload["query"] == "tip calculator CLI"
    assert len(payload["hits"]) >= 1
    hit = payload["hits"][0]
    assert "delegation_id" in hit
    assert "score" in hit
    assert "checkpoint_summary" in hit


def test_mcp_empty_query_returns_found_false(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    raw = rag_search_tool(query="x", workspace_path=str(ws))
    payload = json.loads(raw)
    assert payload["found"] is False
    assert "error" in payload


def test_disabled_search_returns_message(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".mcp-coder").mkdir()
    (ws / ".mcp-coder" / "config.yaml").write_text("rag_enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    result = rag_search_for_mcp(ws, "anything")
    assert result["found"] is False
    assert "disabled" in result["error"].lower()


def test_spec_path_prefix_filter(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    index_delegation_after_delegate(
        workspace=ws,
        delegation_id=str(uuid.uuid4()),
        timestamp_end="2026-06-01T00:00:00Z",
        task="alpha task",
        delegate_mode="implement",
        outcome="success",
        files_changed=[],
        spec_path="tasks/alpha.md",
        checkpoint_summary="alpha calculate_total",
    )
    index_delegation_after_delegate(
        workspace=ws,
        delegation_id=str(uuid.uuid4()),
        timestamp_end="2026-06-01T00:00:00Z",
        task="beta task",
        delegate_mode="implement",
        outcome="success",
        files_changed=[],
        spec_path="tasks/beta.md",
        checkpoint_summary="beta calculate_total",
    )

    hits = rag_search(ws, "calculate_total", spec_path_prefix="tasks/alpha")
    assert len(hits) == 1
    assert hits[0].spec_path == "tasks/alpha.md"


def test_outcome_filter(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    _index(
        ws,
        did=str(uuid.uuid4()),
        summary="calculate_total ok",
        task="ok",
        timestamp_end="2026-06-01T00:00:00Z",
        outcome="success",
    )
    _index(
        ws,
        did=str(uuid.uuid4()),
        summary="calculate_total fail",
        task="fail",
        timestamp_end="2026-06-02T00:00:00Z",
        outcome="failure",
    )

    hits = rag_search(ws, "calculate_total", outcome="failure")
    assert len(hits) == 1
    assert hits[0].outcome == "failure"
