"""Window budget enforcement for the L2 context compiler (P2-220).

Truncates read-tier payloads until estimated prompt tokens fit within a
per-model budget.  Never modifies edit-full entries and never blocks
delegation — returns best-effort package with logged truncations.

Truncation priority (steps applied in order until under budget):
  1. read-full → read-excerpt  (context_budget:read_full_to_excerpt)
  2. read-excerpt head-only    (context_budget:excerpt_shrink)
  3. drop payload → pointer    (context_budget:drop_payload)
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from core.context.excerpts import build_file_excerpt, read_full_max_bytes, write_excerpt_file
from core.context.package import (
    TIER_EDIT_FULL,
    TIER_POINTER,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
)
from core.context.summary import estimate_tokens
from core.usage.rates import lookup_context_budget_tokens

_DEFAULT_BUDGET_TOKENS = 128_000
_EXCERPT_SHRINK_HEAD_LINES = 40
_BUDGET_SECTION_HEADER = "## Paths (budget)"


def _budget_enabled() -> bool:
    raw = os.environ.get("MCP_CODER_CONTEXT_BUDGET_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no")


def resolve_context_budget_tokens(*, model: str | None = None) -> int | None:
    """Return the active token budget, or None when budgeting is disabled.

    Resolution order:
      1. MCP_CODER_CONTEXT_BUDGET_ENABLED=0  → None (disabled)
      2. Per-model context_budget_tokens from model_rates.yaml
      3. MCP_CODER_CONTEXT_BUDGET_TOKENS env var
      4. Default 128_000 when model unknown / not in yaml
    """
    if not _budget_enabled():
        return None

    if model:
        yaml_budget = lookup_context_budget_tokens(model)
        if yaml_budget is not None:
            return yaml_budget

    env_raw = os.environ.get("MCP_CODER_CONTEXT_BUDGET_TOKENS", "").strip()
    if env_raw:
        try:
            val = int(env_raw)
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    return _DEFAULT_BUDGET_TOKENS


def _package_token_estimate(package: ContextPackage) -> int:
    payload_text = "".join(e.payload or "" for e in package.entries)
    return estimate_tokens(package.brief + payload_text)


def _bytes_by_tier(entries: list[PathEntry]) -> dict[str, int]:
    result: dict[str, int] = {}
    for e in entries:
        b = e.bytes or 0
        result[e.tier] = result.get(e.tier, 0) + b
    return result


def _shrink_excerpt_head(payload: str, path: str) -> str:
    """Return first _EXCERPT_SHRINK_HEAD_LINES lines + budget footer."""
    lines = payload.splitlines()
    head = lines[:_EXCERPT_SHRINK_HEAD_LINES]
    return "\n".join(head) + "\n… (budget truncated)\n"


def apply_context_budget(
    package: ContextPackage,
    *,
    workspace: Path,
    budget_tokens: int,
) -> ContextPackage:
    """Return a new package whose estimated tokens are ≤ budget_tokens.

    Steps applied in order until under budget (or no more degradation possible):
      1. read-full → read-excerpt
      2. read-excerpt → head-only excerpt (shrink)
      3. read-excerpt/read-full with payload → pointer (drop payload)

    edit-full entries are never modified.  Returns best-effort package with
    metadata.budget_warnings if still over limit after all steps.
    """
    if _package_token_estimate(package) <= budget_tokens:
        return package

    ws = workspace.resolve()
    max_bytes = read_full_max_bytes()

    entries: list[PathEntry] = [copy.copy(e) for e in package.entries]
    truncations: list[dict[str, Any]] = list(package.metadata.get("truncations", []))
    brief = package.brief

    def _estimate() -> int:
        payload_text = "".join(e.payload or "" for e in entries)
        return estimate_tokens(brief + payload_text)

    # --- Step 1: read-full → read-excerpt ---
    if _estimate() > budget_tokens:
        for i, entry in enumerate(entries):
            if entry.tier != TIER_READ_FULL:
                continue
            original_payload = entry.payload or ""
            original_bytes = len(original_payload.encode("utf-8"))

            abs_path = ws / entry.path
            excerpt = build_file_excerpt(
                abs_path,
                rel_path=entry.path,
                max_full_bytes=max_bytes,
            )
            if excerpt is not None:
                excerpt_rel = write_excerpt_file(ws, entry.path, excerpt.text)
                new_entry = PathEntry(
                    path=entry.path,
                    tier=TIER_READ_EXCERPT,
                    bytes=excerpt.excerpt_bytes,
                    payload=excerpt.text,
                    excerpt_path=excerpt_rel,
                )
                entries[i] = new_entry
                new_bytes = excerpt.excerpt_bytes
            else:
                # File unreadable — just clear payload and demote
                new_entry = PathEntry(
                    path=entry.path,
                    tier=TIER_READ_EXCERPT,
                    bytes=entry.bytes,
                    payload=None,
                    excerpt_path=entry.excerpt_path,
                )
                entries[i] = new_entry
                new_bytes = 0

            truncations.append(
                {
                    "reason": "context_budget:read_full_to_excerpt",
                    "path": entry.path,
                    "bytes_dropped": max(0, original_bytes - new_bytes),
                }
            )
            if _estimate() <= budget_tokens:
                break

    # --- Step 2: read-excerpt → head-only (shrink) ---
    if _estimate() > budget_tokens:
        for i, entry in enumerate(entries):
            if entry.tier != TIER_READ_EXCERPT or entry.payload is None:
                continue
            original_payload = entry.payload
            original_bytes = len(original_payload.encode("utf-8"))

            shrunk = _shrink_excerpt_head(original_payload, entry.path)
            shrunk_bytes = len(shrunk.encode("utf-8"))

            entries[i] = PathEntry(
                path=entry.path,
                tier=TIER_READ_EXCERPT,
                bytes=shrunk_bytes,
                payload=shrunk,
                excerpt_path=entry.excerpt_path,
            )
            truncations.append(
                {
                    "reason": "context_budget:excerpt_shrink",
                    "path": entry.path,
                    "bytes_dropped": max(0, original_bytes - shrunk_bytes),
                }
            )
            if _estimate() <= budget_tokens:
                break

    # --- Step 3: drop payload → pointer ---
    if _estimate() > budget_tokens:
        # Collect paths being dropped to append to brief
        dropped_paths: list[str] = []
        for i, entry in enumerate(entries):
            if entry.tier not in (TIER_READ_FULL, TIER_READ_EXCERPT):
                continue
            if entry.payload is None:
                continue
            original_bytes = len(entry.payload.encode("utf-8"))

            entries[i] = PathEntry(
                path=entry.path,
                tier=TIER_POINTER,
                bytes=entry.bytes,
                payload=None,
                excerpt_path=entry.excerpt_path,
            )
            dropped_paths.append(entry.path)
            truncations.append(
                {
                    "reason": "context_budget:drop_payload",
                    "path": entry.path,
                    "bytes_dropped": original_bytes,
                }
            )
            if _estimate() <= budget_tokens:
                break

        if dropped_paths:
            pointer_lines = "\n".join(f"- {p}" for p in dropped_paths)
            brief = brief.rstrip() + f"\n\n{_BUDGET_SECTION_HEADER}\n{pointer_lines}\n"

    new_metadata = dict(package.metadata)
    new_metadata["truncations"] = truncations
    # Recompute token estimate and bytes_by_tier after truncation
    new_metadata["token_estimate_preflight"] = _estimate()
    new_metadata["bytes_by_tier"] = _bytes_by_tier(entries)

    budget_warnings: list[str] = []
    if _estimate() > budget_tokens:
        budget_warnings.append("context_budget:still_over_limit")
    if budget_warnings:
        new_metadata["budget_warnings"] = budget_warnings

    return ContextPackage(
        brief=brief,
        entries=entries,
        policies=package.policies,
        metadata=new_metadata,
    )
