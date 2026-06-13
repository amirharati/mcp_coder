"""def/class symbol outlines for repo map and workspace RAG (backend-neutral)."""

from __future__ import annotations

from pathlib import Path

from core.context.excerpts import _SYMBOL_RE

MAX_OUTLINE_LINES = 40


def symbol_outline_for_path(
    abs_path: Path,
    *,
    max_lines: int = MAX_OUTLINE_LINES,
) -> str | None:
    """Return newline-separated def/class lines, capped at max_lines."""
    try:
        text = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    lines = [
        line.strip()
        for line in text.splitlines()
        if _SYMBOL_RE.match(line.lstrip())
    ]
    if not lines:
        return None
    return "\n".join(lines[:max_lines])
