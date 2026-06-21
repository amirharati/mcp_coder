#!/usr/bin/env python3
"""Kill mcp-coder stdio server processes for a specific workspace cwd."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _pgrep_pids() -> list[int]:
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "mcp_coder/main.py --mcp"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _cwd_for_pid(pid: int) -> Path | None:
    try:
        proc = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("n") and line[1:]:
            try:
                return Path(line[1:]).resolve()
            except OSError:
                return None
    return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate(pid: int) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    time.sleep(0.2)
    return not _alive(pid)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kill mcp-coder server for one workspace.")
    parser.add_argument(
        "--workspace",
        default=os.getcwd(),
        help="Workspace path to match against server process cwd (default: current directory).",
    )
    args = parser.parse_args()

    target = Path(args.workspace).resolve()
    self_pid = os.getpid()
    candidates = _pgrep_pids()
    matched: list[int] = []
    for pid in candidates:
        if pid == self_pid:
            continue
        cwd = _cwd_for_pid(pid)
        if cwd == target:
            matched.append(pid)

    if not matched:
        print(f"no mcp-coder stdio server for workspace: {target}")
        return 0

    gone: list[int] = []
    failed: list[int] = []
    for pid in matched:
        if _terminate(pid):
            gone.append(pid)
        else:
            failed.append(pid)

    if gone:
        print(f"killed pids for workspace {target}: {' '.join(str(p) for p in gone)}")
    if failed:
        print(f"failed to kill pids for workspace {target}: {' '.join(str(p) for p in failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
