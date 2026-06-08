"""Delegation-scoped workspace hash snapshots (Phase 3 P3-322a)."""

from core.workspace.manifest import DelegationDelta, FileEntry, diff_manifests
from core.workspace.revert import revert_to_before
from core.workspace.walk import walk_workspace

__all__ = [
    "DelegationDelta",
    "FileEntry",
    "diff_manifests",
    "revert_to_before",
    "walk_workspace",
]
