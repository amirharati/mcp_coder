"""Context builder enable flag (D-P4-5). Separate concern from rag_enabled."""

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


def context_builder_enabled(workspace: str | Path) -> bool:
    """Default True. Env MCP_CODER_CONTEXT_BUILDER_ENABLED=0 then yaml context_builder: false → False."""
    return _resolve_flag(
        workspace,
        env_var="MCP_CODER_CONTEXT_BUILDER_ENABLED",
        yaml_key="context_builder",
        default=True,
    )


def context_builder_llm_enabled(workspace: str | Path) -> bool:
    """Default True (D-P4-5 flipped after Phase 4 dogfood, 2026-06-09).

    Env MCP_CODER_CONTEXT_BUILDER_LLM=0 or yaml context_builder_llm: false → off.
    Gated by context_builder_enabled() at the call site — the LLM brief never runs
    when the rules picker is off.
    """
    return _resolve_flag(
        workspace,
        env_var="MCP_CODER_CONTEXT_BUILDER_LLM",
        yaml_key="context_builder_llm",
        default=True,
    )
