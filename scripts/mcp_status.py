#!/usr/bin/env python3
"""Check whether active MCP stdio server is fresh for this repo."""

from __future__ import annotations

import datetime as dt
import shlex
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _candidate_pids(repo: Path) -> list[int]:
    proc = _run(["pgrep", "-f", f"{repo}/main.py"])
    if proc.returncode not in (0, 1):
        return []
    out: list[int] = []
    for line in proc.stdout.splitlines():
        s = line.strip()
        if s.isdigit():
            out.append(int(s))
    return out


def _ps_field(pid: int, field: str) -> str:
    proc = _run(["ps", "-p", str(pid), "-o", f"{field}="])
    return (proc.stdout or "").strip()


def _is_stdio_server_command(command: str) -> bool:
    if not command:
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    idx = -1
    for i, tok in enumerate(argv):
        if tok.endswith("/main.py") or tok == "main.py":
            idx = i
            break
    if idx < 0:
        return False
    tail = argv[idx + 1 :]
    if not tail:
        return True
    return tail[0] == "--mcp"


def _parse_lstart(raw: str) -> dt.datetime | None:
    if not raw:
        return None
    try:
        # Example: Sat Jun 20 13:02:12 2026
        return dt.datetime.strptime(raw, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None


def _dirty_files(repo: Path) -> list[Path]:
    proc = _run(["git", "-C", str(repo), "status", "--porcelain"])
    if proc.returncode != 0:
        return []
    files: list[Path] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        rel = line[3:].strip()
        if not rel:
            continue
        p = repo / rel
        if p.is_file():
            files.append(p)
    return files


def main() -> int:
    repo = _repo_root()
    dirty = _dirty_files(repo)
    latest_change: dt.datetime | None = None
    if dirty:
        latest_ts = max(p.stat().st_mtime for p in dirty)
        latest_change = dt.datetime.fromtimestamp(latest_ts)

    servers: list[tuple[int, str, dt.datetime | None]] = []
    for pid in _candidate_pids(repo):
        cmd = _ps_field(pid, "command")
        if not _is_stdio_server_command(cmd):
            continue
        started = _parse_lstart(_ps_field(pid, "lstart"))
        servers.append((pid, cmd, started))

    print(f"repo: {repo}")
    print(f"dirty_files: {len(dirty)}")
    if latest_change is not None:
        print(f"latest_dirty_change: {latest_change.isoformat(sep=' ', timespec='seconds')}")

    if not servers:
        print("status: NO_STDIO_SERVER")
        print("hint: restart MCP in Cursor or run `make mcp-kill` then restart.")
        return 1

    stale = False
    if len(servers) > 1:
        stale = True
        print(f"status: MULTIPLE_STDIO_SERVERS ({len(servers)})")
    else:
        print("status: ONE_STDIO_SERVER")

    for pid, cmd, started in servers:
        print(f"- pid={pid}")
        print(f"  started={started.isoformat(sep=' ', timespec='seconds') if started else 'unknown'}")
        print(f"  cmd={cmd}")
        if latest_change is not None and started is not None and started < latest_change:
            print("  freshness=STALE (started before latest local change)")
            stale = True
        else:
            print("  freshness=OK")

    if stale:
        print("action: run `make mcp-kill` then restart MCP in Cursor.")
        return 2

    print("action: server looks fresh for current local code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

