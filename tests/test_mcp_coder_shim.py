"""Smoke tests for scripts/mcp-coder CLI shim (P2-ISS-010)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIM = REPO_ROOT / "scripts" / "mcp-coder"


def test_shim_exists_and_is_executable():
    assert SHIM.is_file()
    assert os.access(SHIM, os.X_OK)


def test_shim_help_lists_subcommands():
    proc = subprocess.run(
        ["bash", str(SHIM), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "inspect-context" in proc.stdout
    assert "test-model" in proc.stdout
