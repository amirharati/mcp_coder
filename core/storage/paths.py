"""Resolve MCP_CODER_HOME, project_key, and session paths."""

from __future__ import annotations

import os
from pathlib import Path

from core.context.summary import sha256_hex


def mcp_coder_home() -> Path:
    raw = os.environ.get("MCP_CODER_HOME", "~/.mcp-coder")
    return Path(os.path.expanduser(raw)).resolve()


def ensure_mcp_coder_home() -> Path:
    """Create home root (and projects/) if missing. Safe to call on every startup."""
    home = mcp_coder_home()
    (home / "projects").mkdir(parents=True, exist_ok=True)
    return home


def normalize_workspace(workspace: str | Path) -> str:
    return str(Path(workspace).resolve())


def project_key(workspace: str | Path) -> str:
    """Stable id: full SHA-256 hex of resolved absolute workspace path (UTF-8)."""
    return sha256_hex(normalize_workspace(workspace))


def project_dir(workspace: str | Path) -> Path:
    return mcp_coder_home() / "projects" / project_key(workspace)


def workspace_history_db_path(workspace: str | Path) -> Path:
    """Per-project workspace hash history (D-P3-1 — not under workspace .mcp-coder/)."""
    return project_dir(workspace) / "workspace_history.db"


def project_json_path(workspace: str | Path) -> Path:
    return project_dir(workspace) / "project.json"


def sessions_root(workspace: str | Path) -> Path:
    return project_dir(workspace) / "sessions"


def session_folder(workspace: str | Path, mcp_session_id: str) -> Path:
    return sessions_root(workspace) / mcp_session_id


def session_delegations_path(workspace: str | Path, mcp_session_id: str) -> Path:
    return session_folder(workspace, mcp_session_id) / "delegations.jsonl"


def workspace_pointer_path(workspace: str | Path) -> Path:
    """System-managed pointer under .mcp-coder/session.json."""
    return Path(workspace).resolve() / ".mcp-coder" / "session.json"


def legacy_workspace_pointer_path(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / ".mcp-coder" / "project.json"


def workspace_config_path(workspace: str | Path) -> Path:
    """User-owned repo config — never written by mcp-coder during delegation."""
    return Path(workspace).resolve() / ".mcp-coder" / "config.yaml"


def legacy_workspace_config_path(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / ".mcp-coder" / "config.json"


def legacy_workspace_log_path(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / ".mcp-coder" / "logs" / "delegations.jsonl"


def mirror_log_targets(workspace: str | Path) -> list[Path]:
    """Optional mirror paths (canonical write is always under home)."""
    targets: list[Path] = []
    if should_mirror_to_workspace():
        targets.append(legacy_workspace_log_path(workspace))
    log_dir = os.environ.get("MCP_CODER_LOG_DIR", "").strip()
    if log_dir:
        targets.append(Path(os.path.expanduser(log_dir)).resolve() / "delegations.jsonl")
    return targets


def should_mirror_to_workspace() -> bool:
    return os.environ.get("MCP_CODER_MIRROR_LOGS_TO_WORKSPACE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
