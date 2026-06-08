"""ContextPackage cache key for executor session busting."""

from __future__ import annotations

import json

from core.context.package import COMPILER_VERSION, ContextPackage
from core.context.summary import sha256_hex


def compute_context_package_cache_key(package: ContextPackage) -> str:
    """Stable SHA-256 hex for executor cache busting on run_context path."""
    entries = []
    for entry in sorted(package.entries, key=lambda e: e.path):
        entries.append(
            {
                "path": entry.path,
                "tier": entry.tier,
                "payload_hash": sha256_hex(entry.payload) if entry.payload is not None else "",
                "excerpt_path": entry.excerpt_path or "",
            }
        )
    payload = {
        "compiler_version": str(package.metadata.get("compiler_version", COMPILER_VERSION)),
        "brief": package.brief,
        "entries": entries,
        "truncations": package.metadata.get("truncations", []),
        "capability_warnings": package.metadata.get("capability_warnings", []),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256_hex(canonical)
