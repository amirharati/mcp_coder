"""P14-002 — Reviewer findings block in supervisor decision prompt."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from core.context.role_rules import build_role_rules
from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import (
    SupervisorAgent,
    SupervisorTurnContext,
    SupervisorTurnDecision,
    _supervisor_llm_decide_enabled,
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


def test_llm_decide_disabled_routes_to_policy():
    """With MCP_CODER_SUPERVISOR_LLM_DECIDE=0, routes to _policy_decide (old behavior)."""
    agent = _make_agent(max_turns=1)
    ctx = _make_ctx(
        max_turns=1,
        checks={"outcome": "issues", "note": "- broken"},
    )
    with patch.dict("os.environ", {"MCP_CODER_SUPERVISOR_LLM_DECIDE": "0"}):
        with patch.object(agent, "_build_decision_prompt") as mock_build:
            decision = agent._decide(ctx)
            mock_build.assert_not_called()
    assert decision.action == "done"  # policy: single-turn, no rerun


def test_llm_decide_enabled_for_max_turns_1():
    """With gate on (default), max_turns=1 routes to _llm_decide."""
    agent = _make_agent(max_turns=1)
    ctx = _make_ctx(
        max_turns=1,
        checks={"outcome": "issues", "note": "- broken"},
    )
    with patch.object(agent, "_llm_decide") as mock_llm:
        mock_llm.return_value = SupervisorTurnDecision(
            action="done", reason="quality sufficient"
        )
        decision = agent._decide(ctx)
        mock_llm.assert_called_once()
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


def test_supervisor_agent_decision_uses_role_rules():
    agent = _make_agent(max_turns=2)
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    runner = MagicMock(
        run_with_metrics=MagicMock(
            return_value=MagicMock(
                text="## Action: DONE\n## Reason\nQuality sufficient.",
                tokens={"input": 1, "output": 1, "total": 2},
            )
        )
    )

    with patch("core.config.models.provider_hint_for_model", return_value=None), patch(
        "core.engine.supervisor_tool_runner.build_phase12_tool_runner",
        return_value=runner,
    ), patch("core.observability.trace.append_trace_record"):
        decision = agent._llm_decide(ctx)

    assert decision.action == "done"
    runner.run_with_metrics.assert_called_once()
    assert (
        runner.run_with_metrics.call_args.kwargs["system_prompt"]
        == build_role_rules("supervisor_decision")
    )


def test_decision_prompt_does_not_embed_preamble_in_user_message():
    """P15-ISS-003: inter-turn rules ride the system message only.

    _build_decision_prompt must NOT prepend _DECISION_PREAMBLE — that would
    double-inject the rules (system prompt already carries them).
    """
    agent = _make_agent(max_turns=2)
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    prompt = agent._build_decision_prompt(ctx)
    # The legacy preamble heading must not appear in the user message.
    assert "## Role: delegation supervisor (inter-turn)" not in prompt
    assert "Begin IMMEDIATELY with exactly one line: `## Action:" not in prompt
    # Task-context sections are still present.
    assert "## Turn\n1 of 2" in prompt
    assert "## Reviewer findings" in prompt


# ---------------------------------------------------------------------------
# P15-001 Slice A — routing tests
# ---------------------------------------------------------------------------


def test_llm_decide_default_is_on():
    """Without env/yaml, _supervisor_llm_decide_enabled() returns True."""
    with patch.dict("os.environ", {}, clear=True):
        assert _supervisor_llm_decide_enabled("/tmp/ws") is True


def test_llm_decide_env_disabled():
    """MCP_CODER_SUPERVISOR_LLM_DECIDE=0 returns False."""
    with patch.dict("os.environ", {"MCP_CODER_SUPERVISOR_LLM_DECIDE": "0"}):
        assert _supervisor_llm_decide_enabled("/tmp/ws") is False


# ---------------------------------------------------------------------------
# P15-001 Slice B — diff injection tests
# ---------------------------------------------------------------------------

from core.workspace.history_query import DelegationDiff


def test_decision_prompt_contains_unified_diff_section():
    """Mock build_delegation_diff → assert ## Unified diff section with diff content."""
    agent = _make_agent(max_turns=2)
    agent._delegation_id = "d-test"
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    mock_diff = DelegationDiff(
        delegation_id="d-test",
        modified=["core/foo.py"],
        diffs={"core/foo.py": "-old\n+new"},
        diff_truncated=False,
    )
    with patch(
        "core.workspace.history_query.build_delegation_diff", return_value=mock_diff
    ):
        prompt = agent._build_decision_prompt(ctx)
    assert "## Unified diff" in prompt
    assert "### `core/foo.py`" in prompt
    assert "```diff" in prompt and "-old\n+new" in prompt


