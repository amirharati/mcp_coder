"""P13-008 — delegation viewer handlers for P13-005/006/007 event types (ISS-010 fix).

Covers that `_build_view_events()` (via `enrich_delegation_record()`) now renders
rows for the 8 agent-envelope event types that were previously silently dropped:
- delegation_lifecycle_start / delegation_lifecycle_end
- delegation_phase_start / delegation_phase_end
- agent_checkpoint_saved / agent_rehydrated
- project_state_loaded / project_state_saved

All should appear with scope="agent".
"""

from __future__ import annotations

import json
from pathlib import Path

from core.cli.delegation_view_enrich import enrich_delegation_record


def _enrich_with_trace(tmp_path: Path, trace_lines: list[dict]) -> list[dict]:
    session_dir = tmp_path / "session"
    traces = session_dir / "traces"
    traces.mkdir(parents=True)
    delegation_id = "d-view-1"
    trace_path = traces / f"{delegation_id}.jsonl"
    with trace_path.open("w", encoding="utf-8") as f:
        for line in trace_lines:
            f.write(json.dumps(line) + "\n")
    record = {
        "delegation_id": delegation_id,
        "session_dir": str(session_dir),
        "trace_ref": f"traces/{delegation_id}.jsonl",
        "workspace_path": str(tmp_path),
        "timestamp_start": "2026-06-22T04:00:00Z",
        "timestamp_end": "2026-06-22T04:01:00Z",
        "mcp_request": {"task": "test task"},
        "response_to_cursor": {"output_preview": "done"},
    }
    return enrich_delegation_record(record)["view_events"]


def _names(events: list[dict]) -> list[str]:
    return [e["name"] for e in events]


# ── individual handlers ────────────────────────────────────────────────────


def test_lifecycle_start_renders(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "delegation_lifecycle_start", "timestamp": "2026-06-22T04:00:00.000Z",
         "project_key": "pk", "spec_path": "tasks/s.md", "resumed": False},
    ])
    agent_events = [e for e in events if e.get("scope") == "agent"]
    assert "agent.lifecycle_start" in _names(agent_events)
    e = next(e for e in agent_events if e["name"] == "agent.lifecycle_start")
    assert e["is_boundary"] is True
    assert "lifecycle start" in e["summary"]
    assert e["detail"]["resumed"] is False


def test_lifecycle_start_resumed(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "delegation_lifecycle_start", "timestamp": "2026-06-22T04:00:00.000Z",
         "resumed": True},
    ])
    e = next(e for e in events if e["name"] == "agent.lifecycle_start")
    assert "resumed" in e["summary"]


def test_lifecycle_end_renders_with_outcome(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "delegation_lifecycle_end", "timestamp": "2026-06-22T04:01:00.000Z",
         "outcome": "success", "reviewer_pass_result": "lgtm"},
    ])
    e = next(e for e in events if e["name"] == "agent.lifecycle_end")
    assert e["is_boundary"] is True
    assert "outcome=success" in e["summary"]
    assert "reviewer=lgtm" in e["summary"]
    assert e["detail"]["outcome"] == "success"


def test_phase_start_renders_as_divider(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "delegation_phase_start", "timestamp": "2026-06-22T04:00:01.000Z",
         "phase": "preloop", "resumed": False},
    ])
    e = next(e for e in events if e["name"] == "agent.phase_start")
    assert e["is_divider"] is True
    assert "preloop" in e["summary"]
    assert e["detail"]["phase"] == "preloop"


def test_phase_end_renders_with_status(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "delegation_phase_end", "timestamp": "2026-06-22T04:00:02.000Z",
         "phase": "preloop", "status": "blocked", "detail": "clarity_check"},
    ])
    e = next(e for e in events if e["name"] == "agent.phase_end")
    assert e["is_divider"] is True
    assert "blocked" in e["summary"]
    assert "clarity_check" in e["summary"]


def test_checkpoint_saved_renders(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "agent_checkpoint_saved", "timestamp": "2026-06-22T04:00:30.000Z",
         "project_key": "pk", "last_delegation_id": "d-view-1",
         "last_outcome": "success", "file_path": "/tmp/agent_state.json",
         "delegation_id": "d-view-1"},
    ])
    e = next(e for e in events if e["name"] == "agent.checkpoint_saved")
    assert "checkpoint saved" in e["summary"]
    assert "outcome=success" in e["summary"]
    assert e["detail"]["last_outcome"] == "success"
    assert e["is_boundary"] is False


def test_rehydrated_renders(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "agent_rehydrated", "timestamp": "2026-06-22T04:00:00.000Z",
         "project_key": "pk", "last_delegation_id": "d-prior-1",
         "last_outcome": "success", "last_finished_at": "2026-06-22T03:59:00Z"},
    ])
    e = next(e for e in events if e["name"] == "agent.rehydrated")
    assert "rehydrated" in e["summary"]
    assert "from=" in e["summary"]
    assert e["detail"]["last_delegation_id"] == "d-prior-1"


