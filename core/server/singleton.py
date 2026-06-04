"""Ensure one stdio MCP server per workspace (kill stale instances on startup)."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from core.logging.delegation_log import log_brief, log_stderr
from core.storage.paths import ensure_mcp_coder_home, mcp_coder_home, normalize_workspace, project_key

_STARTUP_GRACE_SEC = 0.5
_TERMINATE_WAIT_SEC = 2.0


def _singleton_enabled() -> bool:
    raw = os.environ.get("MCP_CODER_SINGLETON", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def pidfile_path(workspace: str | Path) -> Path:
    key = project_key(workspace)
    return mcp_coder_home() / "run" / key / "stdio.pid"


def _read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _process_cwd(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["lsof", "-p", str(pid), "-a", "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in result.stdout.splitlines():
        if line.startswith("n") and line[1:]:
            return line[1:]
    return None


def _pgrep_mcp_pids(main_script: str) -> list[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"{main_script} --mcp"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _terminate_pid(pid: int) -> bool:
    """Send SIGTERM then SIGKILL. Returns True if process is gone."""
    if pid == os.getpid():
        return False
    if not _pid_alive(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return not _pid_alive(pid)

    deadline = time.monotonic() + _TERMINATE_WAIT_SEC
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return not _pid_alive(pid)

    time.sleep(_STARTUP_GRACE_SEC)
    return not _pid_alive(pid)


def stale_mcp_pids(workspace: str | Path, *, main_script: str | None = None) -> list[int]:
    """PIDs to kill: pidfile entry + same-workspace siblings matching main.py --mcp."""
    ws = normalize_workspace(workspace)
    script = main_script or str(Path(__file__).resolve().parents[2] / "main.py")
    my_pid = os.getpid()
    stale: set[int] = set()

    recorded = _read_pid(pidfile_path(ws))
    if recorded is not None and recorded != my_pid:
        stale.add(recorded)

    for pid in _pgrep_mcp_pids(script):
        if pid == my_pid:
            continue
        cwd = _process_cwd(pid)
        if cwd and normalize_workspace(cwd) == ws:
            stale.add(pid)

    return sorted(stale)


def enforce_single_stdio_server(
    workspace: str | Path,
    *,
    main_script: str | None = None,
) -> list[int]:
    """
    Kill stale mcp-coder stdio servers for this workspace; register current PID.

    Returns PIDs we attempted to terminate (may include unkillable zombies).
    """
    if not _singleton_enabled():
        return []

    ensure_mcp_coder_home()
    ws = normalize_workspace(workspace)
    attempted: list[int] = []

    for pid in stale_mcp_pids(ws, main_script=main_script):
        attempted.append(pid)
        gone = _terminate_pid(pid)
        if log_brief():
            if gone:
                log_stderr(f"[mcp-coder] terminated stale stdio server pid={pid} ws={ws}")
            else:
                log_stderr(
                    f"[mcp-coder] could not terminate pid={pid} (zombie?); "
                    f"try quitting Cursor or reboot if MCP stays stale"
                )

    _write_pid(pidfile_path(ws), os.getpid())
    return attempted
