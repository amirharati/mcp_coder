from __future__ import annotations

import os

# LiteLLM / Aider read OPENROUTER_API_BASE (see https://docs.litellm.ai/docs/providers/openrouter)
DEFAULT_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"

# Future multi-provider: add DEFAULT_*_API_BASE + resolve_* + apply_* here.


def resolve_openrouter_api_base() -> str:
    """
    OpenRouter API base URL.

    Precedence: OPENROUTER_API_BASE → MCP_CODER_OPENROUTER_API_BASE → default.
    """
    for key in ("OPENROUTER_API_BASE", "MCP_CODER_OPENROUTER_API_BASE"):
        value = os.environ.get(key, "").strip().rstrip("/")
        if value:
            return value
    return DEFAULT_OPENROUTER_API_BASE


def apply_provider_env() -> None:
    """
    Ensure provider env vars are set for Aider/LiteLLM after .env load.

    Uses setdefault so explicit values from the shell or Cursor mcp.json win.
    """
    if not os.environ.get("OPENROUTER_API_BASE", "").strip():
        os.environ["OPENROUTER_API_BASE"] = resolve_openrouter_api_base()
