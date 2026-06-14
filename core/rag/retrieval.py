"""Phase 5 retrieval contract — wraps delegation FTS search (P5-001)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.rag.models import SearchHit, WorkspaceFileHit
from core.rag.search import rag_search
from core.rag.workspace_search import workspace_search

CORPUS_DELEGATION = "delegation"
CORPUS_WORKSPACE_FILES = "workspace_files"


@dataclass
class ContextRef:
    kind: str
    id: str
    corpus: str
    sha256: str | None = None
    snippet: str | None = None
    score: float | None = None
    source_line_range: tuple[int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _search_hit_to_context_ref(hit: SearchHit) -> ContextRef:
    return ContextRef(
        kind=CORPUS_DELEGATION,
        id=hit.delegation_id,
        corpus=CORPUS_DELEGATION,
        sha256=None,
        snippet=hit.checkpoint_summary,
        score=hit.score,
        source_line_range=None,
        metadata={
            "spec_path": hit.spec_path,
            "outcome": hit.outcome,
            "timestamp_end": hit.timestamp_end,
            "files_changed": hit.files_changed,
        },
    )


def _workspace_hit_to_context_ref(hit: WorkspaceFileHit) -> ContextRef:
    symbol_preview = hit.symbol_list
    if symbol_preview and len(symbol_preview) > 200:
        symbol_preview = symbol_preview[:197] + "…"
    return ContextRef(
        kind="workspace_file",
        id=hit.path,
        corpus=CORPUS_WORKSPACE_FILES,
        sha256=hit.sha256,
        snippet=hit.llm_summary,
        score=hit.score,
        source_line_range=None,
        metadata={
            "path": hit.path,
            "symbol_list": symbol_preview,
            "indexed_at": hit.indexed_at,
        },
    )


def retrieve(
    workspace: str | Path,
    query: str,
    *,
    corpus: str,
    k: int = 5,
    spec_path_prefix: str | None = None,
    outcome: str | None = None,
) -> list[ContextRef]:
    """Return ranked context references for a query.

    Supports ``corpus="delegation"`` and ``corpus="workspace_files"``.
    Unknown corpora return an empty list (no error).
    """
    if corpus == CORPUS_DELEGATION:
        hits = rag_search(
            workspace,
            query,
            limit=k,
            spec_path_prefix=spec_path_prefix,
            outcome=outcome,
        )
        return [_search_hit_to_context_ref(hit) for hit in hits]

    if corpus == CORPUS_WORKSPACE_FILES:
        hits = workspace_search(workspace, query, limit=k)
        return [_workspace_hit_to_context_ref(hit) for hit in hits]

    return []


def context_refs_to_dict(refs: list[ContextRef]) -> list[dict[str, Any]]:
    """JSON-serializable representation for JSONL / MCP payloads."""
    out: list[dict[str, Any]] = []
    for ref in refs:
        out.append(
            {
                "kind": ref.kind,
                "id": ref.id,
                "corpus": ref.corpus,
                "sha256": ref.sha256,
                "snippet": ref.snippet,
                "score": round(ref.score, 4) if ref.score is not None else None,
                "source_line_range": (
                    list(ref.source_line_range) if ref.source_line_range else None
                ),
                "metadata": ref.metadata,
            }
        )
    return out


def context_refs_to_lean_dict(refs: list[ContextRef]) -> list[dict[str, Any]]:
    """Pointer-only serialization for delegations.jsonl — no body content.

    Bodies (snippet, metadata, source_line_range) stay in delegation_rag.db.
    Use context_refs_to_dict for full serialization (MCP tool responses, search CLI).
    """
    out: list[dict[str, Any]] = []
    for ref in refs:
        out.append({
            "kind": ref.kind,
            "id": ref.id,
            "corpus": ref.corpus,
            "sha256": ref.sha256,
            "score": round(ref.score, 4) if ref.score is not None else None,
        })
    return out
