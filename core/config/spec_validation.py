"""Pre-delegate spec validation enable flag (D-P4-13)."""

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


def spec_validation_enabled(workspace: str | Path) -> bool:
    """Default False. Env MCP_CODER_SPEC_VALIDATION=1 then yaml spec_validation: true → True."""
    return _resolve_flag(
        workspace,
        env_var="MCP_CODER_SPEC_VALIDATION",
        yaml_key="spec_validation",
        default=False,
    )


def clarity_pass_enabled(workspace: str | Path) -> bool:
    """Default False. Env MCP_CODER_CLARITY_PASS=1 or yaml clarity_pass: true → True."""
    return _resolve_flag(
        workspace,
        env_var="MCP_CODER_CLARITY_PASS",
        yaml_key="clarity_pass",
        default=False,
    )


def reviewer_pass_enabled(workspace: str | Path) -> bool:
    """Default False. Env MCP_CODER_REVIEWER_PASS=1 or yaml reviewer_pass: true → True."""
    return _resolve_flag(
        workspace,
        env_var="MCP_CODER_REVIEWER_PASS",
        yaml_key="reviewer_pass",
        default=False,
    )
