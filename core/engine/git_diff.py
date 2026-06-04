from __future__ import annotations

import subprocess
from pathlib import Path


def snapshot_mtimes(workspace_path: str, relative_paths: list[str]) -> dict[str, float | None]:
    """mtime per repo-relative path (None if missing before run)."""
    root = Path(workspace_path)
    out: dict[str, float | None] = {}
    for rel in relative_paths:
        path = root / rel
        out[rel] = path.stat().st_mtime if path.exists() else None
    return out


def files_changed_since_mtimes(
    workspace_path: str,
    relative_paths: list[str],
    before: dict[str, float | None],
) -> list[str]:
    """Paths in relative_paths whose mtime changed (delegation-scoped)."""
    root = Path(workspace_path)
    changed: list[str] = []
    for rel in relative_paths:
        path = root / rel
        prev = before.get(rel)
        if not path.exists():
            if prev is not None:
                changed.append(rel)
            continue
        cur = path.stat().st_mtime
        if prev is None or cur != prev:
            changed.append(rel)
    return changed


def files_changed_via_git(workspace_path: str) -> list[str]:
    """All dirty paths in the repo (can include unrelated local edits)."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            proc = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def files_changed_for_delegation(
    workspace_path: str,
    target_files: list[str],
    before_mtimes: dict[str, float | None],
) -> list[str]:
    """
    Prefer mtime diff on target_files; fall back to git diff ∩ target_files.
    """
    by_mtime = files_changed_since_mtimes(workspace_path, target_files, before_mtimes)
    if by_mtime:
        return by_mtime
    git_dirty = set(files_changed_via_git(workspace_path))
    return sorted(git_dirty.intersection(target_files))
