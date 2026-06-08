"""MCP response summary for context packages (P2-308)."""

from __future__ import annotations

from typing import Any

from core.context.package import (
    TIER_EDIT_FULL,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    summarize_context_package,
)


def build_mcp_context_summary(
    package: ContextPackage,
    *,
    capability_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Enriched context_package_summary for delegate_to_agent MCP response."""
    base = summarize_context_package(package)
    summary: dict[str, Any] = {
        "compiler_version": base["compiler_version"],
        "edit_paths": sorted(e.path for e in package.entries if e.tier == TIER_EDIT_FULL),
        "read_paths": [
            e.path
            for e in package.entries
            if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT)
        ],
        "entries": base["entries"],
        "truncations": base.get("truncations", []),
    }
    if capability_warnings:
        summary["capability_warnings"] = capability_warnings
    return summary
