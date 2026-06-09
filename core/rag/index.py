from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.config.rag import rag_enabled
from core.context.summary import redact_secrets
from core.logging.delegation_log import log_stderr
from core.rag.db import DelegationRagDB
from core.rag.models import DelegationIndexRow
from core.storage.paths import normalize_workspace, workspace_history_db_path
from core.workspace.checkpoint_summary import resolve_checkpoint_summary
_TASK_PREVIEW_MAX = 500


def build_searchable_text(
    *,
    checkpoint_summary: str | None,
    task_preview: str | None,
    spec_path: str | None,
    files_changed: str | list[str] | None,
    outcome: str | None,
    delegate_mode: str | None,
) -> str:
    if isinstance(files_changed, list):
        files_tokenized = " ".join(files_changed)
    elif files_changed:
        files_tokenized = str(files_changed).replace(",", " ")
    else:
        files_tokenized = None

    parts: list[str] = []
    for value in (
        checkpoint_summary,
        task_preview,
        spec_path,
        files_tokenized,
        outcome,
        delegate_mode,
    ):
        if value:
            text = str(value).strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def make_task_preview(task: str) -> str:
    redacted = redact_secrets(task.strip())
    if len(redacted) <= _TASK_PREVIEW_MAX:
        return redacted
    return redacted[: _TASK_PREVIEW_MAX - 1] + "…"


def _files_changed_csv(paths: list[str]) -> str | None:
    if not paths:
        return None
    return ",".join(sorted(paths))


def index_delegation_after_delegate(
    *,
    workspace: str | Path,
    delegation_id: str,
    timestamp_end: str,
    task: str,
    delegate_mode: str | None,
    outcome: str | None,
    files_changed: list[str],
    spec_path: str | None = None,
    spec_report_path: str | None = None,
    checkpoint_summary: str | None = None,
) -> None:
    """Upsert RAG row after delegation; warn-only on failure."""
    if not rag_enabled(workspace):
        return
    try:
        summary = checkpoint_summary
        if not summary:
            summary = resolve_checkpoint_summary(
                task=task,
                spec_path=spec_path,
                workspace=workspace,
            )
        task_preview = make_task_preview(task)
        searchable = build_searchable_text(
            checkpoint_summary=summary,
            task_preview=task_preview,
            spec_path=spec_path,
            files_changed=files_changed,
            outcome=outcome,
            delegate_mode=delegate_mode,
        )
        row = DelegationIndexRow(
            delegation_id=delegation_id,
            workspace_path=normalize_workspace(workspace),
            timestamp_end=timestamp_end,
            spec_path=spec_path,
            spec_report_path=spec_report_path,
            checkpoint_summary=summary,
            task_preview=task_preview,
            delegate_mode=delegate_mode,
            outcome=outcome,
            files_changed=_files_changed_csv(files_changed),
            searchable_text=searchable,
        )
        DelegationRagDB(workspace).upsert(row)
    except Exception as exc:
        log_stderr(f"[mcp-coder] rag index warning: {exc}")


def _files_from_history(conn: sqlite3.Connection, delegation_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT path FROM file_deltas WHERE delegation_id = ? ORDER BY path",
        (delegation_id,),
    ).fetchall()
    return [str(r[0]) for r in rows]


def _task_from_jsonl(workspace: Path, delegation_id: str) -> str | None:
    from core.storage.paths import sessions_root

    root = sessions_root(workspace)
    if not root.is_dir():
        return None
    for session_dir in root.iterdir():
        if not session_dir.is_dir():
            continue
        log_path = session_dir / "delegations.jsonl"
        if not log_path.is_file():
            continue
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("delegation_id") != delegation_id:
                continue
            mcp_request = record.get("mcp_request") or {}
            task = mcp_request.get("task")
            if isinstance(task, str) and task.strip():
                return task
    return None


def backfill_from_history(workspace: str | Path) -> int:
    """Index snapshot rows missing from RAG DB; returns count indexed."""
    if not rag_enabled(workspace):
        return 0

    history_path = workspace_history_db_path(workspace)
    if not history_path.is_file():
        return 0

    rag_db = DelegationRagDB(workspace)
    ws = Path(workspace).resolve()
    indexed = 0

    with sqlite3.connect(str(history_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT delegation_id, timestamp_end, spec_path, spec_report_path,
                   checkpoint_summary, delegate_mode, outcome
            FROM snapshots
            ORDER BY timestamp_end ASC, timestamp_start ASC
            """
        ).fetchall()

        for snap in rows:
            did = str(snap["delegation_id"])
            if rag_db.has_delegation(did):
                continue

            files = _files_from_history(conn, did)
            summary = snap["checkpoint_summary"]
            if summary is not None:
                summary = str(summary)

            task_preview: str | None = None
            jsonl_task = _task_from_jsonl(ws, did)
            if jsonl_task:
                task_preview = make_task_preview(jsonl_task)
            elif summary:
                task_preview = summary[:_TASK_PREVIEW_MAX]

            searchable = build_searchable_text(
                checkpoint_summary=summary,
                task_preview=task_preview,
                spec_path=str(snap["spec_path"]) if snap["spec_path"] else None,
                files_changed=files,
                outcome=str(snap["outcome"]) if snap["outcome"] else None,
                delegate_mode=str(snap["delegate_mode"]) if snap["delegate_mode"] else None,
            )
            row = DelegationIndexRow(
                delegation_id=did,
                workspace_path=normalize_workspace(workspace),
                timestamp_end=str(snap["timestamp_end"]) if snap["timestamp_end"] else None,
                spec_path=str(snap["spec_path"]) if snap["spec_path"] else None,
                spec_report_path=(
                    str(snap["spec_report_path"]) if snap["spec_report_path"] else None
                ),
                checkpoint_summary=summary,
                task_preview=task_preview,
                delegate_mode=str(snap["delegate_mode"]) if snap["delegate_mode"] else None,
                outcome=str(snap["outcome"]) if snap["outcome"] else None,
                files_changed=_files_changed_csv(files),
                searchable_text=searchable,
            )
            rag_db.upsert(row)
            indexed += 1

    return indexed


def rebuild_fts(workspace: str | Path) -> None:
    """Rebuild FTS index from content table (repair helper)."""
    db = DelegationRagDB(workspace)
    if not db.db_path.is_file():
        return
    with db._connect() as conn:
        conn.execute("INSERT INTO delegation_fts(delegation_fts) VALUES('rebuild')")
        conn.commit()
