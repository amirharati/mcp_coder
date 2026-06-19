"""Per-role model resolution (D-P4-8 Stage 1). Backend-neutral — no Aider APIs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.config.models import resolve_model_name
from core.storage.workspace_config import load_workspace_config

ROLE_EXECUTOR = "executor"
ROLE_REVIEW = "review"
ROLE_CONTEXT_BUILDER = "context_builder"
ROLE_CRITIC = "critic"
ROLE_SUPERVISOR = "supervisor"

# Documented OpenRouter dogfood default — set MCP_CODER_CONTEXT_BUILDER_MODEL in .env
# (do not rely on a hardcoded provider id in code).
RECOMMENDED_CONTEXT_BUILDER_MODEL = "openrouter/google/gemini-2.5-flash"

_ROLE_MODEL_YAML: dict[str, str] = {
    ROLE_REVIEW: "review_model",
    ROLE_CONTEXT_BUILDER: "context_builder_model",
    ROLE_CRITIC: "critic_model",
    ROLE_SUPERVISOR: "supervisor_model",
}

_ROLE_MODEL_ENV: dict[str, str] = {
    ROLE_REVIEW: "MCP_CODER_REVIEW_MODEL",
    ROLE_CONTEXT_BUILDER: "MCP_CODER_CONTEXT_BUILDER_MODEL",
    ROLE_CRITIC: "MCP_CODER_CRITIC_MODEL",
    ROLE_SUPERVISOR: "MCP_CODER_SUPERVISOR_MODEL",
}

_ROLE_BUDGET_YAML: dict[str, str] = {
    ROLE_CONTEXT_BUILDER: "context_builder_budget_tokens",
    ROLE_REVIEW: "review_budget_tokens",
    ROLE_CRITIC: "critic_budget_tokens",
    ROLE_EXECUTOR: "executor_budget_tokens",
}

_ROLE_BUDGET_ENV: dict[str, str] = {
    ROLE_CONTEXT_BUILDER: "MCP_CODER_CONTEXT_BUILDER_BUDGET_TOKENS",
    ROLE_REVIEW: "MCP_CODER_REVIEW_BUDGET_TOKENS",
    ROLE_CRITIC: "MCP_CODER_CRITIC_BUDGET_TOKENS",
    ROLE_EXECUTOR: "MCP_CODER_EXECUTOR_BUDGET_TOKENS",
}


def _context_builder_base_default() -> str:
    """Provider-neutral fallback when role env + yaml are unset.

    Optional MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL (operator default in .env)
    then executor model (AIDER_MODEL / MCP_CODER_MODEL).
    """
    env_raw = os.environ.get("MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL", "").strip()
    if env_raw:
        return env_raw
    return resolve_model_name()


def _role_default_model(role: str, workspace: str | Path) -> str:
    del workspace  # reserved for future workspace-level defaults
    if role == ROLE_EXECUTOR:
        return resolve_model_name()
    if role == ROLE_CONTEXT_BUILDER:
        return _context_builder_base_default()
    if role == ROLE_SUPERVISOR:
        return _context_builder_base_default()
    return resolve_model_name()


def role_config_keys(role: str) -> tuple[str, str]:
    """Return (yaml_key, env_var_name) for a role — for tests/docs."""
    if role == ROLE_EXECUTOR:
        return ("", "")
    return (
        _ROLE_MODEL_YAML.get(role, f"{role}_model"),
        _ROLE_MODEL_ENV.get(role, f"MCP_CODER_{role.upper()}_MODEL"),
    )


def resolve_role_model_name(role: str, workspace: str | Path) -> str:
    """Precedence per role: role-specific default → env → config.yaml (later wins)."""
    if role == ROLE_EXECUTOR:
        return resolve_model_name()

    resolved = _role_default_model(role, workspace)

    env_var = _ROLE_MODEL_ENV.get(role)
    if env_var:
        env_raw = os.environ.get(env_var, "").strip()
        if env_raw:
            resolved = env_raw

    yaml_key = _ROLE_MODEL_YAML.get(role)
    if yaml_key:
        ws_value = load_workspace_config(workspace).get(yaml_key)
        if isinstance(ws_value, str) and ws_value.strip():
            resolved = ws_value.strip()

    return resolved


def _parse_budget_int(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            value = int(text)
            return value if value > 0 else None
        except ValueError:
            return None
    return None


def resolve_role_budget_tokens(role: str, workspace: str | Path) -> int | None:
    """Optional cap from env then config.yaml; None when unset."""
    resolved: int | None = None

    env_var = _ROLE_BUDGET_ENV.get(role)
    if env_var:
        env_raw = os.environ.get(env_var, "").strip()
        if env_raw:
            resolved = _parse_budget_int(env_raw)

    yaml_key = _ROLE_BUDGET_YAML.get(role, f"{role}_budget_tokens")
    ws_value = load_workspace_config(workspace).get(yaml_key)
    parsed = _parse_budget_int(ws_value)
    if parsed is not None:
        resolved = parsed

    return resolved
