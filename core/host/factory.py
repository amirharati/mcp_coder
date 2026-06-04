from __future__ import annotations

import os

from core.host.base import HostContextProvider
from core.host.cursor import CursorHostProvider, cursor_root
from core.host.null import NullHostProvider


def get_host_provider() -> HostContextProvider:
    raw = os.environ.get("MCP_CODER_HOST", "auto").strip().lower() or "auto"
    if raw == "none":
        return NullHostProvider()
    if raw == "cursor":
        return CursorHostProvider()
    if cursor_root().is_dir():
        return CursorHostProvider()
    return NullHostProvider()
