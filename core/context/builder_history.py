"""Builder history gather (P4-001b).

Queries workspace_history.db for recent delegation summaries fed to the
cheap-LLM context builder. Summaries only — no full diffs (v0, too heavy).
Non-fatal: returns empty lists when snapshots are disabled or the DB is missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.engine.git_diff import normalize_repo_path
from core.workspace.history_query import list_delegations
from core.workspace.snapshot import is_snapshot_enabled

_SUMMARY_FIELDS = (
    "delegation_id",
    "outcome",
    "checkpoint_summary",
    "created_count",
    "modified_count",
    "delegate_mode",
    "timestamp_end",
)


@dataclass
class BuilderHistoryContext:
    same_spec: list[dict[str, Any]] = field(default_factory=list)
    project_recent: list[dict[str, Any]] = field(default_factory=list)
    prior_reasoning: list[Any] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.same_spec and not self.project_recent


def _summary_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in _SUMMARY_FIELDS}


def _env_limit(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        val = int(raw)
        return val if val > 0 else default
    except (ValueError, TypeError):
        return default


def gather_builder_history(
    workspace: Path,
    *,
    spec_path: str | None,
    limit_same_spec: int = 5,
    limit_project: int = 5,
) -> BuilderHistoryContext:
    """Recent delegation summaries for the builder prompt.

    same_spec: recent delegations for this spec_path.
    project_recent: recent project-wide rows excluding those already in same_spec.
    """
    if not is_snapshot_enabled():
        return BuilderHistoryContext()

    same_spec_limit = _env_limit(
        "MCP_CODER_BUILDER_HISTORY_SPEC_LIMIT", limit_same_spec
    )
    project_limit = _env_limit(
        "MCP_CODER_BUILDER_HISTORY_PROJECT_LIMIT", limit_project
    )

    try:
        same_spec_rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        if spec_path:
            spec_rel = normalize_repo_path(spec_path)
            for row in list_delegations(
                workspace, limit=same_spec_limit, spec_path=spec_rel
            ):
                same_spec_rows.append(_summary_row(row))
                did = row.get("delegation_id")
                if isinstance(did, str):
                    seen_ids.add(did)

        project_rows: list[dict[str, Any]] = []
        for row in list_delegations(workspace, limit=project_limit + len(seen_ids)):
            did = row.get("delegation_id")
            if isinstance(did, str) and did in seen_ids:
                continue
            project_rows.append(_summary_row(row))
            if len(project_rows) >= project_limit:
                break

        return BuilderHistoryContext(
            same_spec=same_spec_rows,
            project_recent=project_rows,
        )
    except Exception:
        # History is best-effort context; never block delegation.
        return BuilderHistoryContext()
