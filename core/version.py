"""Source identity for dev installs (verify live code is loaded)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def repo_root() -> Path:
    """Absolute path to the mcp-coder repository root."""
    return Path(__file__).resolve().parents[1]


def source_revision() -> str:
    """Short git SHA when available, else 'unknown'."""
    root = repo_root()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode == 0:
            rev = (proc.stdout or "").strip()
            if rev:
                return rev
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"
