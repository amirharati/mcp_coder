"""Workspace-file RAG indexing orchestration (P5-003)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.config.rag import workspace_file_rag_enabled
from core.context.file_picker import SCAN_EXTENSIONS
from core.context.symbol_outline import symbol_outline_for_path
from core.engine.workspace_summarizer_llm import run_workspace_file_summarizer_llm
from core.logging.delegation_log import log_stderr
from core.rag.models import WorkspaceFileIndexRow
from core.rag.workspace_db import WorkspaceRagDB
from core.workspace.walk import read_workspace_file, walk_workspace


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_limit(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        val = int(raw)
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def build_searchable_text(
    *,
    path: str,
    llm_summary: str | None,
    symbol_list: str | None,
) -> str:
    parts: list[str] = [path]
    if llm_summary and llm_summary.strip():
        parts.append(llm_summary.strip())
    if symbol_list and symbol_list.strip():
        parts.append(symbol_list.strip())
    return "\n".join(parts)


def eligible_manifest_paths(workspace: Path) -> dict[str, str]:
    """Workspace-relative paths eligible for indexing → content sha256."""
    manifest = walk_workspace(str(workspace.resolve()))
    eligible: dict[str, str] = {}
    for rel, entry in manifest.items():
        if entry.is_binary:
            continue
        if not rel.lower().endswith(SCAN_EXTENSIONS):
            continue
        eligible[rel] = entry.content_hash
    return eligible


@dataclass
class WorkspaceIndexResult:
    indexed: int = 0
    skipped_unchanged: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)


def _read_source_text(workspace: Path, rel_path: str) -> str | None:
    data = read_workspace_file(str(workspace), rel_path)
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _index_one_path(
    *,
    workspace: Path,
    rel_path: str,
    sha256: str,
    db: WorkspaceRagDB,
) -> str | None:
    """Index a single path. Returns error message or None on success."""
    abs_path = workspace / rel_path
    symbol_list = symbol_outline_for_path(abs_path)
    source = _read_source_text(workspace, rel_path)

    llm_summary = ""
    if source is not None:
        result = run_workspace_file_summarizer_llm(
            rel_path=rel_path,
            source=source,
            workspace_path=workspace,
        )
        if result.success:
            llm_summary = result.summary

    row = WorkspaceFileIndexRow(
        path=rel_path,
        sha256=sha256,
        llm_summary=llm_summary or None,
        symbol_list=symbol_list,
        searchable_text=build_searchable_text(
            path=rel_path,
            llm_summary=llm_summary or None,
            symbol_list=symbol_list,
        ),
        indexed_at=_utc_now_iso(),
    )
    db.upsert(row)
    return None


def index_workspace(
    workspace: str | Path,
    *,
    changed_only: bool = False,
    limit: int | None = None,
    paths: list[str] | None = None,
) -> WorkspaceIndexResult:
    """Index eligible workspace files. No-op when workspace_file_rag is disabled."""
    result = WorkspaceIndexResult()
    ws = Path(workspace).resolve()
    if not workspace_file_rag_enabled(ws):
        return result

    effective_limit = limit if limit is not None else _env_limit("MCP_CODER_WORKSPACE_INDEX_LIMIT")
    db = WorkspaceRagDB(ws)
    eligible = eligible_manifest_paths(ws)

    if paths is not None:
        target_paths = [p for p in paths if p in eligible]
    else:
        target_paths = sorted(eligible)

    to_index: list[tuple[str, str]] = []
    for rel in target_paths:
        sha = eligible[rel]
        if changed_only:
            existing = db.get_sha256(rel)
            if existing == sha:
                result.skipped_unchanged += 1
                continue
        to_index.append((rel, sha))
        if effective_limit is not None and len(to_index) >= effective_limit:
            break

    for rel, sha in to_index:
        err = _index_one_path(workspace=ws, rel_path=rel, sha256=sha, db=db)
        if err:
            result.errors.append(err)
        else:
            result.indexed += 1

    if paths is None:
        stale = db.list_paths() - set(eligible)
        if stale:
            result.deleted = db.delete_paths(stale)

    return result


def index_workspace_paths_after_delegate(
    workspace: str | Path,
    files_changed: list[str],
) -> None:
    """Incremental post-delegate hook for changed files only (warn-only)."""
    if not workspace_file_rag_enabled(workspace):
        return
    if not files_changed:
        return
    try:
        index_workspace(workspace, changed_only=True, paths=files_changed)
    except Exception as exc:
        log_stderr(
            f"[mcp-coder] workspace_file_rag incremental index failed: "
            f"{type(exc).__name__}: {exc}"
        )
