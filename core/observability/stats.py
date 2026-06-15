"""Observability storage stats for maintenance CLI (P6-005)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config.observability import (
    capture_for_training_enabled,
    resolve_observability_retention,
)
from core.rag.db import DelegationRagDB
from core.rag.search import rag_enabled, rag_stats
from core.rag.workspace_db import WorkspaceRagDB
from core.storage.paths import (
    delegation_rag_db_path,
    legacy_workspace_log_path,
    normalize_workspace,
    project_dir,
    sessions_root,
    workspace_rag_db_path,
)


def _count_jsonl_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _count_executor_turns_in_trace_file(path: Path) -> int:
    """Count executor-turn llm_call records in one trace JSONL file."""
    count = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                    if (
                        rec.get("type") == "llm_call"
                        and rec.get("role") == "executor"
                        and rec.get("executor_turn") is True
                    ):
                        count += 1
                except (json.JSONDecodeError, AttributeError):
                    pass
    except OSError:
        pass
    return count


def collect_observability_stats(workspace: str | Path) -> dict[str, Any]:
    """Disk usage and row counts for observability + RAG artifacts."""
    ws = normalize_workspace(workspace)
    project = project_dir(ws)

    delegation_rag = rag_stats(ws)
    workspace_rag_path = workspace_rag_db_path(ws)
    workspace_rag_rows = 0
    if workspace_rag_path.is_file():
        workspace_rag_rows = WorkspaceRagDB(ws).row_count()

    delegations_bytes = 0
    delegations_lines = 0
    trace_files = 0
    trace_bytes = 0
    blob_files = 0
    blob_bytes = 0
    training_files = 0
    training_bytes = 0
    executor_turns = 0
    session_count = 0

    sessions = sessions_root(ws)
    if sessions.is_dir():
        for session_dir in sorted(sessions.iterdir()):
            if not session_dir.is_dir():
                continue
            session_count += 1
            deleg_log = session_dir / "delegations.jsonl"
            if deleg_log.is_file():
                delegations_bytes += deleg_log.stat().st_size
                delegations_lines += _count_jsonl_lines(deleg_log)

            traces_dir = session_dir / "traces"
            if traces_dir.is_dir():
                for artifact in traces_dir.iterdir():
                    if not artifact.is_file():
                        continue
                    if artifact.name.endswith("-training.json"):
                        training_files += 1
                        training_bytes += artifact.stat().st_size
                    elif artifact.suffix == ".jsonl":
                        trace_files += 1
                        trace_bytes += artifact.stat().st_size
                        executor_turns += _count_executor_turns_in_trace_file(artifact)

            blobs_dir = session_dir / "context_packages"
            if blobs_dir.is_dir():
                for blob in blobs_dir.iterdir():
                    if blob.is_file() and blob.suffix == ".json":
                        blob_files += 1
                        blob_bytes += blob.stat().st_size

    legacy_log = legacy_workspace_log_path(ws)
    legacy_bytes = legacy_log.stat().st_size if legacy_log.is_file() else 0

    return {
        "workspace": ws,
        "project_dir": str(project),
        "observability": {
            "capture_for_training": capture_for_training_enabled(ws),
            "retention_policy": resolve_observability_retention(ws),
        },
        "delegation_rag": {
            "enabled": delegation_rag.get("enabled", False),
            "row_count": delegation_rag.get("row_count", 0),
            "db_path": delegation_rag.get("db_path") or str(delegation_rag_db_path(ws)),
            "last_indexed": delegation_rag.get("last_indexed"),
        },
        "workspace_rag": {
            "db_path": str(workspace_rag_path),
            "row_count": workspace_rag_rows,
            "exists": workspace_rag_path.is_file(),
        },
        "sessions": {
            "count": session_count,
            "delegations_jsonl_bytes": delegations_bytes,
            "delegations_jsonl_lines": delegations_lines,
            "legacy_delegations_jsonl_bytes": legacy_bytes,
        },
        "traces": {
            "file_count": trace_files,
            "total_bytes": trace_bytes,
            "training_file_count": training_files,
            "training_total_bytes": training_bytes,
            "executor_turns": executor_turns,
        },
        "context_packages": {
            "file_count": blob_files,
            "total_bytes": blob_bytes,
        },
        "rag_enabled": rag_enabled(ws),
    }