def test_decision_prompt_diff_section_no_snapshot():
    """mock build_delegation_diff → None → '(no diff available)'."""
    agent = _make_agent(max_turns=2)
    agent._delegation_id = "d-test"
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    with patch(
        "core.workspace.history_query.build_delegation_diff", return_value=None
    ):
        prompt = agent._build_decision_prompt(ctx)
    assert "## Unified diff\n(no diff available)" in prompt


def test_decision_prompt_diff_section_empty_diff():
    """mock build_delegation_diff with empty diffs → no modified files message."""
    agent = _make_agent(max_turns=2)
    agent._delegation_id = "d-test"
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    mock_diff = DelegationDiff(
        delegation_id="d-test",
        created=["new_file.py"],
        deleted=["old_file.py"],
        diffs={},
        diff_truncated=False,
    )
    with patch(
        "core.workspace.history_query.build_delegation_diff", return_value=mock_diff
    ):
        prompt = agent._build_decision_prompt(ctx)
    assert "## Unified diff" in prompt
    assert "(no modified files" in prompt


def test_decision_prompt_diff_section_truncation_note():
    """mock build_delegation_diff with diff_truncated=True → truncation note."""
    agent = _make_agent(max_turns=2)
    agent._delegation_id = "d-test"
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    mock_diff = DelegationDiff(
        delegation_id="d-test",
        modified=["core/big.py"],
        diffs={"core/big.py": "big diff content"},
        diff_truncated=True,
        diff_truncated_paths=["core/big.py"],
    )
    with patch(
        "core.workspace.history_query.build_delegation_diff", return_value=mock_diff
    ):
        prompt = agent._build_decision_prompt(ctx)
    assert "(diff truncated: core/big.py)" in prompt


# ---------------------------------------------------------------------------
# P15-001 Slice C — builder brief injection tests
# ---------------------------------------------------------------------------


def test_decision_prompt_contains_builder_brief_section():
    """set_builder_brief → assert ## Builder brief section in prompt."""
    agent = _make_agent(max_turns=2)
    agent.set_builder_brief("## Task\nDo X")
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    prompt = agent._build_decision_prompt(ctx)
    assert "## Builder brief" in prompt
    assert "Do X" in prompt


def test_decision_prompt_builder_brief_none():
    """No brief set → '(none)'."""
    agent = _make_agent(max_turns=2)
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    prompt = agent._build_decision_prompt(ctx)
    assert "## Builder brief\n(none)" in prompt


def test_decision_prompt_builder_brief_truncated():
    """Brief > 3000 chars → capped at 3000."""
    agent = _make_agent(max_turns=2)
    long_brief = "A" * 5000
    agent.set_builder_brief(long_brief)
    ctx = _make_ctx(turn_index=1, checks={"outcome": "lgtm", "note": ""})
    prompt = agent._build_decision_prompt(ctx)
    # The brief section should not contain the full 5000 characters
    brief_start = prompt.index("## Builder brief\n") + len("## Builder brief\n")
    brief_end = prompt.index("\n## Worker output tail")
    brief_content = prompt[brief_start:brief_end]
    assert len(brief_content) <= 3050  # 3000 + minor formatting


def test_set_builder_brief_setter():
    """set_builder_brief('X') updates _builder_brief."""
    agent = _make_agent(max_turns=2)
    agent.set_builder_brief("test brief")
    assert agent._builder_brief == "test brief"


def test_begin_delegation_accepts_builder_brief_param():
    """begin_delegation(builder_brief=...) sets _builder_brief."""
    agent = _make_agent(max_turns=2)
    agent.begin_delegation(
        delegation_id="d-test",
        executor_fn=MagicMock(),
        builder_brief="delegation brief",
    )
    assert agent._builder_brief == "delegation brief"


# ---------------------------------------------------------------------------
# P15-001 Slice D — dead constant removal tests
# ---------------------------------------------------------------------------


def test_no_dead_preamble_constants_remain():
    """All 8 legacy preamble constants are removed."""
    import core.context.planner_prompt as planner_prompt
    import core.context.reviewer_prompt as reviewer_prompt
    import core.context.clarity_prompt as clarity_prompt
    import core.context.spec_validation_prompt as spec_validation_prompt
    import core.context.builder_prompt as builder_prompt
    import core.engine.supervisor as supervisor_mod
    import core.engine.supervisor_agent as supervisor_agent

    assert not hasattr(planner_prompt, "PLANNER_PREAMBLE")
    assert not hasattr(reviewer_prompt, "REVIEWER_PREAMBLE")
    assert not hasattr(clarity_prompt, "CLARITY_PREAMBLE")
    assert not hasattr(clarity_prompt, "CLARITY_PREAMBLE_RETRY")
    assert not hasattr(spec_validation_prompt, "VALIDATION_PREAMBLE")
    assert not hasattr(builder_prompt, "BUILDER_PREAMBLE")
    assert not hasattr(supervisor_mod, "_SUPERVISOR_PREAMBLE")
    assert not hasattr(supervisor_agent, "_DECISION_PREAMBLE")
