"""Judgment checklist for implement delegate responses (P4-006)."""

from __future__ import annotations

from typing import Any

JUDGMENT_REMINDER = (
    "Quote created/modified/deleted and check files_unexpected against spec Files → Edit "
    "before pytest; do not mark done without citing this block."
)


def build_judgment_checklist(
    *,
    delegation_diff: dict[str, Any],
    files_unexpected: list[str] | None = None,
) -> dict[str, Any]:
    """Build informational checklist from delegation_diff path lists (no diff bodies)."""
    checklist: dict[str, Any] = {
        "delegation_id": delegation_diff.get("delegation_id", ""),
        "created": list(delegation_diff.get("created") or []),
        "modified": list(delegation_diff.get("modified") or []),
        "deleted": list(delegation_diff.get("deleted") or []),
        "files_unexpected": list(files_unexpected or []),
        "reminder": JUDGMENT_REMINDER,
    }
    if checklist["files_unexpected"]:
        checklist["files_unexpected_warning"] = True
    return checklist
