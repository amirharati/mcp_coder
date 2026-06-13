"""Backend-neutral repo map (P4-001a, D-P4-11).

Builds map-only PathEntry items from the workspace walk — no git, no Aider
repo map. Payload is a def/class symbol outline per file (Python files);
files without symbols are listed with no payload.
"""

from __future__ import annotations

import os
from pathlib import Path

from core.context.package import TIER_MAP_ONLY, PathEntry
from core.context.symbol_outline import symbol_outline_for_path
from core.workspace.walk import walk_workspace

DEFAULT_MAX_FILES = 150

MAP_EXTENSIONS = frozenset(
    {".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".yaml", ".yml", ".json", ".toml"}
)


def repo_map_max_files() -> int:
    raw = os.environ.get("MCP_CODER_REPO_MAP_MAX_FILES", "").strip()
    try:
        val = int(raw)
        return val if val > 0 else DEFAULT_MAX_FILES
    except (ValueError, TypeError):
        return DEFAULT_MAX_FILES


def build_repo_map_entries(
    workspace: Path,
    *,
    exclude_paths: set[str],
    max_files: int | None = None,
) -> list[PathEntry]:
    """map-only entries for workspace text files not already in the ranked set."""
    limit = max_files if max_files is not None else repo_map_max_files()
    ws = workspace.resolve()
    manifest = walk_workspace(str(ws))

    entries: list[PathEntry] = []
    for rel in sorted(manifest):
        if len(entries) >= limit:
            break
        if rel in exclude_paths:
            continue
        if Path(rel).suffix.lower() not in MAP_EXTENSIONS:
            continue
        if manifest[rel].is_binary:
            continue
        outline = symbol_outline_for_path(ws / rel)
        entries.append(
            PathEntry(
                path=rel,
                tier=TIER_MAP_ONLY,
                bytes=len(outline.encode("utf-8")) if outline else None,
                payload=outline,
            )
        )
    return entries
