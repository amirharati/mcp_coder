"""Unit tests for translate_context_package — no Aider import required."""

from __future__ import annotations

from core.context.package import (
    TIER_EDIT_FULL,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
)
from core.engine.aider_engine import _extract_plan_section, translate_context_package
from core.engine.base import BackendRunRequest


def _make_package(entries: list[PathEntry], brief: str = "## Task\nDo work") -> ContextPackage:
    return ContextPackage(
        brief=brief,
        entries=entries,
        policies=None,
        metadata={},
    )


# ---------------------------------------------------------------------------
# fnames = edit-full only
# ---------------------------------------------------------------------------


def test_translate_fnames_edit_full_only():
    pkg = _make_package([
        PathEntry(path="pkg/cli.py", tier=TIER_EDIT_FULL, bytes=100, payload="x=1"),
        PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=19, payload="def api(): return 1"),
        PathEntry(path="pkg/models.py", tier=TIER_READ_EXCERPT, bytes=50, payload="class M: pass"),
    ])
    req = translate_context_package(pkg)
    assert isinstance(req, BackendRunRequest)
    assert req.fnames == ["pkg/cli.py"]
    assert req.edit_paths == ["pkg/cli.py"]


def test_translate_fnames_empty_when_no_edit_paths():
    pkg = _make_package([
        PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=19, payload="def api(): return 1"),
    ])
    req = translate_context_package(pkg)
    assert req.fnames == []
    assert req.edit_paths == []


def test_translate_fnames_sorted():
    pkg = _make_package([
        PathEntry(path="z.py", tier=TIER_EDIT_FULL),
        PathEntry(path="a.py", tier=TIER_EDIT_FULL),
    ])
    req = translate_context_package(pkg)
    assert req.fnames == ["a.py", "z.py"]


# ---------------------------------------------------------------------------
# read context block in prompt
# ---------------------------------------------------------------------------


def test_translate_prompt_contains_read_context_header():
    pkg = _make_package([
        PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=19, payload="def api(): return 1"),
    ])
    req = translate_context_package(pkg)
    assert "## Read context" in req.prompt
    assert "read-only" in req.prompt


def test_translate_prompt_contains_read_full_payload():
    pkg = _make_package([
        PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=19, payload="def api(): return 1"),
    ])
    req = translate_context_package(pkg)
    assert "pkg/core.py" in req.prompt
    assert "(read-full)" in req.prompt
    assert "def api(): return 1" in req.prompt


def test_translate_prompt_contains_read_excerpt_payload():
    pkg = _make_package([
        PathEntry(path="pkg/big.py", tier=TIER_READ_EXCERPT, bytes=50, payload="def foo(): pass"),
    ])
    req = translate_context_package(pkg)
    assert "pkg/big.py" in req.prompt
    assert "(read-excerpt)" in req.prompt
    assert "def foo(): pass" in req.prompt


def test_translate_prompt_both_read_tiers_present():
    pkg = _make_package([
        PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=19, payload="def api(): return 1"),
        PathEntry(path="pkg/big.py", tier=TIER_READ_EXCERPT, bytes=50, payload="def foo(): pass"),
    ])
    req = translate_context_package(pkg)
    assert "pkg/core.py" in req.prompt
    assert "pkg/big.py" in req.prompt
    assert "def api(): return 1" in req.prompt
    assert "def foo(): pass" in req.prompt


def test_translate_prompt_skips_none_payload():
    pkg = _make_package([
        PathEntry(path="pkg/cli.py", tier=TIER_READ_FULL, bytes=None, payload=None),
    ])
    req = translate_context_package(pkg)
    # no read context block when payload is None
    assert "## Read context" not in req.prompt


def test_translate_prompt_starts_with_brief_when_no_transcript():
    brief = "## Task\nImplement CLI"
    pkg = _make_package([], brief=brief)
    req = translate_context_package(pkg)
    assert req.prompt.startswith(brief)


# ---------------------------------------------------------------------------
# host_transcript prepend
# ---------------------------------------------------------------------------


def test_translate_host_transcript_prepended_before_brief():
    brief = "## Task\nDo work"
    pkg = _make_package([], brief=brief)
    req = translate_context_package(pkg, host_transcript="User: do the thing")
    assert "User: do the thing" in req.prompt
    assert req.prompt.index("User: do the thing") < req.prompt.index(brief)


def test_translate_host_transcript_empty_string_ignored():
    brief = "## Task\nDo work"
    pkg = _make_package([], brief=brief)
    req = translate_context_package(pkg, host_transcript="")
    assert req.prompt.startswith(brief)


def test_translate_host_transcript_whitespace_only_ignored():
    brief = "## Task\nDo work"
    pkg = _make_package([], brief=brief)
    req = translate_context_package(pkg, host_transcript="   ")
    assert req.prompt.startswith(brief)


# ---------------------------------------------------------------------------
# combined: edit + read + transcript
# ---------------------------------------------------------------------------


def test_translate_full_package():
    brief = "## Task\nImplement CLI\n\n## Goal\nCLI uses core."
    pkg = _make_package(
        [
            PathEntry(path="pkg/cli.py", tier=TIER_EDIT_FULL, bytes=None, payload=None),
            PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=19, payload="def api(): return 1"),
            PathEntry(path="pkg/big.py", tier=TIER_READ_EXCERPT, bytes=50, payload="class Expense: pass"),
        ],
        brief=brief,
    )
    req = translate_context_package(pkg, host_transcript="User: step 2")

    assert req.fnames == ["pkg/cli.py"]
    assert "User: step 2" in req.prompt
    assert brief in req.prompt
    assert "def api(): return 1" in req.prompt
    assert "class Expense: pass" in req.prompt
    # read context comes after brief
    assert req.prompt.index(brief) < req.prompt.index("## Read context")


def test_executor_prompt_has_planner_plan_section():
    brief = "## Task\nImplement CLI\n\n---\n\n## Planner plan\n- Touch pkg/cli.py first"
    pkg = _make_package([], brief=brief)
    req = translate_context_package(pkg)
    assert "## Planner plan\n- Touch pkg/cli.py first" in req.prompt
    assert req.prompt.count("## Planner plan") == 1


def test_executor_prompt_has_project_state_section():
    pkg = _make_package([], brief="## Task\nImplement CLI")
    req = translate_context_package(pkg, project_state_summary="Recent work: CLI exported.")
    assert "## Project state\nRecent work: CLI exported." in req.prompt


def test_executor_prompt_section_ordering():
    brief = "## Task\nImplement CLI\n\n---\n\n## Planner plan\n- Touch pkg/cli.py first"
    pkg = _make_package(
        [PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, bytes=19, payload="def api(): return 1")],
        brief=brief,
    )
    req = translate_context_package(pkg, project_state_summary="Recent work: CLI exported.")
    assert req.prompt.index("## Planner plan") < req.prompt.index("## Project state")
    assert req.prompt.index("## Project state") < req.prompt.index("## Read context")


def test_extract_plan_section_legacy_architect():
    brief = "## Task\nImplement CLI\n\n---\n\n## Architect plan\n- Legacy step"
    assert _extract_plan_section(brief) == "## Planner plan\n- Legacy step"
