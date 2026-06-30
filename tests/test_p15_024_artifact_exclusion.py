"""P15-024 — context-builder artifact directory exclusion (B021)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.context.file_picker import _iter_scannable_files
from core.workspace.walk import SKIP_DIRS, should_skip_dir, walk_workspace

# New P15-024 artifact dirs
NEW_SKIP_DIRS = (
    ".next",
    "out",
    "out_deploy",
    ".svelte-kit",
    ".nuxt",
    ".turbo",
    "coverage",
    ".specstory",
)

# Existing built-in skip dirs (regression guard)
EXISTING_SKIP_DIRS = (
    "node_modules",
    "dist",
    "build",
    ".git",
    ".venv",
    ".aider.tags.cache.v4",
)


def _artifact_tree(ws: Path) -> None:
    """Tmp workspace with artifact dirs + one legitimate source file."""
    (ws / "src" / "app.py").parent.mkdir(parents=True)
    (ws / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (ws / ".next" / "server").mkdir(parents=True)
    (ws / ".next" / "server" / "chunks.js").write_text("// chunk\n", encoding="utf-8")
    (ws / "out").mkdir()
    (ws / "out" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (ws / ".specstory").mkdir()
    (ws / ".specstory" / "history.md").write_text("# history\n", encoding="utf-8")


@pytest.mark.parametrize("dirname", NEW_SKIP_DIRS + EXISTING_SKIP_DIRS)
def test_should_skip_dir_builtin(dirname: str) -> None:
    assert should_skip_dir(dirname) is True


def test_should_skip_dir_allows_normal_dirs() -> None:
    assert should_skip_dir("src") is False
    assert should_skip_dir("lib") is False


def test_skip_dirs_contains_all_new_entries() -> None:
    for name in NEW_SKIP_DIRS:
        assert name in SKIP_DIRS


def test_walk_workspace_excludes_artifact_dirs(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    _artifact_tree(ws)

    manifest = walk_workspace(str(ws))
    paths = set(manifest.keys())

    assert "src/app.py" in paths
    assert not any(p.startswith(".next/") for p in paths)
    assert not any(p.startswith("out/") for p in paths)
    assert not any(p.startswith(".specstory/") for p in paths)


def test_file_picker_excludes_artifact_dirs(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    _artifact_tree(ws)

    scanned = _iter_scannable_files(ws)
    rel_paths = {
        p.relative_to(ws.resolve()).as_posix() for p in scanned
    }

    assert "src/app.py" in rel_paths
    assert not any(p.startswith(".next/") for p in rel_paths)
    assert not any(p.startswith("out/") for p in rel_paths)
    assert not any(p.startswith(".specstory/") for p in rel_paths)


def test_env_extra_exclude_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MCP_CODER_CONTEXT_EXCLUDE_DIRS", "custom_cache:tmp_build"
    )
    assert should_skip_dir("custom_cache") is True
    assert should_skip_dir("tmp_build") is True
    assert should_skip_dir("src") is False


def test_env_extra_exclude_dirs_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_CODER_CONTEXT_EXCLUDE_DIRS", raising=False)
    assert should_skip_dir("custom_cache") is False


def test_env_override_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env is merged at call time, not import time (D5)."""
    monkeypatch.delenv("MCP_CODER_CONTEXT_EXCLUDE_DIRS", raising=False)
    assert should_skip_dir("late_added") is False

    monkeypatch.setenv("MCP_CODER_CONTEXT_EXCLUDE_DIRS", "late_added")
    assert should_skip_dir("late_added") is True
