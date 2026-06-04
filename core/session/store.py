from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.host.base import HostSessionHint
from core.session.activity import sessions_root_by_key
from core.session.policy import POLICY_ALIGN_HOST, POLICY_ALWAYS_NEW
from core.storage.paths import (
    ensure_mcp_coder_home,
    normalize_workspace,
    project_key,
    sessions_root,
)
from core.storage.project_registry import ensure_project
from core.storage.session_paths import write_workspace_pointer


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_epoch(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        text = iso.replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


@dataclass(frozen=True)
class SessionAcquireResult:
    project_key: str
    mcp_session_id: str
    session_dir: Path
    log_path: Path
    workspace_path: str
    is_new: bool
    session_action: str
    session_reason: str
    session_policy: str


def find_latest_mcp_session(project_key_value: str, host_session_id: str) -> str | None:
    root = sessions_root_by_key(project_key_value)
    if not root.is_dir():
        return None

    best_id: str | None = None
    best_ts = 0.0
    for session_json in root.glob("*/session.json"):
        try:
            data = json.loads(session_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("host_session_id") != host_session_id:
            continue
        ts = _parse_iso_epoch(data.get("last_delegation_at"))
        if ts >= best_ts:
            best_ts = ts
            best_id = data.get("mcp_session_id")
    return best_id


def _create_session_folder(
    ws: str,
    key: str,
    policy: str,
    *,
    mcp_session_id: str | None = None,
) -> SessionAcquireResult:
    mid = mcp_session_id or str(uuid.uuid4())
    session_dir = sessions_root_by_key(key) / mid
    session_dir.mkdir(parents=True, exist_ok=True)
    now = _utc_now_iso()
    session_json = {
        "mcp_session_id": mid,
        "project_key": key,
        "workspace_path": ws,
        "session_policy": policy,
        "host_kind": None,
        "host_session_id": None,
        "host_transcript_path": None,
        "created_at": now,
        "last_delegation_at": now,
    }
    (session_dir / "session.json").write_text(
        json.dumps(session_json, indent=2) + "\n",
        encoding="utf-8",
    )
    log_path = session_dir / "delegations.jsonl"
    return SessionAcquireResult(
        project_key=key,
        mcp_session_id=mid,
        session_dir=session_dir,
        log_path=log_path,
        workspace_path=ws,
        is_new=True,
        session_action="new",
        session_reason="policy_always_new",
        session_policy=policy,
    )


class SessionStore:
    def acquire(
        self,
        workspace: str | Path,
        policy: str,
        host_hint: HostSessionHint,
    ) -> SessionAcquireResult:
        ensure_mcp_coder_home()
        ws = normalize_workspace(workspace)
        ensure_project(ws)
        write_workspace_pointer(ws)
        key = project_key(ws)

        if policy == POLICY_ALWAYS_NEW:
            result = _create_session_folder(ws, key, policy)
            return SessionAcquireResult(
                project_key=result.project_key,
                mcp_session_id=result.mcp_session_id,
                session_dir=result.session_dir,
                log_path=result.log_path,
                workspace_path=result.workspace_path,
                is_new=True,
                session_action="new",
                session_reason="policy_always_new",
                session_policy=POLICY_ALWAYS_NEW,
            )

        if policy != POLICY_ALIGN_HOST:
            policy = POLICY_ALWAYS_NEW
            return self.acquire(workspace, policy, host_hint)

        if not host_hint.host_session_id:
            result = _create_session_folder(ws, key, policy)
            return SessionAcquireResult(
                project_key=result.project_key,
                mcp_session_id=result.mcp_session_id,
                session_dir=result.session_dir,
                log_path=result.log_path,
                workspace_path=result.workspace_path,
                is_new=True,
                session_action="new",
                session_reason="align_host_no_host_id",
                session_policy=POLICY_ALIGN_HOST,
            )

        existing = find_latest_mcp_session(key, host_hint.host_session_id)
        if existing is None:
            result = _create_session_folder(ws, key, policy)
            return SessionAcquireResult(
                project_key=result.project_key,
                mcp_session_id=result.mcp_session_id,
                session_dir=result.session_dir,
                log_path=result.log_path,
                workspace_path=result.workspace_path,
                is_new=True,
                session_action="new",
                session_reason="align_host_new",
                session_policy=POLICY_ALIGN_HOST,
            )

        session_dir = sessions_root_by_key(key) / existing
        log_path = session_dir / "delegations.jsonl"
        return SessionAcquireResult(
            project_key=key,
            mcp_session_id=existing,
            session_dir=session_dir,
            log_path=log_path,
            workspace_path=ws,
            is_new=False,
            session_action="reuse",
            session_reason="align_host_reuse",
            session_policy=POLICY_ALIGN_HOST,
        )


def sessions_root_for_workspace(workspace: str | Path) -> Path:
    return sessions_root(workspace)
