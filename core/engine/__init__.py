"""
Execution adapters: one module per backend, registered via register_engine().

Import this package (or call ensure_backends_loaded()) before get_engine().
"""

from core.engine.aider_engine import AiderEngine  # noqa: F401 — registers "aider"
from core.engine.base import ExecutionEngine, ExecutionResult
from core.engine.factory import (
    UnknownBackendError,
    default_backend,
    get_engine,
    list_backends,
    register_engine,
)

__all__ = [
    "AiderEngine",
    "ExecutionEngine",
    "ExecutionResult",
    "UnknownBackendError",
    "default_backend",
    "get_engine",
    "list_backends",
    "register_engine",
]
