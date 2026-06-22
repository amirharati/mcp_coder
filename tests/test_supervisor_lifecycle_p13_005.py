"""P13-005 — supervisor lifecycle envelope tests.

Covers:
- delegation_lifecycle_start / delegation_lifecycle_end events present
- preloop / loop / postloop phase_start / phase_end in correct order
- supervisor_loop_* events nested inside loop phase
- resume path emits coherent lifecycle events (no preloop re-run)
- lifecycle_end includes reviewer_pass_result (non-fatal reviewer error)
- SupervisorState.lifecycle_context persisted on escalation and loaded on resume
- Backward-compat: old state files without lifecycle_context load cleanly
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import (
    SupervisorAgent,
    SupervisorTurnContext,
    SupervisorTurnDecision,
)
from core.logging.delegation_log import (
    REVIEWER_PASS_ERROR,
    resolve_reviewer_pass_result,
)
from core.state.supervisor_state import SupervisorState


# ── helpers ──────────────────────────────────────────────────────────────────


def _result(success: bool = True, *, files=None, error=None, error_class=None) -> ExecutionResult:
    return ExecutionResult(
        success=success,
        output="worker output",
        files_changed=list(files or (["a.py"] if success else [])),
        model="test/model",
        error=error,
        error_class=error_class,
    )


def _agent_with_events(executor_fn, **kw):
    events: list[dict] = []
    agent = SupervisorAgent(
        delegation_id=kw.pop("delegation_id", "d-lc-1"),
        workspace_path="/tmp/ws",
        executor_fn=executor_fn,
        event_sink=events.append,
        **kw,
    )
    return agent, events


def _run_full_lifecycle(agent: SupervisorAgent, events: list, *, reviewer_result="lgtm"):
    """Simulate the server's lifecycle event emission around the supervisor loop."""
    # Server emits lifecycle_start + retroactive preloop envelope
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_phase_end("preloop", status="ok")

    # Server emits loop phase start, then drives supervisor loop
    agent.emit_lifecycle_phase_start("loop")
    agent.begin()          # emits supervisor_loop_start
    agent.begin_turn()     # emits supervisor_turn_start

    exec_result = _result(success=True)
    agent.complete_turn(exec_result, {"outcome": reviewer_result, "note": ""})
    agent.finish()         # emits supervisor_loop_end

    # Server stores reviewer result and emits loop phase end
    agent.update_reviewer_pass_result(reviewer_result)
    agent.emit_lifecycle_phase_end("loop", status="ok")

    # Server emits postloop phase
    agent.emit_lifecycle_phase_start("postloop")
    agent.emit_lifecycle_phase_end("postloop", status="ok")

    # Server emits lifecycle end
    agent.emit_lifecycle_end("success")


# ── 1. lifecycle envelope event ordering ─────────────────────────────────────


def test_lifecycle_envelope_event_types_present():
    """All six lifecycle event types must be present in a full delegation."""
    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1)
    agent.set_lifecycle_context(
        project_key="tasks/auth",
        session_policy="existing",
        session_action="reuse",
        mcp_session_id="sess-1",
    )
    _run_full_lifecycle(agent, events)

    types = [e["type"] for e in events]
    assert "delegation_lifecycle_start" in types
    assert "delegation_lifecycle_end" in types
    # preloop, loop, postloop — each has start + end
    phase_starts = [e for e in events if e["type"] == "delegation_phase_start"]
    phase_ends = [e for e in events if e["type"] == "delegation_phase_end"]
    assert {e["phase"] for e in phase_starts} == {"preloop", "loop", "postloop"}
    assert {e["phase"] for e in phase_ends} == {"preloop", "loop", "postloop"}


