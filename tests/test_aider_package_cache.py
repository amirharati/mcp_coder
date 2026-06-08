"""Integration: run_context busts executor cache when package hash changes."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from core.context.package import COMPILER_VERSION, ContextPackage, PathEntry, TIER_EDIT_FULL
from core.engine.aider_engine import AiderEngine
from core.session.executor_cache import clear_executor_cache


def _package(brief: str) -> ContextPackage:
    return ContextPackage(
        brief=brief,
        entries=[PathEntry(path="pkg/cli.py", tier=TIER_EDIT_FULL, payload="x = 1\n")],
        policies=None,
        metadata={"compiler_version": COMPILER_VERSION},
    )


@pytest.fixture
def mock_aider_stack(monkeypatch):
    mock_io = MagicMock()
    mock_io.num_error_outputs = 0
    mock_buffer = MagicMock()
    mock_buffer.getvalue.return_value = ""

    mock_coder = MagicMock()
    mock_coder.run.return_value = "done"

    mock_coder_cls = MagicMock()
    mock_coder_cls.create.return_value = mock_coder

    fake_coders = MagicMock()
    fake_coders.Coder = mock_coder_cls
    fake_models = MagicMock()
    fake_models.Model.return_value = MagicMock()

    monkeypatch.setitem(sys.modules, "aider.coders", fake_coders)
    monkeypatch.setitem(sys.modules, "aider.models", fake_models)

    monkeypatch.setattr("core.engine.aider_engine.create_delegation_io", lambda: (mock_io, mock_buffer))
    monkeypatch.setattr("core.engine.aider_engine.snapshot_git_dirty", lambda ws: set())
    monkeypatch.setattr("core.engine.aider_engine.snapshot_mtimes", lambda ws, paths: {})
    monkeypatch.setattr("core.engine.aider_engine.files_touched_since_snapshot", lambda *a, **k: ([], False))
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

    return mock_coder_cls


def test_run_context_recreates_on_package_hash_change(tmp_path, mock_aider_stack):
    clear_executor_cache()
    ws = tmp_path / "ws"
    (ws / "pkg").mkdir(parents=True)
    (ws / "pkg" / "cli.py").write_text("x = 1\n", encoding="utf-8")

    engine = AiderEngine(model_name="openrouter/openai/gpt-4o-mini")

    first = engine.run_context(_package("brief one"), workspace_path=str(ws), mcp_session_id="sess-rc")
    second = engine.run_context(_package("brief two"), workspace_path=str(ws), mcp_session_id="sess-rc")
    third = engine.run_context(_package("brief two"), workspace_path=str(ws), mcp_session_id="sess-rc")

    assert first.executor_recreated is True
    assert first.executor_reused is False
    assert second.executor_recreated is True
    assert second.executor_reused is False
    assert third.executor_reused is True
    assert third.executor_recreated is False
    assert mock_aider_stack.create.call_count == 2
