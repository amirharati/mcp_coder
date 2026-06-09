"""Auto-merge spec read-deps into delegate target_files (D-P3-7)."""

from __future__ import annotations

import os
from pathlib import Path

from core.storage.workspace_config import load_workspace_config


def _env_bool(raw: str) -> bool | None:
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    return None


def auto_merge_spec_read_enabled(workspace: str | Path) -> bool:
    """Default True; workspace config auto_merge_spec_read: false → False."""
    enabled = True

    env_raw = os.environ.get("MCP_CODER_AUTO_MERGE_SPEC_READ", "").strip()
    if env_raw:
        parsed = _env_bool(env_raw)
        if parsed is not None:
            enabled = parsed

    ws_value = load_workspace_config(workspace).get("auto_merge_spec_read")
    if isinstance(ws_value, bool):
        enabled = ws_value
    elif isinstance(ws_value, str):
        parsed = _env_bool(ws_value)
        if parsed is not None:
            enabled = parsed

    return enabled