def test_lifecycle_envelope_correct_ordering():
    """Lifecycle start → preloop → loop (with supervisor_loop nested) → postloop → lifecycle end."""
    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1)
    agent.set_lifecycle_context(project_key="tasks/auth")
    _run_full_lifecycle(agent, events)

    types = [e["type"] for e in events]

    def idx(t, phase=None):
        for i, e in enumerate(events):
            if e["type"] == t and (phase is None or e.get("phase") == phase):
                return i
        raise AssertionError(f"event {t!r} (phase={phase!r}) not found")

    lc_start = idx("delegation_lifecycle_start")
    preloop_start = idx("delegation_phase_start", "preloop")
    preloop_end = idx("delegation_phase_end", "preloop")
    loop_start = idx("delegation_phase_start", "loop")
    supervisor_loop_start = idx("supervisor_loop_start")
    supervisor_loop_end = idx("supervisor_loop_end")
    loop_end = idx("delegation_phase_end", "loop")
    postloop_start = idx("delegation_phase_start", "postloop")
    postloop_end = idx("delegation_phase_end", "postloop")
    lc_end = idx("delegation_lifecycle_end")

    # Lifecycle envelope ordering
    assert lc_start < preloop_start < preloop_end
    assert preloop_end < loop_start
    assert loop_start < supervisor_loop_start < supervisor_loop_end < loop_end
    assert loop_end < postloop_start < postloop_end < lc_end


def test_lifecycle_start_carries_session_metadata():
    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1)
    agent.set_lifecycle_context(
        project_key="tasks/auth",
        session_policy="existing",
        session_action="reuse",
        mcp_session_id="sess-abc",
    )
    agent.emit_lifecycle_start()

    lc_start = next(e for e in events if e["type"] == "delegation_lifecycle_start")
    assert lc_start["project_key"] == "tasks/auth"
    assert lc_start["session_policy"] == "existing"
    assert lc_start["session_action"] == "reuse"
    assert lc_start["mcp_session_id"] == "sess-abc"
    assert lc_start["resumed"] is False


def test_lifecycle_end_carries_phase_summary_and_reviewer():
    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1)
    agent.set_lifecycle_context(project_key="tasks/auth")
    agent.update_reviewer_pass_result("lgtm")
    _run_full_lifecycle(agent, events, reviewer_result="lgtm")

    lc_end = next(e for e in events if e["type"] == "delegation_lifecycle_end")
    assert lc_end["outcome"] == "success"
    assert lc_end["reviewer_pass_result"] == "lgtm"
    assert "preloop" in lc_end["phase_summary"]
    assert "loop" in lc_end["phase_summary"]
    assert "postloop" in lc_end["phase_summary"]


def test_delegation_id_present_in_lifecycle_events():
    """All lifecycle events must carry delegation_id."""
    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1, delegation_id="deleg-xyz")
    agent.set_lifecycle_context(project_key="tasks/auth")
    _run_full_lifecycle(agent, events)

    lifecycle_types = {
        "delegation_lifecycle_start", "delegation_lifecycle_end",
        "delegation_phase_start", "delegation_phase_end",
    }
    for ev in events:
        if ev["type"] in lifecycle_types:
            assert ev.get("delegation_id") == "deleg-xyz", (
                f"delegation_id missing on {ev['type']}"
            )


# ── 2. resume path lifecycle coherence ───────────────────────────────────────


