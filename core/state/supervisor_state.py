from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from core.state.project_key import ProjectKeyResolver
from core.storage.paths import mcp_coder_home

logger = logging.getLogger(__name__)


class ResumeTokenNotFound(Exception):
    pass


class ResumeTokenExpired(Exception):
    def __init__(self, expired_at: str):
        super().__init__(f"Resume token expired at {expired_at}")
        self.expired_at = expired_at


@dataclass
class SupervisorState:
    resume_token: str
    spec_path: str | None
    project_key: str
    turn_index: int
    plan: str | None
    decision_log: list[dict]
    completed_turn_artifacts: list[dict]
    pause_reason: str
    questions: list[str]
    context_ref: str
    paused_at: str
    expires_at: str
    # P13-005: lifecycle context persisted for coherent resume events
    lifecycle_context: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        spec_path: str | None,
        context_ref: str,
        plan: str | None,
        decision_log: list[dict],
        completed_turn_artifacts: list[dict],
        turn_index: int,
        questions: list[str],
        pause_reason: str = "needs_input",
        ttl_seconds: int = 86400,
        lifecycle_context: dict | None = None,
    ) -> "SupervisorState":
        ttl = _resolve_ttl(ttl_seconds)
        paused = datetime.now(timezone.utc)
        expires = paused + timedelta(seconds=ttl)
        return cls(
            resume_token=str(uuid4()),
            spec_path=spec_path,
            project_key=ProjectKeyResolver.from_spec_path(spec_path),
            turn_index=int(turn_index),
            plan=plan,
            decision_log=list(decision_log or []),
            completed_turn_artifacts=list(completed_turn_artifacts or []),
            pause_reason=pause_reason,
            questions=list(questions or []),
            context_ref=context_ref,
            paused_at=_iso_z(paused),
            expires_at=_iso_z(expires),
            lifecycle_context=dict(lifecycle_context or {}),
        )

    def save(self) -> Path:
        path = self.state_dir(self.project_key) / f"{self.resume_token}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
        return path

    @classmethod
    def load(cls, resume_token: str, project_key: str) -> "SupervisorState":
        path = cls.state_dir(project_key) / f"{resume_token}.json"
        if not path.is_file():
            raise ResumeTokenNotFound(resume_token)
        data = json.loads(path.read_text(encoding="utf-8"))
        # P13-005: backward compat — old state files lack lifecycle_context
        data.setdefault("lifecycle_context", {})
        state = cls(**data)
        if _parse_iso(state.expires_at) <= datetime.now(timezone.utc):
            raise ResumeTokenExpired(state.expires_at)
        return state

    @classmethod
    def find_and_load(cls, resume_token: str) -> "SupervisorState":
        pattern = f"projects/**/supervisor_states/{resume_token}.json"
        candidates = sorted(mcp_coder_home().glob(pattern))
        if not candidates:
            raise ResumeTokenNotFound(resume_token)
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
        if data.get("project_key"):
            project_key = str(data.get("project_key"))
        else:
            rel = candidates[0].relative_to(mcp_coder_home() / "projects")
            project_key = "/".join(rel.parts[:-2])
        return cls.load(resume_token, project_key)

    @classmethod
    def find_latest(cls, project_key: str) -> "SupervisorState | None":
        """Return the most recent non-expired state for this project key."""
        state_root = cls.state_dir(project_key)
        if not state_root.is_dir():
            return None

        latest: SupervisorState | None = None
        latest_paused_at: datetime | None = None
        now = datetime.now(timezone.utc)

        for path in sorted(state_root.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                state = cls(**data)
                if _parse_iso(state.expires_at) <= now:
                    continue
                paused_at = _parse_iso(state.paused_at)
            except Exception as exc:
                logger.warning("Skipping invalid supervisor state file %s: %s", path, exc)
                continue
            if latest is None or latest_paused_at is None or paused_at > latest_paused_at:
                latest = state
                latest_paused_at = paused_at
        return latest

    @staticmethod
    def state_dir(project_key: str) -> Path:
        return mcp_coder_home() / "projects" / project_key / "supervisor_states"


def _resolve_ttl(default_ttl: int) -> int:
    raw = os.environ.get("MCP_CODER_RESUME_TOKEN_TTL", "").strip()
    if not raw:
        return default_ttl
    try:
        value = int(raw)
    except ValueError:
        return default_ttl
    return value if value > 0 else default_ttl


def _parse_iso(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw).astimezone(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
