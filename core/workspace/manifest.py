from __future__ import annotations

from dataclasses import dataclass

Manifest = dict[str, "FileEntry"]


@dataclass(frozen=True)
class FileEntry:
    content_hash: str
    size_bytes: int
    is_binary: bool
    mtime: float


@dataclass
class DelegationDelta:
    created: list[str]
    modified: list[str]
    deleted: list[str]

    @property
    def all_changed(self) -> list[str]:
        return sorted({*self.created, *self.modified, *self.deleted})


def diff_manifests(before: Manifest, after: Manifest) -> DelegationDelta:
    """Compute created / modified / deleted paths between two manifests."""
    before_paths = set(before)
    after_paths = set(after)

    created = sorted(after_paths - before_paths)
    deleted = sorted(before_paths - after_paths)
    modified = sorted(
        path
        for path in before_paths & after_paths
        if before[path].content_hash != after[path].content_hash
    )

    return DelegationDelta(created=created, modified=modified, deleted=deleted)
