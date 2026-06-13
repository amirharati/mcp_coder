import json
import os
from pathlib import Path

from core.logging.delegation_log import (
    append_delegation_record,
    build_delegation_record,
    delegation_log_path,
)
from core.storage.paths import project_key
from core.storage.session_paths import prepare_delegation_storage


def _storage_for(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    monkeypatch.delenv("MCP_CODER_MIRROR_LOGS_TO_WORKSPACE", raising=False)
    return prepare_delegation_storage(workspace)


def test_append_delegation_record(tmp_path, monkeypatch):
    storage = _storage_for(tmp_path, monkeypatch)
    record = build_delegation_record(
        delegation_id="test-id",
        timestamp_start="2026-06-03T00:00:00.000Z",
        timestamp_end="2026-06-03T00:00:01.000Z",
        duration_ms=1000,
        mcp_request={"task": "t"},
        backend="aider",
        model="gpt-4o",
        success=True,
        error=None,
        response_to_cursor={"success": True},
        files_requested=["a.py"],
        files_changed=["a.py"],
        context_block={"prompt_chars": 10},
        timing={"engine_run_ms": 900},
        tokens={"source": "unavailable"},
        project_key=storage.project_key,
        mcp_session_id=storage.mcp_session_id,
        session_dir=storage.session_dir,
        log_path=storage.log_path,
        session_action="new",
        session_reason="policy_always_new",
        session_policy="always_new",
    )
    path = append_delegation_record(record)
    assert path == storage.log_path
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["type"] == "delegation"
    assert parsed["delegation_id"] == "test-id"
    assert parsed["session_action"] == "new"
    assert parsed["session_policy"] == "always_new"
    assert parsed["context_mode"] == "fallback"
    assert parsed["project_key"] == storage.project_key
    assert parsed["mcp_session_id"] == storage.mcp_session_id
    assert parsed["session_dir"] == str(storage.session_dir.resolve())
    assert parsed["log_path"] == str(storage.log_path.resolve())
    assert parsed["host_kind"] is None
    assert parsed["host_session_id"] is None
    assert parsed["session_id"] == storage.mcp_session_id
    assert parsed["context_refs"] == []

    pointer = tmp_path / "workspace" / ".mcp-coder" / "session.json"
    assert pointer.is_file()


def test_delegation_record_includes_usage(tmp_path, monkeypatch):
    storage = _storage_for(tmp_path, monkeypatch)
    usage = {
        "model": "openrouter/openai/gpt-4o-mini",
        "preflight_tokens_est": 42,
        "preflight_chars": 168,
        "actual": {"input": None, "output": None, "total": None, "source": "unavailable"},
    }
    record = build_delegation_record(
        delegation_id="usage-id",
        timestamp_start="2026-06-06T00:00:00.000Z",
        timestamp_end="2026-06-06T00:00:01.000Z",
        duration_ms=1000,
        mcp_request={"task": "t"},
        backend="aider",
        model="openrouter/openai/gpt-4o-mini",
        success=True,
        error=None,
        response_to_cursor={"success": True},
        files_requested=["a.py"],
        files_changed=["a.py"],
        context_block={"prompt_chars": 168, "prompt_tokens_est": 42},
        timing={"engine_run_ms": 900},
        tokens={"source": "unavailable"},
        project_key=storage.project_key,
        mcp_session_id=storage.mcp_session_id,
        session_dir=storage.session_dir,
        log_path=storage.log_path,
        session_action="new",
        session_reason="policy_always_new",
        session_policy="always_new",
        usage=usage,
    )
    path = append_delegation_record(record)
    parsed = json.loads(path.read_text(encoding="utf-8").strip())
    assert parsed["usage"]["preflight_tokens_est"] == 42
    assert parsed["context"]["token_estimate_preflight"] == 42
    assert parsed["context"]["prompt_tokens_est"] == 42


def test_log_dir_mirror(tmp_path, monkeypatch):
    storage = _storage_for(tmp_path, monkeypatch)
    mirror_dir = tmp_path / "custom_logs"
    monkeypatch.setenv("MCP_CODER_LOG_DIR", str(mirror_dir))
    record = build_delegation_record(
        delegation_id="x",
        timestamp_start="t0",
        timestamp_end="t1",
        duration_ms=1,
        mcp_request={},
        backend="aider",
        model=None,
        success=False,
        error="err",
        response_to_cursor={},
        files_requested=[],
        files_changed=[],
        context_block={},
        timing={},
        tokens={},
        project_key=storage.project_key,
        mcp_session_id=storage.mcp_session_id,
        session_dir=storage.session_dir,
        log_path=storage.log_path,
        session_action="new",
        session_reason="policy_always_new",
        session_policy="always_new",
    )
    path = append_delegation_record(record)
    assert path == storage.log_path
    assert (mirror_dir / "delegations.jsonl").is_file()


def test_delegation_log_path_returns_latest_session(tmp_path, monkeypatch):
    storage = _storage_for(tmp_path, monkeypatch)
    record = build_delegation_record(
        delegation_id="x",
        timestamp_start="t0",
        timestamp_end="t1",
        duration_ms=1,
        mcp_request={},
        backend="aider",
        model=None,
        success=True,
        error=None,
        response_to_cursor={},
        files_requested=[],
        files_changed=[],
        context_block={},
        timing={},
        tokens={},
        project_key=storage.project_key,
        mcp_session_id=storage.mcp_session_id,
        session_dir=storage.session_dir,
        log_path=storage.log_path,
        session_action="new",
        session_reason="policy_always_new",
        session_policy="always_new",
    )
    append_delegation_record(record)
    assert delegation_log_path() == storage.log_path
    assert project_key(tmp_path / "workspace") == storage.project_key
