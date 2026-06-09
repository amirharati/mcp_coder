"""Backend-neutral verify command runner (P4-010)."""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

TAIL_MAX_BYTES = 4096


@dataclass
class VerifyResult:
    ran: bool
    passed: bool | None  # None = error/unknown
    command: str
    exit_code: int | None
    duration_ms: int
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None

    def to_response_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ran": self.ran,
            "passed": self.passed,
            "command": self.command,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }
        if self.error:
            payload["error"] = self.error
        return payload

    def to_audit_dict(self, *, enabled: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "enabled": enabled,
            "ran": self.ran,
            "passed": self.passed,
            "command": self.command,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def _tail_bytes(text: str, max_bytes: int = TAIL_MAX_BYTES) -> str:
    if not text:
        return ""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    tail = raw[-max_bytes:]
    while tail:
        try:
            return tail.decode("utf-8")
        except UnicodeDecodeError:
            tail = tail[1:]
    return ""


def run_verify_command(
    *,
    workspace: Path,
    command: str,
    timeout_s: int,
) -> VerifyResult:
    """Run verify shell command in workspace; never raises."""
    ws = workspace.resolve()
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            shlex.split(command),
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=False,
            check=False,
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return VerifyResult(
            ran=True,
            passed=proc.returncode == 0,
            command=command,
            exit_code=proc.returncode,
            duration_ms=duration_ms,
            stdout_tail=_tail_bytes(proc.stdout or ""),
            stderr_tail=_tail_bytes(proc.stderr or ""),
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        return VerifyResult(
            ran=True,
            passed=None,
            command=command,
            exit_code=None,
            duration_ms=duration_ms,
            stdout_tail=_tail_bytes(stdout),
            stderr_tail=_tail_bytes(stderr),
            error="timeout",
        )
    except (OSError, ValueError) as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return VerifyResult(
            ran=True,
            passed=None,
            command=command,
            exit_code=None,
            duration_ms=duration_ms,
            error=f"{type(exc).__name__}: {exc}",
        )
