"""L2 context compiler data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.specs.delegation_policies import DelegationPolicies


TIER_EDIT_FULL = "edit-full"
TIER_READ_FULL = "read-full"
TIER_READ_EXCERPT = "read-excerpt"
TIER_POINTER = "pointer"
TIER_MAP_ONLY = "map-only"
TIER_HIDE = "hide"

COMPILER_VERSION = "0.3.0"


@dataclass
class PathEntry:
    path: str
    tier: str
    bytes: int | None = None
    payload: str | None = None
    excerpt_path: str | None = None


@dataclass
class ContextPackage:
    brief: str
    entries: list[PathEntry]
    policies: DelegationPolicies | None
    metadata: dict[str, Any] = field(default_factory=dict)


def summarize_context_package(package: ContextPackage) -> dict[str, Any]:
    """Compact summary for JSONL context_block (no full payloads)."""
    return {
        "compiler_version": package.metadata.get("compiler_version", COMPILER_VERSION),
        "entries": [
            {
                "path": e.path,
                "tier": e.tier,
                "bytes": e.bytes,
                "excerpt_path": e.excerpt_path,
            }
            for e in package.entries
        ],
        "token_estimate_preflight": package.metadata.get("token_estimate_preflight"),
        "excerpt_paths": package.metadata.get("excerpt_paths", []),
        "truncations": package.metadata.get("truncations", []),
    }
