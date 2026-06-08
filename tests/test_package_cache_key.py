"""Unit tests for ContextPackage cache key hashing (P2-300a)."""

from __future__ import annotations

from core.context.package import (
    COMPILER_VERSION,
    TIER_EDIT_FULL,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
)
from core.context.package_cache import compute_context_package_cache_key


def _package(
    *,
    brief: str = "brief",
    entries: list[PathEntry] | None = None,
    metadata: dict | None = None,
) -> ContextPackage:
    return ContextPackage(
        brief=brief,
        entries=entries
        or [PathEntry(path="pkg/cli.py", tier=TIER_EDIT_FULL, payload="x = 1\n")],
        policies=None,
        metadata=metadata or {"compiler_version": COMPILER_VERSION},
    )


def test_cache_key_stable_for_same_package():
    pkg_a = _package()
    pkg_b = _package()
    assert compute_context_package_cache_key(pkg_a) == compute_context_package_cache_key(pkg_b)


def test_cache_key_changes_when_brief_changes():
    before = compute_context_package_cache_key(_package(brief="brief one"))
    after = compute_context_package_cache_key(_package(brief="brief two"))
    assert before != after


def test_cache_key_changes_when_tier_changes():
    full = _package(
        entries=[PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, payload="a = 1\n")]
    )
    excerpt = _package(
        entries=[PathEntry(path="pkg/core.py", tier=TIER_READ_EXCERPT, payload="a = 1\n")]
    )
    assert compute_context_package_cache_key(full) != compute_context_package_cache_key(excerpt)


def test_cache_key_changes_when_payload_changes():
    before = _package(
        entries=[PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, payload="a = 1\n")]
    )
    after = _package(
        entries=[PathEntry(path="pkg/core.py", tier=TIER_READ_FULL, payload="a = 2\n")]
    )
    assert compute_context_package_cache_key(before) != compute_context_package_cache_key(after)


def test_cache_key_changes_when_truncations_added():
    base = _package()
    with_trunc = _package(metadata={"compiler_version": COMPILER_VERSION, "truncations": [{"path": "pkg/core.py", "reason": "budget"}]})
    assert compute_context_package_cache_key(base) != compute_context_package_cache_key(with_trunc)


def test_cache_key_changes_when_capability_warnings_added():
    base = _package()
    warned = _package(
        metadata={
            "compiler_version": COMPILER_VERSION,
            "capability_warnings": ["capability_degraded:read_only_not_supported:pkg/core.py"],
        }
    )
    assert compute_context_package_cache_key(base) != compute_context_package_cache_key(warned)
