"""Delegate modes for spec-based multi-call workflows."""

from __future__ import annotations

DELEGATE_MODE_IMPLEMENT = "implement"
DELEGATE_MODE_REVIEW = "review"

DELEGATE_MODES = frozenset({DELEGATE_MODE_IMPLEMENT, DELEGATE_MODE_REVIEW})


def normalize_delegate_mode(mode: str | None) -> str:
    raw = (mode or DELEGATE_MODE_IMPLEMENT).strip().lower()
    if raw not in DELEGATE_MODES:
        raise ValueError(
            f"mode must be {DELEGATE_MODE_IMPLEMENT!r} or {DELEGATE_MODE_REVIEW!r} (got {mode!r})"
        )
    return raw
