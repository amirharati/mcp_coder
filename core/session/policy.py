from __future__ import annotations

import os
from pathlib import Path

from core.logging.delegation_log import log_stderr
from core.storage.workspace_config import load_workspace_config

POLICY_ALWAYS_NEW = "always_new"
POLICY_ALIGN_HOST = "align_host"
VALID_POLICIES = frozenset({POLICY_ALWAYS_NEW, POLICY_ALIGN_HOST})

_deprecation_warned = False


def _warn_fallback_session_deprecated() -> None:
    global _deprecation_warned
    if _deprecation_warned:
        return
    if os.environ.get("MCP_CODER_FALLBACK_SESSION", "").strip():
        log_stderr(
            "[mcp-coder] MCP_CODER_FALLBACK_SESSION is deprecated; "
            "use MCP_CODER_SESSION_POLICY (new var wins if both set)"
        )
        _deprecation_warned = True


def resolve_session_policy(workspace: str | Path) -> str:
    """Default → env → workspace .mcp-coder/config.yaml (later wins)."""
    _warn_fallback_session_deprecated()
    policy = POLICY_ALWAYS_NEW

    env_policy = os.environ.get("MCP_CODER_SESSION_POLICY", "").strip()
    old_fallback = os.environ.get("MCP_CODER_FALLBACK_SESSION", "").strip()

    if env_policy:
        policy = env_policy
    elif old_fallback:
        policy = POLICY_ALWAYS_NEW if old_fallback == "always_new" else old_fallback

    ws_policy = load_workspace_config(workspace).get("session_policy")
    if isinstance(ws_policy, str) and ws_policy.strip():
        policy = ws_policy.strip()

    if policy not in VALID_POLICIES:
        return POLICY_ALWAYS_NEW
    return policy
