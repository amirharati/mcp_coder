"""Builder-path RAG retrieval for delegate pipeline (P5-002, P5-004)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from core.config.rag import builder_history_rag_enabled, workspace_file_hints_enabled
from core.rag.retrieval import CORPUS_DELEGATION, CORPUS_WORKSPACE_FILES, ContextRef, retrieve

_DEFAULT_K = 5


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        val = int(raw)
        return val if val > 0 else default
    except (ValueError, TypeError):
        return default


def resolve_builder_rag_k() -> int:
    """Max delegation hits for builder RAG (env MCP_CODER_BUILDER_RAG_K, default 5)."""
    return _env_int("MCP_CODER_BUILDER_RAG_K", _DEFAULT_K)


def resolve_workspace_file_rag_k() -> int:
    """Max workspace-file hits for builder RAG (env MCP_CODER_WORKSPACE_FILE_RAG_K, default 5)."""
    return _env_int("MCP_CODER_WORKSPACE_FILE_RAG_K", _DEFAULT_K)


def rag_retrieval_should_run(
    workspace: str | Path,
    *,
    builder_on: bool,
    implement_mode: bool,
) -> tuple[bool, str | None]:
    """Whether rag_retrieval phase runs; returns (should_run, skip_detail)."""
    if not implement_mode:
        return False, "not_implement"
    if not builder_on:
        return False, "context_builder_disabled"
    if not builder_history_rag_enabled(workspace) and not workspace_file_hints_enabled(
        workspace
    ):
        return False, "disabled"
    # workspace_file_hints layers on rag_enabled via its own gate; delegation needs rag_enabled
    if builder_history_rag_enabled(workspace):
        from core.config.rag import rag_enabled

        if not rag_enabled(workspace):
            return False, "rag_disabled"
    elif not workspace_file_hints_enabled(workspace):
        return False, "disabled"
    return True, None


def build_delegation_search_query(
    *,
    task: str,
    spec_sections: dict[str, str] | None,
) -> str:
    """Combine task + spec ## Goal text for FTS query."""
    parts: list[str] = []
    task_text = task.strip()
    if task_text:
        parts.append(task_text)
    if spec_sections:
        goal = (spec_sections.get("Goal") or "").strip()
        if goal:
            parts.append(goal)
    query = " ".join(parts)
    # Drop punctuation that breaks SQLite FTS MATCH (e.g. trailing periods).
    query = re.sub(r"[^\w\s-]", " ", query)
    return re.sub(r"\s+", " ", query).strip()


def run_builder_delegation_retrieval(
    workspace: str | Path,
    *,
    task: str,
    spec_sections: dict[str, str] | None,
    k: int | None = None,
) -> list[ContextRef]:
    """Call retrieve() for builder history; non-fatal — return [] on any error."""
    try:
        query = build_delegation_search_query(task=task, spec_sections=spec_sections)
        if not query:
            return []
        limit = k if k is not None else resolve_builder_rag_k()
        return retrieve(workspace, query, corpus=CORPUS_DELEGATION, k=limit)
    except Exception:
        return []


def run_builder_workspace_file_retrieval(
    workspace: str | Path,
    *,
    task: str,
    spec_sections: dict[str, str] | None,
    k: int | None = None,
) -> list[ContextRef]:
    """Call retrieve() for workspace files; non-fatal — return [] on any error."""
    if not workspace_file_hints_enabled(workspace):
        return []
    try:
        query = build_delegation_search_query(task=task, spec_sections=spec_sections)
        if not query:
            return []
        limit = k if k is not None else resolve_workspace_file_rag_k()
        return retrieve(workspace, query, corpus=CORPUS_WORKSPACE_FILES, k=limit)
    except Exception:
        return []


def run_merged_builder_rag_retrieval(
    workspace: str | Path,
    *,
    task: str,
    spec_sections: dict[str, str] | None,
) -> tuple[list[ContextRef], list[ContextRef], list[ContextRef]]:
    """Return (delegation_refs, workspace_file_refs, merged).

    Merge order: delegation refs first, then workspace-file refs (stable audit).
    """
    delegation_refs: list[ContextRef] = []
    workspace_refs: list[ContextRef] = []

    if builder_history_rag_enabled(workspace):
        delegation_refs = run_builder_delegation_retrieval(
            workspace, task=task, spec_sections=spec_sections
        )
    if workspace_file_hints_enabled(workspace):
        workspace_refs = run_builder_workspace_file_retrieval(
            workspace, task=task, spec_sections=spec_sections
        )

    return delegation_refs, workspace_refs, delegation_refs + workspace_refs
