"""Backend-neutral repo map (P4-001a, D-P4-11)."""

from __future__ import annotations

from pathlib import Path

from core.context.package import TIER_MAP_ONLY
from core.context.repo_map import build_repo_map_entries


def _write(workspace: Path, rel: str, text: str) -> None:
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_map_entries_exclude_ranked_paths(tmp_path):
    _write(tmp_path, "src/app.py", "def main():\n    pass\n")
    _write(tmp_path, "src/util.py", "def helper():\n    pass\n")
    entries = build_repo_map_entries(tmp_path, exclude_paths={"src/app.py"})
    paths = [e.path for e in entries]
    assert "src/util.py" in paths
    assert "src/app.py" not in paths
    assert all(e.tier == TIER_MAP_ONLY for e in entries)


def test_symbol_outline_payload(tmp_path):
    _write(
        tmp_path,
        "src/mod.py",
        "import os\n\n\nclass Widget:\n    def render(self):\n        pass\n\n\ndef main():\n    pass\n",
    )
    entries = build_repo_map_entries(tmp_path, exclude_paths=set())
    entry = next(e for e in entries if e.path == "src/mod.py")
    assert entry.payload is not None
    assert "class Widget:" in entry.payload
    assert "def main():" in entry.payload
    assert "import os" not in entry.payload


def test_file_without_symbols_has_no_payload(tmp_path):
    _write(tmp_path, "notes.md", "# Notes\n\nplain text\n")
    entries = build_repo_map_entries(tmp_path, exclude_paths=set())
    entry = next(e for e in entries if e.path == "notes.md")
    assert entry.payload is None


def test_respects_max_files_cap(tmp_path):
    for i in range(10):
        _write(tmp_path, f"src/mod_{i}.py", "def f():\n    pass\n")
    entries = build_repo_map_entries(tmp_path, exclude_paths=set(), max_files=3)
    assert len(entries) == 3


def test_max_files_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_REPO_MAP_MAX_FILES", "2")
    for i in range(5):
        _write(tmp_path, f"src/mod_{i}.py", "def f():\n    pass\n")
    entries = build_repo_map_entries(tmp_path, exclude_paths=set())
    assert len(entries) == 2


def test_skips_non_map_extensions_and_skip_dirs(tmp_path):
    _write(tmp_path, "src/app.py", "def main():\n    pass\n")
    _write(tmp_path, "data.csv", "a,b\n1,2\n")
    _write(tmp_path, "node_modules/pkg/index.js", "function f() {}\n")
    entries = build_repo_map_entries(tmp_path, exclude_paths=set())
    paths = [e.path for e in entries]
    assert "src/app.py" in paths
    assert "data.csv" not in paths
    assert all("node_modules" not in p for p in paths)
