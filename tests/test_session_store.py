from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from core.host.apply import apply_host_hint
from core.host.base import HostSessionHint
from core.session.policy import POLICY_ALIGN_HOST, POLICY_ALWAYS_NEW
from core.session.store import SessionStore
from server.mcp_server import delegate_to_agent


def _setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    return home, workspace


def _mock_engine():
    fake_result = ExecutionResult(
        success=True,
        output="done",
        files_changed=["hello.py"],
        model="gpt-4o",
        tokens={"source": "unavailable"},
    )
    return type(
        "MockEngine",
        (),
        {"model_name": "gpt-4o", "backend_id": "aider", "run": lambda *a, **k: fake_result},
    )()


def test_always_new_creates_two_session_dirs(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_HOST", "none")

    with patch("server.mcp_server.get_engine", return_value=_mock_engine()):
        r1 = json.loads(delegate_to_agent("t1", ["hello.py"], "ctx", backend="aider"))
        r2 = json.loads(delegate_to_agent("t2", ["hello.py"], "ctx", backend="aider"))

    assert r1["mcp_session_id"] != r2["mcp_session_id"]
    assert r1["session_policy"] == POLICY_ALWAYS_NEW
    assert r1["session_reused"] is False
    assert r2["session_reused"] is False


def test_align_host_reuses_session(tmp_path, monkeypatch):
    _, workspace = _setup(tmp_path, monkeypatch)
    store = SessionStore()
    hint = HostSessionHint(host_kind="cursor", host_session_id="host-1")
    first = store.acquire(workspace, POLICY_ALIGN_HOST, hint)
    apply_host_hint(first.session_dir, hint)
    second = store.acquire(workspace, POLICY_ALIGN_HOST, hint)

    assert first.mcp_session_id == second.mcp_session_id
    assert first.is_new is True
    assert second.is_new is False
    assert second.session_action == "reuse"
    assert second.session_reason == "align_host_reuse"


def test_align_host_no_host_creates_new_each_time(tmp_path, monkeypatch):
    _, workspace = _setup(tmp_path, monkeypatch)
    store = SessionStore()
    hint = HostSessionHint()
    first = store.acquire(workspace, POLICY_ALIGN_HOST, hint)
    second = store.acquire(workspace, POLICY_ALIGN_HOST, hint)
    assert first.mcp_session_id != second.mcp_session_id
    assert second.session_reason == "align_host_no_host_id"


def test_align_host_new_host_creates_session(tmp_path, monkeypatch):
    _, workspace = _setup(tmp_path, monkeypatch)
    store = SessionStore()
    hint = HostSessionHint(host_kind="cursor", host_session_id="brand-new")
    result = store.acquire(workspace, POLICY_ALIGN_HOST, hint)
    assert result.is_new is True
    assert result.session_reason == "align_host_new"


def test_delegate_align_host_two_calls_one_jsonl(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_SESSION_POLICY", POLICY_ALIGN_HOST)
    hint = HostSessionHint(host_kind="test", host_session_id="fixed-host")

    with patch("server.mcp_server.get_engine", return_value=_mock_engine()), patch(
        "server.mcp_server.get_host_provider"
    ) as mock_provider:
        mock_provider.return_value.resolve_active_session.return_value = hint
        r1 = json.loads(delegate_to_agent("t1", ["a.py"], "ctx"))
        r2 = json.loads(delegate_to_agent("t2", ["a.py"], "ctx"))

    assert r1["mcp_session_id"] == r2["mcp_session_id"]
    assert r2["session_reused"] is True
    log_path = Path(r2["log_path"])
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    second = json.loads(lines[1])
    assert second["session_action"] == "reuse"
    assert second["session_policy"] == POLICY_ALIGN_HOST


def test_session_policy_in_jsonl_is_always_new_not_fallback(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_HOST", "none")

    with patch("server.mcp_server.get_engine", return_value=_mock_engine()):
        payload = json.loads(delegate_to_agent("t", ["a.py"], "ctx"))

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["session_policy"] == "always_new"
    assert record["session_policy"] != "fallback:always_new"
