from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _parse_iso_epoch(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        text = iso.replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def sessions_root_by_key(project_key_value: str) -> Path:
    from core.storage.paths import mcp_coder_home

    return mcp_coder_home() / "projects" / project_key_value / "sessions"


def host_delegation_activity(project_key_value: str) -> dict[str, float]:
    """Map host_session_id → last delegation epoch for this project."""
    activity: dict[str, float] = {}
    root = sessions_root_by_key(project_key_value)
    if not root.is_dir():
        return activity

    for session_json in root.glob("*/session.json"):
        try:
            data = json.loads(session_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        host_id = data.get("host_session_id")
        if not host_id:
            continue
        ts = _parse_iso_epoch(data.get("last_delegation_at"))
        activity[host_id] = max(activity.get(host_id, 0.0), ts)
    return activity
