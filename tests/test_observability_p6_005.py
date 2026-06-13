"""P6-005: version tags, training capture, maintenance stats."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config.observability import (
    capture_for_training_enabled,
    resolve_observability_retention,
)
from core.observability.trace import TRACE_TYPE_HEADER, append_trace_record, ensure_trace_header
from core.observability.training_capture import (
    build_training_record,
    training_capture_path,
    write_training_capture_if_enabled,
)
from core.observability.version_tags import (
    CAPTURE_SCHEMA_VERSION,
    build_config_fingerprint,
    build_trace_version_tags,
    extract_model_versions,
)


def _write_config(ws: Path, text: str) -> None:
    cfg = ws / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(text, encoding="utf-8")


def test_build_trace_version_tags_includes_schema_and_fingerprint(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    _write_config(ws, "capture_reasoning: true\nobservability_verbosity: lean\n")

    tags = build_trace_version_tags(ws)
    assert tags["capture_schema_version"] == CAPTURE_SCHEMA_VERSION
    assert tags["mcp_coder_version"]
    assert len(tags["config_fingerprint"]) == 64
    assert tags["observability"]["verbosity"] == "lean"
    assert "pipeline_flags" in tags


def test_extract_model_versions():
    roles = {
        "executor": {"model": "openrouter/google/gemini-2.5-flash"},
        "context_builder": {"model": "openrouter/openai/gpt-4o-mini"},
    }
    assert extract_model_versions(roles) == {
        "executor": "openrouter/google/gemini-2.5-flash",
        "context_builder": "openrouter/openai/gpt-4o-mini",
    }


def test_ensure_trace_header_written_once(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    session_dir = tmp_path / "session"
    delegation_id = "d-1"

    ensure_trace_header(session_dir=session_dir, delegation_id=delegation_id, workspace=ws)
    path = session_dir / "traces" / f"{delegation_id}.jsonl"
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    header = json.loads(lines[0])
    assert header["type"] == TRACE_TYPE_HEADER
    assert header["version_tags"]["capture_schema_version"] == CAPTURE_SCHEMA_VERSION

    append_trace_record(
        {
            "type": "llm_call",
            "delegation_id": delegation_id,
            "role": "executor",
            "call_index": 0,
        },
        session_dir=session_dir,
        delegation_id=delegation_id,
        workspace=ws,
    )
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == TRACE_TYPE_HEADER


def test_training_capture_disabled_by_default(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    session_dir = tmp_path / "session"
    path = write_training_capture_if_enabled(
        workspace=ws,
        session_dir=session_dir,
        delegation_id="d-train",
        timestamp_end="2026-06-13T00:00:00.000Z",
        task="do thing",
        context_package_hash="abc",
        reasoning_summary=None,
        outcome="success",
        verify_result=None,
        success=True,
        model_roles=None,
    )
    assert path is None
    assert not training_capture_path(session_dir, "d-train").exists()


def test_training_capture_writes_when_enabled(tmp_path, monkeypatch):
    ws = tmp_path / "repo"
    ws.mkdir()
    _write_config(ws, "capture_for_training: true\n")
    monkeypatch.setenv("MCP_CODER_CAPTURE_FOR_TRAINING", "")
    assert capture_for_training_enabled(ws) is True

    session_dir = tmp_path / "session"
    path = write_training_capture_if_enabled(
        workspace=ws,
        session_dir=session_dir,
        delegation_id="d-train",
        timestamp_end="2026-06-13T00:00:00.000Z",
        task="do thing",
        context_package_hash="abc123",
        reasoning_summary="thought about contracts",
        outcome="success",
        verify_result={"passed": True},
        success=True,
        model_roles={"executor": {"model": "test/model"}},
        pipeline_flags_runtime={"spec_validation_ran": False},
    )
    assert path is not None and path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task"] == "do thing"
    assert payload["context_package_hash"] == "abc123"
    assert payload["trace_ref"] == "traces/d-train.jsonl"
    assert payload["reasoning_summary"] == "thought about contracts"
    assert payload["version_tags"]["model_versions"]["executor"] == "test/model"


def test_observability_retention_config(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    assert resolve_observability_retention(ws) == "session"
    _write_config(ws, "observability_retention: 30_days\n")
    assert resolve_observability_retention(ws) == "30_days"


def test_build_config_fingerprint_stable(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    _write_config(ws, "capture_reasoning: false\n")
    first = build_config_fingerprint(ws)
    second = build_config_fingerprint(ws)
    assert first == second


def test_build_training_record_omits_empty_reasoning(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    record = build_training_record(
        workspace=ws,
        delegation_id="d",
        timestamp_end="t",
        task="t",
        context_package_hash=None,
        trace_ref="traces/d.jsonl",
        reasoning_summary=None,
        outcome=None,
        verify_result=None,
        success=False,
        model_roles=None,
    )
    assert "reasoning_summary" not in record
