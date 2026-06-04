#!/usr/bin/env python3
"""Print summary of the latest delegation for a workspace."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.storage.paths import sessions_root


def main() -> int:
    ws = Path(sys.argv[1] if len(sys.argv) > 1 else Path.cwd()).resolve()
    root = sessions_root(ws)
    if not root.is_dir():
        print(f"workspace: {ws}")
        print("(no sessions yet)")
        return 0

    logs = sorted(root.glob("*/delegations.jsonl"), key=lambda p: p.stat().st_mtime)
    if not logs:
        print(f"workspace: {ws}")
        print("(no delegations yet)")
        return 0

    last_log = logs[-1]
    record = json.loads(last_log.read_text(encoding="utf-8").strip().splitlines()[-1])
    print(f"workspace: {ws}")
    print(f"log: {last_log}")
    print(f"  time:    {record.get('timestamp_end', '')[:19]}")
    print(f"  policy:  {record.get('session_policy')}")
    print(f"  action:  {record.get('session_action')} ({record.get('session_reason')})")
    host = record.get("host_session_id") or "null"
    print(f"  host:    {host[:12]}")
    print(f"  session: {str(record.get('mcp_session_id', ''))[:8]}…")
    print(f"  success: {record.get('success')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
