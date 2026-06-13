"""Workspace-file RAG in picker + builder (P5-004)."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config.rag import workspace_file_hints_enabled, workspace_file_rag_enabled
from core.context.builder_history import BuilderHistoryContext
from core.context.builder_prompt import build_builder_llm_prompt
from core.context.file_picker import (
    SOURCE_WORKSPACE_RAG,
    CandidateFilesResult,
    pick_candidate_files,
)
from core.context.inspect import inspect_context_package
from core.engine.workspace_summarizer_llm import WorkspaceSummaryResult
from core.rag.builder_retrieval import run_merged_builder_rag_retrieval
from core.rag.index import index_delegation_after_delegate
from core.rag.retrieval import CORPUS_WORKSPACE_FILES, ContextRef, context_refs_to_dict
from core.rag.workspace_indexer import index_workspace
from core.specs.delegation_policies import DelegationPolicies


def _write_py(ws: Path, rel: str, body: str) -> None:
    path = ws / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _mock_summarizer(rel_path: str, source: str, workspace_path: Path | str):
    summaries = {
        "core/host/cursor.py": (
            "Handles Cursor host transcript resolution and session metadata."
        ),
        "core/logging/delegation_log.py": (
            "Delegation audit trail JSONL logging for delegate_to_agent."
        ),
    }
    return WorkspaceSummaryResult(
        success=True,
        summary=summaries.get(rel_path, f"Summary for {rel_path}."),
        model="mock",
    )


@pytest.fixture
def rag_ws(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = ws / ".mcp-coder"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        "rag_enabled: true\n"
        "workspace_file_rag: true\n"
        "workspace_file_hints: true\n"
        "builder_history_rag: true\n"
        "context_builder: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    return ws


def _discover_policies(*, files_edit: list[str], files_read: list[str] | None = None):
    read = files_read or []
    return DelegationPolicies(
        files_edit=files_edit,
        files_read=read,
        all_paths=sorted(set(files_edit) | set(read)),
        edit_scope="discover",
        allow_create=True,
        untracked_policy="materialize",
    )


def test_workspace_file_hints_default_on_when_rag_layers(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_WORKSPACE_FILE_HINTS", raising=False)
    assert workspace_file_hints_enabled(tmp_path) is True

    cfg = tmp_path / ".mcp-coder"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        "rag_enabled: false\nworkspace_file_rag: true\nworkspace_file_hints: true\n",
        encoding="utf-8",
    )
    assert workspace_file_rag_enabled(tmp_path) is True
    assert workspace_file_hints_enabled(tmp_path) is False


def test_picker_merges_workspace_rag_paths(rag_ws):
    ws = rag_ws
    policies = _discover_policies(files_edit=["pkg/auth.py"])
    result = pick_candidate_files(
        workspace=ws,
        task="refactor auth module",
        spec_text="## Goal\nRefactor auth module",
        policies=policies,
        target_files=[],
        workspace_rag_paths=["core/host/cursor.py"],
    )
    assert "core/host/cursor.py" in result.discovered_read
    assert result.path_sources.get("core/host/cursor.py") == SOURCE_WORKSPACE_RAG
    assert "core/host/cursor.py" not in result.edit_paths
    assert "core/host/cursor.py" not in result.suggested_edit_paths


def test_picker_workspace_rag_not_in_edit_paths(rag_ws):
    ws = rag_ws
    policies = _discover_policies(files_edit=["other/module.py"])
    result = pick_candidate_files(
        workspace=ws,
        task="t",
        spec_text=None,
        policies=policies,
        target_files=[],
        workspace_rag_paths=["core/host/cursor.py"],
    )
    assert "core/host/cursor.py" not in result.edit_paths


def test_builder_prompt_related_files_section(rag_ws):
    file_refs = [
        ContextRef(
            kind="workspace_file",
            id="core/host/cursor.py",
            corpus=CORPUS_WORKSPACE_FILES,
            snippet="Handles Cursor host transcript resolution",
            score=1.2,
            metadata={"path": "core/host/cursor.py"},
        )
    ]
    prompt = build_builder_llm_prompt(
        mechanical_brief="## Paths\n- pkg/auth.py",
        picker_result=None,
        package_metadata={},
        history=BuilderHistoryContext(),
        host_transcript=None,
        context_summary="",
        task="refactor auth module",
        rag_refs=file_refs,
    )
    assert "## Related files (by summary)" in prompt
    assert "core/host/cursor.py" in prompt
    assert "Cursor host transcript" in prompt
    assert "## Relevant prior work" not in prompt


def test_merged_context_refs_both_kinds(rag_ws):
    ws = rag_ws
    _write_py(
        ws,
        "core/host/cursor.py",
        "def resolve_host():\n    pass\n",
    )
    index_delegation_after_delegate(
        workspace=ws,
        delegation_id=str(uuid.uuid4()),
        timestamp_end="2026-06-01T00:00:00Z",
        task="auth session token",
        delegate_mode="implement",
        outcome="success",
        files_changed=["core/host/cursor.py"],
        spec_path="tasks/auth-a.md",
        checkpoint_summary="Token refresh in session module",
    )
    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        index_workspace(ws, paths=["core/host/cursor.py"])

    delegation_refs, workspace_refs, merged = run_merged_builder_rag_retrieval(
        ws,
        task="refactor auth module session",
        spec_sections={"Goal": "Refactor auth module for Cursor host"},
    )
    assert len(delegation_refs) >= 1
    assert len(workspace_refs) >= 1
    assert len(merged) == len(delegation_refs) + len(workspace_refs)
    kinds = {r.kind for r in merged}
    assert kinds == {"delegation", "workspace_file"}

    payload = context_refs_to_dict(merged)
    assert any(r["kind"] == "delegation" for r in payload)
    assert any(r["kind"] == "workspace_file" for r in payload)


def test_hints_off_no_workspace_paths_in_picker(rag_ws):
    ws = rag_ws
    (ws / ".mcp-coder" / "config.yaml").write_text(
        "rag_enabled: true\nworkspace_file_rag: true\nworkspace_file_hints: false\n",
        encoding="utf-8",
    )
    assert workspace_file_hints_enabled(ws) is False
    policies = _discover_policies(files_edit=["pkg/a.py"])
    result = pick_candidate_files(
        workspace=ws,
        task="t",
        spec_text=None,
        policies=policies,
        target_files=[],
        workspace_rag_paths=None,
    )
    assert not any(
        src == SOURCE_WORKSPACE_RAG for src in result.path_sources.values()
    )


def test_inspect_merged_rag_retrieval_hits(rag_ws):
    ws = rag_ws
    _write_py(
        ws,
        "core/host/cursor.py",
        "def resolve_host():\n    pass\n",
    )
    spec_path = ws / ".mcp-coder" / "specs" / "tasks" / "auth-step.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        """---
