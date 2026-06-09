"""Post-delegate verify loop enable flag (D-P4-2, D-P4-7)."""

from __future__ import annotations

import os
from pathlib import Path

from core.storage.workspace_config import load_workspace_config

DEFAULT_VERIFY_COMMAND = "pytest -q"
DEFAULT_VERIFY_TIMEOUT_S = 120


def _env_bool(raw: str) -> bool | None:
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    return None


def _resolve_flag(
    workspace: str | Path,
    *,
    env_var: str,
    yaml_key: str,
    default: bool,
) -> bool:
    """Shared precedence: default → env → workspace yaml (later wins)."""
    enabled = default

    env_raw = os.environ.get(env_var, "").strip()
    if env_raw:
        parsed = _env_bool(env_raw)
        if parsed is not None:
            enabled = parsed

    ws_value = load_workspace_config(workspace).get(yaml_key)
    if isinstance(ws_value, bool):
        enabled = ws_value
    elif isinstance(ws_value, str):
        parsed = _env_bool(ws_value)
        if parsed is not None:
            enabled = parsed

    return enabled


def auto_verify_enabled(workspace: str | Path) -> bool:
    """Default False. Env MCP_CODER_AUTO_VERIFY=1 then yaml auto_verify: true → True."""
    return _resolve_flag(
        workspace,
        env_var="MCP_CODER_AUTO_VERIFY",
        yaml_key="auto_verify",
        default=False,
    )


def resolve_verify_command(workspace: str | Path) -> str:
    """Default pytest -q when auto_verify on; env then yaml override."""
    resolved = DEFAULT_VERIFY_COMMAND

    env_raw = os.environ.get("MCP_CODER_VERIFY_COMMAND", "").strip()
    if env_raw:
        resolved = env_raw

    ws_value = load_workspace_config(workspace).get("verify_command")
    if isinstance(ws_value, str) and ws_value.strip():
        resolved = ws_value.strip()

    return resolved


def resolve_verify_timeout_s(workspace: str | Path) -> int:
    """Default 120s; env then yaml override."""
    resolved = DEFAULT_VERIFY_TIMEOUT_S

    env_raw = os.environ.get("MCP_CODER_VERIFY_TIMEOUT_S", "").strip()
    if env_raw:
        try:
            val = int(env_raw)
            if val > 0:
                resolved = val
        except ValueError:
            pass

    ws_value = load_workspace_config(workspace).get("verify_timeout_s")
    if ws_value is not None:
        try:
            val = int(ws_value)
            if val > 0:
                resolved = val
        except (ValueError, TypeError):
            pass

    return resolved
