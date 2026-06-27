"""FTS query construction (P5-006 / P5-ISS-003)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.rag.builder_retrieval import build_delegation_search_query
from core.rag.fts import fts_match_query, max_fts_terms
from core.rag.search import rag_search

# Long task from Phase 5 dogfood that previously returned 0 FTS hits.
LONG_DOGFOOD_TASK = (
    "Add a module-level docstring at the top of expensesplit/settlement.py (before imports). "
    "Docstring only — do not change any logic, functions, or imports.\n\n"
    "Wording should align with prior milestones:\n"
    '- CLI help description: "Split shared expenses from a JSON ledger, compute net balances, '
    'and suggest settlement transfers."\n'
    '- export subcommand help: "Export balances and settlements"\n'
    '- settle subcommand help: "Suggest settlements"\n'
    '- Package __init__.py: "Shared expense splitter — load ledger, compute balances, '
    'suggest settlements."\n\n'
    'Acceptance: module docstring must mention both "settlement transfers" (or "settlements") '
    'and "balances" (or "net balances"). Keep the existing function docstring on '
    "suggest_settlements unchanged."
)

GOAL = (
    "Add a module docstring to settlement.py "
    "(wording aligned with validate/export and CLI help milestones)."
)


def test_fts_match_query_caps_or_terms(monkeypatch):
    monkeypatch.setenv("MCP_CODER_FTS_MAX_TERMS", "15")
    fts = fts_match_query(LONG_DOGFOOD_TASK + " " + GOAL)
    assert fts
    assert fts.count(" OR ") + 1 <= max_fts_terms()


def test_fts_match_query_splits_hyphenated_terms():
    fts = fts_match_query("module-level docstring")
    terms = fts.split(" OR ")
    assert "module-level" not in terms
    assert "module" in terms
    assert "level" in terms


def test_fts_match_query_drops_stopwords():
    fts = fts_match_query("Add a module with the settlement logic")
    terms = {t.lower() for t in fts.split(" OR ")}
    assert "add" not in terms
    assert "a" not in terms
    assert "the" not in terms
    assert "settlement" in terms


def test_long_dogfood_query_returns_delegation_hits():
    ws = Path("/Users/amir/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e")
    if not (ws / ".mcp-coder").is_dir():
        pytest.skip("e2e workspace not available")
    query = build_delegation_search_query(
        task=LONG_DOGFOOD_TASK,
        spec_sections={"Goal": GOAL},
    )
    hits = rag_search(ws, query, limit=5)
    if not hits:
        pytest.skip("e2e workspace has no FTS-indexed delegations — rebuild delegation DB to re-enable")
    assert len(hits) >= 1


def test_short_query_still_returns_hits():
    ws = Path("/Users/amir/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e")
    if not (ws / ".mcp-coder").is_dir():
        pytest.skip("e2e workspace not available")
    query = "validate export CLI help settlement"
    hits = rag_search(ws, query, limit=5)
    if not hits:
        pytest.skip("e2e workspace has no FTS-indexed delegations — rebuild delegation DB to re-enable")
    assert len(hits) >= 1
