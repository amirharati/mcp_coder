"""Builder delegation RAG integration (P5-002)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from core.cli.search import main_search
from core.config.rag import builder_history_rag_enabled, rag_enabled
from core.context.builder_history import BuilderHistoryContext
from core.context.builder_prompt import (
    build_builder_llm_prompt,
    dedupe_rag_refs_against_history,
)
from core.context.inspect import inspect_context_package
from core.pipeline.phases import PipelineRecorder
from core.rag.builder_retrieval import (
    build_delegation_search_query,
    run_builder_delegation_retrieval,
)
from core.rag.index import index_delegation_after_delegate
from core.rag.retrieval import CORPUS_DELEGATION, ContextRef, retrieve
from core.rag.search import rag_search_for_mcp


def _index(
    ws: Path,
    *,
    did: str,
    summary: str,
    task: str,
    timestamp_end: str,
    spec_path: str = "tasks/spec-a.md",
    outcome: str = "success",
) -> None:
    index_delegation_after_delegate(
        workspace=ws,
        delegation_id=did,
        timestamp_end=timestamp_end,
        task=task,
        delegate_mode="implement",
        outcome=outcome,
        files_changed=["pkg/session.py"],
        spec_path=spec_path,
        checkpoint_summary=summary,
    )


SPEC_B_GOAL = "Wire OAuth callback handling for login flow."


@pytest.fixture
def rag_workspace(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = ws / ".mcp-coder"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        "rag_enabled: true\nbuilder_history_rag: true\ncontext_builder: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    return ws


def test_builder_history_rag_default_true(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_BUILDER_HISTORY_RAG", raising=False)
    assert builder_history_rag_enabled(tmp_path) is True


def test_builder_history_rag_opt_out_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_BUILDER_HISTORY_RAG", raising=False)
    cfg = tmp_path / ".mcp-coder"
    cfg.mkdir()
    (cfg / "config.yaml").write_text("builder_history_rag: false\n", encoding="utf-8")
    assert builder_history_rag_enabled(tmp_path) is False


def test_builder_history_rag_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_BUILDER_HISTORY_RAG", "1")
    assert builder_history_rag_enabled(tmp_path) is True


def test_build_delegation_search_query_combines_task_and_goal():
    query = build_delegation_search_query(
        task="Fix token refresh bug",
        spec_sections={"Goal": SPEC_B_GOAL},
    )
    assert "token refresh" in query.lower()
    assert "OAuth" in query


def test_cross_spec_retrieval_in_builder_prompt(rag_workspace):
    ws = rag_workspace
    spec_a_id = str(uuid.uuid4())
    _index(
        ws,
        did=spec_a_id,
        summary="Token refresh implemented in session.py with sliding expiry",
        task="Add token refresh to session",
        timestamp_end="2026-06-01T00:00:00Z",
        spec_path="tasks/auth-01.md",
    )

    refs = run_builder_delegation_retrieval(
        ws,
        task="Implement token refresh for OAuth session handling",
        spec_sections={"Goal": SPEC_B_GOAL},
    )
    assert len(refs) >= 1
    assert any("token refresh" in (r.snippet or "").lower() for r in refs)

    prompt = build_builder_llm_prompt(
        mechanical_brief="## Paths\n- pkg/oauth.py",
        picker_result=None,
        package_metadata={},
        history=BuilderHistoryContext(),
        host_transcript=None,
        context_summary="",
        task="Implement token refresh for OAuth session handling",
        rag_refs=refs,
    )
    assert "## Relevant prior work" in prompt
    assert "session.py" in prompt
    assert "tasks/auth-01.md" in prompt


def test_dedupe_rag_refs_against_history():
    did = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    history = BuilderHistoryContext(
        same_spec=[
            {
                "delegation_id": did,
                "outcome": "success",
                "checkpoint_summary": "already in history",
                "created_count": 1,
                "modified_count": 0,
                "delegate_mode": "implement",
                "timestamp_end": "2026-06-01T00:00:00Z",
            }
        ],
        project_recent=[],
    )
    rag_refs = [
        ContextRef(
            kind=CORPUS_DELEGATION,
            id=did,
            corpus=CORPUS_DELEGATION,
            snippet="duplicate from RAG",
            score=2.0,
            metadata={"spec_path": "tasks/a.md", "outcome": "success"},
        ),
        ContextRef(
            kind=CORPUS_DELEGATION,
            id="bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee",
            corpus=CORPUS_DELEGATION,
            snippet="unique RAG hit",
            score=1.5,
            metadata={"spec_path": "tasks/b.md", "outcome": "success"},
        ),
    ]
    deduped = dedupe_rag_refs_against_history(rag_refs, history)
    assert len(deduped) == 1
    assert deduped[0].snippet == "unique RAG hit"

    prompt = build_builder_llm_prompt(
        mechanical_brief="brief",
        picker_result=None,
        package_metadata={},
        history=history,
        host_transcript=None,
        context_summary="",
        task="task",
        rag_refs=rag_refs,
    )
    assert "duplicate from RAG" not in prompt
    assert "unique RAG hit" in prompt
    assert "## Prior delegations" in prompt


def test_toggle_off_no_relevant_prior_work_section(rag_workspace):
    ws = rag_workspace
    (ws / ".mcp-coder" / "config.yaml").write_text(
        "rag_enabled: true\nbuilder_history_rag: false\n",
        encoding="utf-8",
    )
    assert builder_history_rag_enabled(ws) is False

    prompt = build_builder_llm_prompt(
        mechanical_brief="brief",
        picker_result=None,
        package_metadata={},
        history=BuilderHistoryContext(),
        host_transcript=None,
        context_summary="",
        task="token refresh",
        rag_refs=None,
    )
    assert "## Relevant prior work" not in prompt


def test_pipeline_recorder_rag_retrieval_phase():
    recorder = PipelineRecorder()
    recorder.start("rag_retrieval")
    recorder.end("rag_retrieval", status="ok", detail="2 hits")
    phases = recorder.to_list()
    assert any(p["phase"] == "rag_retrieval" and p["status"] == "ok" for p in phases)
    assert phases[-1]["detail"] == "2 hits"


def test_cli_search_delegations_plain_format(rag_workspace, monkeypatch, capsys):
    ws = rag_workspace
    monkeypatch.chdir(ws)
    _index(
        ws,
        did=str(uuid.uuid4()),
        summary="Token refresh implemented in session.py",
        task="token refresh",
        timestamp_end="2026-06-01T00:00:00Z",
        spec_path="tasks/auth-01.md",
        outcome="success",
    )
    rc = main_search(
        ["delegations", "token refresh session", "--workspace", str(ws), "--format", "plain"]
    )
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("Prior delegation tasks/auth-01.md (success):")
    assert "session.py" in out
    assert "{" not in out


def test_cli_search_delegations_json_matches_mcp(rag_workspace, monkeypatch, capsys):
    ws = rag_workspace
    monkeypatch.chdir(ws)
    did = str(uuid.uuid4())
    _index(
        ws,
        did=did,
        summary="OAuth callback URL mismatch fixed in routes",
        task="oauth callback",
        timestamp_end="2026-06-02T00:00:00Z",
        spec_path="tasks/other.md",
        outcome="partial",
    )

    mcp_payload = rag_search_for_mcp(ws, "oauth callback", limit=5)
    assert mcp_payload["found"] is True

    rc = main_search(["delegations", "oauth callback", "--workspace", str(ws), "--json"])
    assert rc == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["found"] is True
    mcp_ids = [h["delegation_id"] for h in mcp_payload["hits"]]
    cli_ids = [h["delegation_id"] for h in cli_payload["hits"]]
    assert mcp_ids == cli_ids
    assert mcp_ids[0] == did


def test_inspect_context_includes_rag_refs(rag_workspace):
    ws = rag_workspace
    _index(
        ws,
        did=str(uuid.uuid4()),
        summary="Token refresh implemented in session.py",
        task="token refresh",
        timestamp_end="2026-06-01T00:00:00Z",
        spec_path="tasks/auth-01.md",
    )
    spec_path = ws / ".mcp-coder" / "specs" / "tasks" / "oauth-step.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        """---
spec_id: oauth-step
files_edit:
  - pkg/oauth.py
edit_scope: discover
---

## Goal

Implement token refresh for OAuth session handling.

## Files

### Edit
- `pkg/oauth.py`
""",
        encoding="utf-8",
    )
    (ws / "pkg").mkdir(exist_ok=True)
    (ws / "pkg" / "oauth.py").write_text("# oauth\n", encoding="utf-8")

    result = inspect_context_package(
        workspace=ws,
        task="Implement token refresh for OAuth session handling",
        target_files=["pkg/oauth.py"],
        spec_path="tasks/oauth-step.md",
        run_builder_llm=False,
    )
    assert result["ok"] is True
    assert result["helper_phases"]["rag_retrieval"]["ran"] is True
    assert result["helper_phases"]["rag_retrieval"]["hit_count"] >= 1
    assert len(result["context_refs"]) >= 1


def test_retrieve_respects_rag_enabled_false(tmp_path, monkeypatch):
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
        task="calculate_total",
        timestamp_end="2026-06-01T00:00:00Z",
    )
    assert rag_enabled(ws) is False
    assert retrieve(ws, "calculate_total", corpus=CORPUS_DELEGATION, k=5) == []
