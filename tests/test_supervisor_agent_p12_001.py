"""P12-001 — unit tests for the unified SupervisorAgent loop.

Covers:
- single-turn happy path (done after 1 run)
- rerun path (done after 2 runs, max_turns=3)
- max-turns-reached → escalate
- escalate_host on first turn
- decision log entries count matches turns
- canonical event lifecycle (exactly one loop_start / loop_end, no outer_loop)
- executor exception handling
- context_block shape
- max-turns config resolution
"""

from __future__ import annotations

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import (
    SupervisorAgent,
    SupervisorTurnContext,
    SupervisorTurnDecision,
    resolve_supervisor_max_turns,
)


def _result(success: bool = True, *, files=None, error=None, error_class=None) -> ExecutionResult:
    return ExecutionResult(
        success=success,
        output="worker output tail",
        files_changed=list(files or (["a.py"] if success else [])),
        model="test/model",
        error=error,
        error_class=error_class,
    )


def _agent(executor_fn, **kw):
    events: list[dict] = []
    agent = SupervisorAgent(
        delegation_id="d-1",
        workspace_path="/tmp/ws",
        executor_fn=executor_fn,
        event_sink=events.append,
        **kw,
    )
    return agent, events


# ── 1. single-turn happy path ────────────────────────────────────────────────


def test_single_turn_happy_path_done():
    calls: list[tuple[int, str | None]] = []

    def executor(turn, correction):
        calls.append((turn, correction))
        return _result(success=True)

    agent, events = _agent(executor, max_turns=1)
    res = agent.run()

    assert res.outcome == "success"
    assert res.turns_completed == 1
    assert res.final_action == "done"
    assert res.end_reason == "completed"
    assert len(res.decisions) == 1
    assert res.decisions[0].action == "done"
    assert calls == [(1, None)]


# ── 2. rerun path → done after 2 runs ────────────────────────────────────────


