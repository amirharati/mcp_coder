"""In-process Aider Coder cache keyed by mcp_session_id (single-threaded MCP stdio)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_CODERS: dict[str, tuple[Any, tuple[frozenset[str], str]]] = {}


def clear_executor_cache() -> None:
    _CODERS.clear()


def drop_coder(mcp_session_id: str) -> None:
    _CODERS.pop(mcp_session_id, None)


def get_or_create_coder(
    mcp_session_id: str,
    edit_paths: list[str],
    create_fn: Callable[[], T],
    *,
    context_package_key: str | None = None,
) -> tuple[T, bool, bool]:
    """
    Return (bundle, executor_reused, executor_recreated).

    bundle is whatever create_fn returns (typically coder + io + buffer).
    executor_reused: cache hit with same edit_paths + context package key.
    executor_recreated: new Coder instance (cache miss or cache token changed).
    """
    cache_token = (frozenset(edit_paths), context_package_key or "")
    cached = _CODERS.get(mcp_session_id)
    if cached is not None and cached[1] == cache_token:
        return cached[0], True, False

    bundle = create_fn()
    _CODERS[mcp_session_id] = (bundle, cache_token)
    return bundle, False, True
