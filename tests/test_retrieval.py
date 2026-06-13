"""Phase 5 retrieval contract (P5-001)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from core.rag.index import index_delegation_after_delegate
from core.rag.retrieval import (
    CORPUS_DELEGATION,
    context_refs_to_dict,
    retrieve,
)


def _index(
    ws: Path,
    *,
    did: str,
    summary: str,
    task: str,
    timestamp_end: str,
    outcome: str = "success",
    spec_path: str = "tasks/tip-calc.md",
) -> None:
    index_delegation_after_delegate(
        workspace=ws,
        delegation_id=did,
        timestamp_end=timestamp_end,
        task=task,
        delegate_mode="implement",
        outcome=outcome,
        files_changed=["tip_calc/core.py"],
        spec_path=spec_path,
        checkpoint_summary=summary,
    )


def test_retrieve_delegation_corpus_returns_context_refs(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    did = str(uuid.uuid4())
    _index(
        ws,
        did=did,
        summary="Introduce calculate_total for CLI",
        task="Wire calculate_total into CLI entrypoint",
        timestamp_end="2026-06-01T00:00:00Z",
    )

    refs = retrieve(ws, "calculate_total CLI", corpus=CORPUS_DELEGATION, k=5)
    assert len(refs) >= 1
    ref = refs[0]
    assert ref.kind == CORPUS_DELEGATION
    assert ref.corpus == CORPUS_DELEGATION
    assert ref.id == did
    assert ref.score is not None
    assert ref.score > 0
    assert ref.snippet is not None
    assert "calculate_total" in ref.snippet
    assert ref.metadata["spec_path"] == "tasks/tip-calc.md"
    assert ref.metadata["outcome"] == "success"
    assert ref.metadata["files_changed"] == ["tip_calc/core.py"]


def test_retrieve_unknown_corpus_returns_empty(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    _index(
        ws,
        did=str(uuid.uuid4()),
        summary="calculate_total helper",
        task="calculate_total task",
        timestamp_end="2026-06-01T00:00:00Z",
    )

    assert retrieve(ws, "calculate_total", corpus="workspace_files", k=5) == []


def test_retrieve_disabled_rag_returns_empty(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".mcp-coder").mkdir()
    (ws / ".mcp-coder" / "config.yaml").write_text("rag_enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    _index(
        ws,
        did=str(uuid.uuid4()),
        summary="calculate_total helper",
        task="calculate_total task",
        timestamp_end="2026-06-01T00:00:00Z",
    )

    assert retrieve(ws, "calculate_total", corpus=CORPUS_DELEGATION, k=5) == []


def test_retrieve_passes_filters(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    alpha_id = str(uuid.uuid4())
    beta_id = str(uuid.uuid4())
    _index(
        ws,
        did=alpha_id,
        summary="calculate_total alpha",
        task="alpha",
        timestamp_end="2026-06-01T00:00:00Z",
        spec_path="tasks/alpha.md",
        outcome="success",
    )
    _index(
        ws,
        did=beta_id,
        summary="calculate_total beta",
        task="beta",
        timestamp_end="2026-06-02T00:00:00Z",
        spec_path="tasks/beta.md",
        outcome="failure",
    )

    refs = retrieve(
        ws,
        "calculate_total",
        corpus=CORPUS_DELEGATION,
        k=5,
        spec_path_prefix="tasks/alpha",
        outcome="success",
    )
    assert len(refs) == 1
    assert refs[0].id == alpha_id


def test_context_refs_to_dict_json_round_trip(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    did = str(uuid.uuid4())
    _index(
        ws,
        did=did,
        summary="calculate_total round trip",
        task="round trip",
        timestamp_end="2026-06-01T00:00:00Z",
    )

    refs = retrieve(ws, "calculate_total", corpus=CORPUS_DELEGATION, k=5)
    payload = context_refs_to_dict(refs)
    line = json.dumps(payload)
    restored = json.loads(line)
    assert isinstance(restored, list)
    assert restored[0]["kind"] == CORPUS_DELEGATION
    assert restored[0]["id"] == did
    assert restored[0]["source_line_range"] is None
    assert "score" in restored[0]
