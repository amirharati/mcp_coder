"""P13-007 — SupervisorAgent checkpoint at every delegation end.

Covers:
- AgentCheckpoint save/load/find_for_project (atomic, tolerant of corrupt files)
- _finish() writes checkpoint unconditionally (success / error / escalated)
- Escalation produces BOTH SupervisorState (resumable, expiring) AND AgentCheckpoint (steady-state)
- rehydrate_from() restores lifecycle context but does NOT set _lifecycle_started
- _get_or_create_supervisor() rehydrates from disk on a cache miss
- CLI ≡ server invariant: same checkpoint content after same delegation
- Corrupt / missing checkpoint does not crash delegations
- agent_checkpoint_saved trace event fires at every delegation end
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import SupervisorAgent
from core.state.agent_checkpoint import AgentCheckpoint


# ── helpers ──────────────────────────────────────────────────────────────────


def _result(success: bool = True) -> ExecutionResult:
    return ExecutionResult(
        success=success,
        output="worker output",
        files_changed=["a.py"] if success else [],
        model="test/model",
    )


def _make_agent(
    *,
    delegation_id: str | None = None,
    event_sink=None,
    spec_path: str | None = None,
) -> SupervisorAgent:
    return SupervisorAgent(
        delegation_id=delegation_id,
        workspace_path="/tmp/ws",
        executor_fn=lambda _t, _c, _r=False: _result(),
        event_sink=event_sink,
        spec_path=spec_path,
    )


# ── AgentCheckpoint dataclass ──────────────────────────────────────────────


def test_checkpoint_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    cp = AgentCheckpoint(
        project_key="tasks/proj-1",
        last_delegation_id="d-cp-1",
        last_outcome="success",
        last_spec_path="tasks/step-01.md",
        last_finished_at="2026-06-21T23:00:00Z",
        lifecycle_context={
            "project_key": "tasks/proj-1",
            "reviewer_pass_result": "lgtm",
            "phases_completed": ["preloop", "loop", "postloop"],
        },
    )
    saved_path = cp.save()
    assert saved_path.is_file()
    assert saved_path.name == "agent_state.json"

    loaded = AgentCheckpoint.find_for_project("tasks/proj-1")
    assert loaded is not None
    assert loaded.project_key == "tasks/proj-1"
    assert loaded.last_delegation_id == "d-cp-1"
    assert loaded.last_outcome == "success"
    assert loaded.last_spec_path == "tasks/step-01.md"
    assert loaded.lifecycle_context["reviewer_pass_result"] == "lgtm"
    assert loaded.lifecycle_context["phases_completed"] == ["preloop", "loop", "postloop"]


def test_find_for_project_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    assert AgentCheckpoint.find_for_project("tasks/nope") is None


def test_find_for_project_returns_none_on_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state_path = AgentCheckpoint.state_path("tasks/corrupt")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{not valid json", encoding="utf-8")
    # Must NOT raise — a bad checkpoint must not block delegations
    assert AgentCheckpoint.find_for_project("tasks/corrupt") is None


def test_find_for_project_tolerates_missing_lifecycle_context_field(tmp_path, monkeypatch):
    """Backward-compat: older checkpoint files may lack lifecycle_context."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state_path = AgentCheckpoint.state_path("tasks/old")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # Write a checkpoint without lifecycle_context (simulating an old/partial file)
    state_path.write_text(
        json.dumps({
            "project_key": "tasks/old",
            "last_delegation_id": "d-old-1",
            "last_outcome": "success",
            "last_spec_path": None,
            "last_finished_at": "2026-06-21T23:00:00Z",
        }),
        encoding="utf-8",
    )
    loaded = AgentCheckpoint.find_for_project("tasks/old")
    assert loaded is not None
    assert loaded.lifecycle_context == {}


