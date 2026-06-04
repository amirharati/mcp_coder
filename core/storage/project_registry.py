"""Ensure ~/.mcp-coder/projects/<project_key>/project.json exists."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datetime import datetime, timezone

from core.storage.paths import (
    normalize_workspace,
    project_json_path,
    project_key,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_project(workspace: str | Path) -> dict[str, Any]:
    ws = normalize_workspace(workspace)
    key = project_key(ws)
    path = project_json_path(ws)
    now = _utc_now_iso()

    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        data["project_key"] = key
        data["workspace_path"] = ws
        data["last_seen_at"] = now
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "project_key": key,
            "workspace_path": ws,
            "created_at": now,
            "last_seen_at": now,
        }

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data
