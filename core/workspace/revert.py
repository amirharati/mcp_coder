from __future__ import annotations

from pathlib import Path

from core.engine.git_diff import normalize_repo_path
from core.workspace.history_db import WorkspaceHistoryDB


def revert_to_before(
    workspace: str | Path,
    delegation_id: str,
    paths: list[str],
) -> list[str]:
    """
    Restore paths to their content immediately BEFORE delegation_id ran.

    - created during delegation → delete file from disk
    - modified → write before-content from prev_hash blob
    - deleted during delegation → restore from prev_hash blob

    Returns paths successfully reverted. Skips paths with no delta row or missing blob.
    """
    root = Path(workspace).resolve()
    db = WorkspaceHistoryDB(workspace)
    reverted: list[str] = []

    for raw in paths:
        rel = normalize_repo_path(raw)
        if not rel:
            continue

        delta = db.get_file_delta(delegation_id, rel)
        if delta is None:
            continue

        change_type = str(delta["change_type"])
        abs_path = root / rel

        if change_type == "created":
            try:
                if abs_path.is_file():
                    abs_path.unlink()
                reverted.append(rel)
            except OSError:
                continue
            continue

        prev_hash = delta.get("prev_hash")
        if not prev_hash:
            continue

        content = db.fetch_blob(str(prev_hash))
        if content is None:
            continue

        try:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(content)
            reverted.append(rel)
        except OSError:
            continue

    return sorted(reverted)