def test_rerun_then_done_two_runs():
    runs: list[int] = []

    def executor(turn, correction):
        runs.append(turn)
        # turn 2 receives a non-empty correction note
        if turn == 2:
            assert correction
        return _result(success=True)

    def reviewer(turn, result):
        return {"outcome": "issues" if turn == 1 else "lgtm", "note": "fix the bug"}

    def decider(ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        if (ctx.checks or {}).get("outcome") == "issues" and ctx.turns_remaining > 0:
            return SupervisorTurnDecision(action="rerun_aider", reason="reviewer issues")
        return SupervisorTurnDecision(action="done", reason="clean")

    agent, events = _agent(
        executor, reviewer_fn=reviewer, decision_fn=decider, max_turns=3
    )
    res = agent.run()

    assert runs == [1, 2]
    assert res.turns_completed == 2
    assert res.final_action == "done"
    assert [d.action for d in res.decisions] == ["rerun_aider", "done"]


# ── 3. max-turns-reached → escalate ──────────────────────────────────────────


def test_max_turns_reached_escalates():
    def executor(turn, correction):
        return _result(success=True)

    def always_rerun(ctx):
        return SupervisorTurnDecision(action="rerun_aider", reason="never satisfied")

    agent, events = _agent(executor, decision_fn=always_rerun, max_turns=2)
    res = agent.run()

    assert res.turns_completed == 2
    assert res.final_action == "escalate_host"
    assert res.end_reason == "max_turns_reached"
    assert res.outcome == "escalated"


# ── 4. escalate_host on first turn ───────────────────────────────────────────


def test_escalate_host_first_turn():
    def executor(turn, correction):
        return _result(success=False, error="needs human", error_class="needs_input")

    def decider(ctx):
        return SupervisorTurnDecision(action="escalate_host", reason="human judgement")

    agent, events = _agent(executor, decision_fn=decider, max_turns=3)
    res = agent.run()

    assert res.turns_completed == 1
    assert res.final_action == "escalate_host"
    assert res.outcome == "escalated"
    assert res.end_reason == "escalated"


# ── 5. decision log count matches turns ──────────────────────────────────────


def test_decision_log_count_matches_turns():
    def executor(turn, correction):
        return _result(success=True)

    def rerun_until_last(ctx):
        if ctx.turns_remaining > 0:
            return SupervisorTurnDecision(action="rerun_aider", reason="more")
        return SupervisorTurnDecision(action="done", reason="stop")

    agent, events = _agent(executor, decision_fn=rerun_until_last, max_turns=4)
    res = agent.run()

    assert res.turns_completed == len(res.decisions)
    assert res.turns_completed == 4


# ── 6. canonical lifecycle: exactly one loop_start / loop_end, no outer_loop ──


def test_canonical_event_lifecycle_single_turn():
    def executor(turn, correction):
        return _result(success=True)

    agent, events = _agent(executor, max_turns=1)
    agent.run()

    types = [e["type"] for e in events]
    assert types == [
        "supervisor_loop_start",
        "supervisor_turn_start",
        "supervisor_turn_end",
        "supervisor_decision",
        "supervisor_loop_end",
    ]
    assert types.count("supervisor_loop_start") == 1
    assert types.count("supervisor_loop_end") == 1
    assert not any(t.startswith("supervisor_outer_loop") for t in types)


def test_loop_start_and_end_payload_fields():
    def executor(turn, correction):
        return _result(success=True)

    agent, events = _agent(executor, max_turns=2)
    agent.run()

    start = next(e for e in events if e["type"] == "supervisor_loop_start")
    end = next(e for e in events if e["type"] == "supervisor_loop_end")
    assert start["max_turns"] == 2
    assert start["loop_id"] == "d-1:supervisor:1"
    assert end["turns_completed"] == 1
    assert end["final_action"] == "done"
    assert end["end_reason"] == "completed"


def test_turn_end_carries_worker_outcome_and_checks():
    def executor(turn, correction):
        return _result(success=True)

    def reviewer(turn, result):
        return {"outcome": "lgtm", "note": ""}

    agent, events = _agent(executor, reviewer_fn=reviewer, max_turns=1)
    agent.run()

    turn_end = next(e for e in events if e["type"] == "supervisor_turn_end")
    assert turn_end["worker_outcome"] == "success"
    assert turn_end["checks_result"] == {"outcome": "lgtm", "note": ""}


# ── 7. executor exception → error outcome, loop still closed ──────────────────


def test_executor_exception_closes_loop():
    def executor(turn, correction):
        raise RuntimeError("boom")

    agent, events = _agent(executor, max_turns=2)
    res = agent.run()

    assert res.outcome == "error"
    assert res.final_action == "escalate_host"
    assert res.end_reason.startswith("executor_exception")
    types = [e["type"] for e in events]
    assert types.count("supervisor_loop_start") == 1
    assert types.count("supervisor_loop_end") == 1


# ── 8. single-turn default policy: reviewer issues still ends (no rerun) ──────


def test_single_turn_policy_does_not_rerun_on_issues():
    def executor(turn, correction):
        return _result(success=True)

    def reviewer(turn, result):
        return {"outcome": "issues", "note": "minor nit"}

    # No decision_fn → default policy decider (max_turns=1 → done, never rerun).
    agent, events = _agent(executor, reviewer_fn=reviewer, max_turns=1)
    res = agent.run()

    assert res.turns_completed == 1
    assert res.final_action == "done"
    assert res.decisions[0].action == "done"


# ── 9. context_block shape ───────────────────────────────────────────────────


def test_context_block_shape():
    def executor(turn, correction):
        return _result(success=True)

    agent, events = _agent(executor, max_turns=1)
    res = agent.run()
    block = agent.context_block(res)
    assert set(block) == {"loop_id", "turns_completed", "final_action", "end_reason"}
    assert block["loop_id"] == "d-1:supervisor:1"
    assert block["turns_completed"] == 1
    assert block["final_action"] == "done"


# ── 10. max-turns config resolution ──────────────────────────────────────────


def test_resolve_max_turns_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_SUPERVISOR_MAX_TURNS", raising=False)
    assert resolve_supervisor_max_turns(tmp_path) == 1


def test_resolve_max_turns_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_SUPERVISOR_MAX_TURNS", "3")
    assert resolve_supervisor_max_turns(tmp_path) == 3


def test_resolve_max_turns_clamped(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_SUPERVISOR_MAX_TURNS", "99")
    assert resolve_supervisor_max_turns(tmp_path) == 5
    monkeypatch.setenv("MCP_CODER_SUPERVISOR_MAX_TURNS", "0")
    assert resolve_supervisor_max_turns(tmp_path) == 1


# ── 11. failed single run reports error outcome but done action ──────────────


# ── 12. host-driven (manual) API used by mcp_server ──────────────────────────


def test_manual_driver_single_turn():
    events: list[dict] = []
    agent = SupervisorAgent(
        delegation_id="d-2",
        workspace_path="/tmp/ws",
        executor_fn=lambda t, c: _result(True),  # unused in manual mode
        event_sink=events.append,
        max_turns=1,
    )
    agent.begin()
    turn = agent.begin_turn()
    assert turn == 1
    decision = agent.complete_turn(_result(success=True), {"outcome": "lgtm"})
    assert decision.action == "done"
    assert not agent.can_rerun()
    res = agent.finish()

    assert res.outcome == "success"
    assert res.turns_completed == 1
    assert res.final_action == "done"
    types = [e["type"] for e in events]
    assert types == [
        "supervisor_loop_start",
        "supervisor_turn_start",
        "supervisor_turn_end",
        "supervisor_decision",
        "supervisor_loop_end",
    ]


def test_manual_driver_rerun_then_done():
    events: list[dict] = []

    def decider(ctx):
        if (ctx.checks or {}).get("outcome") == "issues" and ctx.turns_remaining > 0:
            return SupervisorTurnDecision(action="rerun_aider", reason="issues")
        return SupervisorTurnDecision(action="done", reason="ok")

    agent = SupervisorAgent(
        delegation_id="d-3",
        workspace_path="/tmp/ws",
        executor_fn=lambda t, c: _result(True),
        decision_fn=decider,
        event_sink=events.append,
        max_turns=3,
    )
    agent.begin()
    turns_run = 0
    checks_by_turn = {1: {"outcome": "issues", "note": "x"}, 2: {"outcome": "lgtm"}}
    while True:
        t = agent.begin_turn()
        turns_run += 1
        decision = agent.complete_turn(_result(True), checks_by_turn.get(t))
        if decision.action != "rerun_aider" or not agent.can_rerun():
            break
    res = agent.finish()

    assert turns_run == 2
    assert res.turns_completed == 2
    assert res.final_action == "done"
    assert [d.action for d in res.decisions] == ["rerun_aider", "done"]


def test_failed_single_run_outcome_error():
    def executor(turn, correction):
        return _result(success=False, error="exec failed", error_class="executor_error")

    agent, events = _agent(executor, max_turns=1)
    res = agent.run()

    assert res.final_action == "done"
    assert res.outcome == "error"
    assert res.end_reason == "executor_error"
