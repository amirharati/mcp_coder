"""Hash-addressed ContextPackage blob storage for replay (P9-002, D-P9-8)."""

from __future__ import annotations

import json
from pathlib import Path

from core.context.package import ContextPackage, PathEntry
from core.context.summary import sha256_hex


def serialize_context_package(package: ContextPackage) -> dict:
    """Serialize full package content for replay-grade blob storage."""
    entries = [
        _serialize_entry(entry)
        for entry in sorted(package.entries, key=lambda e: e.path)
    ]
    policies = None
    if package.policies is not None:
        policies = {
            **package.policies.to_response_dict(),
            "all_paths": package.policies.all_paths,
        }
    return {
        "brief": package.brief,
        "entries": entries,
        "metadata": package.metadata,
        "policies": policies,
    }


def _serialize_entry(entry: PathEntry) -> dict:
    return {
        "path": entry.path,
        "tier": entry.tier,
        "bytes": entry.bytes,
        "payload": entry.payload,
        "excerpt_path": entry.excerpt_path,
    }


def compute_context_package_blob_hash(package: ContextPackage) -> str:
    """Deterministic SHA-256 hex for the full serialized package blob."""
    serialized = serialize_context_package(package)
    canonical = json.dumps(
        serialized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return sha256_hex(canonical)


def persist_context_package_blob(
    session_dir: str | Path,
    package: ContextPackage,
) -> tuple[str, Path, bool]:
    """Write deduped blob under session_dir/context_packages/<hash>.json.

    Returns (context_package_hash, blob_path, wrote_new_blob).
    """
    serialized = serialize_context_package(package)
    canonical = json.dumps(
        serialized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    context_package_hash = sha256_hex(canonical)
    blob_dir = Path(session_dir) / "context_packages"
    blob_path = blob_dir / f"{context_package_hash}.json"

    if blob_path.is_file():
        return context_package_hash, blob_path, False

    blob_dir.mkdir(parents=True, exist_ok=True)
    blob_path.write_text(
        json.dumps(serialized, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return context_package_hash, blob_path, True
