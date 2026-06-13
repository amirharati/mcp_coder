"""Shared FTS5 query helpers for RAG corpora."""

from __future__ import annotations

import os
import re

_DEFAULT_MAX_TERMS = 15

# Noise terms that inflate OR queries without improving recall.
_FTS_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "for",
        "from",
        "had",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "not",
        "of",
        "on",
        "or",
        "per",
        "so",
        "the",
        "this",
        "to",
        "via",
        "was",
        "were",
        "with",
        "add",
        "all",
        "any",
        "both",
        "can",
        "file",
        "files",
        "into",
        "keep",
        "may",
        "must",
        "new",
        "no",
        "only",
        "one",
        "out",
        "run",
        "see",
        "task",
        "that",
        "top",
        "use",
        "using",
        "when",
        "will",
        "you",
        "your",
    }
)


def max_fts_terms() -> int:
    """Max OR terms for FTS MATCH (env MCP_CODER_FTS_MAX_TERMS, default 15)."""
    raw = os.environ.get("MCP_CODER_FTS_MAX_TERMS", "").strip()
    try:
        val = int(raw)
        return val if val > 0 else _DEFAULT_MAX_TERMS
    except (ValueError, TypeError):
        return _DEFAULT_MAX_TERMS


def _clean_term(term: str) -> str:
    return re.sub(r"[^\w-]", "", term)


def _term_parts(term: str) -> list[str]:
    """Split compound tokens; hyphens break SQLite FTS5 MATCH (P5-ISS-003)."""
    safe = _clean_term(term)
    if not safe:
        return []
    parts: list[str] = []
    for piece in re.split(r"[-_]+", safe):
        if len(piece) >= 2:
            parts.append(piece)
    return parts


def _select_terms(terms: list[str], cap: int) -> list[str]:
    """Drop stopwords/dupes; when over cap keep longest terms (discriminative)."""
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        for safe in _term_parts(term):
            key = safe.lower()
            if key in _FTS_STOPWORDS or key in seen:
                continue
            seen.add(key)
            unique.append(safe)

    if len(unique) <= cap:
        return unique

    indexed = list(enumerate(unique))
    indexed.sort(key=lambda pair: (-len(pair[1]), pair[0]))
    chosen = indexed[:cap]
    chosen.sort(key=lambda pair: pair[0])
    return [term for _, term in chosen]


def fts_match_query(raw: str) -> str:
    """Build SQLite FTS5 MATCH query from free text (OR-joined terms, capped)."""
    terms = [t for t in re.split(r"\s+", raw.strip()) if t]
    if not terms:
        return ""
    selected = _select_terms(terms, max_fts_terms())
    if not selected:
        return ""
    return " OR ".join(selected)
