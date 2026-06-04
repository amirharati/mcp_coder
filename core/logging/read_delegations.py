from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.logging.delegation_log import delegation_log_paths_for_workspace


def _load_jsonl_file(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def load_delegations(path: Path | str) -> list[dict[str, Any]]:
    """Parse one delegations.jsonl; newest records first."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    records = _load_jsonl_file(p)
    records.reverse()
    return records


def load_delegations_merged(paths: list[Path | str]) -> list[dict[str, Any]]:
    """Merge multiple session logs; newest records first."""
    records: list[dict[str, Any]] = []
    for path in paths:
        p = Path(path)
        if p.is_file():
            records.extend(_load_jsonl_file(p))
    records.sort(
        key=lambda r: r.get("timestamp_end") or r.get("timestamp_start") or "",
        reverse=True,
    )
    return records


def load_delegations_for_workspace(ws: str | Path) -> list[dict[str, Any]]:
    """Load all session logs for a workspace from home store (or legacy fallback)."""
    paths = delegation_log_paths_for_workspace(str(ws))
    if not paths:
        raise FileNotFoundError(f"No delegation logs found for workspace: {ws}")
    return load_delegations_merged(paths)
