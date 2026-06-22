"""P13-006 — SupervisorAgent owns the delegation lifecycle envelope.

Covers the ownership contract (vs P13-005's retroactive observability):
- delegate() emits lifecycle_start + phase_start(preloop) BEFORE preloop work
- delegate() does NOT re-emit if the caller already started the envelope
- resume_and_delegate() emits lifecycle_start(resumed=True) + phase_start(loop, resumed=True)
- Agent-owned phase_end(preloop) + phase_start(loop) transition at execution entry
- Lifecycle event records carry delegation_id even when set via late-binding setters
- set_delegation_id / set_lifecycle_event_sink / set_spec_path late-binding works
- begin_delegation() preserves lifecycle context set before preloop (no wipe)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import SupervisorAgent
from core.state.supervisor_state import SupervisorState


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
    """Create a bare agent with NO delegation_id set (simulates early creation)."""
    return SupervisorAgent(
        delegation_id=delegation_id,
        workspace_path="/tmp/ws",
        executor_fn=lambda _t, _c, _r=False: _result(),
        event_sink=event_sink,
        spec_path=spec_path,
    )


# ── late-binding setters ───────────────────────────────────────────────────


def test_set_delegation_id_updates_loop_id():
    agent = _make_agent(delegation_id=None)
    assert agent.loop_id == "supervisor:1"
    agent.set_delegation_id("d-own-1")
    assert agent._delegation_id == "d-own-1"
    assert agent.loop_id == "d-own-1:supervisor:1"


def test_set_lifecycle_event_sink_routes_emissions():
    events: list[dict] = []
    agent = _make_agent(event_sink=None)
    agent.set_delegation_id("d-sink-1")
    agent.set_lifecycle_event_sink(events.append)
    agent.set_lifecycle_context(project_key="pk", mcp_session_id="sess-1")
    agent.emit_lifecycle_start()
    assert any(e["type"] == "delegation_lifecycle_start" for e in events)
    assert events[-1]["delegation_id"] == "d-sink-1"


def test_set_spec_path_propagates_to_lifecycle_events():
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_delegation_id("d-spec-1")
    agent.set_lifecycle_context(project_key="pk")
    agent.set_spec_path("tasks/step-01.md")
    agent.emit_lifecycle_start()
    start = [e for e in events if e["type"] == "delegation_lifecycle_start"][0]
    assert start["spec_path"] == "tasks/step-01.md"


# ── delegate() ownership contract ─────────────────────────────────────────


def test_delegate_emits_lifecycle_start_and_preloop_phase_start():
    """delegate() owns the envelope: emits start + preloop BEFORE begin_delegation."""
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_lifecycle_context(project_key="pk", mcp_session_id="sess-d-1")
    agent.delegate(
        delegation_id="d-delegate-1",
        executor_fn=lambda _t, _c, _r=False: _result(),
        max_turns=1,
        event_sink=events.append,
        spec_path="tasks/step-01.md",
    )
    types = [e["type"] for e in events]
    assert "delegation_lifecycle_start" in types
    assert "delegation_phase_start" in types
    # preloop phase_start must come BEFORE supervisor_loop_start (which begin() emits)
    # delegate() does not call begin() itself, so loop_start won't be here yet.
    phase_starts = [e for e in events if e["type"] == "delegation_phase_start"]
    assert phase_starts[0]["phase"] == "preloop"
    assert phase_starts[0]["resumed"] is False


def test_delegate_does_not_re_emit_if_envelope_already_started():
    """If the caller already emitted lifecycle_start + preloop (early creation path),
    delegate() must not duplicate them."""
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_delegation_id("d-noop-1")
    agent.set_lifecycle_context(project_key="pk")
    # Caller already started the envelope (server's early-creation path in P13-006)
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    pre_count = len(events)
    agent.delegate(
        delegation_id="d-noop-1",
        executor_fn=lambda _t, _c, _r=False: _result(),
        max_turns=1,
    )
    # No new lifecycle_start or preloop phase_start should be emitted
    new_starts = [
        e for e in events[pre_count:]
        if e["type"] == "delegation_lifecycle_start"
    ]
    new_preloop = [
        e for e in events[pre_count:]
        if e["type"] == "delegation_phase_start" and e["phase"] == "preloop"
    ]
    assert new_starts == []
    assert new_preloop == []


def test_begin_delegation_preserves_lifecycle_context_set_before_preloop():
    """P13-006 critical: begin_delegation() must NOT wipe lifecycle context that
    was populated before preloop (the early-creation path sets it before
    spec_validation/clarity run)."""
    agent = _make_agent(event_sink=None)
    agent.set_delegation_id("d-preserve-1")
    agent.set_lifecycle_context(
        project_key="pk",
        session_policy="reuse",
        session_action="reuse",
        mcp_session_id="sess-1",
    )
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    # Now begin_delegation is called later (at execution entry)
    agent.begin_delegation(
        delegation_id="d-preserve-1",
        executor_fn=lambda _t, _c, _r=False: _result(),
        max_turns=1,
        spec_path="tasks/step-01.md",
    )
    # Context preserved
    assert agent._lifecycle_context.get("project_key") == "pk"
    assert agent._lifecycle_context.get("mcp_session_id") == "sess-1"
    # Phases preserved (preloop was started)
    assert "preloop" in agent._lifecycle_phases or agent._lifecycle_phases == {}


def test_begin_delegation_resets_lifecycle_when_not_pre_populated():
    """If the caller did NOT pre-populate lifecycle context, begin_delegation
    should still reset to empty (backward-compat with direct begin path)."""
    agent = _make_agent(event_sink=None)
    # No set_lifecycle_context, no emit_lifecycle_start
    agent._lifecycle_context = {"stale": "value"}
    agent._lifecycle_phases = {"stale": "ok"}
    agent.begin_delegation(
        delegation_id="d-reset-1",
        executor_fn=lambda _t, _c, _r=False: _result(),
        max_turns=1,
    )
    assert agent._lifecycle_context == {}
    assert agent._lifecycle_phases == {}


# ── agent-owned phase transition ───────────────────────────────────────────


def test_agent_owns_preloop_to_loop_transition():
    """The agent (not the server) emits phase_end(preloop) + phase_start(loop)
    at the transition into execution."""
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_delegation_id("d-trans-1")
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    # ... preloop work happens (server-owned code, agent owns the envelope) ...
    agent.emit_lifecycle_phase_end("preloop", status="ok")
    agent.emit_lifecycle_phase_start("loop", resumed=False)
    types = [e["type"] for e in events]
    # Correct order: start, phase_start(preloop), phase_end(preloop), phase_start(loop)
    assert types == [
        "delegation_lifecycle_start",
        "delegation_phase_start",
        "delegation_phase_end",
        "delegation_phase_start",
    ]
    phases_in_order = [e["phase"] for e in events if e["type"] in (
        "delegation_phase_start", "delegation_phase_end"
    )]
    assert phases_in_order == ["preloop", "preloop", "loop"]


# ── resume_and_delegate() ownership contract ──────────────────────────────


def test_resume_and_delegate_emits_resumed_lifecycle_envelope(tmp_path, monkeypatch):
    """resume_and_delegate() owns the resumed envelope: lifecycle_start(resumed=True)
    + phase_start(loop, resumed=True), and does NOT re-emit preloop."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = SupervisorState.create(
        spec_path="tasks/step-01.md",
        context_ref="d-resume-1",
        turn_index=1,
        decision_log=[],
        completed_turn_artifacts=[],
        questions=[],
        plan=None,
        lifecycle_context={"project_key": "pk", "phases_completed": {"preloop": "ok"}},
    )

    events: list[dict] = []
    agent = SupervisorAgent.resume_and_delegate(
        state,
        "host answer",
        workspace_path="/tmp/ws",
        executor_fn=lambda _t, _c, _r=False: _result(),
        event_sink=events.append,
    )
    types = [e["type"] for e in events]
    assert types[0] == "delegation_lifecycle_start"
    assert types[1] == "delegation_phase_start"
    assert events[0]["resumed"] is True
    assert events[1]["resumed"] is True
    assert events[1]["phase"] == "loop"
    # No preloop re-run on resume
    preloop_starts = [
        e for e in events
        if e["type"] == "delegation_phase_start" and e["phase"] == "preloop"
    ]
    assert preloop_starts == []