def test_resume_emits_lifecycle_start_with_resumed_flag(tmp_path, monkeypatch):
    """Resumed delegation emits lifecycle_start with resumed=True (no preloop)."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = SupervisorState.create(
        spec_path="tasks/auth-01.md",
        context_ref="deleg-resume-1",
        plan="plan",
        decision_log=[],
        completed_turn_artifacts=[],
        turn_index=1,
        questions=["Q?"],
        lifecycle_context={
            "project_key": "tasks/auth",
            "session_policy": "existing",
            "session_action": "reuse",
            "mcp_session_id": "sess-orig",
            "phases_completed": ["preloop"],
        },
    )

    events: list[dict] = []

    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent = SupervisorAgent.resume(
        state,
        "My answer",
        workspace_path=str(tmp_path),
        executor_fn=executor,
        event_sink=events.append,
    )
    result = agent.run()

    # Server closes lifecycle after run()
    agent.emit_lifecycle_phase_end("loop", status="ok")
    agent.emit_lifecycle_end(result.outcome)

    types = [e["type"] for e in events]
    assert "delegation_lifecycle_start" in types
    assert "delegation_lifecycle_end" in types

    lc_start = next(e for e in events if e["type"] == "delegation_lifecycle_start")
    assert lc_start["resumed"] is True

    # No preloop phase in resumed path
    preloop_starts = [e for e in events if e.get("phase") == "preloop"]
    assert not preloop_starts, "preloop must not be re-run on resume"

    # Loop phase started in resume()
    loop_starts = [e for e in events if e["type"] == "delegation_phase_start" and e.get("phase") == "loop"]
    assert loop_starts
    assert loop_starts[0]["resumed"] is True


def test_resume_lifecycle_ordering(tmp_path, monkeypatch):
    """Resume trace: lifecycle_start < loop_phase_start < supervisor_loop_start < loop_end < lifecycle_end."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = SupervisorState.create(
        spec_path="tasks/p1.md",
        context_ref="deleg-resume-ord",
        plan=None,
        decision_log=[],
        completed_turn_artifacts=[],
        turn_index=1,
        questions=["Clarify?"],
    )

    events: list[dict] = []

    agent = SupervisorAgent.resume(
        state, "ok",
        workspace_path=str(tmp_path),
        executor_fn=lambda t, c, r=False: _result(success=True),
        event_sink=events.append,
    )
    result = agent.run()
    agent.emit_lifecycle_phase_end("loop", status="ok")
    agent.emit_lifecycle_end(result.outcome)

    types = [e["type"] for e in events]

    def idx(t, phase=None, flag=None):
        for i, e in enumerate(events):
            if e["type"] == t:
                if phase is not None and e.get("phase") != phase:
                    continue
                if flag is not None and e.get("resumed") != flag:
                    continue
                return i
        raise AssertionError(f"event {t!r} (phase={phase!r}, resumed={flag!r}) not found")

    lc_start = idx("delegation_lifecycle_start")
    loop_phase_start = idx("delegation_phase_start", "loop")
    sup_loop_start = idx("supervisor_loop_start")
    loop_phase_end = idx("delegation_phase_end", "loop")
    lc_end = idx("delegation_lifecycle_end")

    assert lc_start < loop_phase_start < sup_loop_start < loop_phase_end < lc_end


# ── 3. SupervisorState lifecycle_context persistence ─────────────────────────


