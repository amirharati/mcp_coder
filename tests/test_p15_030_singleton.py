"""P15-030: MCP singleton reliability — startup enforce + stdio_health + cross-ws kill."""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from unittest.mock import patch

import pytest

# Resolve circular import (same precondition as test_main_crash_handling.py).
import server.mcp_server  # noqa: F401
import main
from server.mcp_server import _build_server_status, get_server_status


@contextmanager
def _patch_mcp_startup(monkeypatch, tmp_path):
    """Minimal stubs so main.main() reaches run_stdio on the --mcp path."""
    ws = tmp_path / "consumer-repo"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_WORKSPACE", str(ws))
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "mcp-home"))
    monkeypatch.setenv("MCP_CODER_SINGLETON", "1")

    monkeypatch.setattr(main, "_bootstrap_cli_env", lambda: None)
    monkeypatch.setattr(main, "_reconcile_on_startup", lambda _ws: None)

    with (
        patch("core.host.cursor_rules.sync_workspace_cursor_rules", return_value={}),
        patch("core.specs.bootstrap.ensure_workspace_spec_layout", return_value={}),
        patch("core.logging.server_log.resolve_config") as resolve_cfg,
        patch("core.logging.server_log.server_log_emit"),
        patch("core.session.policy.resolve_session_policy", return_value={}),
        patch("server.mcp_server.run_stdio", side_effect=SystemExit(0)),
    ):
        resolve_cfg.return_value.scope = "test"
        resolve_cfg.return_value.level = "info"
        yield ws


def test_t1_enforce_single_stdio_server_called_at_startup(tmp_path, monkeypatch):
    """T1: --mcp startup path calls enforce_single_stdio_server with workspace."""
    calls: list[tuple] = []

    def _track_enforce(ws, *, main_script=None):
        calls.append((ws, main_script))
        return []

    with _patch_mcp_startup(monkeypatch, tmp_path):
        with patch(
            "core.server.singleton.enforce_single_stdio_server",
            side_effect=_track_enforce,
        ):
            monkeypatch.setattr(sys, "argv", ["mcp-coder", "--mcp"])
            with pytest.raises(SystemExit) as exc:
                main.main()

    assert exc.value.code == 0
    assert len(calls) == 1
    ws_arg, script_arg = calls[0]
    assert os.path.samefile(ws_arg, os.environ["MCP_CODER_WORKSPACE"])
    assert script_arg is not None and script_arg.endswith("main.py")


def test_t2_stdio_health_one_when_no_stale_pids(monkeypatch):
    """T2: stdio_health ONE when no stale or cross-workspace servers."""
    my_pid = os.getpid()
    with (
        patch("server.mcp_server.stale_mcp_pids", return_value=[]),
        patch("core.server.singleton._pgrep_mcp_pids", return_value=[my_pid]),
    ):
        data = _build_server_status("/tmp/ws")

    assert data["stdio_health"] == "ONE"
    assert data["recommended_action"] is None


def test_t3_stdio_health_multiple_when_stale_same_workspace(monkeypatch):
    """T3: stdio_health MULTIPLE + kill-all hint when same-ws stale pids."""
    my_pid = os.getpid()
    with (
        patch("server.mcp_server.stale_mcp_pids", return_value=[1234]),
        patch("core.server.singleton._pgrep_mcp_pids", return_value=[my_pid, 1234]),
    ):
        data = _build_server_status("/tmp/ws")

    assert data["stdio_health"] == "MULTIPLE"
    assert data["recommended_action"] is not None
    assert "mcp-coder kill --all" in data["recommended_action"]


def test_t4_stdio_health_multiple_when_cross_workspace_servers(monkeypatch):
    """T4: stdio_health MULTIPLE when other-workspace servers are alive."""
    my_pid = os.getpid()
    with (
        patch("server.mcp_server.stale_mcp_pids", return_value=[]),
        patch("core.server.singleton._pgrep_mcp_pids", return_value=[my_pid, 9999]),
    ):
        data = _build_server_status("/tmp/ws")

    assert data["stdio_health"] == "MULTIPLE"


def test_t5_get_server_status_includes_stdio_health():
    """T5: live get_server_status response includes stdio_health."""
    raw = get_server_status()
    data = json.loads(raw)
    assert "stdio_health" in data


def test_t6_singleton_kill_all_terminates_cross_workspace_pids(tmp_path, monkeypatch):
    """T6: MCP_CODER_SINGLETON_KILL_ALL=1 kills non-self MCP pids at startup."""
    my_pid = os.getpid()
    terminated: list[int] = []

    def _track_terminate(pid: int) -> bool:
        terminated.append(pid)
        return True

    monkeypatch.setenv("MCP_CODER_SINGLETON_KILL_ALL", "1")

    with _patch_mcp_startup(monkeypatch, tmp_path):
        with (
            patch("core.server.singleton.enforce_single_stdio_server", return_value=[]),
            patch("core.server.singleton._pgrep_mcp_pids", return_value=[my_pid, 7777]),
            patch("core.server.singleton._terminate_pid", side_effect=_track_terminate),
        ):
            monkeypatch.setattr(sys, "argv", ["mcp-coder", "--mcp"])
            with pytest.raises(SystemExit) as exc:
                main.main()

    assert exc.value.code == 0
    assert terminated == [7777]
