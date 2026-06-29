from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from core.engine.git_diff import (
    compute_files_unexpected,
    files_touched_since_snapshot,
    snapshot_git_dirty,
)
from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.manifest import Manifest, diff_manifests
from core.workspace.walk import walk_workspace


def is_snapshot_enabled() -> bool:
    """Manifest walk is on unless MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT=1."""
    return os.environ.get("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", "").strip() not in (
        "1",
        "true",
        "yes",
    )


def read_snapshot_retention(workspace_path: str) -> str:
    """Read snapshot_retention from workspace config; cleanup is a no-op stub in P3-322a."""
    from core.storage.workspace_config import load_workspace_config

    config = load_workspace_config(workspace_path)
    value = config.get("snapshot_retention", "session")
    if value in ("ephemeral", "session", "all"):
        return str(value)
    return "session"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SnapshotSession:
    """Holds before-manifest state for one delegation run."""

    def __init__(
        self,
        before_manifest: Manifest,
        history_db: WorkspaceHistoryDB | None,
        walk_ms_before: int = 0,
        contract_paths_snapshotted: int = 0,
    ) -> None:
        self.before_manifest = before_manifest
        self.history_db = history_db
        self.walk_ms_before = walk_ms_before
        self.contract_paths_snapshotted = contract_paths_snapshotted


def begin_delegation_snapshot(
    *,
    workspace_path: str,
    delegation_id: str | None,
    mcp_session_id: str | None,
    timestamp_start: str | None,
    spec_path: str | None,
    contract_paths: list[str] | None = None,
) -> SnapshotSession | None:
    if not is_snapshot_enabled():
        return None

    read_snapshot_retention(workspace_path)

    t0 = time.perf_counter()
    before_manifest = walk_workspace(workspace_path)
    walk_ms = int((time.perf_counter() - t0) * 1000)

    history_db: WorkspaceHistoryDB | None = None
    contract_paths_snapshotted = 0
    if delegation_id and mcp_session_id:
        history_db = WorkspaceHistoryDB(workspace_path)
        begin_stats = history_db.begin_snapshot(
            delegation_id=delegation_id,
            mcp_session_id=mcp_session_id,
            timestamp_start=timestamp_start or utc_now_iso(),
            spec_path=spec_path,
            before_manifest=before_manifest,
            contract_paths=contract_paths,
        )
        contract_paths_snapshotted = begin_stats.get("contract_paths_snapshotted", 0)

    return SnapshotSession(
        before_manifest=before_manifest,
        history_db=history_db,
        walk_ms_before=walk_ms,
        contract_paths_snapshotted=contract_paths_snapshotted,
    )


def resolve_delegation_attribution(
    *,
    workspace_path: str,
    snapshot_session: SnapshotSession | None,
    contract_paths: list[str],
    edit_paths_rel: list[str],
    before_git: set[str] | None,
    before_mtimes: dict[str, float | None] | None,
    delegation_id: str | None = None,
) -> tuple[list[str], list[str], dict[str, Any] | None, bool, int]:
    """
    Resolve files_changed / files_unexpected after a delegation.

    Returns (files_changed, files_unexpected, workspace_snapshot_meta, used_git, walk_ms).
    """
    if snapshot_session is not None:
        t0 = time.perf_counter()
        after_manifest = walk_workspace(workspace_path)
        walk_ms_after = int((time.perf_counter() - t0) * 1000)
        total_walk_ms = snapshot_session.walk_ms_before + walk_ms_after

        delta = diff_manifests(snapshot_session.before_manifest, after_manifest)
        timestamp_end = utc_now_iso()

        diffs_stored = 0
        if snapshot_session.history_db and delegation_id:
            commit_stats = snapshot_session.history_db.commit_snapshot(
                delegation_id=delegation_id,
                timestamp_end=timestamp_end,
                delta=delta,
                after_manifest=after_manifest,
            )
            diffs_stored = commit_stats.get("diffs_stored", 0)

        paths = contract_paths if contract_paths else edit_paths_rel
        # B002 fix: filter Aider-internal cache files from files_changed so the
        # delegation log and diff don't show tooling noise.
        from core.engine.git_diff import _is_tooling_noise

        files_changed = [
            f for f in delta.all_changed if not _is_tooling_noise(f)
        ]
        files_unexpected = compute_files_unexpected(
            files_changed,
            paths,
            attribution_source="manifest",
        )

        after_git = snapshot_git_dirty(workspace_path)
        used_git = before_git is not None and after_git is not None

        from core.storage.paths import workspace_history_db_path

        workspace_snapshot: dict[str, Any] = {
            "attribution_source": "manifest",
            "delta": {
                "created": delta.created,
                "modified": delta.modified,
                "deleted": delta.deleted,
            },
            "db_path": str(workspace_history_db_path(workspace_path)),
            "diffs_stored": diffs_stored,
            "contract_paths_snapshotted": snapshot_session.contract_paths_snapshotted,
        }
        return files_changed, files_unexpected, workspace_snapshot, used_git, total_walk_ms

    files_changed, used_git = files_touched_since_snapshot(
        workspace_path,
        before_git,
        target_files=edit_paths_rel,
        before_mtimes=before_mtimes,
    )
    paths = contract_paths if contract_paths else edit_paths_rel
    files_unexpected = compute_files_unexpected(
        files_changed,
        paths,
        used_git=used_git,
        attribution_source="legacy",
    )
    return files_changed, files_unexpected, None, used_git, 0
