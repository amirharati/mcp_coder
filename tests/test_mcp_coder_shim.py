"""Smoke tests for scripts/mcp-coder CLI shim (P2-ISS-010)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIM = REPO_ROOT / "scripts" / "mcp-coder"


def test_shim_exists_and_is_executable():
    assert SHIM.is_file()
    assert os.access(SHIM, os.X_OK)


def test_shim_help_lists_subcommands():
    proc = subprocess.run(
        ["bash", str(SHIM), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "inspect-context" in proc.stdout
    assert "history" in proc.stdout
    assert "test-model" in proc.stdout


def test_shim_no_args_passes_mcp_flag():
    """MCP launch (no args) must include --mcp for singleton process matching."""
    text = SHIM.read_text(encoding="utf-8")
    # The no-arg path runs main.py with --mcp inside an auto-restart loop
    # (P15-ISS-027); it must still pass --mcp.
    assert '"$REPO_ROOT/main.py" --mcp' in text


def test_shim_no_args_has_restart_loop():
    """P15-ISS-027: no-arg path must auto-restart main.py on benign disconnect."""
    text = SHIM.read_text(encoding="utf-8")
    # The restart loop guards the no-arg server path so a benign client
    # disconnect (main.py exits 0) doesn't leave Cursor on "Not connected".
    assert "while true" in text
    assert "restarting" in text
    assert "130" in text and "143" in text  # SIGINT/SIGTERM stop the loop


def test_shim_no_args_restarts_on_benign_disconnect(tmp_path):
    """P15-ISS-027: loop restarts main.py after an exit-0 (benign) disconnect."""
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_py = venv_bin / "python"
    marker = tmp_path / "count"
    # Fake python: counts invocations; exits 0 (benign) twice, then 130 (SIGINT)
    # to stop the loop cleanly so the test doesn't hang.
    fake_py.write_text(
        f'''#!/usr/bin/env bash
n=$(cat "{marker}" 2>/dev/null || echo 0)
n=$((n+1))
echo "$n" > "{marker}"
if [[ "$n" -ge 3 ]]; then
  exit 130
fi
exit 0
''',
        encoding="utf-8",
    )
    fake_py.chmod(0o755)
    # main.py must exist (the shim references it) but the fake python ignores it.
    (tmp_path / "main.py").write_text("# stub\n", encoding="utf-8")

    env = {
        **os.environ,
        "MCP_CODER_REPO_ROOT": str(tmp_path),
        "MCP_CODER_ENV_FILE": str(tmp_path / "nonexistent.env"),  # skip .env sourcing
    }
    proc = subprocess.run(
        ["bash", str(SHIM)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
        env=env,
    )
    # Loop stopped via SIGINT (130) on the 3rd invocation.
    assert proc.returncode == 130
    assert marker.read_text(encoding="utf-8").strip() == "3"
    # Two benign restarts were logged.
    assert proc.stderr.count("restarting") == 2


def test_shim_cli_path_still_execs():
    """CLI path (args present) must still exec main.py directly, no loop."""
    text = SHIM.read_text(encoding="utf-8")
    assert 'exec "$PYTHON" "$REPO_ROOT/main.py" "$@"' in text
