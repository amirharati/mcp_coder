from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import (
    SupervisorAgent,
    SupervisorAgentResult,
    SupervisorTurnContext,
    SupervisorTurnDecision,
)
from core.state.supervisor_state import SupervisorState
from server.mcp_server import _SUPERVISOR_REGISTRY, _handle_resume


def _ok_result() -> ExecutionResult:
    return ExecutionResult(success=True, output="ok", files_changed=["main.py"])


def _state(*, turn_index: int) -> SupervisorState:
    return SupervisorState.create(
        spec_path="tasks/auth-01.md",
        context_ref="deleg-reset",
        plan="## Plan\n- Continue",
        decision_log=[],
        completed_turn_artifacts=[],
        turn_index=turn_index,
        questions=["Continue?"],
    )


def test_executor_fn_receives_reset_false_on_normal_first_turn(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY", raising=False)
    calls: list[tuple[int, str | None, bool]] = []

    def executor(turn: int, correction: str | None, reset_session: bool) -> ExecutionResult:
        calls.append((turn, correction, reset_session))
        return _ok_result()

    agent = SupervisorAgent(
        delegation_id="deleg-1",
        workspace_path=str(tmp_path),
        executor_fn=executor,
        max_turns=1,
    )
    result = agent.run()

    assert result.outcome == "success"
    assert calls == [(1, None, False)]


def test_resumed_first_turn_signals_reset_true(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY", raising=False)
    calls: list[tuple[int, str | None, bool]] = []
    events: list[dict] = []

    def executor(turn: int, correction: str | None, reset_session: bool) -> ExecutionResult:
        calls.append((turn, correction, reset_session))
        return _ok_result()

    agent = SupervisorAgent.resume(
        _state(turn_index=0),
        "Please continue.",
        workspace_path=str(tmp_path),
        executor_fn=executor,
        event_sink=events.append,
    )
    result = agent.run()

    assert result.outcome == "success"
    assert calls[0][0] == 1
    assert calls[0][2] is True


def test_resumed_reset_flag_cleared_after_first_turn(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY", raising=False)
    reset_by_turn: list[tuple[int, bool]] = []

    def executor(turn: int, correction: str | None, reset_session: bool) -> ExecutionResult:
        reset_by_turn.append((turn, reset_session))
        return _ok_result()

    def decider(ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        if ctx.turns_remaining > 0:
            return SupervisorTurnDecision(action="rerun_aider", reason="one more pass")
        return SupervisorTurnDecision(action="done", reason="finished")

    agent = SupervisorAgent.resume(
        _state(turn_index=1),
        "",
        workspace_path=str(tmp_path),
        executor_fn=executor,
    )
    agent._max_turns = 3
    agent._decision_fn = decider
    result = agent.run()

    assert result.turns_completed == 3
    assert reset_by_turn == [(2, True), (3, False)]


def test_interval_reset_every_n(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY", "2")
    reset_by_turn: dict[int, bool] = {}

    def executor(turn: int, correction: str | None, reset_session: bool) -> ExecutionResult:
        reset_by_turn[turn] = reset_session
        return _ok_result()

    def decider(ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        if ctx.turns_remaining > 0:
            return SupervisorTurnDecision(action="rerun_aider", reason="continue")
        return SupervisorTurnDecision(action="done", reason="stop")

    agent = SupervisorAgent(
        delegation_id="deleg-interval",
        workspace_path=str(tmp_path),
        executor_fn=executor,
        decision_fn=decider,
        max_turns=4,
    )
    result = agent.run()

    assert result.outcome == "success"
    assert reset_by_turn == {1: False, 2: False, 3: True, 4: False}


def test_supervisor_session_reset_event_emitted(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY", raising=False)
    events: list[dict] = []

    agent = SupervisorAgent.resume(
        _state(turn_index=0),
        "continue",
        workspace_path=str(tmp_path),
        executor_fn=lambda _turn, _correction, _reset: _ok_result(),
        event_sink=events.append,
    )
    agent.run()

    reset_events = [event for event in events if event.get("type") == "supervisor_session_reset"]
    assert len(reset_events) == 1
    assert reset_events[0]["turn_index"] == 1
    assert reset_events[0]["reason"] == "resumed_first_turn"


def test_resume_executor_fn_drops_coder_only_when_hinted(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    _SUPERVISOR_REGISTRY.clear()

    def run_resume_once(*, reset_session: bool) -> tuple[int, int, dict]:
        state = _state(turn_index=0)
        engine_run = Mock(return_value=_ok_result())
        fake_engine = SimpleNamespace(run=engine_run)
        record = {
            "backend": "aider",
            "mcp_request": {"effective_target_files": ["main.py"]},
            "context": {"prompt_full": "Base prompt"},
            "model": "test-model",
        }

        def fake_resume(*_args, **kwargs):
            executor_fn = kwargs["executor_fn"]

            class _FakeAgent:
                def run(self) -> SupervisorAgentResult:
                    exec_result = executor_fn(1, None, reset_session)
                    return SupervisorAgentResult(
                        outcome="success",
                        turns_completed=1,
                        final_action="done",
                        end_reason="completed",
                        executor_result=exec_result,
                        decisions=[],
                        loop_id="resume-loop",
                    )

            return _FakeAgent()

        with patch("server.mcp_server.obs.default_workspace_path", return_value=str(tmp_path)), patch(
            "server.mcp_server._find_delegation_record_for_resume",
            return_value=record,
        ), patch("server.mcp_server.get_engine", return_value=fake_engine), patch(
            "core.engine.supervisor_agent.SupervisorAgent.resume",
            side_effect=fake_resume,
        ), patch(
            "core.session.executor_cache.drop_coder"
        ) as drop_mock:
            payload = json.loads(
                _handle_resume(
                    state=state,
                    answer="continue",
                    task="Continue task",
                    ctx=None,
                    mcp_session_id="mcp-session-1",
                )
            )
            return drop_mock.call_count, engine_run.call_count, payload

    drop_calls_true, run_calls_true, payload_true = run_resume_once(reset_session=True)
    drop_calls_false, run_calls_false, payload_false = run_resume_once(reset_session=False)

    assert drop_calls_true == 1
    assert drop_calls_false == 0
    assert run_calls_true == 1
    assert run_calls_false == 1
    assert payload_true["success"] is True
    assert payload_false["success"] is True
