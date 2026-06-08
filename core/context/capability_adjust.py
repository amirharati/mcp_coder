"""Capability-aware ContextPackage adjustment (P2-212).

v0 rule: when the backend cannot honour read-only entries in chat
(supports_read_only_in_chat=False), force read-full entries to
read-excerpt via the existing excerpt engine.
"""

from __future__ import annotations

from pathlib import Path

from core.context.excerpts import build_file_excerpt, read_full_max_bytes, write_excerpt_file
from core.context.package import (
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
)
from core.engine.capabilities import BackendCapabilities


def apply_backend_capabilities(
    package: ContextPackage,
    caps: BackendCapabilities,
    *,
    workspace: Path,
) -> tuple[ContextPackage, list[str]]:
    """Adjust package entries for what the backend supports.

    Returns ``(adjusted_package, capability_warnings)``.
    When ``caps.supports_read_only_in_chat`` is True, the package is
    returned unchanged with an empty warnings list.
    """
    if caps.supports_read_only_in_chat:
        return package, []

    ws = workspace.resolve()
    max_bytes = read_full_max_bytes()
    warnings: list[str] = []
    new_entries: list[PathEntry] = []

    for entry in package.entries:
        if entry.tier != TIER_READ_FULL:
            new_entries.append(entry)
            continue

        abs_path = ws / entry.path
        excerpt = build_file_excerpt(
            abs_path,
            rel_path=entry.path,
            max_full_bytes=max_bytes,
        )

        if excerpt is None:
            # File unreadable — keep entry unchanged, warn
            new_entries.append(entry)
            warnings.append(
                f"capability_degraded:read_only_not_supported:{entry.path}"
                ":file_unreadable"
            )
            continue

        # Write excerpt to disk so excerpt_path is populated
        excerpt_rel = write_excerpt_file(ws, entry.path, excerpt.text)

        new_entry = PathEntry(
            path=entry.path,
            tier=TIER_READ_EXCERPT,
            bytes=excerpt.excerpt_bytes,
            payload=excerpt.text,
            excerpt_path=excerpt_rel,
        )
        new_entries.append(new_entry)
        warnings.append(
            f"capability_degraded:read_only_not_supported:{entry.path}"
        )

    if not warnings:
        return package, []

    # Rebuild metadata with capability_warnings
    new_metadata = dict(package.metadata)
    new_metadata["capability_warnings"] = warnings

    new_package = ContextPackage(
        brief=package.brief,
        entries=new_entries,
        policies=package.policies,
        metadata=new_metadata,
    )
    return new_package, warnings
