"""Workspace pointer (`.mcp-coder/session.json`) — system-managed, safe to overwrite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.storage.paths import (
    legacy_workspace_pointer_path,
    normalize_workspace,
    workspace_pointer_path,
)


def load_workspace_pointer(workspace: str | Path) -> dict[str, Any]:
    """Load pointer from session.json, falling back to legacy project.json."""
    ws = normalize_workspace(workspace)
    for path in (workspace_pointer_path(ws), legacy_workspace_pointer_path(ws)):
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def save_workspace_pointer(workspace: str | Path, data: dict[str, Any]) -> Path:
    path = workspace_pointer_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
