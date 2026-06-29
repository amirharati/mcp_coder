from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.engine.git_diff import normalize_repo_path
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


def resolve_delegation_id(
    workspace: str | Path,
    *,
    delegation_id: str | None = None,
    latest: bool = False,
) -> str | None:
    """Resolve delegation_id from explicit id or latest snapshot row."""
    if delegation_id:
        return delegation_id
    if latest:
        return WorkspaceHistoryDB(workspace).get_latest_delegation_id()
    return None


@dataclass
class CheckpointDetail:
    delegation_id: str
    checkpoint_summary: str | None = None
    spec_path: str | None = None
    spec_report_path: str | None = None
    delegate_mode: str | None = None
    outcome: str | None = None
    model: str | None = None
    duration_ms: int | None = None
    tokens_total: int | None = None
    error_class: str | None = None
    timestamp_start: str | None = None
    timestamp_end: str | None = None
    created: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "checkpoint_summary": self.checkpoint_summary,
            "spec_path": self.spec_path,
            "spec_report_path": self.spec_report_path,
            "delegate_mode": self.delegate_mode,
            "outcome": self.outcome,
            "model": self.model,
            "duration_ms": self.duration_ms,
            "tokens_total": self.tokens_total,
            "error_class": self.error_class,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "created": self.created,
            "modified": self.modified,
            "deleted": self.deleted,
        }


def build_checkpoint_detail(
    workspace: str | Path,
    delegation_id: str,
) -> CheckpointDetail | None:
    """Lightweight checkpoint inspect — metadata + path lists, no diff bodies."""
    db = WorkspaceHistoryDB(workspace)
    snapshot = db.get_snapshot(delegation_id)
    if snapshot is None:
        return None

    created: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    for row in db.get_file_deltas(delegation_id):
        path = str(row["path"])
        change_type = str(row["change_type"])
        if change_type == "created":
            created.append(path)
        elif change_type == "modified":
            modified.append(path)
        elif change_type == "deleted":
            deleted.append(path)

    return CheckpointDetail(
        delegation_id=delegation_id,
        checkpoint_summary=(
            str(snapshot["checkpoint_summary"])
            if snapshot.get("checkpoint_summary")
            else None
        ),
        spec_path=snapshot.get("spec_path"),
        spec_report_path=snapshot.get("spec_report_path"),
        delegate_mode=snapshot.get("delegate_mode"),
        outcome=snapshot.get("outcome"),
        model=snapshot.get("model"),
        duration_ms=snapshot.get("duration_ms"),
        tokens_total=snapshot.get("tokens_total"),
        error_class=snapshot.get("error_class"),
        timestamp_start=snapshot.get("timestamp_start"),
        timestamp_end=snapshot.get("timestamp_end"),
        created=sorted(created),
        modified=sorted(modified),
        deleted=sorted(deleted),
    )


def _filter_diff_by_file_path(diff: DelegationDiff, file_path: str) -> DelegationDiff:
    rel = normalize_repo_path(file_path)
    diffs = {rel: diff.diffs[rel]} if rel in diff.diffs else {}
    return DelegationDiff(
        delegation_id=diff.delegation_id,
        created=[p for p in diff.created if p == rel],
        modified=[p for p in diff.modified if p == rel],
        deleted=[p for p in diff.deleted if p == rel],
        diffs=diffs,
        spec_path=diff.spec_path,
        timestamp_start=diff.timestamp_start,
        timestamp_end=diff.timestamp_end,
        diff_truncated=diff.diff_truncated,
        diff_truncated_paths=[p for p in diff.diff_truncated_paths if p == rel],
        checkpoint_summary=diff.checkpoint_summary,
    )


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
    file_path: str | None = None,
) -> list[dict[str, Any]]:
    """List recent delegations with delta counts."""
    db = WorkspaceHistoryDB(workspace)
    rows = db.list_snapshots(limit=limit, spec_path=spec_path, file_path=file_path)
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
            "spec_report_path": row.get("spec_report_path"),
        }
        out.append(item)
    return out


