"""Review model resolution for mode=review delegations."""

from __future__ import annotations

import os
from pathlib import Path

from core.config.models import resolve_model_name
from core.storage.workspace_config import load_workspace_config


def resolve_review_model_name(workspace: str | Path) -> str:
    """
    Model for mode=review (spec Q&A). Separate from executor.

    Precedence (later wins):
      1. Executor default — resolve_model_name()  (AIDER_MODEL → MCP_CODER_MODEL → DEFAULT)
      2. MCP_CODER_REVIEW_MODEL env (if non-empty)
      3. workspace .mcp-coder/config.yaml review_model (if non-empty string)
    """
    resolved = resolve_model_name()

    env_raw = os.environ.get("MCP_CODER_REVIEW_MODEL", "").strip()
    if env_raw:
        resolved = env_raw

    ws_value = load_workspace_config(workspace).get("review_model")
    if isinstance(ws_value, str) and ws_value.strip():
        resolved = ws_value.strip()

    return resolved
