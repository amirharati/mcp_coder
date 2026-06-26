"""P14-ISS-010: silent-swallow sites must log a warning + bump a counter.

Three sites previously had bare ``except Exception: pass`` that could hide
real bugs (the P14-ISS-008 pattern). The fix keeps the swallow (observability
must never break completions) but adds ``logger.warning(..., exc_info=True)``
and increments a module-level counter via ``bump_supervisor_swallow_count``.

Sites:
1. supervisor.py::_emit_llm_call_event — the P14-ISS-008 site itself
2. supervisor_agent.py::_llm_decide — graceful degradation fallback
3. supervisor_agent.py reviewer swallow — checks=None on reviewer failure
"""

from __future__ import annotations

import logging

import pytest

from core.engine._swallow_counts import (
    get_supervisor_swallow_counts,
    reset_supervisor_swallow_counts,
)


@pytest.fixture(autouse=True)
def _reset_counts():
    reset_supervisor_swallow_counts()
    yield
    reset_supervisor_swallow_counts()


def _build_supervisor():
    from core.engine.supervisor import DelegationSupervisor

    return DelegationSupervisor(
        workspace_path="/tmp/test",
        delegation_id="d-swallow-1",
        spec_contract=None,
        architect_plan=None,
        output_tail_provider=lambda: "",
        project_state_summary=None,
        target_files={"files_edit": [], "files_read": []},
    )


def _build_agent():
    from core.engine.supervisor_agent import (
        SupervisorAgent,
        SupervisorTurnContext,
        SupervisorTurnDecision,
    )
    from core.engine.base import ExecutionResult

    def _executor_fn(turn_index, correction_note, reset_session):
        return ExecutionResult(success=True, output="ok")

    return SupervisorAgent(
        delegation_id="d-swallow-agent",
        workspace_path="/tmp/test",
        executor_fn=_executor_fn,
        max_turns=3,
    )


# ── Site 1: supervisor._emit_llm_call_event ────────────────────────────────


def test_emit_llm_call_event_warns_and_counts_on_failure(caplog):
    """P14-ISS-008 site: a swallowed exception in _emit_llm_call_event must
    now log a warning + bump the counter; the swallow still hides the error."""
    from core.observability.context import (
        bind_delegation_trace_scope,
        delegation_context,
    )

    sup = _build_supervisor()
    from types import SimpleNamespace

    decision = SimpleNamespace(
        model="m", duration_ms=10, tokens=None, decision="APPROVE", risk_tier="low"
    )

    # Force build_trace_record to raise by monkeypatching the import target.
    import core.observability.trace as trace_mod

    original = trace_mod.build_trace_record

    def _boom(*a, **kw):
        raise RuntimeError("boom-emit-llm")

    trace_mod.build_trace_record = _boom
    try:
        with delegation_context("d-swallow-1"):
            bind_delegation_trace_scope(
                workspace="/tmp/test",
                session_dir="/tmp/test/session",
            )
            with caplog.at_level(logging.WARNING, logger="core.engine.supervisor"):
                sup._emit_llm_call_event(
                    question="q?",
                    prompt="p",
                    response="r",
                    decision=decision,
                )
    finally:
        trace_mod.build_trace_record = original

    # Swallow preserved: no exception propagated.
    counts = get_supervisor_swallow_counts()
    assert counts.get("_emit_llm_call_event") == 1

    # Warning was logged with the site name.
    site_warnings = [r for r in caplog.records if "_emit_llm_call_event" in r.message]
    assert site_warnings, "expected a warning mentioning _emit_llm_call_event"
    assert site_warnings[0].exc_info is not None, "exc_info should be attached"


# ── Site 2: supervisor_agent._llm_decide fallback ──────────────────────────


def test_llm_decide_warns_and_counts_on_failure(caplog, monkeypatch):
    """_llm_decide swallows any exception and falls back to _policy_decide;
    the warning now makes that visible + bumps the counter."""
    from core.engine.supervisor_agent import SupervisorAgent, SupervisorTurnContext
    from core.engine.base import ExecutionResult

    agent = _build_agent()
    # Force the inner LLM call path to raise by making apply_provider_env boom.
    import core.config.providers as providers_mod

    def _boom(*a, **kw):
        raise RuntimeError("boom-llm-decide")

    monkeypatch.setattr(providers_mod, "apply_provider_env", _boom)

    ctx = SupervisorTurnContext(
        turn_index=1,
        max_turns=3,
        turns_remaining=2,
        result=ExecutionResult(success=True, output="ok"),
        checks=None,
        prior_decisions=[],
    )

    with caplog.at_level(logging.WARNING, logger="core.engine.supervisor_agent"):
        decision = agent._llm_decide(ctx)

    # Fallback still returns a policy decision (graceful degradation).
    assert decision.action in ("done", "rerun_aider", "escalate_host")

    counts = get_supervisor_swallow_counts()
    assert counts.get("_llm_decide") == 1

    warnings = [r for r in caplog.records if "_llm_decide" in r.message]
    assert warnings, "expected a warning mentioning _llm_decide"
    assert warnings[0].exc_info is not None


# ── Site 3: reviewer swallow ───────────────────────────────────────────────


def test_reviewer_swallow_warns_and_counts(caplog, monkeypatch):
    """A failing reviewer must log a warning + bump the counter; checks stays None."""
    from core.engine.supervisor_agent import SupervisorAgent
    from core.engine.base import ExecutionResult

    def _failing_reviewer(turn_index, result):
        raise RuntimeError("boom-reviewer")

    agent = _build_agent()
    agent._reviewer_fn = _failing_reviewer

    # Drive one turn through the host-driven API so the reviewer runs.
    agent.begin()
    turn = agent.begin_turn()
    with caplog.at_level(logging.WARNING, logger="core.engine.supervisor_agent"):
        decision = agent.complete_turn(
            ExecutionResult(success=True, output="ok"), checks=None
        )
    # The reviewer was called via run() path, not complete_turn() — drive through run()
    # instead. complete_turn takes checks directly. Test the run() path.

    # Reset and exercise the run() path where reviewer_fn is actually invoked.
    reset_supervisor_swallow_counts()
    agent2 = _build_agent()
    agent2._reviewer_fn = _failing_reviewer

    with caplog.at_level(logging.WARNING, logger="core.engine.supervisor_agent"):
        agent2.run()

    counts = get_supervisor_swallow_counts()
    assert counts.get("reviewer_call") == 1, counts

    warnings = [r for r in caplog.records if "reviewer call failed" in r.message]
    assert warnings, "expected a warning mentioning reviewer call failed"
    assert warnings[0].exc_info is not None
