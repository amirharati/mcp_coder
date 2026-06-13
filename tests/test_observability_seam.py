"""P6-001: observability adapter seam — NullObservability swap + LocalObservability round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.observability import (
    LocalObservability,
    NullObservability,
    reset_observability,
    set_observability,
)
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


def test_null_observability_append_writes_no_file(tmp_path, monkeypatch):
    """NullObservability swap: append is a no-op — no JSONL file created."""
    storage = _storage_for(tmp_path, monkeypatch)
    null_obs = NullObservability()
    record = null_obs.build_delegation_record(
        delegation_id="null-id",
        timestamp_start="2026-06-13T00:00:00.000Z",
        timestamp_end="2026-06-13T00:00:01.000Z",
        duration_ms=1000,
        mcp_request={"task": "t"},
        backend="aider",
        model=None,
        success=True,
        error=None,
        response_to_cursor={"success": True},
        files_requested=[],
        files_changed=[],
        context_block={},
        timing={},
        tokens={"source": "unavailable"},
        project_key=storage.project_key,
        mcp_session_id=storage.mcp_session_id,
        session_dir=storage.session_dir,
        log_path=storage.log_path,
        session_action="new",
        session_reason="policy_always_new",
        session_policy="always_new",
    )
    path = null_obs.append_delegation_record(record)
    assert not storage.log_path.is_file()
    assert not path.is_file()


def test_null_observability_emit_and_warn_no_crash():
    null_obs = NullObservability()
    null_obs.emit("test_event", level="info", foo="bar")
    null_obs.warn("test_warn", {"detail": "x"})


def test_null_merge_model_roles_returns_dict():
    null_obs = NullObservability()
    result = null_obs.merge_model_roles(None, None)
    assert isinstance(result, dict)


def test_local_observability_delegation_round_trip(tmp_path, monkeypatch):
    """LocalObservability: build → append writes expected JSONL line."""
    storage = _storage_for(tmp_path, monkeypatch)
    local_obs = LocalObservability()
    record = local_obs.build_delegation_record(
        delegation_id="local-id",
        timestamp_start="2026-06-13T00:00:00.000Z",
        timestamp_end="2026-06-13T00:00:01.000Z",
        duration_ms=500,
        mcp_request={"task": "round-trip"},
        backend="aider",
        model="gpt-4o",
        success=True,
        error=None,
        response_to_cursor={"success": True},
        files_requested=["a.py"],
        files_changed=["a.py"],
        context_block={"prompt_chars": 10},
        timing={"engine_run_ms": 400},
        tokens={"source": "unavailable"},
        project_key=storage.project_key,
        mcp_session_id=storage.mcp_session_id,
        session_dir=storage.session_dir,
        log_path=storage.log_path,
        session_action="new",
        session_reason="policy_always_new",
        session_policy="always_new",
    )
    path = local_obs.append_delegation_record(record)
    assert path == storage.log_path
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["delegation_id"] == "local-id"
    assert parsed["type"] == "delegation"


def test_new_pipeline_recorder_usable():
    local_obs = LocalObservability()
    recorder = local_obs.new_pipeline_recorder()
    recorder.mark("spec_read", status="ok", duration_ms=10)
    recorder.start("engine")
    recorder.end("engine", status="ok")
    phases = recorder.to_list()
    assert len(phases) == 2
    assert phases[0]["phase"] == "spec_read"
    assert phases[1]["phase"] == "engine"


def test_emit_warn_level_smoke(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    local_obs = LocalObservability()
    local_obs.emit("smoke_test", level="warn", delegation_id="x")
    log_path = home / "server.jsonl"
    if log_path.is_file():
        last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert last.get("event") == "smoke_test"


def test_set_observability_swap(monkeypatch):
    """Process-wide singleton swap via set_observability (used by integration tests)."""
    reset_observability()
    try:
        set_observability(NullObservability())
        from core.observability import get_observability

        assert isinstance(get_observability(), NullObservability)
    finally:
        reset_observability()
