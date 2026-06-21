"""Heuristic extraction of explicit decisions from planner output (P12-005)."""

from __future__ import annotations

import re

_DECISION_PATTERNS = [
    re.compile(
        r"(?:^|\n)\s*(?:\d+\.\s+)?(?:we\s+will|will\s+use|decided?\s+to|approach:|strategy:|use\s+\w+\s+for)\s+(.{10,120})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|\n)\*\*Decision[:\s]+\*\*(.{10,120})", re.IGNORECASE),
    re.compile(r"(?:^|\n)-\s+(?:Decision|Decided):\s+(.{10,120})", re.IGNORECASE),
]
_MAX_DECISIONS = 5


def extract_decisions_from_plan(plan_text: str) -> list[str]:
    """Extract explicit decision statements from plan text.

    Heuristic only — no LLM call. False negatives are acceptable; false positives
    are constrained by the 10-120 char capture window.
    """
    seen: set[str] = set()
    results: list[str] = []
    for pattern in _DECISION_PATTERNS:
        for m in pattern.finditer(plan_text or ""):
            text = m.group(1).strip().rstrip(".,;:")
            if text and text not in seen:
                seen.add(text)
                results.append(text)
            if len(results) >= _MAX_DECISIONS:
                return results
    return results
