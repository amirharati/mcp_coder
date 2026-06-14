"""Delegation timeout must return without blocking on executor shutdown (P2-ISS-006)."""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from core.engine.aider_engine import AiderEngine


@pytest.fixture
def mock_aider_slow_coder(monkeypatch):
    mock_io = MagicMock()
    mock_io.num_error_outputs = 0
    mock_buffer = MagicMock()
    mock_buffer.getvalue.return_value = ""

    def slow_run(_prompt):
        time.sleep(5)
        return "done"

    mock_coder = MagicMock()
    mock_coder.run.side_effect = slow_run

    mock_coder_cls = MagicMock()
    mock_coder_cls.create.return_value = mock_coder

    fake_coders = MagicMock()
    fake_coders.Coder = mock_coder_cls
    fake_models = MagicMock()
    fake_models.Model.return_value = MagicMock()
    mock_observable_cls = MagicMock()
    mock_observable_cls.return_value = MagicMock()

    monkeypatch.setitem(sys.modules, "aider.coders", fake_coders)
    monkeypatch.setitem(sys.modules, "aider.models", fake_models)
    monkeypatch.setattr("core.engine.observable_model.ObservableModel", mock_observable_cls)

    monkeypatch.setattr("core.engine.aider_engine.create_delegation_io", lambda: (mock_io, mock_buffer))
    monkeypatch.setattr("core.engine.aider_engine.snapshot_git_dirty", lambda ws: set())
    monkeypatch.setattr("core.engine.aider_engine.snapshot_mtimes", lambda ws, paths: {})
    monkeypatch.setattr("core.engine.aider_engine.begin_delegation_snapshot", lambda **k: None)
    monkeypatch.setattr(
        "core.engine.aider_engine.resolve_delegation_attribution",
        lambda **k: ([], [], None, False, 0),
    )
    monkeypatch.setattr("core.engine.aider_engine.merged_capture", lambda *a: "")

    @contextmanager
    def fake_block_webbrowser_open():
        yield

    @contextmanager
    def fake_isolated_stdio():
        yield MagicMock(), MagicMock()

    monkeypatch.setattr("core.engine.aider_engine.block_webbrowser_open", fake_block_webbrowser_open)
    monkeypatch.setattr("core.engine.aider_engine.isolated_stdio", fake_isolated_stdio)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")


def test_timeout_returns_without_waiting_for_worker(tmp_path, mock_aider_slow_coder, monkeypatch):
    monkeypatch.setenv("MCP_CODER_DELEGATION_TIMEOUT_S", "0.1")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "foo.py").write_text("x = 1\n", encoding="utf-8")

    engine = AiderEngine(model_name="openrouter/openai/gpt-4o-mini")

    t0 = time.perf_counter()
    result = engine.run("task", ["foo.py"], workspace_path=str(ws), mcp_session_id="sess-timeout")
    elapsed = time.perf_counter() - t0

    assert result.success is False
    assert result.error_class == "timeout"
    assert elapsed < 2.0