def list_interrupted_delegations(
    workspace: str | Path,
) -> list[dict[str, Any]]:
    """P15-019: surface delegations left with timestamp_end IS NULL.

    These are crash-orphaned delegations that the startup reconciliation pass
    will backfill. Each item carries the snapshot row fields plus whether a
    persisted before-manifest exists (so callers can tell legacy rows apart).
    """
    db = WorkspaceHistoryDB(workspace)
    rows = db.list_interrupted_snapshots()
    out: list[dict[str, Any]] = []
    for row in rows:
        delegation_id = str(row["delegation_id"])
        before_manifest = db.get_manifest(delegation_id, role="before")
        out.append(
            {
                "delegation_id": delegation_id,
                "timestamp_start": row.get("timestamp_start"),
                "spec_path": row.get("spec_path"),
                "mcp_session_id": row.get("mcp_session_id"),
                "workspace_path": row.get("workspace_path"),
                "before_manifest_entries": len(before_manifest),
                "has_before_manifest": bool(before_manifest),
            }
        )
    return out


def build_file_history(
    workspace: str | Path,
    file_path: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Per-file timeline across delegations."""
    db = WorkspaceHistoryDB(workspace)
    rel = normalize_repo_path(file_path)
    changes: list[dict[str, Any]] = []
    for row in db.get_file_history_rows(rel, limit=limit):
        change_type = str(row["change_type"])
        item: dict[str, Any] = {
            "delegation_id": row["delegation_id"],
            "checkpoint_summary": row.get("checkpoint_summary"),
            "spec_path": row.get("spec_path"),
            "spec_report_path": row.get("spec_report_path"),
            "timestamp_end": row.get("timestamp_end"),
            "change_type": change_type,
        }
        if change_type == "modified" and row.get("diff") and not row.get("is_binary"):
            raw_diffs = {rel: str(row["diff"])}
            diffs, truncated, truncated_paths = apply_diff_truncation(raw_diffs)
            if rel in diffs:
                item["diff"] = diffs[rel]
            if truncated:
                item["diff_truncated"] = True
                item["diff_truncated_paths"] = truncated_paths
        changes.append(item)
    return changes


def _snapshot_unavailable(workspace: str | Path) -> dict[str, Any] | None:
    if not is_snapshot_enabled():
        return {"found": False, "error": "workspace snapshot disabled"}
    db_path = WorkspaceHistoryDB(workspace).db_path
    if not db_path.is_file():
        return {"found": False, "error": "workspace_history.db not found"}
    return None


def delegation_diff_for_mcp(
    workspace: str | Path,
    delegation_id: str | None = None,
    *,
    latest: bool = False,
    file_path: str | None = None,
) -> dict[str, Any]:
    """MCP-safe fetch: returns {found: true, delegation_diff: ...} or {found: false, error}."""
    unavailable = _snapshot_unavailable(workspace)
    if unavailable is not None:
        return unavailable

    resolved = resolve_delegation_id(
        workspace, delegation_id=delegation_id, latest=latest
    )
    if not resolved:
        return {
            "found": False,
            "error": "delegation_id required or set latest=true",
        }

    diff = build_delegation_diff(workspace, resolved)
    if diff is None:
        return {"found": False, "error": f"delegation_id not found: {resolved}"}

    if file_path:
        diff = _filter_diff_by_file_path(diff, file_path)

    return {"found": True, "delegation_diff": diff.to_dict()}


def list_delegations_for_mcp(
    workspace: str | Path,
    *,
    limit: int = 20,
    spec_path: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    unavailable = _snapshot_unavailable(workspace)
    if unavailable is not None:
        return unavailable
    rows = list_delegations(
        workspace, limit=limit, spec_path=spec_path, file_path=file_path
    )
    return {"found": True, "delegations": rows}


def checkpoint_detail_for_mcp(
    workspace: str | Path,
    delegation_id: str | None = None,
    *,
    latest: bool = False,
) -> dict[str, Any]:
    unavailable = _snapshot_unavailable(workspace)
    if unavailable is not None:
        return unavailable

    resolved = resolve_delegation_id(
        workspace, delegation_id=delegation_id, latest=latest
    )
    if not resolved:
        return {
            "found": False,
            "error": "delegation_id required or set latest=true",
        }

    detail = build_checkpoint_detail(workspace, resolved)
    if detail is None:
        return {"found": False, "error": f"delegation_id not found: {resolved}"}

    return {"found": True, "checkpoint": detail.to_dict()}


def file_history_for_mcp(
    workspace: str | Path,
    file_path: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    unavailable = _snapshot_unavailable(workspace)
    if unavailable is not None:
        return unavailable

    rel = normalize_repo_path(file_path)
    changes = build_file_history(workspace, rel, limit=limit)
    return {"found": True, "file_path": rel, "changes": changes}


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
