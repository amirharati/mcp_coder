"""Steady-state agent checkpoint (P13-007).

Complementary to `SupervisorState` (escalation-only, expiring, intra-delegation
resume) and `ProjectState` (project memory: risks/decisions/hot areas).

`AgentCheckpoint` stores the agent's *identity + lifecycle position* at the end
of every delegation (success / error / escalated), non-expiring, one file per
project. This is what makes the agent genuinely stateful across process
restarts: CLI and server mode both rehydrate from this file, so the in-memory
`_SUPERVISOR_REGISTRY` becomes a cache rather than the source of truth.

Path: ``mcp_coder_home() / projects / <project_key> / agent_state.json``
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.storage.paths import mcp_coder_home

logger = logging.getLogger(__name__)


@dataclass
class AgentCheckpoint:
    """Steady-state snapshot of a SupervisorAgent at delegation end.

    Non-expiring; overwritten each delegation. Distinct from `SupervisorState`
    (which is escalation-only, expiring, and carries turn_index / decision_log /
    questions for intra-delegation resume).
    """

    project_key: str
    last_delegation_id: str | None
    last_outcome: str  # "success" | "error" | "escalated"
    last_spec_path: str | None
    last_finished_at: str  # ISO-8601 UTC
    lifecycle_context: dict = field(default_factory=dict)
    # NOTE: turn_index / decision_log / questions are NOT here — those live in
    # SupervisorState (escalation-only, expiring). AgentCheckpoint is the
    # non-expiring identity + lifecycle-position store.

    def save(self) -> Path:
        """Atomically write the checkpoint to disk (temp + os.replace)."""
        path = self.state_path(self.project_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
        return path

    @classmethod
    def find_for_project(cls, project_key: str) -> "AgentCheckpoint | None":
        """Load the checkpoint for a project, or None if missing/corrupt.

        Never raises — a bad checkpoint must not block delegations. Logs a
        warning and returns None on any parse / IO error.
        """
        path = cls.state_path(project_key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Backward-compat: older files may lack lifecycle_context
            data.setdefault("lifecycle_context", {})
            return cls(**data)
        except Exception as exc:
            logger.warning(
                "Ignoring corrupt agent checkpoint at %s: %s", path, exc
            )
            return None

    @staticmethod
    def state_path(project_key: str) -> Path:
        return mcp_coder_home() / "projects" / project_key / "agent_state.json"


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with trailing Z (matches obs.utc_now_iso format)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
