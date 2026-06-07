"""Unit tests for the excerpt engine (core/context/excerpts.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.context.excerpts import (
    ExcerptResult,
    build_file_excerpt,
    excerpt_materialize_path,
    read_full_max_bytes,
    write_excerpt_file,
)


# ---------------------------------------------------------------------------
# read_full_max_bytes
# ---------------------------------------------------------------------------


def test_read_full_max_bytes_default(monkeypatch):
    monkeypatch.delenv("MCP_CODER_READ_FULL_MAX_BYTES", raising=False)
    assert read_full_max_bytes() == 8192


def test_read_full_max_bytes_env(monkeypatch):
    monkeypatch.setenv("MCP_CODER_READ_FULL_MAX_BYTES", "4096")
    assert read_full_max_bytes() == 4096


def test_read_full_max_bytes_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("MCP_CODER_READ_FULL_MAX_BYTES", "not_a_number")
    assert read_full_max_bytes() == 8192


def test_read_full_max_bytes_zero_falls_back(monkeypatch):
    monkeypatch.setenv("MCP_CODER_READ_FULL_MAX_BYTES", "0")
    assert read_full_max_bytes() == 8192


# ---------------------------------------------------------------------------
# build_file_excerpt — missing / unreadable
# ---------------------------------------------------------------------------


def test_build_file_excerpt_missing_returns_none(tmp_path):
    result = build_file_excerpt(
        tmp_path / "nonexistent.py",
        rel_path="nonexistent.py",
        max_full_bytes=8192,
    )
    assert result is None


# ---------------------------------------------------------------------------
# build_file_excerpt — full_small strategy
# ---------------------------------------------------------------------------


def test_build_file_excerpt_small_file_returns_full_small(tmp_path):
    f = tmp_path / "small.py"
    content = "x = 1\n"
    f.write_text(content, encoding="utf-8")

    result = build_file_excerpt(f, rel_path="small.py", max_full_bytes=8192)
    assert result is not None
    assert result.strategy == "full_small"
    assert result.text == content
    assert result.full_bytes == result.excerpt_bytes


# ---------------------------------------------------------------------------
# build_file_excerpt — symbol_windows strategy
# ---------------------------------------------------------------------------


def _make_large_py(tmp_path: Path, name: str = "big.py") -> Path:
    """Generate a large Python file with def/class symbols."""
    padding = "# padding\n" * 1000  # ~11 000 bytes
    symbols = """\
def load_expense(path):
    pass


def split_expense(expense):
    pass


class Expense:
    pass
"""
    content = padding + symbols
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


def test_build_file_excerpt_symbol_windows(tmp_path):
    f = _make_large_py(tmp_path)
    result = build_file_excerpt(f, rel_path="pkg/big.py", max_full_bytes=8192)

    assert result is not None
    assert result.strategy == "symbol_windows"
    assert result.excerpt_bytes < result.full_bytes
    assert "def load_expense" in result.text
    assert "def split_expense" in result.text
    assert "class Expense" in result.text
    assert result.text.startswith("# excerpt from: pkg/big.py\n")


def test_symbol_windows_merges_close_ranges(tmp_path):
    """Two def lines close together should produce one merged window."""
    padding = "# x\n" * 1000
    close = "def a():\n    pass\ndef b():\n    pass\n"
    f = tmp_path / "close.py"
    f.write_text(padding + close, encoding="utf-8")

    result = build_file_excerpt(f, rel_path="close.py", max_full_bytes=8192)
    assert result is not None
    # Both symbols present; no duplicate blank separator between them
    assert "def a" in result.text
    assert "def b" in result.text


# ---------------------------------------------------------------------------
# build_file_excerpt — head_tail strategy (no symbols)
# ---------------------------------------------------------------------------


def test_build_file_excerpt_head_tail_when_no_symbols(tmp_path):
    lines = [f"line_{i:04d} = {i}" for i in range(200)]
    content = "\n".join(lines) + "\n"
    f = tmp_path / "nosym.py"
    f.write_text(content, encoding="utf-8")

    result = build_file_excerpt(f, rel_path="nosym.py", max_full_bytes=100)
    assert result is not None
    assert result.strategy == "head_tail"
    assert "line_0000" in result.text
    assert "… (excerpt truncated," in result.text
    assert result.excerpt_bytes < result.full_bytes


# ---------------------------------------------------------------------------
# excerpt_materialize_path + write_excerpt_file
# ---------------------------------------------------------------------------


def test_excerpt_materialize_path(tmp_path):
    p = excerpt_materialize_path(tmp_path, "pkg/core.py")
    assert p.name == "pkg__core.py.excerpt.txt"
    assert ".mcp-coder/context/excerpts" in str(p)


def test_write_excerpt_file_creates_file_and_returns_rel_path(tmp_path):
    text = "# excerpt from: a/b.py\n\ndef foo(): pass\n"
    rel = write_excerpt_file(tmp_path, "a/b.py", text)

    assert rel == ".mcp-coder/context/excerpts/a__b.py.excerpt.txt"
    abs_p = tmp_path / rel
    assert abs_p.is_file()
    assert abs_p.read_text(encoding="utf-8") == text


def test_write_excerpt_file_overwrites_on_rerun(tmp_path):
    write_excerpt_file(tmp_path, "x.py", "v1\n")
    write_excerpt_file(tmp_path, "x.py", "v2\n")
    abs_p = tmp_path / ".mcp-coder/context/excerpts/x.py.excerpt.txt"
    assert abs_p.read_text(encoding="utf-8") == "v2\n"
