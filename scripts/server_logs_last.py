#!/usr/bin/env python3
"""Print the last N server audit log lines (global or per-project)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.logging.server_log import server_log_path_global, server_log_path_project
from core.storage.paths import normalize_workspace


def _read_last_lines(path: Path, n: int = 5) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def main() -> int:
    n = 5
    args = sys.argv[1:]
    if args and args[0].isdigit():
        n = int(args.pop(0))

    if args:
        ws = normalize_workspace(args[0])
        path = server_log_path_project(ws)
        label = f"project server log ({ws})"
    else:
        path = server_log_path_global()
        label = "global server log"

    records = _read_last_lines(path, n)
    print(f"{label}: {path}")
    if not records:
        if args and not path.is_file():
            global_path = server_log_path_global()
            print(f"(no project log; try global: {global_path})")
        else:
            print("(no server log lines yet)")
        return 0

    for record in records:
        event = record.get("event", "?")
        ts = str(record.get("timestamp", ""))[:19]
        level = record.get("level", "")
        extra = {k: v for k, v in record.items() if k not in ("type", "event", "timestamp", "level", "pid")}
        print(f"  [{ts}] {level} {event} {extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
