"""Excerpt engine for the read-excerpt tier (P2-205).

Text-window v0: scans for def/class symbol lines; no AST, no ripgrep required.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

EXCERPT_CONTEXT_LINES = 5
EXCERPT_HEAD_LINES = 80
EXCERPTS_SUBDIR = ".mcp-coder/context/excerpts"

_SYMBOL_RE = re.compile(r"^(async\s+def\s|def\s|class\s)")


def read_full_max_bytes() -> int:
    """Return byte threshold above which read paths are excerpted (default 8192)."""
    raw = os.environ.get("MCP_CODER_READ_FULL_MAX_BYTES", "")
    try:
        val = int(raw)
        return val if val > 0 else 8192
    except (ValueError, TypeError):
        return 8192


@dataclass
class ExcerptResult:
    text: str
    full_bytes: int
    excerpt_bytes: int
    strategy: str  # "symbol_windows" | "head_tail" | "full_small"


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    merged: list[list[int]] = [list(ranges[0])]
    for start, end in sorted(ranges)[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _symbol_windows(lines: list[str], context: int) -> list[str]:
    n = len(lines)
    raw_ranges: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        if _SYMBOL_RE.match(line):
            raw_ranges.append((max(0, i - context), min(n - 1, i + context)))
    if not raw_ranges:
        return []
    merged = _merge_ranges(raw_ranges)
    result: list[str] = []
    for start, end in merged:
        result.extend(lines[start : end + 1])
        if end + 1 < n:
            result.append("")
    while result and result[-1] == "":
        result.pop()
    return result


def build_file_excerpt(
    abs_path: Path,
    *,
    rel_path: str,
    max_full_bytes: int,
    context_lines: int = EXCERPT_CONTEXT_LINES,
) -> ExcerptResult | None:
    """Build an excerpt for a file.

    Returns None if the file is missing or unreadable.
    Returns ExcerptResult with strategy='full_small' if file is within threshold
    (caller normally checks size first; this case is exposed for testability).
    """
    try:
        full_text = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    full_bytes = len(full_text.encode("utf-8"))

    if full_bytes <= max_full_bytes:
        return ExcerptResult(
            text=full_text,
            full_bytes=full_bytes,
            excerpt_bytes=full_bytes,
            strategy="full_small",
        )

    lines = full_text.splitlines()
    header = f"# excerpt from: {rel_path}\n"

    symbol_lines = _symbol_windows(lines, context_lines)
    if symbol_lines:
        body = "\n".join(symbol_lines)
        excerpt_text = header + "\n" + body + "\n"
        strategy = "symbol_windows"
    else:
        head = lines[:EXCERPT_HEAD_LINES]
        footer = f"\n… (excerpt truncated, {full_bytes} bytes total)"
        body = "\n".join(head) + footer
        excerpt_text = header + "\n" + body + "\n"
        strategy = "head_tail"

    return ExcerptResult(
        text=excerpt_text,
        full_bytes=full_bytes,
        excerpt_bytes=len(excerpt_text.encode("utf-8")),
        strategy=strategy,
    )


def excerpt_materialize_path(workspace: Path, rel_path: str) -> Path:
    """Absolute path for the materialized excerpt file."""
    safe_name = rel_path.replace("/", "__") + ".excerpt.txt"
    return workspace.resolve() / EXCERPTS_SUBDIR / safe_name


def write_excerpt_file(workspace: Path, rel_path: str, text: str) -> str:
    """Write excerpt to .mcp-coder/context/excerpts/; return repo-relative path."""
    abs_path = excerpt_materialize_path(workspace, rel_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(text, encoding="utf-8")
    ws = workspace.resolve()
    return str(abs_path.relative_to(ws))