def test_lifecycle_context_persisted_on_escalation(tmp_path, monkeypatch):
    """When escalated, lifecycle_context including reviewer_pass_result is saved."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    events: list[dict] = []

    def escalate(ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        return SupervisorTurnDecision(action="escalate_host", reason="needs human")

    agent = SupervisorAgent(
        delegation_id="deleg-esc",
        workspace_path=str(tmp_path),
        executor_fn=lambda t, c, r=False: _result(success=False, error="Q?"),
        decision_fn=escalate,
        event_sink=events.append,
        spec_path="tasks/auth-01.md",
        max_turns=2,
    )
    agent.set_lifecycle_context(
        project_key="tasks/auth",
        session_policy="new",
        session_action="create",
        mcp_session_id="sess-esc",
    )
    agent.update_reviewer_pass_result("error")

    agent.begin()
    agent.begin_turn()
    agent.complete_turn(_result(success=False, error="Q?"), {"outcome": None, "note": ""})
    result = agent.finish()

    assert result.outcome == "escalated"
    assert result.resume_token

    saved = SupervisorState.find_and_load(result.resume_token)
    lc = saved.lifecycle_context
    assert lc.get("project_key") == "tasks/auth"
    assert lc.get("reviewer_pass_result") == "error"
    assert lc.get("session_policy") == "new"


def test_lifecycle_context_backward_compat_missing_field(tmp_path, monkeypatch):
    """Old state JSON without lifecycle_context loads without error."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = SupervisorState.create(
        spec_path="tasks/auth-01.md",
        context_ref="deleg-old",
        plan=None,
        decision_log=[],
        completed_turn_artifacts=[],
        turn_index=1,
        questions=[],
    )
    path = state.save()

    # Simulate old state file: remove lifecycle_context
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["lifecycle_context"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = SupervisorState.load(state.resume_token, state.project_key)
    assert loaded.lifecycle_context == {}


# ── 4. Non-fatal reviewer parse error (P13-ISS-005) ──────────────────────────


def test_reviewer_parse_error_resolves_to_error_result():
    """resolve_reviewer_pass_result returns 'error' for null outcome (parse fail)."""
    result = resolve_reviewer_pass_result(
        enabled=True,
        ran=True,
        outcome=None,  # parse failed — no lgtm/issues
        error="Failed to parse reviewer output: missing heading",
    )
    assert result == REVIEWER_PASS_ERROR


def test_reviewer_parse_error_does_not_fail_delegation():
    """Executor success + reviewer parse error → delegation outcome = success."""
    events: list[dict] = []

    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1)
    agent.set_lifecycle_context(project_key="tasks/auth")

    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_phase_end("preloop")
    agent.emit_lifecycle_phase_start("loop")
    agent.begin()
    agent.begin_turn()
    exec_res = _result(success=True)
    # Reviewer gave no parseable outcome — treated as error, not delegation failure
    checks_with_parse_error = {"outcome": None, "note": "reviewer parse failed"}
    agent.complete_turn(exec_res, checks_with_parse_error)
    agent_result = agent.finish()

    # Delegation should succeed despite reviewer parse error
    assert agent_result.outcome == "success"

    # Record reviewer error in lifecycle context
    agent.update_reviewer_pass_result("error")
    agent.emit_lifecycle_phase_end("loop", status="ok")
    agent.emit_lifecycle_phase_start("postloop")
    agent.emit_lifecycle_phase_end("postloop")
    agent.emit_lifecycle_end("success")

    lc_end = next(e for e in events if e["type"] == "delegation_lifecycle_end")
    # Lifecycle end records reviewer_pass_result=error but delegation outcome=success
    assert lc_end["outcome"] == "success"
    assert lc_end["reviewer_pass_result"] == "error"


def test_reviewer_parse_error_lifecycle_shows_non_fatal():
    """Phase summary shows loop=ok even when reviewer encountered a parse error."""
    events: list[dict] = []

    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1)
    agent.set_lifecycle_context(project_key="tasks/auth")
    _run_full_lifecycle(agent, events, reviewer_result="error")

    lc_end = next(e for e in events if e["type"] == "delegation_lifecycle_end")
    # reviewer error is recorded but delegation and loop are "ok"
    assert lc_end["outcome"] == "success"
    assert lc_end["phase_summary"].get("loop") == "ok"
    assert lc_end["reviewer_pass_result"] == "error"


# ── 5. Existing loop events unaffected ───────────────────────────────────────


def test_existing_supervisor_loop_events_still_present():
    """Existing supervisor_loop_* events remain in the trace (additive only)."""
    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1)
    agent.set_lifecycle_context(project_key="tasks/auth")
    _run_full_lifecycle(agent, events)

    types = [e["type"] for e in events]
    assert "supervisor_loop_start" in types
    assert "supervisor_loop_end" in types
    assert "supervisor_turn_start" in types
    assert "supervisor_turn_end" in types
    assert "supervisor_decision" in types


def test_lifecycle_events_do_not_appear_in_direct_agent_run():
    """Running the agent via agent.run() without explicit lifecycle calls produces no lifecycle events."""
    def executor(turn, correction, reset=False):
        return _result(success=True)

    agent, events = _agent_with_events(executor, max_turns=1)
    agent.run()

    lifecycle_types = {
        "delegation_lifecycle_start", "delegation_lifecycle_end",
        "delegation_phase_start", "delegation_phase_end",
    }
    for ev in events:
        assert ev["type"] not in lifecycle_types, (
            f"Unexpected lifecycle event {ev['type']!r} from bare agent.run()"
        )
