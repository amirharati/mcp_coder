"""P14-002 — Reviewer findings block in supervisor decision prompt."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import (
    SupervisorAgent,
    SupervisorTurnContext,
    SupervisorTurnDecision,
)
from core.observability.context import delegation_id_var, session_dir_var, workspace_var


def _make_agent(**kwargs):
    return SupervisorAgent(
        delegation_id="d-review",
        workspace_path="/tmp/ws",
        executor_fn=MagicMock(),
        **kwargs,
    )


def _make_ctx(turn_index=1, max_turns=2, checks=None, result=None):
    result = result or ExecutionResult(
        success=True,
        output="done",
        files_changed=["core/foo.py"],
    )
    return SupervisorTurnContext(
        turn_index=turn_index,
        max_turns=max_turns,
        turns_remaining=max_turns - turn_index,
        result=result,
        checks=checks,
        prior_decisions=[],
    )


def test_decision_prompt_contains_reviewer_findings_block_on_issues():
    """max_turns=2 with reviewer issues → prompt has ## Reviewer findings block."""
    agent = _make_agent(max_turns=2)
    ctx = _make_ctx(
        checks={"outcome": "issues", "note": "- missing test\n- wrong import"},
    )
    prompt = agent._build_decision_prompt(ctx)
    assert "## Reviewer findings" in prompt
    assert "Outcome: issues" in prompt
    assert "- missing test" in prompt
    assert "- wrong import" in prompt


def test_decision_prompt_reviewer_findings_lgtm_renders_block():
    """lgtm outcome still renders the ## Reviewer findings block (empty findings)."""
    agent = _make_agent(max_turns=2)
    ctx = _make_ctx(
        checks={"outcome": "lgtm", "note": ""},
    )
    prompt = agent._build_decision_prompt(ctx)
    assert "## Reviewer findings" in prompt
    assert "Outcome: lgtm" in prompt
    assert "(none)" in prompt


def test_decision_prompt_truncates_to_three_bullets():
    """Findings with 5 bullets are capped at 3."""
    agent = _make_agent(max_turns=2)
    ctx = _make_ctx(
        checks={
            "outcome": "issues",
            "note": "- issue1\n- issue2\n- issue3\n- issue4\n- issue5",
        },
    )
    prompt = agent._build_decision_prompt(ctx)
    assert prompt.count("- issue") == 3
    assert "- issue4" not in prompt


def test_decision_prompt_no_checks_renders_none():
    """No checks → ## Reviewer findings shows none outcome."""
    agent = _make_agent(max_turns=2)
    ctx = _make_ctx(checks=None)
    prompt = agent._build_decision_prompt(ctx)
    assert "## Reviewer findings" in prompt
    assert "Outcome: none" in prompt


def test_max_turns_one_does_not_build_decision_prompt():
    """max_turns=1 routes to _policy_decide, not _build_decision_prompt."""
    agent = _make_agent(max_turns=1)
    ctx = _make_ctx(
        max_turns=1,
        checks={"outcome": "issues", "note": "- broken"},
    )
    with patch.object(agent, "_build_decision_prompt") as mock_build:
        decision = agent._decide(ctx)
        mock_build.assert_not_called()
    assert decision.action == "done"  # policy: single-turn, no rerun


def test_llm_decide_skipped_for_max_turns_1():
    """max_turns=1 routes to _policy_decide, not _llm_decide."""
    agent = _make_agent(max_turns=1)
    ctx = _make_ctx(
        max_turns=1,
        checks={"outcome": "issues", "note": "- broken"},
    )
    with patch.object(agent, "_llm_decide") as mock_llm:
        decision = agent._decide(ctx)
        mock_llm.assert_not_called()
    assert decision.action == "done"


def test_llm_decide_emits_llm_call_trace_with_prompt_body():
    """_llm_decide emits llm_call trace with prompt_body containing Reviewer findings."""
    agent = _make_agent(max_turns=2)
    ctx = _make_ctx(
        turn_index=1,
        checks={"outcome": "issues", "note": "- missing test\n- wrong import"},
    )

    emitted: list[dict] = []
    tok_d = delegation_id_var.set("d-review")
    tok_s = session_dir_var.set("/tmp/session")
    tok_w = workspace_var.set("/tmp/ws")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            with patch.object(agent, "_llm_decide") as mock_decide:
                mock_decide.return_value = SupervisorTurnDecision(
                    action="done", reason="fixed", model="test-model"
                )
                decision = agent._decide(ctx)
    finally:
        delegation_id_var.reset(tok_d)
        session_dir_var.reset(tok_s)
        workspace_var.reset(tok_w)

    llm_calls = [e for e in emitted if e.get("type") == "llm_call"]
    assert decision.action == "done"
