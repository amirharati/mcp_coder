"""Tests for apply_backend_capabilities() degradation logic."""

from __future__ import annotations

from pathlib import Path

from core.context.capability_adjust import apply_backend_capabilities
from core.context.package import (
    TIER_EDIT_FULL,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
)
from core.engine.capabilities import AIDER_CAPABILITIES, BackendCapabilities


def _make_caps(*, supports_read_only_in_chat: bool) -> BackendCapabilities:
    return BackendCapabilities(
        backend_id="test",
        repo_map_source="git-tracked-only",
        chat_file_mode="full-text-in-chat",
        supports_read_only_in_chat=supports_read_only_in_chat,
        dynamic_add_files=True,
        dynamic_create_files=True,
        shell_default=False,
        session_continuity=False,
    )


def _make_package(entries: list[PathEntry]) -> ContextPackage:
    return ContextPackage(
        brief="## Task\nTest",
        entries=entries,
        policies=None,
        metadata={},
    )


# ---------------------------------------------------------------------------
# supports_read_only_in_chat=True → no change
# ---------------------------------------------------------------------------


def test_no_degradation_when_supports_read_only_in_chat_true(tmp_path):
    pkg = _make_package([
        PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=100, payload="def api(): pass"),
    ])
    adjusted, warnings = apply_backend_capabilities(pkg, AIDER_CAPABILITIES, workspace=tmp_path)

    assert warnings == []
    assert adjusted is pkg, "package should be returned unchanged"
    assert adjusted.entries[0].tier == TIER_READ_FULL


def test_edit_full_unchanged_when_supports_read_only_false(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "cli.py").write_text("x = 1", encoding="utf-8")

    pkg = _make_package([
        PathEntry(path="pkg/cli.py", tier=TIER_EDIT_FULL, bytes=5, payload="x = 1"),
    ])
    caps = _make_caps(supports_read_only_in_chat=False)
    adjusted, warnings = apply_backend_capabilities(pkg, caps, workspace=tmp_path)

    assert warnings == []
    assert adjusted.entries[0].tier == TIER_EDIT_FULL


# ---------------------------------------------------------------------------
# supports_read_only_in_chat=False → read-full → read-excerpt
# ---------------------------------------------------------------------------


def test_read_full_degraded_to_read_excerpt(tmp_path):
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    content = "def api():\n    return 1\n"
    (pkg_dir / "core.py").write_text(content, encoding="utf-8")

    pkg = _make_package([
        PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=len(content.encode()), payload=content),
    ])
    caps = _make_caps(supports_read_only_in_chat=False)
    adjusted, warnings = apply_backend_capabilities(pkg, caps, workspace=tmp_path)

    assert len(warnings) == 1
    assert "capability_degraded:read_only_not_supported:pkg/core.py" in warnings[0]
    entry = adjusted.entries[0]
    assert entry.tier == TIER_READ_EXCERPT
    assert entry.excerpt_path is not None


def test_capability_warnings_in_metadata(tmp_path):
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "core.py").write_text("def api(): pass\n", encoding="utf-8")

    pkg = _make_package([
        PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=16, payload="def api(): pass\n"),
    ])
    caps = _make_caps(supports_read_only_in_chat=False)
    adjusted, warnings = apply_backend_capabilities(pkg, caps, workspace=tmp_path)

    assert adjusted.metadata.get("capability_warnings") == warnings
    assert len(warnings) > 0


def test_multiple_read_full_entries_all_degraded(tmp_path):
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    (pkg_dir / "b.py").write_text("def b(): pass\n", encoding="utf-8")

    pkg = _make_package([
        PathEntry(path="pkg/a.py", tier=TIER_READ_FULL, bytes=14, payload="def a(): pass\n"),
        PathEntry(path="pkg/b.py", tier=TIER_READ_FULL, bytes=14, payload="def b(): pass\n"),
    ])
    caps = _make_caps(supports_read_only_in_chat=False)
    adjusted, warnings = apply_backend_capabilities(pkg, caps, workspace=tmp_path)

    assert len(warnings) == 2
    tiers = {e.path: e.tier for e in adjusted.entries}
    assert tiers["pkg/a.py"] == TIER_READ_EXCERPT
    assert tiers["pkg/b.py"] == TIER_READ_EXCERPT


def test_missing_file_kept_with_warning(tmp_path):
    pkg = _make_package([
        PathEntry(path="pkg/missing.py", tier=TIER_READ_FULL, bytes=None, payload=None),
    ])
    caps = _make_caps(supports_read_only_in_chat=False)
    adjusted, warnings = apply_backend_capabilities(pkg, caps, workspace=tmp_path)

    # File does not exist on disk → build_file_excerpt returns None → entry kept unchanged
    assert len(warnings) == 1
    assert "file_unreadable" in warnings[0]
    assert adjusted.entries[0].tier == TIER_READ_FULL


def test_original_package_not_mutated(tmp_path):
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "core.py").write_text("def api(): pass\n", encoding="utf-8")

    orig_entry = PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=16, payload="def api(): pass\n")
    pkg = _make_package([orig_entry])
    caps = _make_caps(supports_read_only_in_chat=False)
    adjusted, _ = apply_backend_capabilities(pkg, caps, workspace=tmp_path)

    assert orig_entry.tier == TIER_READ_FULL, "original PathEntry must not be mutated"
    assert pkg.entries[0].tier == TIER_READ_FULL, "original package must not be mutated"
    assert adjusted is not pkg
