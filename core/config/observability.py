"""Phase 6 observability config — trace verbosity tiers (D-P6-4)."""

from __future__ import annotations

import os
from pathlib import Path

from core.logging.server_log import server_log_warn
from core.storage.workspace_config import load_workspace_config

VERBOSITY_LEAN = "lean"
VERBOSITY_STANDARD = "standard"
VERBOSITY_FULL = "full"

_VALID = frozenset({VERBOSITY_LEAN, VERBOSITY_STANDARD, VERBOSITY_FULL})

_warned_invalid_verbosity = False


def _warn_invalid(value: str, *, workspace: str | Path) -> None:
    global _warned_invalid_verbosity
    if _warned_invalid_verbosity:
        return
    _warned_invalid_verbosity = True
    server_log_warn(
        f"invalid observability_verbosity '{value}' — using '{VERBOSITY_STANDARD}'",
        workspace_path=str(workspace),
    )


def resolve_observability_verbosity(workspace: str | Path) -> str:
    """Default standard. Env MCP_CODER_OBS_VERBOSITY then yaml observability_verbosity."""
    verbosity = VERBOSITY_STANDARD

    env_raw = os.environ.get("MCP_CODER_OBS_VERBOSITY", "").strip().lower()
    if env_raw:
        if env_raw in _VALID:
            verbosity = env_raw
        else:
            _warn_invalid(env_raw, workspace=workspace)

    ws_value = load_workspace_config(workspace).get("observability_verbosity")
    if isinstance(ws_value, str):
        normalized = ws_value.strip().lower()
        if normalized in _VALID:
            verbosity = normalized
        elif normalized:
            _warn_invalid(normalized, workspace=workspace)

    return verbosity