def test_project_state_loaded_renders(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "project_state_loaded", "timestamp": "2026-06-22T04:00:01.000Z",
         "project_key": "pk"},
    ])
    e = next(e for e in events if e["name"] == "agent.project_state_loaded")
    assert "loaded" in e["summary"]
    assert e["detail"]["project_key"] == "pk"


def test_project_state_saved_renders(tmp_path):
    events = _enrich_with_trace(tmp_path, [
        {"type": "project_state_saved", "timestamp": "2026-06-22T04:00:30.000Z",
         "project_key": "pk", "hot_areas_updated": 2,
         "decisions_added": 0, "risks_added": 0,
         "file_path": "/tmp/project_state.json"},
    ])
    e = next(e for e in events if e["name"] == "agent.project_state_saved")
    assert "saved" in e["summary"]
    assert "hot_areas=2" in e["summary"]


# ── full envelope renders in order ─────────────────────────────────────────


def test_full_envelope_renders_all_agent_rows(tmp_path):
    """Simulates a complete delegation trace with all 8 new event types and
    confirms the viewer renders a row for each (scope=agent), in order.
    """
    trace_lines = [
        {"type": "trace_header", "timestamp": "2026-06-22T04:00:00.000Z"},
        {"type": "delegation_lifecycle_start", "timestamp": "2026-06-22T04:00:00.100Z",
         "project_key": "pk", "resumed": False},
        {"type": "delegation_phase_start", "timestamp": "2026-06-22T04:00:00.200Z",
         "phase": "preloop"},
        {"type": "delegation_phase_end", "timestamp": "2026-06-22T04:00:01.000Z",
         "phase": "preloop", "status": "ok"},
        {"type": "project_state_loaded", "timestamp": "2026-06-22T04:00:01.100Z",
         "project_key": "pk"},
        {"type": "delegation_phase_start", "timestamp": "2026-06-22T04:00:01.200Z",
         "phase": "loop"},
        {"type": "delegation_phase_end", "timestamp": "2026-06-22T04:00:30.000Z",
         "phase": "loop", "status": "ok"},
        {"type": "project_state_saved", "timestamp": "2026-06-22T04:00:30.100Z",
         "project_key": "pk", "hot_areas_updated": 1,
         "decisions_added": 0, "risks_added": 0},
        {"type": "agent_checkpoint_saved", "timestamp": "2026-06-22T04:00:30.200Z",
         "project_key": "pk", "last_delegation_id": "d-view-1",
         "last_outcome": "success"},
        {"type": "delegation_phase_start", "timestamp": "2026-06-22T04:00:30.300Z",
         "phase": "postloop"},
        {"type": "delegation_phase_end", "timestamp": "2026-06-22T04:00:31.000Z",
         "phase": "postloop", "status": "ok"},
        {"type": "delegation_lifecycle_end", "timestamp": "2026-06-22T04:00:31.100Z",
         "outcome": "success"},
    ]
    events = _enrich_with_trace(tmp_path, trace_lines)
    agent_events = [e for e in events if e.get("scope") == "agent"]
    names = _names(agent_events)
    # All 8 event types present (lifecycle_start/end = 2, phase_start/end = 4
    # total but 2+2 split, checkpoint = 1, project_state_loaded = 1, project_state_saved = 1)
    assert "agent.lifecycle_start" in names
    assert "agent.lifecycle_end" in names
    assert names.count("agent.phase_start") == 3  # preloop + loop + postloop
    assert names.count("agent.phase_end") == 3
    assert "agent.checkpoint_saved" in names
    assert "agent.project_state_loaded" in names
    assert "agent.project_state_saved" in names


def test_full_envelope_phase_count(tmp_path):
    """A full success delegation has 3 phase_starts (preloop/loop/postloop)
    and 3 phase_ends. Separate test because the count assertion above was
    off-by-one in the comment.
    """
    trace_lines = [
        {"type": "trace_header", "timestamp": "2026-06-22T04:00:00.000Z"},
        {"type": "delegation_phase_start", "timestamp": "2026-06-22T04:00:00.200Z", "phase": "preloop"},
        {"type": "delegation_phase_end", "timestamp": "2026-06-22T04:00:01.000Z", "phase": "preloop", "status": "ok"},
        {"type": "delegation_phase_start", "timestamp": "2026-06-22T04:00:01.200Z", "phase": "loop"},
        {"type": "delegation_phase_end", "timestamp": "2026-06-22T04:00:30.000Z", "phase": "loop", "status": "ok"},
        {"type": "delegation_phase_start", "timestamp": "2026-06-22T04:00:30.300Z", "phase": "postloop"},
        {"type": "delegation_phase_end", "timestamp": "2026-06-22T04:00:31.000Z", "phase": "postloop", "status": "ok"},
    ]
    events = _enrich_with_trace(tmp_path, trace_lines)
    agent_events = [e for e in events if e.get("scope") == "agent"]
    assert _names(agent_events).count("agent.phase_start") == 3
    assert _names(agent_events).count("agent.phase_end") == 3
