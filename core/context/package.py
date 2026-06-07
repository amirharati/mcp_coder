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

COMPILER_VERSION = "0.1.0"


@dataclass
class PathEntry:
    path: str
    tier: str
    bytes: int | None = None
    payload: str | None = None


@dataclass
class ContextPackage:
    brief: str
    entries: list[PathEntry]
    policies: DelegationPolicies | None
    metadata: dict[str, Any] = field(default_factory=dict)
