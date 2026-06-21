from __future__ import annotations

import datetime as dt
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

from core.logging.delegation_log import workspace_path
from core.version import repo_root


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _parse_lstart(raw: str) -> dt.datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    formats = (
        "%a %b %d %H:%M:%S %Y",  # e.g. Sat Jun 20 15:25:54 2026
        "%a %d %b %H:%M:%S %Y",  # e.g. Sat 20 Jun 15:25:54 2026 (locale variant)
    )
    for fmt in formats:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _ps_field(pid: int, field: str) -> str:
    proc = _run(["ps", "-p", str(pid), "-o", f"{field}="])
    return (proc.stdout or "").strip()


def _cwd_for_pid(pid: int) -> Path | None:
    proc = _run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"])
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("n") and line[1:]:
            try:
                return Path(line[1:]).resolve()
            except OSError:
                return None
    return None


def _is_stdio_server_command(command: str, repo: Path) -> bool:
    if not command:
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    idx = -1
    for i, tok in enumerate(argv):
        if tok == str(repo / "main.py") or tok.endswith("/main.py") or tok == "main.py":
            idx = i
            break
    if idx < 0:
        return False
    tail = argv[idx + 1 :]
    return bool(tail) and tail[0] == "--mcp"


def _candidate_pids(repo: Path) -> list[int]:
    proc = _run(["pgrep", "-f", str(repo / "main.py")])
    if proc.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in proc.stdout.splitlines():
        s = line.strip()
        if s.isdigit():
            pids.append(int(s))
    return pids


def _server_rows(repo: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for pid in _candidate_pids(repo):
        cmd = _ps_field(pid, "command")
        if not _is_stdio_server_command(cmd, repo):
            continue
        started_raw = _ps_field(pid, "lstart")
        rows.append(
            {
                "pid": pid,
                "started": _parse_lstart(started_raw),
                "started_raw": started_raw,
                "command": cmd,
                "cwd": _cwd_for_pid(pid),
            }
        )
    rows.sort(key=lambda r: int(r["pid"]))
    return rows


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


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_pid(pid: int) -> bool:
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


def cmd_ps() -> int:
    repo = repo_root()
    rows = _server_rows(repo)
    if not rows:
        print("(no mcp-coder processes)")
        return 0
    for row in rows:
        started = row["started"]
        started_raw = str(row.get("started_raw") or "").strip()
        if isinstance(started, dt.datetime):
            started_s = started.isoformat(sep=" ", timespec="seconds")
        elif started_raw:
            started_s = started_raw
        else:
            started_s = "unknown"
        cwd = str(row["cwd"]) if row["cwd"] else "unknown"
        print(f"{row['pid']}  {started_s}  cwd={cwd}\n    {row['command']}")
    return 0


def cmd_status() -> int:
    repo = repo_root()
    dirty = _dirty_files(repo)
    latest_change: dt.datetime | None = None
    if dirty:
        latest_change = dt.datetime.fromtimestamp(max(p.stat().st_mtime for p in dirty))
    rows = _server_rows(repo)

    print(f"repo: {repo}")
    print(f"dirty_files: {len(dirty)}")
    if latest_change is not None:
        print(f"latest_dirty_change: {latest_change.isoformat(sep=' ', timespec='seconds')}")

    if not rows:
        print("status: NO_STDIO_SERVER")
        print("hint: restart MCP in Cursor (or run `mcp-coder --mcp` manually).")
        return 1

    stale = False
    freshness_unknown = False
    if len(rows) > 1:
        stale = True
        print(f"status: MULTIPLE_STDIO_SERVERS ({len(rows)})")
    else:
        print("status: ONE_STDIO_SERVER")

    for row in rows:
        pid = row["pid"]
        started = row["started"]
        cmd = row["command"]
        cwd = row["cwd"]
        print(f"- pid={pid}")
        started_raw = str(row.get("started_raw") or "").strip()
        if isinstance(started, dt.datetime):
            started_s = started.isoformat(sep=" ", timespec="seconds")
        elif started_raw:
            started_s = started_raw
        else:
            started_s = "unknown"
        print(f"  started={started_s}")
        print(f"  cwd={cwd or 'unknown'}")
        print(f"  cmd={cmd}")
        if started is None:
            print("  freshness=UNKNOWN (cannot read process start time)")
            freshness_unknown = True
        elif (
            latest_change is not None
            and started < latest_change
        ):
            print("  freshness=STALE (started before latest local change)")
            stale = True
        else:
            print("  freshness=OK")

    if stale:
        print("action: run `mcp-coder kill --all` then restart MCP in Cursor.")
        return 2
    if freshness_unknown:
        print("action: start time unavailable; run `mcp-coder kill --all` then restart MCP in Cursor.")
        return 2
    print("action: server looks fresh for current local code.")
    return 0


def cmd_kill(
    *,
    all_processes: bool = False,
    workspace: str | None = None,
    min_age_seconds: float = 0.0,
) -> int:
    repo = repo_root()
    rows = _server_rows(repo)
    if not rows:
        print("(no mcp-coder processes)")
        return 0

    ws = Path(workspace or workspace_path()).resolve()
    targets: list[dict[str, object]] = []
    if all_processes:
        targets = rows
    else:
        for row in rows:
            cwd = row.get("cwd")
            if isinstance(cwd, Path) and cwd == ws:
                targets.append(row)

    if not targets:
        scope = "all workspaces" if all_processes else f"workspace {ws}"
        print(f"no matching mcp-coder processes for {scope}")
        return 0

    killed: list[int] = []
    failed: list[int] = []
    now = dt.datetime.now()
    for row in targets:
        pid = int(row["pid"])
        started = row.get("started")
        if (
            min_age_seconds > 0
            and isinstance(started, dt.datetime)
            and (now - started).total_seconds() < min_age_seconds
        ):
            continue
        if _terminate_pid(pid):
            killed.append(pid)
        else:
            failed.append(pid)

    if killed:
        print("killed pids:", " ".join(str(p) for p in killed))
    if failed:
        print("failed to kill pids:", " ".join(str(p) for p in failed))
        return 1
    if not killed:
        print("no matching mcp-coder processes old enough to kill")
    return 0
