from __future__ import annotations

import subprocess
from pathlib import Path


def normalize_repo_path(path: str) -> str:
    """Normalize repo-relative path for set comparison."""
    p = path.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


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


def _is_git_repo(workspace_path: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False


def _git_tracked_dirty(workspace_path: str) -> list[str] | None:
    """Tracked paths differing from HEAD/index; None if git fails."""
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
            return None
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_untracked(workspace_path: str) -> list[str] | None:
    """Untracked paths (respecting .gitignore); None if git fails."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return None


def snapshot_git_dirty(workspace_path: str) -> set[str] | None:
    """
    All dirty + untracked repo-relative paths at a point in time.
    Returns None when not a git repo or git commands fail.
    """
    if not _is_git_repo(workspace_path):
        return None
    tracked = _git_tracked_dirty(workspace_path)
    if tracked is None:
        return None
    untracked = _git_untracked(workspace_path)
    if untracked is None:
        return None
    return {normalize_repo_path(p) for p in (*tracked, *untracked)}


def files_touched_since_snapshot(
    workspace_path: str,
    before: set[str] | None,
    *,
    target_files: list[str],
    before_mtimes: dict[str, float | None] | None = None,
) -> tuple[list[str], bool]:
    """
    Paths newly dirty/untracked since before snapshot.

    Returns (files_changed, used_git). When git is unavailable, falls back to
    mtime diff on target_files only (used_git=False).
    """
    after = snapshot_git_dirty(workspace_path)
    if before is not None and after is not None:
        return sorted(after - before), True
    mtimes = before_mtimes if before_mtimes is not None else snapshot_mtimes(
        workspace_path, target_files
    )
    return files_changed_for_delegation(workspace_path, target_files, mtimes), False


def compute_files_unexpected(
    files_changed: list[str],
    target_files: list[str],
    *,
    used_git: bool,
) -> list[str]:
    """Paths touched outside normalized target_files; empty when git fallback."""
    if not used_git:
        return []
    norm_targets = {normalize_repo_path(f) for f in target_files}
    return sorted(
        {normalize_repo_path(f) for f in files_changed} - norm_targets
    )


def files_changed_via_git(workspace_path: str) -> list[str]:
    """All dirty paths in the repo (can include unrelated local edits)."""
    snap = snapshot_git_dirty(workspace_path)
    return sorted(snap) if snap is not None else []


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
    norm_targets = {normalize_repo_path(f) for f in target_files}
    return sorted(git_dirty.intersection(norm_targets))
