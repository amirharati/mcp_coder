from __future__ import annotations

import os

# Single default for Phase 1 — swap via AIDER_MODEL or MCP_CODER_MODEL in .env.
# Must use the openrouter/ prefix for Aider: https://aider.chat/docs/llms/openrouter.html
DEFAULT_MODEL = "openrouter/openai/gpt-4o-mini"

# Examples for .env (not used unless you set AIDER_MODEL):
# Dev (cheap):  openrouter/openai/gpt-4o-mini
# Serious test: openrouter/anthropic/claude-sonnet-4
# Coding-focused: openrouter/qwen/qwen-2.5-coder-32b-instruct


def resolve_model_name() -> str:
    """
    Model id passed to Aider's Model().

    Precedence: AIDER_MODEL → MCP_CODER_MODEL → DEFAULT_MODEL.
    """
    for key in ("AIDER_MODEL", "MCP_CODER_MODEL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return DEFAULT_MODEL


def provider_hint_for_model(model_name: str) -> str | None:
    """Return a clear error if required API keys are missing (best-effort)."""
    if model_name.startswith("openrouter/"):
        if not os.environ.get("OPENROUTER_API_KEY", "").strip():
            return (
                "OPENROUTER_API_KEY is not set. "
                "Get a key at https://openrouter.ai/keys and add it to .env or mcp.json env."
            )
        from core.config.openrouter_models import validate_openrouter_model

        catalog_error = validate_openrouter_model(model_name)
        if catalog_error:
            return catalog_error
        return None
    if model_name.startswith("anthropic/") or "claude" in model_name.lower():
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            return "ANTHROPIC_API_KEY is not set for this model."
        return None
    if model_name.startswith("openai/") or model_name.startswith("gpt-"):
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            return "OPENAI_API_KEY is not set for this model."
        return None
    return None
