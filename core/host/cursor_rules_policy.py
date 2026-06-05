"""Resolve which bundled Cursor rule policy to sync (env → workspace yaml)."""

from __future__ import annotations

import os
from pathlib import Path

from core.logging.delegation_log import log_stderr
from core.logging.server_log import server_log_warn
from core.storage.workspace_config import load_workspace_config

POLICY_DEFAULT = "default"
POLICY_STRICT = "strict"
VALID_POLICIES = frozenset({POLICY_DEFAULT, POLICY_STRICT})


def sync_cursor_rules_enabled(workspace: str | Path | None = None) -> bool:
    raw = os.environ.get("MCP_CODER_SYNC_CURSOR_RULE", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if workspace is not None:
        sync_cfg = load_workspace_config(workspace).get("cursor_rules")
        if isinstance(sync_cfg, dict) and sync_cfg.get("sync") is False:
            return False
    return True


def resolve_cursor_rules_policy(workspace: str | Path) -> str:
    """Default → env → workspace .mcp-coder/config.yaml (yaml wins)."""
    policy = POLICY_DEFAULT

    env_policy = os.environ.get("MCP_CODER_CURSOR_RULES_POLICY", "").strip()
    if env_policy:
        policy = env_policy

    ws_cfg = load_workspace_config(workspace)
    ws_policy = ws_cfg.get("cursor_rules_policy")
    if isinstance(ws_policy, str) and ws_policy.strip():
        policy = ws_policy.strip()

    sync_cfg = ws_cfg.get("cursor_rules")
    if isinstance(sync_cfg, dict):
        nested = sync_cfg.get("policy")
        if isinstance(nested, str) and nested.strip():
            policy = nested.strip()
        if sync_cfg.get("sync") is False:
            pass  # handled by sync_cursor_rules_enabled via separate key later

    if policy not in VALID_POLICIES:
        if policy:
            message = (
                f"Invalid cursor_rules_policy {policy!r}; "
                f"expected {POLICY_DEFAULT!r} or {POLICY_STRICT!r}, using {POLICY_DEFAULT!r}"
            )
            log_stderr(f"[mcp-coder] {message}")
            server_log_warn(message, workspace_path=str(workspace))
        return POLICY_DEFAULT
    return policy
