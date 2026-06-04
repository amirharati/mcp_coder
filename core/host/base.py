from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class HostSessionHint:
    host_kind: str | None = None
    host_session_id: str | None = None
    host_transcript_path: str | None = None
    host_project_slug: str | None = None
    resolve_error: str | None = None
    host_resolve_method: str | None = None

    @property
    def resolved(self) -> bool:
        return self.host_kind is not None and self.host_session_id is not None


class HostContextProvider(Protocol):
    def resolve_active_session(self, workspace_path: str | Path) -> HostSessionHint: ...
