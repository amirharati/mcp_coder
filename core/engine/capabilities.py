"""BackendCapabilities — static feature declaration for each execution adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BackendCapabilities:
    """Immutable feature declaration for one execution backend.

    Values are set once per backend class and queried by the compiler
    to adjust tiers before calling run / run_context.
    """

    backend_id: str
    repo_map_source: str           # e.g. "git-tracked-only"
    chat_file_mode: str            # e.g. "full-text-in-chat"
    supports_read_only_in_chat: bool
    dynamic_add_files: bool
    dynamic_create_files: bool
    shell_default: bool
    session_continuity: bool       # in-process executor cache

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "repo_map_source": self.repo_map_source,
            "chat_file_mode": self.chat_file_mode,
            "supports_read_only_in_chat": self.supports_read_only_in_chat,
            "dynamic_add_files": self.dynamic_add_files,
            "dynamic_create_files": self.dynamic_create_files,
            "shell_default": self.shell_default,
            "session_continuity": self.session_continuity,
        }


# Aider locked defaults (see P2-212 spec table)
AIDER_CAPABILITIES = BackendCapabilities(
    backend_id="aider",
    repo_map_source="git-tracked-only",
    chat_file_mode="full-text-in-chat",
    supports_read_only_in_chat=True,   # mcp-coder injects read tiers in prompt (P2-210)
    dynamic_add_files=True,
    dynamic_create_files=True,
    shell_default=False,
    session_continuity=True,
)
