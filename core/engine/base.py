from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """Normalized outcome from any execution backend (Aider, OpenCode, …)."""

    success: bool
    output: str
    files_changed: list[str] = field(default_factory=list)
    model: str | None = None
    error: str | None = None
    tokens: dict[str, Any] = field(default_factory=dict)
    executor_reused: bool = False
    executor_recreated: bool = False


class ExecutionEngine(ABC):
    """
    Adapter interface for delegated coding agents.

    Each CLI / API tool implements this contract. The MCP server calls
    get_engine(backend) and invokes run() — it must not import Aider (or others) directly.
    """

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Stable id stored in delegation logs and the MCP `backend` argument."""

    @property
    def model_name(self) -> str | None:
        """Executor model id, if known before run (optional)."""
        return None

    @abstractmethod
    def run(
        self,
        prompt: str,
        target_files: list[str],
        *,
        workspace_path: str,
        mcp_session_id: str | None = None,
    ) -> ExecutionResult:
        """Execute one delegation in workspace_path."""