spec_id: auth-step
files_edit:
  - pkg/auth.py
edit_scope: discover
---

## Goal

Refactor auth module for Cursor host integration.

## Files

### Edit
- `pkg/auth.py`
""",
        encoding="utf-8",
    )
    (ws / "pkg").mkdir(exist_ok=True)
    (ws / "pkg" / "auth.py").write_text("# auth\n", encoding="utf-8")

    with patch(
        "core.rag.workspace_indexer.run_workspace_file_summarizer_llm",
        side_effect=_mock_summarizer,
    ):
        index_workspace(ws, paths=["core/host/cursor.py"])

    result = inspect_context_package(
        workspace=ws,
        task="refactor auth module Cursor host",
        target_files=["pkg/auth.py"],
        spec_path="tasks/auth-step.md",
    )
    assert result["ok"] is True
    rag_phase = result["helper_phases"]["rag_retrieval"]
    assert rag_phase["ran"] is True
    assert rag_phase["hit_count"] >= 1
    assert rag_phase.get("file_hits", 0) >= 1
    assert len(result["context_refs"]) >= 1


def test_builder_dedupes_file_refs_in_picker(rag_ws):
    picker = CandidateFilesResult(
        ranked_paths=["core/host/cursor.py", "pkg/auth.py"],
        edit_paths=["pkg/auth.py"],
        read_paths=["core/host/cursor.py", "pkg/auth.py"],
    )
    file_refs = [
        ContextRef(
            kind="workspace_file",
            id="core/host/cursor.py",
            corpus=CORPUS_WORKSPACE_FILES,
            snippet="duplicate",
            score=1.0,
        ),
        ContextRef(
            kind="workspace_file",
            id="core/other.py",
            corpus=CORPUS_WORKSPACE_FILES,
            snippet="unique file",
            score=0.9,
        ),
    ]
    prompt = build_builder_llm_prompt(
        mechanical_brief="brief",
        picker_result=picker,
        package_metadata={},
        history=BuilderHistoryContext(),
        host_transcript=None,
        context_summary="",
        task="t",
        rag_refs=file_refs,
    )
    assert "core/other.py" in prompt
    assert "duplicate" not in prompt
