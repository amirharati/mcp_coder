from __future__ import annotations

import io
import os
from typing import Any

# Defaults for MCP delegations — non-interactive, no git commits from Aider.
# Override via MCP_CODER_AIDER_* or AIDER_* env (see .env.example).


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def delegation_auto_commits() -> bool:
    if os.environ.get("MCP_CODER_AIDER_AUTO_COMMITS") is not None:
        return _env_bool("MCP_CODER_AIDER_AUTO_COMMITS", False)
    if os.environ.get("AIDER_AUTO_COMMITS") is not None:
        return _env_bool("AIDER_AUTO_COMMITS", False)
    return False


def delegation_dirty_commits() -> bool:
    if os.environ.get("MCP_CODER_AIDER_DIRTY_COMMITS") is not None:
        return _env_bool("MCP_CODER_AIDER_DIRTY_COMMITS", False)
    if os.environ.get("AIDER_DIRTY_COMMITS") is not None:
        return _env_bool("AIDER_DIRTY_COMMITS", False)
    return False


def delegation_use_git() -> bool:
    """Keep git for diffs; set MCP_CODER_AIDER_USE_GIT=0 for --no-git."""
    return _env_bool("MCP_CODER_AIDER_USE_GIT", _env_bool("AIDER_USE_GIT", True))


def delegation_suggest_shell() -> bool:
    return _env_bool("MCP_CODER_AIDER_SUGGEST_SHELL", False)


def delegation_stream() -> bool:
    return _env_bool("MCP_CODER_AIDER_STREAM", False)


def delegation_auto_lint() -> bool:
    return _env_bool("MCP_CODER_AIDER_AUTO_LINT", False)


def create_delegation_io() -> tuple[Any, io.StringIO]:
    """
  InputOutput for headless delegation (~ aider --yes-always --no-auto-commits).

  Returns (io, buffer) so callers can read captured tool output.

  Must be called inside core.engine.stdio_isolation.isolated_stdio() so Aider
  init does not write to the process stdout (breaks MCP JSON-RPC).
  """
    from aider.io import InputOutput

    from core.engine.stdio_isolation import bind_aider_io_to_buffer

    buffer = io.StringIO()
    io_obj = InputOutput(
        pretty=False,
        yes=True,
        fancy_input=False,
        output=buffer,
    )
    bind_aider_io_to_buffer(io_obj, buffer)
    return io_obj, buffer


def delegation_coder_kwargs() -> dict[str, Any]:
    """Keyword args for Coder.create() during MCP delegations."""
    return {
        "auto_commits": delegation_auto_commits(),
        "dirty_commits": delegation_dirty_commits(),
        "use_git": delegation_use_git(),
        "suggest_shell_commands": delegation_suggest_shell(),
        "stream": delegation_stream(),
        "auto_lint": delegation_auto_lint(),
        "show_diffs": False,
    }


def infer_run_success(
    *,
    io: Any,
    output: str,
    partial_response: str | None,
) -> tuple[bool, str | None]:
    """Treat Aider/LiteLLM tool errors as delegation failure."""
    if getattr(io, "num_error_outputs", 0) > 0:
        return False, "Aider reported one or more errors (see output)"
    text = "\n".join(filter(None, [output, partial_response or ""]))
    error_markers = (
        "litellm.",
        "NotFoundError",
        "AuthenticationError",
        "RateLimitError",
        "OpenrouterException",
        "OpenAIError",
    )
    lower = text.lower()
    if any(m.lower() in lower for m in error_markers):
        return False, text.strip()[:2000] or "LLM provider error"
    if not text.strip():
        return False, "Empty response from Aider (no edits applied?)"
    return True, None