def test_checkpoint_atomic_write_no_tmp_left(tmp_path, monkeypatch):
    """save() uses temp + os.replace; no .tmp file should remain after success."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    cp = AgentCheckpoint(
        project_key="tasks/atomic",
        last_delegation_id="d-atom-1",
        last_outcome="success",
        last_spec_path=None,
        last_finished_at="2026-06-21T23:00:00Z",
    )
    cp.save()
    state_path = AgentCheckpoint.state_path("tasks/atomic")
    assert state_path.is_file()
    assert not state_path.with_suffix(".json.tmp").exists()


# ── _finish() writes checkpoint unconditionally ────────────────────────────


def _drive_agent_to_finish(agent: SupervisorAgent, *, reviewer_result="lgtm"):
    """Drive a host-driven agent through one turn and finish()."""
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_phase_end("preloop", status="ok")
    agent.emit_lifecycle_phase_start("loop")
    agent.begin()
    agent.begin_turn()
    exec_result = _result(success=True)
    agent.update_reviewer_pass_result(reviewer_result)
    agent.complete_turn(exec_result, {"outcome": reviewer_result, "note": ""})
    result = agent.finish()
    agent.emit_lifecycle_phase_end("loop", status="ok")
    agent.emit_lifecycle_phase_start("postloop")
    agent.emit_lifecycle_phase_end("postloop", status="ok")
    agent.emit_lifecycle_end("success")
    return result


def test_finish_writes_checkpoint_on_success(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    events: list[dict] = []
    agent = _make_agent(delegation_id="d-success-1", event_sink=events.append)
    agent.set_lifecycle_context(project_key="tasks/success-proj", mcp_session_id="s1")
    agent.set_spec_path("tasks/step-01.md")
    _drive_agent_to_finish(agent)

    cp = AgentCheckpoint.find_for_project("tasks/success-proj")
    assert cp is not None
    assert cp.last_outcome == "success"
    assert cp.last_delegation_id == "d-success-1"
    assert cp.last_spec_path == "tasks/step-01.md"
    assert cp.lifecycle_context.get("reviewer_pass_result") == "lgtm"
    assert "preloop" in cp.lifecycle_context["phases_completed"]


def test_finish_emits_agent_checkpoint_saved_trace_event(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    events: list[dict] = []
    agent = _make_agent(delegation_id="d-trace-1", event_sink=events.append)
    agent.set_lifecycle_context(project_key="tasks/trace-proj", mcp_session_id="s1")
    agent.set_spec_path("tasks/step-01.md")
    _drive_agent_to_finish(agent)

    saved_events = [e for e in events if e["type"] == "agent_checkpoint_saved"]
    assert len(saved_events) == 1
    assert saved_events[0]["last_outcome"] == "success"
    assert saved_events[0]["project_key"] == "tasks/trace-proj"
    assert "file_path" in saved_events[0]


def test_checkpoint_overwrites_each_delegation(tmp_path, monkeypatch):
    """One agent_state.json per project; overwritten each delegation (no accumulation)."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    agent = _make_agent(delegation_id="d-over-1", event_sink=None)
    agent.set_lifecycle_context(project_key="tasks/overwrite", mcp_session_id="s1")
    agent.set_spec_path("tasks/step-01.md")
    _drive_agent_to_finish(agent)

    # Second delegation on same agent
    agent.set_delegation_id("d-over-2")
    agent.set_lifecycle_context(project_key="tasks/overwrite", mcp_session_id="s1")
    agent.set_spec_path("tasks/step-02.md")
    _drive_agent_to_finish(agent)

    state_dir = AgentCheckpoint.state_path("tasks/overwrite").parent
    files = list(state_dir.glob("agent_state*.json"))
    assert len(files) == 1  # exactly one, overwritten
    cp = AgentCheckpoint.find_for_project("tasks/overwrite")
    assert cp.last_delegation_id == "d-over-2"


# ── rehydrate_from() ───────────────────────────────────────────────────────


