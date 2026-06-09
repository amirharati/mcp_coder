from __future__ import annotations

import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config.rag import rag_enabled
from core.rag.db import DelegationRagDB
from core.rag.models import SearchHit
from core.storage.paths import delegation_rag_db_path

_MIN_QUERY_LEN = 2
_DEFAULT_LIMIT = 5
_MAX_LIMIT = 20


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    text = ts.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _recency_weight(timestamp_end: str | None) -> float:
    """Boost newer delegations: 1.0 + 0.1 * exp(-days_ago / 30)."""
    dt = _parse_iso(timestamp_end)
    if dt is None:
        return 1.0
    now = datetime.now(timezone.utc)
    days_ago = max(0.0, (now - dt).total_seconds() / 86400.0)
    return 1.0 + 0.1 * math.exp(-days_ago / 30.0)


def _fts_match_query(raw: str) -> str:
    terms = [t for t in re.split(r"\s+", raw.strip()) if len(t) >= 2]
    if not terms:
        return ""
    cleaned: list[str] = []
    for term in terms:
        safe = re.sub(r'["*()\-:]', "", term)
        if safe:
            cleaned.append(safe)
    return " OR ".join(cleaned)


def _parse_files_changed(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def rag_search(
    workspace: str | Path,
    query: str,
    *,
    limit: int = _DEFAULT_LIMIT,
    spec_path_prefix: str | None = None,
    outcome: str | None = None,
) -> list[SearchHit]:
    if not rag_enabled(workspace):
        return []

    q = query.strip()
    if len(q) < _MIN_QUERY_LEN:
        return []

    limit = max(1, min(limit, _MAX_LIMIT))
    fts_q = _fts_match_query(q)
    if not fts_q:
        return []

    db_path = delegation_rag_db_path(workspace)
    if not db_path.is_file():
        return []

    fetch_limit = min(limit * 4, 80)

    sql = """
        SELECT
            d.delegation_id,
            d.checkpoint_summary,
            d.spec_path,
            d.outcome,
            d.timestamp_end,
            d.files_changed,
            bm25(delegation_fts) AS bm25_score
        FROM delegation_fts
        JOIN delegation_index d ON d.rowid = delegation_fts.rowid
        WHERE delegation_fts MATCH ?
    """
    params: list[Any] = [fts_q]

    if spec_path_prefix:
        sql += " AND d.spec_path LIKE ?"
        params.append(f"{spec_path_prefix}%")
    if outcome:
        sql += " AND d.outcome = ?"
        params.append(outcome)

    sql += " ORDER BY bm25_score LIMIT ?"
    params.append(fetch_limit)

    hits: list[SearchHit] = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

    for row in rows:
        bm25_score = float(row["bm25_score"])
        # SQLite bm25: lower (more negative) is better match → invert for API
        relevance = -bm25_score
        recency = _recency_weight(
            str(row["timestamp_end"]) if row["timestamp_end"] else None
        )
        api_score = relevance * recency
        hits.append(
            SearchHit(
                delegation_id=str(row["delegation_id"]),
                score=api_score,
                checkpoint_summary=(
                    str(row["checkpoint_summary"]) if row["checkpoint_summary"] else None
                ),
                spec_path=str(row["spec_path"]) if row["spec_path"] else None,
                outcome=str(row["outcome"]) if row["outcome"] else None,
                timestamp_end=str(row["timestamp_end"]) if row["timestamp_end"] else None,
                files_changed=_parse_files_changed(
                    str(row["files_changed"]) if row["files_changed"] else None
                ),
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def rag_search_for_mcp(
    workspace: str | Path,
    query: str,
    *,
    limit: int = _DEFAULT_LIMIT,
    spec_path_prefix: str | None = None,
    outcome: str | None = None,
) -> dict[str, Any]:
    if not rag_enabled(workspace):
        return {"found": False, "error": "delegation RAG disabled"}

    q = query.strip()
    if len(q) < _MIN_QUERY_LEN:
        return {"found": False, "error": "query must be at least 2 characters"}

    db_path = delegation_rag_db_path(workspace)
    if not db_path.is_file():
        return {"found": False, "error": "delegation_rag.db not found"}

    hits = rag_search(
        workspace,
        q,
        limit=limit,
        spec_path_prefix=spec_path_prefix,
        outcome=outcome,
    )
    return {
        "found": True,
        "query": q,
        "hits": [h.to_dict() for h in hits],
    }


def rag_stats(workspace: str | Path) -> dict[str, Any]:
    if not rag_enabled(workspace):
        return {"enabled": False, "row_count": 0, "last_indexed": None}

    db = DelegationRagDB(workspace)
    return {
        "enabled": True,
        "row_count": db.row_count(),
        "last_indexed": db.last_indexed_timestamp(),
        "db_path": str(db.db_path),
    }
