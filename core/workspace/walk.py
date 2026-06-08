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


def _max_file_bytes() -> int:
    raw = os.environ.get("MCP_CODER_SNAPSHOT_MAX_FILE_MB", "1").strip()
    try:
        mb = float(raw)
    except ValueError:
        mb = 1.0
    return max(1, int(mb * 1024 * 1024))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_binary(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS


def _should_skip_file(name: str) -> bool:
    return Path(name).suffix.lower() in SKIP_EXTENSIONS


def walk_workspace(workspace_path: str) -> Manifest:
    """Hash-walk workspace → manifest (path → FileEntry). Not .gitignore-aware."""
    root = Path(workspace_path).resolve()
    manifest: Manifest = {}
    max_bytes = _max_file_bytes()

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for filename in filenames:
            if _should_skip_file(filename):
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

            if stat.st_size > max_bytes:
                continue

            try:
                data = abs_path.read_bytes()
            except OSError:
                continue

            manifest[rel] = FileEntry(
                content_hash=_sha256_bytes(data),
                size_bytes=len(data),
                is_binary=_is_binary(data),
                mtime=stat.st_mtime,
            )

    return manifest
