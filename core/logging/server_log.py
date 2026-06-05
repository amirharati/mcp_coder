"""Persistent structured MCP server audit log (JSONL under MCP_CODER_HOME)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.context.summary import redact_secrets
from core.storage.paths import mcp_coder_home, normalize_workspace, project_dir, project_key

LEVEL_NUM: dict[str, int] = {
    "debug": 10,
    "info": 20,
    "warn": 30,
    "error": 40,
}

VALID_LEVELS = frozenset(LEVEL_NUM)
VALID_SCOPES = frozenset({"global", "project", "both"})

REDACT_STRING_FIELDS = frozenset({"task_preview", "error", "message"})


@dataclass(frozen=True)
class ServerLogConfig:
    enabled: bool
    level: str
    scope: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def server_log_path_global() -> Path:
    return mcp_coder_home() / "server.jsonl"


def server_log_path_project(workspace: str | Path) -> Path:
    return project_dir(workspace) / "server.jsonl"


def _parse_enabled(raw: str | bool | None, *, default: bool = True) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in ("0", "false", "no", "off"):
        return False
    if text in ("1", "true", "yes", "on"):
        return True
    return default


def _parse_level(raw: str | None, *, default: str = "info") -> str:
    if not raw:
        return default
    level = str(raw).strip().lower()
    return level if level in VALID_LEVELS else default


def _parse_scope(raw: str | None, *, default: str = "global") -> str:
    if not raw:
        return default
    scope = str(raw).strip().lower()
    return scope if scope in VALID_SCOPES else default


def resolve_config(workspace: str | Path | None = None) -> ServerLogConfig:
    """Built-in defaults → env → workspace config.yaml (yaml wins)."""
    enabled = _parse_enabled(os.environ.get("MCP_CODER_SERVER_LOG", "1"))
    level = _parse_level(os.environ.get("MCP_CODER_SERVER_LOG_LEVEL"))
    scope = _parse_scope(os.environ.get("MCP_CODER_SERVER_LOG_SCOPE"))

    ws = workspace
    if ws is None:
        ws = os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())

    from core.storage.paths import workspace_config_path

    yaml_path = workspace_config_path(ws)
    if yaml_path.is_file():
        try:
            import yaml

            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            cfg = data if isinstance(data, dict) else {}
            if "server_log" in cfg:
                enabled = _parse_enabled(cfg.get("server_log"), default=enabled)
            if cfg.get("server_log_level") is not None:
                level = _parse_level(str(cfg.get("server_log_level")), default=level)
            if cfg.get("server_log_scope") is not None:
                scope = _parse_scope(str(cfg.get("server_log_scope")), default=scope)
        except Exception:
            pass

    return ServerLogConfig(enabled=enabled, level=level, scope=scope)


def _level_allows(event_level: str, configured_level: str) -> bool:
    return LEVEL_NUM.get(event_level, 20) >= LEVEL_NUM.get(configured_level, 20)


def _redact_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in fields.items():
        if key in REDACT_STRING_FIELDS and isinstance(value, str):
            out[key] = redact_secrets(value)
        else:
            out[key] = value
    return out


def _target_paths(scope: str, workspace: str | None) -> list[Path]:
    paths: list[Path] = []
    if scope in ("global", "both"):
        paths.append(server_log_path_global())
    if scope in ("project", "both") and workspace:
        paths.append(server_log_path_project(workspace))
    return paths


class ServerLog:
    def emit(
        self,
        event: str,
        *,
        level: str = "info",
        workspace_path: str | None = None,
        **fields: Any,
    ) -> None:
        ws = workspace_path
        if ws is None:
            ws = os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())
        ws_resolved = normalize_workspace(ws) if ws else None

        config = resolve_config(ws_resolved)
        if not config.enabled:
            return
        if not _level_allows(level, config.level):
            return

        record: dict[str, Any] = {
            "type": "server",
            "event": event,
            "timestamp": utc_now_iso(),
            "level": level,
            "pid": os.getpid(),
            **_redact_fields(fields),
        }
        if ws_resolved:
            record["workspace_path"] = ws_resolved
            record["project_key"] = project_key(ws_resolved)

        for path in _target_paths(config.scope, ws_resolved):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                line = json.dumps(record, ensure_ascii=False, default=str)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:
                print(
                    f"[mcp-coder] server log write failed: {exc}",
                    file=sys.stderr,
                    flush=True,
                )


_instance: ServerLog | None = None


def get_server_log() -> ServerLog:
    global _instance
    if _instance is None:
        _instance = ServerLog()
    return _instance


def server_log_emit(
    event: str,
    *,
    level: str = "info",
    workspace_path: str | None = None,
    **fields: Any,
) -> None:
    get_server_log().emit(event, level=level, workspace_path=workspace_path, **fields)


def server_log_warn(message: str, *, workspace_path: str | None = None) -> None:
    server_log_emit(
        "config_deprecated",
        level="warn",
        message=message,
        workspace_path=workspace_path,
    )
