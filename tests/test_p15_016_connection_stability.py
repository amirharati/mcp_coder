"""P15-ISS-016: connection stability — progress heartbeat + MCP wrapper script."""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


def _wrapper_path() -> str:
    from core.version import repo_root

    return str(repo_root() / "bin" / "mcp-coder-server")


@pytest.fixture
def ctx_mock():
    ctx = MagicMock()
    ctx.info = AsyncMock()
    return ctx


def test_heartbeat_fires_after_configured_interval(ctx_mock):
    import server.mcp_server  # noqa: F401 — resolve circular imports
    from server.mcp_server import _DelegationProgressBridge

    progress = _DelegationProgressBridge(ctx_mock, heartbeat_seconds=0.1)
    try:
        time.sleep(0.35)
    finally:
        progress.close()

    assert ctx_mock.info.await_count >= 1
    messages = [str(call.args[0]) for call in ctx_mock.info.await_args_list]
    assert any("⏳" in msg for msg in messages)


def test_heartbeat_disabled_when_zero(ctx_mock):
    import server.mcp_server  # noqa: F401
    from server.mcp_server import _DelegationProgressBridge

    progress = _DelegationProgressBridge(ctx_mock, heartbeat_seconds=0)
    try:
        time.sleep(0.35)
    finally:
        progress.close()

    ctx_mock.info.assert_not_awaited()


def test_heartbeat_does_not_fire_when_notify_called_frequently(ctx_mock):
    import server.mcp_server  # noqa: F401
    from server.mcp_server import _DelegationProgressBridge

    progress = _DelegationProgressBridge(ctx_mock, heartbeat_seconds=0.3)
    try:
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            progress.notify("working", force=True)
            time.sleep(0.1)
    finally:
        progress.close()

    messages = [str(call.args[0]) for call in ctx_mock.info.await_args_list]
    assert messages
    assert not any("⏳" in msg for msg in messages)


def test_wrapper_script_path_in_mcp_json_config(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("AIDER_MODEL=openrouter/test/m\n", encoding="utf-8")

    from core.cli.setup import mcp_json_config

    entry = mcp_json_config(env_file=str(env_file))
    wrapper = _wrapper_path()

    assert entry["command"].endswith("mcp-coder-server")
    assert entry["command"] == wrapper
    assert entry["args"] == []
    assert entry["env"]["MCP_CODER_ENV_FILE"] == str(env_file)

    wrapper_path = os.path.join(
        os.path.dirname(__file__), "..", "bin", "mcp-coder-server"
    )
    wrapper_path = os.path.realpath(wrapper_path)
    assert os.path.isfile(wrapper_path)
    assert os.access(wrapper_path, os.X_OK)
