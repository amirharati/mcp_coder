"""Per-delegation session folder under MCP_CODER_HOME."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from datetime import datetime, timezone

from core.storage.paths import (
    mcp_coder_home,
    normalize_workspace,
    project_key,
    sessions_root,
    workspace_pointer_path,
)
from core.storage.workspace_session import save_workspace_pointer


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class DelegationStorage:
    project_key: str
    mcp_session_id: str
    session_dir: Path
    log_path: Path
    workspace_path: str


def write_workspace_pointer(workspace: str | Path) -> Path:
    ws = normalize_workspace(workspace)
    key = project_key(ws)
    home = mcp_coder_home()
    return save_workspace_pointer(
        ws,
        {
            "project_key": key,
            "mcp_coder_home": str(home),
            "sessions_root": str(sessions_root(ws)),
        },
    )


def prepare_delegation_storage(workspace: str | Path) -> DelegationStorage:
    """Create project registry entry, new session folder, and workspace pointer."""
    from core.host.base import HostSessionHint
    from core.session.policy import POLICY_ALWAYS_NEW
    from core.session.store import SessionStore

    result = SessionStore().acquire(workspace, POLICY_ALWAYS_NEW, HostSessionHint())
    return DelegationStorage(
        project_key=result.project_key,
        mcp_session_id=result.mcp_session_id,
        session_dir=result.session_dir,
        log_path=result.log_path,
        workspace_path=result.workspace_path,
    )


def touch_session_last_delegation(session_dir: Path) -> None:
    session_json_path = session_dir / "session.json"
    if not session_json_path.is_file():
        return
    data = json.loads(session_json_path.read_text(encoding="utf-8"))
    data["last_delegation_at"] = _utc_now_iso()
    session_json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
