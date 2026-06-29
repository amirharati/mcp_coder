from __future__ import annotations

import hashlib
import os
from pathlib import Path

from core.engine.git_diff import normalize_repo_path
from core.workspace.manifest import FileEntry, Manifest

SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".git",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".mcp-coder",
        # B002 fix: Aider's internal tag cache — tooling noise, not source files.
        ".aider.tags.cache.v4",
        ".aider.cache.v3",
    }
)

SKIP_EXTENSIONS = frozenset(
    {
        ".pyc",
        ".so",
        ".dll",
        ".exe",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".whl",
    }
)


def max_file_bytes() -> int:
    raw = os.environ.get("MCP_CODER_SNAPSHOT_MAX_FILE_MB", "1").strip()
    try:
        mb = float(raw)
    except ValueError:
        mb = 1.0
    return max(1, int(mb * 1024 * 1024))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_binary_content(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS


def should_skip_file(name: str) -> bool:
    return Path(name).suffix.lower() in SKIP_EXTENSIONS


def read_workspace_file(workspace_path: str, rel_path: str) -> bytes | None:
    """Read a workspace-relative file respecting skip rules and max size."""
    rel = normalize_repo_path(rel_path)
    if not rel or should_skip_file(rel):
        return None

    root = Path(workspace_path).resolve()
    abs_path = root / rel
    try:
        if not abs_path.is_file():
            return None
        stat = abs_path.stat()
        if stat.st_size > max_file_bytes():
            return None
        return abs_path.read_bytes()
    except OSError:
        return None


def walk_workspace(workspace_path: str) -> Manifest:
    """Hash-walk workspace → manifest (path → FileEntry). Not .gitignore-aware."""
    root = Path(workspace_path).resolve()
    manifest: Manifest = {}
    limit = max_file_bytes()

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        for filename in filenames:
            if should_skip_file(filename):
                continue

            abs_path = Path(dirpath) / filename
            try:
                rel = abs_path.relative_to(root).as_posix()
            except ValueError:
                continue

            rel = normalize_repo_path(rel)
            if not rel:
                continue

            try:
                stat = abs_path.stat()
            except OSError:
                continue

            if stat.st_size > limit:
                continue

            try:
                data = abs_path.read_bytes()
            except OSError:
                continue

            manifest[rel] = FileEntry(
                content_hash=sha256_bytes(data),
                size_bytes=len(data),
                is_binary=is_binary_content(data),
                mtime=stat.st_mtime,
            )

    return manifest
