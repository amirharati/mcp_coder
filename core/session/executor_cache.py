"""In-process Aider Coder cache keyed by mcp_session_id (single-threaded MCP stdio)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_CODERS: dict[str, tuple[Any, frozenset[str]]] = {}


def clear_executor_cache() -> None:
    _CODERS.clear()


def drop_coder(mcp_session_id: str) -> None:
    _CODERS.pop(mcp_session_id, None)


def get_or_create_coder(
    mcp_session_id: str,
    target_files: list[str],
    create_fn: Callable[[], T],
) -> tuple[T, bool, bool]:
    """
    Return (bundle, executor_reused, executor_recreated).

    bundle is whatever create_fn returns (typically coder + io + buffer).
    executor_reused: cache hit with same target_files set.
    executor_recreated: new Coder instance (cache miss or target_files changed).
    """
    key_files = frozenset(target_files)
    cached = _CODERS.get(mcp_session_id)
    if cached is not None and cached[1] == key_files:
        return cached[0], True, False

    bundle = create_fn()
    _CODERS[mcp_session_id] = (bundle, key_files)
    return bundle, False, True
