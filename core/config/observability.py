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


def _env_bool(raw: str) -> bool | None:
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    return None


def capture_reasoning_enabled(workspace: str | Path) -> bool:
    """Default True. Env MCP_CODER_CAPTURE_REASONING=0 then yaml capture_reasoning: false."""
    enabled = True

    env_raw = os.environ.get("MCP_CODER_CAPTURE_REASONING", "").strip()
    if env_raw:
        parsed = _env_bool(env_raw)
        if parsed is not None:
            enabled = parsed

    ws_value = load_workspace_config(workspace).get("capture_reasoning")
    if isinstance(ws_value, bool):
        enabled = ws_value
    elif isinstance(ws_value, str):
        parsed = _env_bool(ws_value)
        if parsed is not None:
            enabled = parsed

    return enabled


def resolve_reasoning_buffer_size(workspace: str | Path) -> int:
    """Default 3. Env MCP_CODER_REASONING_BUFFER_SIZE then yaml reasoning_buffer_size."""
    size = 3

    env_raw = os.environ.get("MCP_CODER_REASONING_BUFFER_SIZE", "").strip()
    if env_raw:
        try:
            parsed = int(env_raw)
            if parsed > 0:
                size = parsed
        except ValueError:
            pass

    ws_value = load_workspace_config(workspace).get("reasoning_buffer_size")
    if isinstance(ws_value, int) and ws_value > 0:
        size = ws_value
    elif isinstance(ws_value, str):
        try:
            parsed = int(ws_value.strip())
            if parsed > 0:
                size = parsed
        except ValueError:
            pass

    return size


RETENTION_SESSION = "session"
RETENTION_FOREVER = "forever"
_VALID_RETENTION = frozenset({RETENTION_SESSION, RETENTION_FOREVER})


def _warn_invalid_retention(value: str, *, workspace: str | Path) -> None:
    server_log_warn(
        f"invalid observability_retention '{value}' — using '{RETENTION_SESSION}'",
        workspace_path=str(workspace),
    )


def resolve_observability_retention(workspace: str | Path) -> str:
    """Default session. Env MCP_CODER_OBS_RETENTION then yaml observability_retention.

    Accepts ``session``, ``forever``, or ``<N>_days`` (e.g. ``30_days``) as policy stub.
  """
    retention = RETENTION_SESSION

    env_raw = os.environ.get("MCP_CODER_OBS_RETENTION", "").strip().lower()
    if env_raw:
        if env_raw in _VALID_RETENTION or env_raw.endswith("_days"):
            retention = env_raw
        else:
            _warn_invalid_retention(env_raw, workspace=workspace)

    ws_value = load_workspace_config(workspace).get("observability_retention")
    if isinstance(ws_value, str):
        normalized = ws_value.strip().lower()
        if normalized in _VALID_RETENTION or normalized.endswith("_days"):
            retention = normalized
        elif normalized:
            _warn_invalid_retention(normalized, workspace=workspace)

    return retention


def capture_for_training_enabled(workspace: str | Path) -> bool:
    """Default False. Env MCP_CODER_CAPTURE_FOR_TRAINING=1 then yaml capture_for_training: true."""
    enabled = False

    env_raw = os.environ.get("MCP_CODER_CAPTURE_FOR_TRAINING", "").strip()
    if env_raw:
        parsed = _env_bool(env_raw)
        if parsed is not None:
            enabled = parsed

    ws_value = load_workspace_config(workspace).get("capture_for_training")
    if isinstance(ws_value, bool):
        enabled = ws_value
    elif isinstance(ws_value, str):
        parsed = _env_bool(ws_value)
        if parsed is not None:
            enabled = parsed

    return enabled
