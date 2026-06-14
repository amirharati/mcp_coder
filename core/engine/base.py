from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.context.package import ContextPackage
    from core.engine.capabilities import BackendCapabilities
    from core.engine.interception_profile import InterceptionProfile


@dataclass
class BackendRunRequest:
    """Aider-specific translated run request produced by translate_context_package."""

    prompt: str
    fnames: list[str]       # repo-relative edit-full paths ONLY
    edit_paths: list[str]   # same as fnames (contract edit scope for audit)


@dataclass
class ExecutionResult:
    """Normalized outcome from any execution backend (Aider, OpenCode, …)."""

    success: bool
    output: str
    files_changed: list[str] = field(default_factory=list)
    files_unexpected: list[str] = field(default_factory=list)
    model: str | None = None
    error: str | None = None
    error_class: str | None = None
    tokens: dict[str, Any] = field(default_factory=dict)
    executor_reused: bool = False
    executor_recreated: bool = False
    prompt_used: str | None = None  # set by run_context for usage/JSONL logging
    workspace_snapshot: dict[str, Any] | None = None
    workspace_snapshot_ms: int | None = None


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
    @abstractmethod
    def interception_profile(self) -> "InterceptionProfile":
        """Declare how this backend's LLM calls are intercepted for observability."""

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

    def capabilities(self) -> "BackendCapabilities":
        """Return the static capability declaration for this backend.

        Engines must override. The compiler calls this before run_context
        to adjust tiers for what the backend can honour.
        """
        raise NotImplementedError(
            f"{self.backend_id} does not implement capabilities()"
        )

    def run_context(
        self,
        package: "ContextPackage",
        *,
        workspace_path: str,
        mcp_session_id: str | None = None,
        host_transcript: str | None = None,
    ) -> ExecutionResult:
        """Execute from a ContextPackage (L2 → L3 adapter hinge).

        Default raises NotImplementedError. AiderEngine overrides this.
        Future backends may not support it.
        """
        raise NotImplementedError(
            f"{self.backend_id} does not support run_context"
        )