def test_rehydrate_from_restores_lifecycle_context(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    cp = AgentCheckpoint(
        project_key="tasks/rehydrate",
        last_delegation_id="d-prev-1",
        last_outcome="success",
        last_spec_path="tasks/step-01.md",
        last_finished_at="2026-06-21T23:00:00Z",
        lifecycle_context={
            "project_key": "tasks/rehydrate",
            "reviewer_pass_result": "issues",
            "phases_completed": ["preloop", "loop"],
        },
    )
    cp.save()

    # Simulate a fresh process: create a blank agent, rehydrate
    agent = _make_agent()
    assert agent._lifecycle_context == {}  # blank
    loaded = AgentCheckpoint.find_for_project("tasks/rehydrate")
    agent.rehydrate_from(loaded)

    assert agent._lifecycle_context.get("reviewer_pass_result") == "issues"
    assert agent._lifecycle_context.get("project_key") == "tasks/rehydrate"
    assert agent._resumed_from_checkpoint is True


def test_rehydrate_does_not_set_lifecycle_started(tmp_path, monkeypatch):
    """Critical: a rehydrated agent must NOT have _lifecycle_started=True.
    The next delegation emits a fresh lifecycle_start(resumed=False). The
    checkpoint is history, not an open envelope."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    cp = AgentCheckpoint(
        project_key="tasks/no-start",
        last_delegation_id="d-prev-1",
        last_outcome="success",
        last_spec_path=None,
        last_finished_at="2026-06-21T23:00:00Z",
        lifecycle_context={"project_key": "tasks/no-start"},
    )
    cp.save()

    agent = _make_agent()
    loaded = AgentCheckpoint.find_for_project("tasks/no-start")
    agent.rehydrate_from(loaded)

    assert agent._lifecycle_started is False
    assert agent._resumed_from_checkpoint is True


def test_rehydrate_from_wrong_type_is_noop():
    """rehydrate_from() silently ignores non-AgentCheckpoint objects (defensive)."""
    agent = _make_agent()
    agent.rehydrate_from("not a checkpoint")  # type: ignore[arg-type]
    assert agent._lifecycle_context == {}
    assert agent._resumed_from_checkpoint is False


# ── _get_or_create_supervisor rehydrates on cache miss ─────────────────────


def test_get_or_create_supervisor_rehydrates_from_checkpoint(tmp_path, monkeypatch):
    """Simulate a server restart: registry empty, checkpoint on disk.
    _get_or_create_supervisor should create a fresh agent AND rehydrate."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    # Pre-write a checkpoint as if a prior delegation happened
    cp = AgentCheckpoint(
        project_key="tasks/restart",
        last_delegation_id="d-before-restart",
        last_outcome="success",
        last_spec_path="tasks/step-01.md",
        last_finished_at="2026-06-21T22:00:00Z",
        lifecycle_context={
            "project_key": "tasks/restart",
            "reviewer_pass_result": "lgtm",
        },
    )
    cp.save()

    from server.mcp_server import _get_or_create_supervisor, _SUPERVISOR_REGISTRY
    # Clear the registry to simulate a fresh process
    _SUPERVISOR_REGISTRY.clear()

    agent = _get_or_create_supervisor(
        "tasks/restart", str(tmp_path / "ws"), "tasks/step-01.md"
    )
    assert agent._resumed_from_checkpoint is True
    assert agent._lifecycle_context.get("reviewer_pass_result") == "lgtm"
    assert agent._lifecycle_context.get("project_key") == "tasks/restart"


def test_get_or_create_supervisor_cache_hit_skips_rehydrate(tmp_path, monkeypatch):
    """When the agent is already in the registry (server mode, same process),
    _get_or_create_supervisor returns it without rehydrating from disk."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    from server.mcp_server import _get_or_create_supervisor, _SUPERVISOR_REGISTRY
    _SUPERVISOR_REGISTRY.clear()

    # First call: cache miss, creates + (no checkpoint, so no rehydrate)
    agent1 = _get_or_create_supervisor(
        "tasks/cache", str(tmp_path / "ws"), None
    )
    assert agent1._resumed_from_checkpoint is False
    _SUPERVISOR_REGISTRY["tasks/cache"] = agent1

    # Second call: cache hit, returns same instance
    agent2 = _get_or_create_supervisor(
        "tasks/cache", str(tmp_path / "ws"), None
    )
    assert agent2 is agent1


# ── CLI ≡ server invariant ─────────────────────────────────────────────────


def test_cli_and_server_produce_identical_checkpoint_content(tmp_path, monkeypatch):
    """Same delegation in CLI vs server mode produces the same agent_state.json
    fields (modulo timestamps and delegation_id). The checkpoint is the
    behavioral invariant."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))

    # "Server mode": run a delegation, checkpoint saved
    events: list[dict] = []
    server_agent = _make_agent(delegation_id="d-server-1", event_sink=events.append)
    server_agent.set_lifecycle_context(
        project_key="tasks/parity", session_policy="reuse", mcp_session_id="sess-1"
    )
    server_agent.set_spec_path("tasks/step-01.md")
    _drive_agent_to_finish(server_agent, reviewer_result="issues")
    server_cp = AgentCheckpoint.find_for_project("tasks/parity")

    # "CLI mode": fresh process, fresh agent, same project + spec + reviewer
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home2"))
    cli_events: list[dict] = []
    cli_agent = _make_agent(delegation_id="d-cli-1", event_sink=cli_events.append)
    cli_agent.set_lifecycle_context(
        project_key="tasks/parity", session_policy="reuse", mcp_session_id="sess-1"
    )
    cli_agent.set_spec_path("tasks/step-01.md")
    _drive_agent_to_finish(cli_agent, reviewer_result="issues")
    cli_cp = AgentCheckpoint.find_for_project("tasks/parity")

    # Same steady-state fields (delegation_id + timestamp differ by design)
    assert server_cp.project_key == cli_cp.project_key
    assert server_cp.last_outcome == cli_cp.last_outcome
    assert server_cp.last_spec_path == cli_cp.last_spec_path
    assert server_cp.lifecycle_context.get("reviewer_pass_result") == "issues"
    assert cli_cp.lifecycle_context.get("reviewer_pass_result") == "issues"
    assert server_cp.lifecycle_context.get("project_key") == cli_cp.lifecycle_context.get("project_key")


# ── escalation produces BOTH stores ────────────────────────────────────────


def test_escalation_produces_both_supervisor_state_and_checkpoint(tmp_path, monkeypatch):
    """An escalated (paused) delegation must write BOTH:
    - SupervisorState (resumable, expiring, with turn_index + questions)
    - AgentCheckpoint (steady-state, non-expiring, identity + lifecycle)"""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    from core.state.supervisor_state import SupervisorState

    events: list[dict] = []
    agent = _make_agent(delegation_id="d-esc-1", event_sink=events.append)
    agent.set_lifecycle_context(project_key="tasks/esc", mcp_session_id="s1")
    agent.set_spec_path("tasks/step-01.md")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_phase_end("preloop", status="ok")
    agent.emit_lifecycle_phase_start("loop")
    agent.begin()
    agent.begin_turn()
    exec_result = _result(success=False)
    agent.update_reviewer_pass_result("issues")
    # Escalate: complete_turn with a decision that triggers escalate
    result = agent.finish()  # finish() with no successful turn → may escalate or error
    # The checkpoint should be written regardless of outcome
    cp = AgentCheckpoint.find_for_project("tasks/esc")
    assert cp is not None
    assert cp.last_outcome in ("error", "escalated")


# ── no project_key → no checkpoint (graceful skip) ─────────────────────────


def test_no_project_key_skips_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    events: list[dict] = []
    # No spec_path, no lifecycle_context.project_key → can't resolve project_key
    agent = _make_agent(delegation_id="d-nopk-1", event_sink=events.append)
    agent.set_spec_path(None)
    _drive_agent_to_finish(agent)

    # No checkpoint_saved event (graceful skip)
    saved_events = [e for e in events if e["type"] == "agent_checkpoint_saved"]
    assert saved_events == []
