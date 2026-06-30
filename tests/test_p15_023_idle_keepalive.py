"""P15-023: server-level idle keepalive between tool calls."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def session_mock():
    session = MagicMock()
    session.send_log_message = AsyncMock()
    return session


def test_keepalive_fires_after_idle_interval(monkeypatch, session_mock):
    """D1: keepalive sends notifications/message after silence exceeds interval."""
    monkeypatch.setenv("MCP_CODER_IDLE_KEEPALIVE_S", "0.15")
    import server.mcp_server as ms

    ms._idle_session = session_mock
    ms._idle_last_activity = time.monotonic() - 1.0

    async def _run() -> None:
        async with ms._idle_keepalive_lifespan(None):
            await asyncio.sleep(0.35)

    asyncio.run(_run())

    session_mock.send_log_message.assert_awaited()
    kwargs = session_mock.send_log_message.await_args.kwargs
    assert kwargs.get("level") == "info"
    assert "keepalive" in str(kwargs.get("data", ""))


def test_keepalive_silent_when_recent_activity(monkeypatch, session_mock):
    """D2: keepalive does not fire while activity timestamps stay fresh."""
    monkeypatch.setenv("MCP_CODER_IDLE_KEEPALIVE_S", "0.5")
    import server.mcp_server as ms

    ms._idle_session = session_mock
    handler = ms.mcp._mcp_server._handle_message

    async def _run() -> None:
        async with ms._idle_keepalive_lifespan(None):
            end = time.monotonic() + 0.7
            while time.monotonic() < end:
                try:
                    await handler(MagicMock(), session_mock, MagicMock(), False)
                except Exception:
                    pass
                await asyncio.sleep(0.2)

    asyncio.run(_run())

    session_mock.send_log_message.assert_not_awaited()


def test_keepalive_disabled_when_zero(monkeypatch, session_mock):
    """D3: MCP_CODER_IDLE_KEEPALIVE_S=0 disables the background task."""
    monkeypatch.setenv("MCP_CODER_IDLE_KEEPALIVE_S", "0")
    import server.mcp_server as ms

    ms._idle_session = session_mock
    ms._idle_last_activity = time.monotonic() - 60.0

    async def _run() -> None:
        async with ms._idle_keepalive_lifespan(None):
            await asyncio.sleep(0.2)

    asyncio.run(_run())

    session_mock.send_log_message.assert_not_awaited()


def test_session_capture_updates_holder():
    """D4: tracking _handle_message sets _idle_session and _idle_last_activity."""
    import server.mcp_server as ms

    mock_session = MagicMock()
    handler = ms.mcp._mcp_server._handle_message
    before_activity = ms._idle_last_activity

    async def _run() -> None:
        try:
            await handler(MagicMock(), mock_session, MagicMock(), False)
        except Exception:
            pass

    asyncio.run(_run())

    assert ms._idle_session is mock_session
    assert ms._idle_last_activity >= before_activity


def test_idle_keepalive_seconds_env_reading(monkeypatch):
    """D5: _idle_keepalive_seconds() parses env with sane fallbacks."""
    import server.mcp_server as ms

    monkeypatch.delenv("MCP_CODER_IDLE_KEEPALIVE_S", raising=False)
    assert ms._idle_keepalive_seconds() == 25.0

    monkeypatch.setenv("MCP_CODER_IDLE_KEEPALIVE_S", "12.5")
    assert ms._idle_keepalive_seconds() == 12.5

    monkeypatch.setenv("MCP_CODER_IDLE_KEEPALIVE_S", "not-a-number")
    assert ms._idle_keepalive_seconds() == 25.0

    monkeypatch.setenv("MCP_CODER_IDLE_KEEPALIVE_S", "0")
    assert ms._idle_keepalive_seconds() == 0.0


def test_delegation_heartbeat_unchanged():
    """D6: delegation heartbeat bridge remains orthogonal to idle keepalive."""
    import server.mcp_server as ms
    from server.mcp_server import _DelegationProgressBridge

    assert callable(ms._progress_heartbeat_seconds)
    assert callable(ms._idle_keepalive_seconds)

    ctx = MagicMock()
    ctx.info = AsyncMock()
    progress = _DelegationProgressBridge(ctx, heartbeat_seconds=0.1)
    try:
        time.sleep(0.35)
    finally:
        progress.close()

    assert ctx.info.await_count >= 1
    messages = [str(call.args[0]) for call in ctx.info.await_args_list]
    assert any("delegation" in msg for msg in messages)
