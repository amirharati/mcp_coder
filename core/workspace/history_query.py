from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.snapshot import is_snapshot_enabled


def _diff_max_chars_per_file() -> int:
    raw = os.environ.get("MCP_CODER_DIFF_MAX_CHARS_PER_FILE", "8000").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 8000


def _diff_max_total_chars() -> int:
    raw = os.environ.get("MCP_CODER_DIFF_MAX_TOTAL_CHARS", "32000").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 32000


def apply_diff_truncation(
    diffs: dict[str, str],
) -> tuple[dict[str, str], bool, list[str]]:
    """Truncate per-file and total diff size; return (diffs, truncated, truncated_paths)."""
    per_file = _diff_max_chars_per_file()
    total_max = _diff_max_total_chars()
    truncated_paths: list[str] = []
    out: dict[str, str] = {}
    total_used = 0

    for path in sorted(diffs):
        text = diffs[path]
        if len(text) > per_file:
            text = text[: per_file - 20] + "\n…[diff truncated]\n"
            truncated_paths.append(path)

        remaining = total_max - total_used
        if remaining <= 0:
            truncated_paths.append(path)
            continue

        if len(text) > remaining:
            text = text[: max(0, remaining - 20)] + "\n…[diff truncated]\n"
            if path not in truncated_paths:
                truncated_paths.append(path)

        if not text:
            continue

        out[path] = text
        total_used += len(text)

    return out, bool(truncated_paths), sorted(set(truncated_paths))


@dataclass
class DelegationDiff:
    delegation_id: str
    created: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    diffs: dict[str, str] = field(default_factory=dict)
    spec_path: str | None = None
    timestamp_start: str | None = None
    timestamp_end: str | None = None
    diff_truncated: bool = False
    diff_truncated_paths: list[str] = field(default_factory=list)
    checkpoint_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "delegation_id": self.delegation_id,
            "created": self.created,
            "modified": self.modified,
            "deleted": self.deleted,
            "diffs": self.diffs,
            "spec_path": self.spec_path,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
        }
        if self.checkpoint_summary:
            payload["checkpoint_summary"] = self.checkpoint_summary
        if self.diff_truncated:
            payload["diff_truncated"] = True
            payload["diff_truncated_paths"] = self.diff_truncated_paths
        return payload

    @property
    def all_paths(self) -> list[str]:
        return sorted({*self.created, *self.modified, *self.deleted})


def build_delegation_diff(
    workspace: str | Path,
    delegation_id: str,
) -> DelegationDiff | None:
    """Build DelegationDiff from workspace_history.db; None when snapshot row missing."""
    db = WorkspaceHistoryDB(workspace)
    snapshot = db.get_snapshot(delegation_id)
    if snapshot is None:
        return None

    created: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    raw_diffs: dict[str, str] = {}

    for row in db.get_file_deltas(delegation_id):
        path = str(row["path"])
        change_type = str(row["change_type"])
        if change_type == "created":
            created.append(path)
        elif change_type == "modified":
            modified.append(path)
            diff_text = row.get("diff")
            if diff_text and not row.get("is_binary"):
                raw_diffs[path] = str(diff_text)
        elif change_type == "deleted":
            deleted.append(path)

    diffs, truncated, truncated_paths = apply_diff_truncation(raw_diffs)

    summary = snapshot.get("checkpoint_summary")
    return DelegationDiff(
        delegation_id=delegation_id,
        created=sorted(created),
        modified=sorted(modified),
        deleted=sorted(deleted),
        diffs=diffs,
        spec_path=snapshot.get("spec_path"),
        timestamp_start=snapshot.get("timestamp_start"),
        timestamp_end=snapshot.get("timestamp_end"),
        diff_truncated=truncated,
        diff_truncated_paths=truncated_paths,
        checkpoint_summary=str(summary) if summary else None,
    )


def list_delegations(
    workspace: str | Path,
    *,
    limit: int = 20,
    spec_path: str | None = None,
) -> list[dict[str, Any]]:
    """List recent delegations with delta counts."""
    db = WorkspaceHistoryDB(workspace)
    rows = db.list_snapshots(limit=limit, spec_path=spec_path)
    out: list[dict[str, Any]] = []
    for row in rows:
        delegation_id = str(row["delegation_id"])
        delta_created = row.get("delta_created")
        delta_modified = row.get("delta_modified")
        delta_deleted = row.get("delta_deleted")
        if (
            delta_created is not None
            and delta_modified is not None
            and delta_deleted is not None
        ):
            created = int(delta_created)
            modified = int(delta_modified)
            deleted = int(delta_deleted)
        else:
            deltas = db.get_file_deltas(delegation_id)
            created = sum(1 for d in deltas if d["change_type"] == "created")
            modified = sum(1 for d in deltas if d["change_type"] == "modified")
            deleted = sum(1 for d in deltas if d["change_type"] == "deleted")
        item: dict[str, Any] = {
            "delegation_id": delegation_id,
            "timestamp_start": row.get("timestamp_start"),
            "timestamp_end": row.get("timestamp_end"),
            "spec_path": row.get("spec_path"),
            "created_count": created,
            "modified_count": modified,
            "deleted_count": deleted,
            "checkpoint_summary": row.get("checkpoint_summary"),
            "delegate_mode": row.get("delegate_mode"),
            "outcome": row.get("outcome"),
            "model": row.get("model"),
            "duration_ms": row.get("duration_ms"),
            "tokens_total": row.get("tokens_total"),
            "error_class": row.get("error_class"),
        }
        out.append(item)
    return out


def delegation_diff_for_mcp(
    workspace: str | Path,
    delegation_id: str,
) -> dict[str, Any]:
    """MCP-safe fetch: returns {found: true, delegation_diff: ...} or {found: false, error}."""
    if not is_snapshot_enabled():
        return {"found": False, "error": "workspace snapshot disabled"}

    db_path = WorkspaceHistoryDB(workspace).db_path
    if not db_path.is_file():
        return {"found": False, "error": "workspace_history.db not found"}

    diff = build_delegation_diff(workspace, delegation_id)
    if diff is None:
        return {"found": False, "error": f"delegation_id not found: {delegation_id}"}

    return {"found": True, "delegation_diff": diff.to_dict()}


def safe_delegation_diff_dict(
    workspace: str | Path,
    delegation_id: str,
) -> dict[str, Any] | None:
    """Build delegation_diff for delegate response; None on missing data or errors."""
    if not is_snapshot_enabled():
        return None
    try:
        diff = build_delegation_diff(workspace, delegation_id)
        return diff.to_dict() if diff is not None else None
    except Exception as exc:
        from core.logging.server_log import server_log_emit

        server_log_emit(
            "delegation_diff_read_failed",
            level="warn",
            delegation_id=delegation_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        return None