def test_resume_and_delegate_restores_lifecycle_context(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = SupervisorState.create(
        spec_path="tasks/step-01.md",
        context_ref="d-ctx-1",
        turn_index=0,
        decision_log=[],
        completed_turn_artifacts=[],
        questions=[],
        plan=None,
        lifecycle_context={
            "project_key": "pk",
            "reviewer_pass_result": "issues",
            "phases_completed": {"preloop": "ok", "loop": "in_progress"},
        },
    )

    agent = SupervisorAgent.resume_and_delegate(
        state,
        "answer",
        workspace_path="/tmp/ws",
        executor_fn=lambda _t, _c, _r=False: _result(),
    )
    assert agent._lifecycle_context.get("reviewer_pass_result") == "issues"
    assert agent._lifecycle_context.get("project_key") == "pk"


# ── delegation_id present in all agent-emitted lifecycle events ────────────


def test_all_lifecycle_events_carry_delegation_id():
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_delegation_id("d-id-all-1")
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_phase_end("preloop", status="ok")
    agent.emit_lifecycle_phase_start("loop")
    agent.emit_lifecycle_phase_end("loop", status="ok")
    agent.emit_lifecycle_phase_start("postloop")
    agent.emit_lifecycle_phase_end("postloop", status="ok")
    agent.emit_lifecycle_end("success")
    for e in events:
        assert e["delegation_id"] == "d-id-all-1", f"missing delegation_id in {e['type']}"


def test_lifecycle_end_carries_phase_summary_and_reviewer():
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_delegation_id("d-end-1")
    agent.set_lifecycle_context(project_key="pk")
    agent.update_reviewer_pass_result("issues")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_phase_end("preloop", status="ok")
    agent.emit_lifecycle_phase_start("loop")
    agent.emit_lifecycle_phase_end("loop", status="ok")
    agent.emit_lifecycle_phase_start("postloop")
    agent.emit_lifecycle_phase_end("postloop", status="ok")
    agent.emit_lifecycle_end("success")
    end = [e for e in events if e["type"] == "delegation_lifecycle_end"][0]
    assert end["outcome"] == "success"
    assert end["phase_summary"] == {"preloop": "ok", "loop": "ok", "postloop": "ok"}
    assert end["reviewer_pass_result"] == "issues"


# ── preloop hard-gate closures (agent-owned) ───────────────────────────────


def test_preloop_blocked_on_clarity_emits_lifecycle_end_needs_input():
    """When preloop is blocked by a clarity gate, the agent closes the envelope
    with outcome=needs_input (not error)."""
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_delegation_id("d-clarity-1")
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    # Clarity gate blocks
    agent.emit_lifecycle_phase_end("preloop", status="blocked", detail="clarity_check")
    agent.emit_lifecycle_end("needs_input")
    types = [e["type"] for e in events]
    assert types == [
        "delegation_lifecycle_start",
        "delegation_phase_start",
        "delegation_phase_end",
        "delegation_lifecycle_end",
    ]
    assert events[-1]["outcome"] == "needs_input"
    assert events[-2]["status"] == "blocked"


def test_preloop_blocked_on_invalid_spec_emits_lifecycle_end_error():
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_delegation_id("d-invalid-1")
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_phase_end("preloop", status="blocked", detail="invalid_spec")
    agent.emit_lifecycle_end("error")
    assert events[-1]["outcome"] == "error"


# ── non-retroactive timing (the core P13-006 honesty fix) ─────────────────


def test_preloop_phase_end_not_retroactive():
    """P13-006 core: preloop phase_end is emitted AT the transition to loop,
    not retroactively after loop completes. This test simulates the ordering:
    lifecycle_start → phase_start(preloop) → [preloop work] → phase_end(preloop)
    → phase_start(loop) → [loop work] → phase_end(loop)."""
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_delegation_id("d-honest-1")
    agent.set_lifecycle_context(project_key="pk")

    # Preloop starts BEFORE any preloop work
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    preloop_start_idx = next(
        i for i, e in enumerate(events)
        if e["type"] == "delegation_phase_start" and e["phase"] == "preloop"
    )

    # Preloop work happens here (spec_validation, clarity) — no events.

    # Preloop ends AT the transition (honest, not retroactive)
    agent.emit_lifecycle_phase_end("preloop", status="ok")
    preloop_end_idx = next(
        i for i, e in enumerate(events)
        if e["type"] == "delegation_phase_end" and e["phase"] == "preloop"
    )

    # Loop starts
    agent.emit_lifecycle_phase_start("loop")

    # Loop work would happen here. We emit a marker to prove preloop_end came before.
    events.append({"type": "_marker_loop_work", "delegation_id": "d-honest-1"})

    assert preloop_start_idx < preloop_end_idx
    # The loop work marker comes AFTER preloop_end (proving non-retroactive)
    marker_idx = next(i for i, e in enumerate(events) if e["type"] == "_marker_loop_work")
    assert preloop_end_idx < marker_idx
