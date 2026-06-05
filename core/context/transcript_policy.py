from __future__ import annotations

import os
from pathlib import Path

from core.logging.delegation_log import log_stderr
from core.logging.server_log import server_log_warn
from core.storage.workspace_config import load_workspace_config

POLICY_NONE = "none"
POLICY_DUMP = "dump"
VALID_POLICIES = frozenset({POLICY_NONE, POLICY_DUMP})


def resolve_host_transcript_policy(workspace: str | Path) -> str:
    """Default → env → workspace .mcp-coder/config.yaml (yaml wins)."""
    policy = POLICY_NONE

    env_policy = os.environ.get("MCP_CODER_HOST_TRANSCRIPT", "").strip()
    if env_policy:
        policy = env_policy

    ws_policy = load_workspace_config(workspace).get("host_transcript")
    if isinstance(ws_policy, str) and ws_policy.strip():
        policy = ws_policy.strip()

    if policy not in VALID_POLICIES:
        if policy:
            message = (
                f"Invalid host_transcript policy {policy!r}; "
                f"expected {POLICY_NONE!r} or {POLICY_DUMP!r}, using {POLICY_NONE!r}"
            )
            log_stderr(f"[mcp-coder] {message}")
            server_log_warn(message, workspace_path=str(workspace))
        return POLICY_NONE
    return policy
