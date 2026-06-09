"""Delegation RAG enable flag (D-P3-5)."""

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


def rag_enabled(workspace: str | Path) -> bool:
    """Default True; env MCP_CODER_RAG_ENABLED=0 then workspace rag_enabled: false → False."""
    enabled = True

    env_raw = os.environ.get("MCP_CODER_RAG_ENABLED", "").strip()
    if env_raw:
        parsed = _env_bool(env_raw)
        if parsed is not None:
            enabled = parsed

    ws_value = load_workspace_config(workspace).get("rag_enabled")
    if isinstance(ws_value, bool):
        enabled = ws_value
    elif isinstance(ws_value, str):
        parsed = _env_bool(ws_value)
        if parsed is not None:
            enabled = parsed

    return enabled
