from __future__ import annotations

from pathlib import Path

from core.host.base import HostSessionHint


class NullHostProvider:
    def resolve_active_session(self, workspace_path: str | Path) -> HostSessionHint:
        return HostSessionHint()
