"""P12-ISS-004 — token accounting for SupervisorToolRunner in agent and supervisor."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.engine.supervisor_tool_runner import SupervisorToolRunnerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _known_result(text: str, input_: int, output: int, total: int) -> SupervisorToolRunnerResult:
    return SupervisorToolRunnerResult(
        text=text,
        tokens={
            "input": input_,
            "output": output,
            "total": total,
            "source": "supervisor_tool_runner",
        },
        llm_duration_ms=50,
        llm_calls=2,
    )


# ---------------------------------------------------------------------------
# Test 1 — supervisor_agent._llm_decide() writes runner tokens to decision
# ---------------------------------------------------------------------------


def test_supervisor_agent_llm_decide_writes_runner_tokens(tmp_path):
    """_llm_decide() must set SupervisorTurnDecision.tokens from run_with_metrics result."""
    known_result = _known_result(
        "## Action: DONE\n## Reason\nall good", 20, 10, 30
    )

    from core.engine.supervisor_agent import SupervisorAgent, SupervisorTurnContext

    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._workspace_path = str(tmp_path)
    agent._spec_path = "tasks/foo.md"
    agent._supervisor_model = "test/model"
    agent._project_state = None
    agent._event_sink = None
    agent._decisions = []
    agent._plan = None  # needed by _build_decision_prompt

    result_obj = MagicMock()
    result_obj.outcome = "done"
    result_obj.files_changed = []
    result_obj.output = "done"

    ctx = SupervisorTurnContext(
        turn_index=1,
        max_turns=3,
        turns_remaining=2,
        result=result_obj,
        checks={},
        prior_decisions=[],
    )

    mock_runner = MagicMock()
    mock_runner.run_with_metrics.return_value = known_result

    # All of these are locally imported inside _llm_decide(), so we patch at source.
    with (
        patch("core.config.providers.apply_provider_env"),
        patch("core.config.models.provider_hint_for_model", return_value=None),
        patch(
            "core.config.role_models.resolve_role_model_name",
            return_value="test/model",
        ),
        patch(
            "core.engine.supervisor_tool_runner.build_phase12_tool_runner",
            return_value=mock_runner,
        ),
        patch(
            "core.state.project_key.ProjectKeyResolver.from_spec_path",
            return_value="default",
        ),
    ):
        decision = agent._llm_decide(ctx)

    assert decision.tokens.get("input") == 20
    assert decision.tokens.get("output") == 10
    assert decision.tokens.get("total") == 30
    assert decision.tokens.get("source") == "supervisor_tool_runner"


# ---------------------------------------------------------------------------
# Test 2 — DelegationSupervisor.evaluate() writes runner tokens to SupervisorDecision
# ---------------------------------------------------------------------------


def test_delegation_supervisor_evaluate_writes_tokens(tmp_path):
    """evaluate() must set SupervisorDecision.tokens from runner.run_with_metrics."""
    approve_text = "## Decision: APPROVE\n## Reason\nLooks fine."
    known_result = _known_result(approve_text, 15, 7, 22)

    from core.engine.supervisor import DelegationSupervisor

    sup = DelegationSupervisor(
        workspace_path=str(tmp_path),
        delegation_id="del-001",
        spec_contract="# Contract",
        architect_plan="# Plan",
        output_tail_provider=lambda: "tail",
    )

    mock_runner = MagicMock()
    mock_runner.run_with_metrics.return_value = known_result

    # apply_provider_env, provider_hint_for_model, resolve_role_model_name are
    # module-level imports in supervisor.py; build_phase12_tool_runner and
    # ProjectKeyResolver are locally imported inside evaluate().
    with (
        patch("core.engine.supervisor.apply_provider_env"),
        patch("core.engine.supervisor.provider_hint_for_model", return_value=None),
        patch(
            "core.engine.supervisor.resolve_role_model_name",
            return_value="test/model",
        ),
        patch(
            "core.engine.supervisor_tool_runner.build_phase12_tool_runner",
            return_value=mock_runner,
        ),
        patch(
            "core.state.project_key.ProjectKeyResolver.from_spec_path",
            return_value="default",
        ),
        patch(
            "core.state.project_state.ProjectState.load",
            return_value=MagicMock(
                decisions=[],
                open_risks=[],
                hot_areas=[],
                last_delegation=None,
                reviewer_findings_summary=[],
            ),
        ),
    ):
        sd = sup.evaluate(question="Can I write to db.py?", risk_tier="medium")

    assert sd.decision == "approve"
    assert sd.tokens.get("input") == 15
    assert sd.tokens.get("output") == 7
    assert sd.tokens.get("total") == 22
    assert sd.tokens.get("source") == "supervisor_tool_runner"


# ---------------------------------------------------------------------------
# Test 3 — DelegationSupervisor.usage_record accumulates tokens across calls
# ---------------------------------------------------------------------------


def test_delegation_supervisor_usage_record_accumulates_runner_tokens(tmp_path):
    """Running evaluate() twice should sum token counts in usage_record."""
    approve_text = "## Decision: APPROVE\n## Reason\nOK."

    call_tokens = [
        _known_result(approve_text, 10, 5, 15),
        _known_result(approve_text, 8, 4, 12),
    ]

    from core.engine.supervisor import DelegationSupervisor

    sup = DelegationSupervisor(
        workspace_path=str(tmp_path),
        delegation_id="del-001",
        spec_contract="# Contract",
        architect_plan="# Plan",
        output_tail_provider=lambda: "tail",
    )

    mock_runner = MagicMock()
    mock_runner.run_with_metrics.side_effect = call_tokens

    with (
        patch("core.engine.supervisor.apply_provider_env"),
        patch("core.engine.supervisor.provider_hint_for_model", return_value=None),
        patch(
            "core.engine.supervisor.resolve_role_model_name",
            return_value="test/model",
        ),
        patch(
            "core.engine.supervisor_tool_runner.build_phase12_tool_runner",
            return_value=mock_runner,
        ),
        patch(
            "core.state.project_key.ProjectKeyResolver.from_spec_path",
            return_value="default",
        ),
        patch(
            "core.state.project_state.ProjectState.load",
            return_value=MagicMock(
                decisions=[],
                open_risks=[],
                hot_areas=[],
                last_delegation=None,
                reviewer_findings_summary=[],
            ),
        ),
    ):
        sup.evaluate(question="First question?", risk_tier="low")
        sup.evaluate(question="Second question?", risk_tier="low")

    rec = sup.usage_record
    assert rec["input_tokens"] == 18    # 10 + 8
    assert rec["output_tokens"] == 9    # 5 + 4
    assert rec["total_tokens"] == 27    # 15 + 12
