from __future__ import annotations

from unittest.mock import patch

from core.server.singleton import (
    _is_stdio_server_cmdline,
    enforce_single_stdio_server,
    pidfile_path,
    stale_mcp_pids,
)


def test_pidfile_path_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    ws = tmp_path / "workspace"
    ws.mkdir()
    path = pidfile_path(ws)
    assert "run" in path.parts
    assert path.name == "stdio.pid"


def test_stale_mcp_pids_includes_pidfile_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    ws = tmp_path / "workspace"
    ws.mkdir()
    pf = pidfile_path(ws)
    pf.parent.mkdir(parents=True)
    pf.write_text("99999\n", encoding="utf-8")

    with patch("core.server.singleton._pgrep_mcp_pids", return_value=[]):
        with patch("core.server.singleton._pid_alive", return_value=True):
            stale = stale_mcp_pids(ws, main_script="/tmp/main.py")
    assert 99999 in stale


def test_enforce_single_stdio_server_writes_current_pid(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_SINGLETON", "1")
    ws = tmp_path / "workspace"
    ws.mkdir()

    with patch("core.server.singleton.stale_mcp_pids", return_value=[4242]):
        with patch("core.server.singleton._terminate_pid", return_value=True):
            killed = enforce_single_stdio_server(ws, main_script="/tmp/main.py")

    assert killed == [4242]
    assert pidfile_path(ws).read_text().strip() == str(__import__("os").getpid())


def test_singleton_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_SINGLETON", "0")
    ws = tmp_path / "workspace"
    ws.mkdir()
    assert enforce_single_stdio_server(ws) == []


def test_is_stdio_server_cmdline():
    script = "/repo/mcp_coder/main.py"
    assert _is_stdio_server_cmdline(f"python {script}", script)
    assert _is_stdio_server_cmdline(f"python {script} --mcp", script)
    assert not _is_stdio_server_cmdline(f"python {script} delegate --task t", script)
    assert not _is_stdio_server_cmdline(f"python {script} setup", script)
    assert not _is_stdio_server_cmdline(None, script)
