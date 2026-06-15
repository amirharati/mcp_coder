"""Internal LLM HTTP proxy (P9-003)."""

from core.proxy.local_proxy import (
    ensure_local_llm_proxy,
    get_local_llm_proxy,
    reset_local_llm_proxy_for_tests,
)

__all__ = [
    "ensure_local_llm_proxy",
    "get_local_llm_proxy",
    "reset_local_llm_proxy_for_tests",
]
