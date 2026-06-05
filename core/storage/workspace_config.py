"""User-owned workspace config (`.mcp-coder/config.yaml`) — read-only for mcp-coder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.logging.delegation_log import log_stderr
from core.logging.server_log import server_log_warn
from core.storage.paths import legacy_workspace_config_path, workspace_config_path

_legacy_json_warned = False


def _warn_legacy_json_config(workspace: str | Path | None = None) -> None:
    global _legacy_json_warned
    if _legacy_json_warned:
        return
    message = ".mcp-coder/config.json is deprecated; use config.yaml (comments supported)"
    log_stderr(f"[mcp-coder] {message}")
    server_log_warn(message, workspace_path=str(workspace) if workspace else None)
    _legacy_json_warned = True


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_workspace_config(workspace: str | Path) -> dict[str, Any]:
    """Load config.yaml; fall back to legacy config.json if yaml is missing."""
    yaml_path = workspace_config_path(workspace)
    if yaml_path.is_file():
        try:
            return _load_yaml(yaml_path)
        except Exception:
            return {}

    json_path = legacy_workspace_config_path(workspace)
    if json_path.is_file():
        _warn_legacy_json_config(workspace)
        try:
            return _load_json(json_path)
        except (json.JSONDecodeError, OSError):
            return {}

    return {}
