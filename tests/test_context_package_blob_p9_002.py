"""Context package blob sidecar storage (P9-002)."""

from __future__ import annotations

from core.context.package import (
    COMPILER_VERSION,
    TIER_EDIT_FULL,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
)
from core.context.package_blob import (
    compute_context_package_blob_hash,
    persist_context_package_blob,
    serialize_context_package,
)
from core.context.package_cache import compute_context_package_cache_key
from core.specs.delegation_policies import (
    EDIT_SCOPE_DISCOVER,
    UNTRACKED_POLICY_MATERIALIZE,
    DelegationPolicies,
)


def _package(
    *,
    brief: str = "brief",
    entries: list[PathEntry] | None = None,
    policies: DelegationPolicies | None = None,
    metadata: dict | None = None,
) -> ContextPackage:
    return ContextPackage(
        brief=brief,
        entries=entries
        or [
            PathEntry(path="pkg/cli.py", tier=TIER_EDIT_FULL, payload="x = 1\n", bytes=6),
            PathEntry(
                path="pkg/core.py",
                tier=TIER_READ_FULL,
                payload="y = 2\n",
                bytes=6,
                excerpt_path=None,
            ),
        ],
        policies=policies,
        metadata=metadata or {"compiler_version": COMPILER_VERSION},
    )


def _policies() -> DelegationPolicies:
    return DelegationPolicies(
        files_edit=["pkg/cli.py"],
        files_read=["pkg/core.py"],
        files_delete=[],
        edit_scope=EDIT_SCOPE_DISCOVER,
        allow_create=False,
        untracked_policy=UNTRACKED_POLICY_MATERIALIZE,
        all_paths=["pkg/cli.py", "pkg/core.py"],
    )


def test_blob_hash_stable_for_equivalent_packages():
    pkg_a = _package(policies=_policies())
    pkg_b = _package(policies=_policies())
    assert compute_context_package_blob_hash(pkg_a) == compute_context_package_blob_hash(pkg_b)


def test_blob_hash_differs_from_executor_cache_key():
    pkg = _package(policies=_policies())
    assert compute_context_package_blob_hash(pkg) != compute_context_package_cache_key(pkg)


def test_serialize_includes_policies_all_paths():
    serialized = serialize_context_package(_package(policies=_policies()))
    assert "brief" in serialized
    assert "entries" in serialized
    assert "metadata" in serialized
    assert serialized["policies"]["all_paths"] == ["pkg/cli.py", "pkg/core.py"]
    assert serialized["entries"][0]["payload"] == "x = 1\n"


def test_persist_writes_blob_and_dedups(tmp_path):
    session_dir = tmp_path / "session"
    pkg = _package(policies=_policies())

    hash_one, path_one, wrote_one = persist_context_package_blob(session_dir, pkg)
    assert wrote_one is True
    assert path_one.is_file()
    assert path_one.parent.name == "context_packages"
    assert path_one.name == f"{hash_one}.json"

    blob = path_one.read_text(encoding="utf-8")
    assert '"brief"' in blob
    assert '"entries"' in blob
    assert '"metadata"' in blob
    assert '"policies"' in blob

    hash_two, path_two, wrote_two = persist_context_package_blob(session_dir, pkg)
    assert hash_two == hash_one
    assert path_two == path_one
    assert wrote_two is False
