"""Sync bundled Cursor rules into consumer workspaces on MCP startup."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from core.resources_paths import resources_dir
from core.host.cursor_rules_policy import (
    POLICY_DEFAULT,
    resolve_cursor_rules_policy,
    sync_cursor_rules_enabled,
)

MANAGED_MARKER = "mcp_coder_managed"
MANIFEST_FILENAME = "manifest.yaml"
USE_MCP_CODER_DEST = "use-mcp-coder.mdc"
# Managed rules removed when upgrading policy layout or reducing rule count.
LEGACY_MANAGED_FILENAMES = frozenset(
    {"use-mcp-coder-strict.mdc", "mcp-coder-delegate.mdc"}
)


@dataclass(frozen=True)
class RuleSyncEntry:
    dest: str
    src: str


def bundled_cursor_rules_dir() -> Path:
    return resources_dir() / "cursor-rules"


def bundled_use_mcp_coder_default_path() -> Path:
    return bundled_cursor_rules_dir() / "use-mcp-coder.default.mdc"


def bundled_delegate_rule_path() -> Path:
    """Backward-compatible alias for tests."""
    return bundled_use_mcp_coder_default_path()


def workspace_cursor_rules_dir(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / ".cursor" / "rules"


def workspace_delegate_rule_path(workspace: str | Path) -> Path:
    """Backward-compatible alias — consumer workspaces use use-mcp-coder.mdc only."""
    return workspace_cursor_rules_dir(workspace) / USE_MCP_CODER_DEST


def is_mcp_coder_source_root(workspace: str | Path) -> bool:
    """True when MCP cwd is the mcp-coder package repo (keep hand-maintained dev rules)."""
    ws = Path(workspace).resolve()
    return (
        (ws / "main.py").is_file()
        and (ws / "server" / "mcp_server.py").is_file()
        and (ws / "core" / "specs" / "bootstrap.py").is_file()
    )


@lru_cache(maxsize=1)
def _load_manifest() -> dict[str, Any]:
    path = bundled_cursor_rules_dir() / MANIFEST_FILENAME
    if not path.is_file():
        return {
            "policies": {
                POLICY_DEFAULT: {
                    "rules": [
                        {
                            "dest": USE_MCP_CODER_DEST,
                            "src": "use-mcp-coder.default.mdc",
                        },
                    ]
                }
            }
        }
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _parse_rule_entry(item: Any) -> RuleSyncEntry | None:
    if isinstance(item, str):
        return RuleSyncEntry(dest=item, src=item)
    if isinstance(item, dict):
        dest = item.get("dest")
        src = item.get("src", dest)
        if isinstance(dest, str) and isinstance(src, str):
            return RuleSyncEntry(dest=dest, src=src)
    return None


def rule_entries_for_policy(policy: str) -> list[RuleSyncEntry]:
    manifest = _load_manifest()
    policies = manifest.get("policies")
    if isinstance(policies, dict):
        for key in (policy, manifest.get("default_policy", POLICY_DEFAULT)):
            if not isinstance(key, str):
                continue
            policy_cfg = policies.get(key)
            if not isinstance(policy_cfg, dict):
                continue
            rules = policy_cfg.get("rules")
            if not isinstance(rules, list):
                continue
            entries = [_parse_rule_entry(r) for r in rules]
            parsed = [e for e in entries if e is not None]
            if parsed:
                return parsed
    return [
        RuleSyncEntry(dest=USE_MCP_CODER_DEST, src="use-mcp-coder.default.mdc"),
    ]


def rule_filenames_for_policy(policy: str) -> list[str]:
    """Workspace filenames synced for a policy (dest names)."""
    return [e.dest for e in rule_entries_for_policy(policy)]


def all_bundled_src_filenames() -> list[str]:
    manifest = _load_manifest()
    seen: set[str] = set()
    ordered: list[str] = []
    policies = manifest.get("policies")
    if not isinstance(policies, dict):
        return ["use-mcp-coder.default.mdc"]
    for policy_cfg in policies.values():
        if not isinstance(policy_cfg, dict):
            continue
        rules = policy_cfg.get("rules")
        if not isinstance(rules, list):
            continue
        for item in rules:
            entry = _parse_rule_entry(item)
            if entry and entry.src not in seen:
                seen.add(entry.src)
                ordered.append(entry.src)
    return ordered or ["use-mcp-coder.default.mdc"]


def _read_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1])
    return data if isinstance(data, dict) else {}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sync_one_rule(workspace: Path, entry: RuleSyncEntry) -> dict[str, Any]:
    dest = workspace_cursor_rules_dir(workspace) / entry.dest
    bundled = bundled_cursor_rules_dir() / entry.src

    if not bundled.is_file():
        return {
            "filename": entry.dest,
            "src": entry.src,
            "skipped": True,
            "reason": "bundled_missing",
            "rule_path": str(dest),
        }

    bundled_text = bundled.read_text(encoding="utf-8")
    bundled_hash = _sha256_text(bundled_text)
    existed = dest.is_file()

    if existed:
        dest_text = dest.read_text(encoding="utf-8")
        if _sha256_text(dest_text) == bundled_hash:
            return {
                "filename": entry.dest,
                "src": entry.src,
                "updated": False,
                "created": False,
                "rule_path": str(dest.resolve()),
                "rule_sha256": bundled_hash,
            }
        fm = _read_frontmatter(dest_text)
        if not fm.get(MANAGED_MARKER):
            return {
                "filename": entry.dest,
                "src": entry.src,
                "skipped": True,
                "reason": "user_owned_rule",
                "rule_path": str(dest.resolve()),
            }

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(bundled, dest)
    return {
        "filename": entry.dest,
        "src": entry.src,
        "updated": existed,
        "created": not existed,
        "rule_path": str(dest.resolve()),
        "rule_sha256": bundled_hash,
    }


def _cleanup_stale_managed_rules(workspace: Path, active_dests: set[str]) -> list[str]:
    """Remove managed rules no longer used (policy switch or legacy filenames)."""
    removed: list[str] = []
    known_dests = {e.dest for e in rule_entries_for_policy(POLICY_DEFAULT)} | {
        e.dest for e in rule_entries_for_policy("strict")
    }
    rules_dir = workspace_cursor_rules_dir(workspace)
    if not rules_dir.is_dir():
        return removed
    for path in rules_dir.glob("*.mdc"):
        if path.name in active_dests:
            continue
        text = path.read_text(encoding="utf-8")
        fm = _read_frontmatter(text)
        if not fm.get(MANAGED_MARKER):
            continue
        if path.name in LEGACY_MANAGED_FILENAMES or path.name in known_dests:
            path.unlink()
            removed.append(path.name)
    return removed


def sync_workspace_cursor_rules(workspace: str | Path) -> dict[str, Any]:
    """
    Sync bundled Cursor rules for the resolved policy into .cursor/rules/.

    Exactly one managed rule file (use-mcp-coder.mdc); content depends on policy.
    Change policy in config, restart MCP.
    """
    ws = Path(workspace).resolve()
    if not sync_cursor_rules_enabled(ws):
        return {"skipped": True, "reason": "disabled", "rules": []}

    if is_mcp_coder_source_root(ws):
        return {"skipped": True, "reason": "mcp_coder_source_root", "rules": []}

    policy = resolve_cursor_rules_policy(ws)
    entries = rule_entries_for_policy(policy)
    active_dests = {e.dest for e in entries}

    removed = _cleanup_stale_managed_rules(ws, active_dests)
    results = [_sync_one_rule(ws, entry) for entry in entries]

    created = sum(1 for r in results if r.get("created"))
    updated = sum(1 for r in results if r.get("updated"))
    skipped = [r for r in results if r.get("skipped")]

    return {
        "skipped": False,
        "policy": policy,
        "rules": results,
        "removed": removed,
        "created_count": created,
        "updated_count": updated,
        "skipped_count": len(skipped),
    }


def sync_workspace_delegate_rule(workspace: str | Path) -> dict[str, Any]:
    """Backward-compatible wrapper; prefer sync_workspace_cursor_rules."""
    summary = sync_workspace_cursor_rules(workspace)
    if summary.get("skipped"):
        return {
            "skipped": True,
            "reason": summary.get("reason"),
            "rule_path": str(workspace_delegate_rule_path(workspace)),
        }
    rule = next(
        (r for r in summary.get("rules", []) if r.get("filename") == USE_MCP_CODER_DEST),
        {},
    )
    if rule:
        return rule
    return {
        "skipped": True,
        "reason": "rule_not_synced",
        "rule_path": str(workspace_delegate_rule_path(workspace)),
    }
