"""Review model resolution for mode=review delegations."""

from __future__ import annotations

from pathlib import Path

from core.config.role_models import ROLE_REVIEW, resolve_role_model_name


def resolve_review_model_name(workspace: str | Path) -> str:
    """
    Model for mode=review (spec Q&A). Separate from executor.

    Precedence (later wins):
      1. Executor default — resolve_model_name()  (AIDER_MODEL → MCP_CODER_MODEL → DEFAULT)
      2. MCP_CODER_REVIEW_MODEL env (if non-empty)
      3. workspace .mcp-coder/config.yaml review_model (if non-empty string)
    """
    return resolve_role_model_name(ROLE_REVIEW, workspace)
