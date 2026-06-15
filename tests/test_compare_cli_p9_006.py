"""Tests for compare CLI and dual-capture pairing (P9-006)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import main
import pytest

from core.cli.compare import main_compare, pair_dual_capture_events
from core.cli.delegation_view_enrich import enrich_delegation_record
from core.storage.paths import session_folder


def _write_trace(session_dir: Path, delegation_id: str, events: list[dict]) -> Path:
    traces = session_dir / "traces"
    traces.mkdir(parents=True, exist_ok=True)
    trace_path = traces / f"{delegation_id}.jsonl"
    trace_path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )
    return trace_path


def _seed_workspace(
    tmp_path: Path,
    monkeypatch,
    *,
    events: list[dict],
    delegation_id: str = "deleg-compare-1",
) -> tuple[Path, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    session_id = "sess-compare"
    session_dir = session_folder(workspace, session_id)
    trace_path = _write_trace(session_dir, delegation_id, events)

    row = {
        "type": "delegation",
        "delegation_id": delegation_id,
        "timestamp_end": "2026-06-15T12:00:00Z",
        "session_dir": str(session_dir.resolve()),
        "trace_ref": f"traces/{delegation_id}.jsonl",
    }
    (session_dir / "delegations.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return workspace, delegation_id


def _matched_events() -> list[dict]:
    return [
        {"type": "trace_header", "delegation_id": "deleg-compare-1"},
        {
            "type": "proxy_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "openrouter/test-model",
            "wire_latency_ms": 120,
            "status_code": 200,
            "raw_response": json.dumps(
                {
                    "choices": [
                        {"message": {"content": "ok", "reasoning_content": "thinking at wire"}}
                    ]
                }
            ),
        },
        {
            "type": "backend_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "openrouter/test-model",
            "duration_ms": 170,
            "thinking_text": "normalized thinking",
            "usage": {"input": 10, "output": 5, "total": 15},
        },
    ]


def test_compare_found_human_output(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch, events=_matched_events())
    rc = main_compare([delegation_id, "--workspace", str(workspace)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Compare" in out
    assert f"- delegation_id: {delegation_id}" in out
    assert "status=matched" in out
    assert "BL-507" in out


def test_compare_found_json_shape(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch, events=_matched_events())
    rc = main_compare([delegation_id, "--workspace", str(workspace), "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["found"] is True
    assert payload["delegation_id"] == delegation_id
    assert payload["trace_path"]
    assert payload["summary"]["matched"] == 1
    assert payload["calls"][0]["status"] == "matched"
    assert payload["calls"][0]["litellm_overhead_ms"] == 50
    assert "gaps" in payload
    assert "bl507" in payload
    assert isinstance(payload["warnings"], list)


def test_compare_unknown_id_returns_1(tmp_path, monkeypatch, capsys):
    workspace, _ = _seed_workspace(tmp_path, monkeypatch, events=_matched_events())
    rc = main_compare(["missing-id", "--workspace", str(workspace)])
    assert rc == 1
    assert "delegation not found: missing-id" in capsys.readouterr().err


def test_compare_flags_proxy_only_gap():
    events = [
        {
            "type": "proxy_llm_call",
            "step_index": 1,
            "call_index": 9,
            "model": "proxy-only-model",
            "wire_latency_ms": 10,
            "status_code": 200,
            "raw_response": "{}",
        }
    ]
    paired = pair_dual_capture_events(events)
    assert paired["summary"]["proxy_only"] == 1
    assert paired["gaps"]["proxy_only"][0]["proxy_model"] == "proxy-only-model"


def test_compare_flags_backend_only_gap():
    events = [
        {
            "type": "backend_llm_call",
            "step_index": 1,
            "call_index": 2,
            "model": "backend-only-model",
            "duration_ms": 33,
        }
    ]
    paired = pair_dual_capture_events(events)
    assert paired["summary"]["backend_only"] == 1
    assert paired["gaps"]["backend_only"][0]["backend_model"] == "backend-only-model"


def test_compare_latency_overhead_calculation():
    events = [
        {
            "type": "proxy_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "m",
            "wire_latency_ms": 100,
            "status_code": 200,
            "raw_response": "{}",
        },
        {
            "type": "backend_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "m",
            "duration_ms": 150,
        },
    ]
    row = pair_dual_capture_events(events)["calls"][0]
    assert row["wire_latency_ms"] == 100
    assert row["total_latency_ms"] == 150
    assert row["litellm_overhead_ms"] == 50


def test_compare_bl507_visibility_fields():
    events = [
        {
            "type": "proxy_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "m",
            "wire_latency_ms": 1,
            "status_code": 200,
            "raw_response": '{"choices":[{"message":{"reasoning_content":"wire thought"}}]}',
        },
        {
            "type": "backend_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "m",
            "duration_ms": 2,
            "thinking_text": "backend thought",
        },
    ]
    paired = pair_dual_capture_events(events)
    row = paired["calls"][0]
    assert row["bl507"]["proxy_thinking_present"] is True
    assert row["bl507"]["backend_thinking_present"] is True
    assert paired["bl507"]["proxy_thinking_present"] is True
    assert paired["bl507"]["backend_thinking_present"] is True


def test_compare_field_diff_status():
    events = [
        {
            "type": "proxy_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "proxy/model-a",
            "wire_latency_ms": 10,
            "status_code": 200,
            "raw_response": "{}",
        },
        {
            "type": "backend_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "backend/model-b",
            "duration_ms": 20,
        },
    ]
    row = pair_dual_capture_events(events)["calls"][0]
    assert row["status"] == "field_diff"
    assert "model" in row["field_diffs"]


def test_compare_fallback_backend_only_missing_call_index_no_crash():
    """Regression (P9-ISS-003): fallback backend-only row must not crash on call_index lookup."""
    events = [
        {
            "type": "proxy_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "m1",
            "wire_latency_ms": 10,
            "status_code": 200,
            "raw_response": "{}",
        },
        {
            "type": "backend_llm_call",
            "step_index": 1,
            "call_index": 1,
            "model": "m1",
            "duration_ms": 20,
        },
        {
            "type": "backend_llm_call",
            "step_index": 1,
            # intentionally missing call_index to force fallback backend-only row
            "model": "m2",
            "duration_ms": 30,
        },
    ]
    paired = pair_dual_capture_events(events)
    assert paired["summary"]["matched"] == 1
    assert paired["summary"]["backend_only"] == 1
    backend_only = paired["gaps"]["backend_only"][0]
    assert backend_only["call_index"] is None
    assert backend_only["backend_model"] == "m2"


def test_main_compare_subcommand_dispatch(monkeypatch):
    with patch("core.cli.compare.main_compare", return_value=0) as compare_mock:
        monkeypatch.setattr(
            sys,
            "argv",
            ["mcp-coder", "compare", "deleg-123", "--workspace", "/tmp/ws", "--format", "json"],
        )
        with pytest.raises(SystemExit) as exc:
            main.main()
    assert exc.value.code == 0
    compare_mock.assert_called_once_with(
        ["deleg-123", "--workspace", "/tmp/ws", "--format", "json"]
    )


def test_enrich_includes_dual_capture_compare_rows(tmp_path):
    delegation_id = "deleg-viewer"
    session_dir = tmp_path / "session"
    _write_trace(
        session_dir,
        delegation_id,
        [
            {
                "type": "proxy_llm_call",
                "step_index": 1,
                "call_index": 1,
                "model": "proxy-model",
                "wire_latency_ms": 11,
                "status_code": 200,
                "raw_response": "{}",
            },
            {
                "type": "backend_llm_call",
                "step_index": 1,
                "call_index": 1,
                "model": "proxy-model",
                "duration_ms": 22,
            },
        ],
    )
    record = {
        "delegation_id": delegation_id,
        "session_dir": str(session_dir),
        "trace_ref": f"traces/{delegation_id}.jsonl",
    }
    enriched = enrich_delegation_record(record)
    compare = enriched["trace"]["dual_capture_compare"]
    assert compare is not None
    assert compare["summary"]["matched"] == 1
    assert len(compare["calls"]) == 1


def test_enrich_legacy_trace_without_dual_capture_still_safe(tmp_path):
    delegation_id = "deleg-legacy"
    session_dir = tmp_path / "session"
    _write_trace(
        session_dir,
        delegation_id,
        [
            {
                "type": "llm_call",
                "role": "executor",
                "model": "legacy-model",
                "response_preview": "legacy output",
            }
        ],
    )
    record = {
        "delegation_id": delegation_id,
        "session_dir": str(session_dir),
        "trace_ref": f"traces/{delegation_id}.jsonl",
        "response_to_cursor": {"output_preview": "digest"},
    }
    enriched = enrich_delegation_record(record)
    assert enriched["trace"]["dual_capture_compare"] is None
    assert len(enriched["trace"]["llm_calls"]) == 1
