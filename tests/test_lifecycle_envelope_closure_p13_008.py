"""P13-008 — lifecycle envelope closure guard (ISS-008 fix).

Covers the agent-side idempotent close + phase-event guard:
- emit_lifecycle_end is idempotent: a second call is a no-op with a warning
- emit_lifecycle_phase_start/end are no-ops after the envelope closes
- begin_delegation resets _lifecycle_closed so the next delegation opens fresh
- rehydrate_from does NOT set _lifecycle_closed (next delegation opens fresh)
"""

from __future__ import annotations

import logging

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import SupervisorAgent


def _result(success: bool = True) -> ExecutionResult:
    return ExecutionResult(
        success=success,
        output="worker output",
        files_changed=["a.py"] if success else [],
        model="test/model",
    )


def _make_agent(*, event_sink=None) -> SupervisorAgent:
    return SupervisorAgent(
        delegation_id="d-closure-1",
        workspace_path="/tmp/ws",
        executor_fn=lambda _t, _c, _r=False: _result(),
        event_sink=event_sink,
        spec_path="tasks/step-01.md",
    )


# ── emit_lifecycle_end idempotency ─────────────────────────────────────────


def test_emit_lifecycle_end_is_idempotent_second_call_noops():
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_end("success")
    agent.emit_lifecycle_end("error")  # second call — must be no-op

    end_events = [e for e in events if e["type"] == "delegation_lifecycle_end"]
    assert len(end_events) == 1, "second emit_lifecycle_end must not emit"
    assert end_events[0]["outcome"] == "success"


def test_emit_lifecycle_end_second_call_logs_warning(caplog):
    agent = _make_agent(event_sink=lambda _e: None)
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_end("success")
    with caplog.at_level(logging.WARNING, logger="core.engine.supervisor_agent"):
        agent.emit_lifecycle_end("error")
    assert any(
        "already closed" in rec.message for rec in caplog.records
    ), "second emit_lifecycle_end must log a warning"


def test_lifecycle_closed_flag_set_after_end():
    agent = _make_agent(event_sink=lambda _e: None)
    agent.set_lifecycle_context(project_key="pk")
    assert agent._lifecycle_closed is False
    agent.emit_lifecycle_start()
    assert agent._lifecycle_closed is False
    agent.emit_lifecycle_end("success")
    assert agent._lifecycle_closed is True


# ── phase events gated after close ─────────────────────────────────────────


def test_phase_start_after_close_is_noop():
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_end("needs_input")
    agent.emit_lifecycle_phase_start("loop")  # must be no-op

    phase_starts = [e for e in events if e["type"] == "delegation_phase_start"]
    assert len(phase_starts) == 1
    assert phase_starts[0]["phase"] == "preloop"


def test_phase_end_after_close_is_noop():
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_end("needs_input")
    agent.emit_lifecycle_phase_end("loop", status="ok")  # must be no-op

    phase_ends = [e for e in events if e["type"] == "delegation_phase_end"]
    assert len(phase_ends) == 0


def test_phase_events_after_close_log_warning(caplog):
    agent = _make_agent(event_sink=lambda _e: None)
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_end("success")
    with caplog.at_level(logging.WARNING, logger="core.engine.supervisor_agent"):
        agent.emit_lifecycle_phase_start("loop")
        agent.emit_lifecycle_phase_end("loop")
    assert any("already closed" in rec.message for rec in caplog.records)


# ── begin_delegation resets the closed flag ────────────────────────────────


def test_begin_delegation_resets_lifecycle_closed():
    """A registry cache hit (same agent, next delegation) opens a fresh envelope."""
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_end("success")
    assert agent._lifecycle_closed is True

    # Next delegation on the same agent instance:
    agent.begin_delegation(
        delegation_id="d-closure-2",
        executor_fn=lambda _t, _c, _r=False: _result(),
        event_sink=events.append,
        spec_path="tasks/step-02.md",
    )
    assert agent._lifecycle_closed is False
    # And a new envelope can be opened:
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_end("success")
    end_events = [e for e in events if e["type"] == "delegation_lifecycle_end"]
    assert len(end_events) == 2


def test_begin_delegation_resets_even_when_lifecycle_started_preserved():
    """When the caller pre-populated lifecycle context, the closed flag still resets."""
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()  # sets _lifecycle_started = True
    agent.emit_lifecycle_end("success")
    assert agent._lifecycle_closed is True

    # Simulate the server's early-creation path: set context before begin_delegation
    agent.set_lifecycle_context(project_key="pk")
    agent.begin_delegation(
        delegation_id="d-closure-3",
        executor_fn=lambda _t, _c, _r=False: _result(),
        event_sink=events.append,
        spec_path="tasks/step-03.md",
    )
    assert agent._lifecycle_closed is False


# ── full envelope: one start, one end, no stray phase events ──────────────


def test_full_envelope_emits_exactly_one_end():
    """Simulates the ISS-008 scenario: early-close + fall-through to postloop.
    With the P13-008 guard, the stray postloop phase events and second
    lifecycle_end are silently dropped (no-op + warning), preserving the
    single-envelope-per-delegation invariant.
    """
    events: list[dict] = []
    agent = _make_agent(event_sink=events.append)
    agent.set_lifecycle_context(project_key="pk")
    agent.emit_lifecycle_start()
    agent.emit_lifecycle_phase_start("preloop")
    agent.emit_lifecycle_phase_end("preloop", status="blocked", detail="clarity_check")
    agent.emit_lifecycle_end("needs_input")  # early close (correct)

    # Simulate the bug: server falls through to postloop block
    agent.emit_lifecycle_phase_end("loop", status="ok")  # stray — must be no-op
    agent.emit_lifecycle_phase_start("postloop")          # stray — must be no-op
    agent.emit_lifecycle_phase_end("postloop", status="ok")  # stray — no-op
    agent.emit_lifecycle_end("error")                     # stray second close — no-op

    end_events = [e for e in events if e["type"] == "delegation_lifecycle_end"]
    phase_starts = [e for e in events if e["type"] == "delegation_phase_start"]
    phase_ends = [e for e in events if e["type"] == "delegation_phase_end"]

    assert len(end_events) == 1
    assert end_events[0]["outcome"] == "needs_input"
    assert len(phase_starts) == 1
    assert phase_starts[0]["phase"] == "preloop"
    assert len(phase_ends) == 1
    assert phase_ends[0]["phase"] == "preloop"
