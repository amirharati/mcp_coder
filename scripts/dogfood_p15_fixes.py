"""Quick auto-dogfood for P15-ISS-010 and P15-ISS-011 fixes.

Verifies the three fixes end-to-end without a full MCP delegation:
1. P15-ISS-010: host-driven retry loop contract (can_rerun + correction_note + finish).
2. P15-ISS-011: clarity parser strips leaked <tool_call> text.
3. B009: delegation_timeout_seconds default is 600.

Run: .venv/bin/python scripts/dogfood_p15_fixes.py
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

# Ensure repo root on path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Disable LLM-decide so the deterministic _policy_decide path is used.
os.environ.setdefault("MCP_CODER_SUPERVISOR_LLM_DECIDE", "0")

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import (
    SupervisorAgent,
    SupervisorTurnContext,
    SupervisorTurnDecision,
)
from core.engine.clarity_resolution import run_clarity_resolution
from core.config.aider_runtime import delegation_timeout_seconds

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def _result(success=True, *, files=None, error=None, error_class=None):
    return ExecutionResult(
        success=success,
        output="worker output tail",
        files_changed=list(files or (["a.py"] if success else [])),
        model="test/model",
        error=error,
        error_class=error_class,
    )


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        check.failed += 1
check.failed = 0


# ─── Fix 1: P15-ISS-010 — host-driven retry loop ────────────────────────────
print("\n=== Fix 1: P15-ISS-010 — host-driven retry loop ===")


def test_host_driven_retry():
    """Simulate the mcp_server.py host-driven loop: rerun_aider on turn 1
    should retry, not escalate immediately."""

    def decider(ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        if (ctx.checks or {}).get("outcome") == "issues" and ctx.turns_remaining > 0:
            return SupervisorTurnDecision(action="rerun_aider", reason="reviewer issues")
        return SupervisorTurnDecision(action="done", reason="clean")

    events: list[dict] = []
    agent = SupervisorAgent(
        delegation_id="d-dogfood",
        workspace_path="/tmp/ws",
        executor_fn=lambda t, c: _result(success=True),
        decision_fn=decider,
        max_turns=3,
        event_sink=events.append,
    )
    agent.begin_delegation(
        delegation_id="d-dogfood",
        executor_fn=lambda t, c: _result(success=True),
        decision_fn=decider,
        max_turns=3,
    )
    agent.begin()

    # Turn 1: reviewer found issues → rerun_aider.
    agent.begin_turn()
    dec1 = agent.complete_turn(_result(success=True), {"outcome": "issues", "note": "fix bug"})
    check("turn 1 decision is rerun_aider", dec1.action == "rerun_aider")
    check("can_rerun() is True (turns remain)", agent.can_rerun() is True)

    # Retry: correction note + new turn.
    correction = agent.correction_note({"outcome": "issues", "note": "fix bug"})
    check("correction note contains reviewer issue", "fix bug" in correction)
    agent.begin_turn()

    # Turn 2: reviewer says lgtm → done.
    dec2 = agent.complete_turn(_result(success=True), {"outcome": "lgtm", "note": ""})
    check("turn 2 decision is done", dec2.action == "done")

    res = agent.finish()
    check("final outcome is success (not escalated)", res.outcome == "success")
    check("final action is done (not escalate_host)", res.final_action == "done")
    check("end_reason is completed (not max_turns_reached)", res.end_reason == "completed")
    check("turns_completed is 2", res.turns_completed == 2)
    check(
        "decisions are [rerun_aider, done]",
        [d.action for d in res.decisions] == ["rerun_aider", "done"],
    )


test_host_driven_retry()


def test_host_driven_max_turns_exhausted():
    """When rerun_aider is decided but can_rerun() is False, finish() must escalate."""
    def always_rerun(ctx):
        return SupervisorTurnDecision(action="rerun_aider", reason="never satisfied")

    agent = SupervisorAgent(
        delegation_id="d-dogfood2",
        workspace_path="/tmp/ws",
        executor_fn=lambda t, c: _result(success=True),
        decision_fn=always_rerun,
        max_turns=1,
        event_sink=lambda _e: None,
    )
    agent.begin_delegation(
        delegation_id="d-dogfood2",
        executor_fn=lambda t, c: _result(success=True),
        decision_fn=always_rerun,
        max_turns=1,
    )
    agent.begin()
    agent.begin_turn()
    dec = agent.complete_turn(_result(success=True), {"outcome": "issues", "note": "still bad"})
    check("rerun_aider decided", dec.action == "rerun_aider")
    check("can_rerun() is False (no turns left)", agent.can_rerun() is False)
    res = agent.finish()
    check("outcome is escalated", res.outcome == "escalated")
    check("end_reason is max_turns_reached", res.end_reason == "max_turns_reached")


test_host_driven_max_turns_exhausted()


# ─── Fix 2: P15-ISS-011 — clarity parser strips <tool_call> text ────────────
print("\n=== Fix 2: P15-ISS-011 — clarity parser strips <tool_call> text ===")


def test_clarity_strips_tool_call_answers():
    """GLM-5.2-style output with <tool_call> text + ## Answers should parse."""
    from core.engine.supervisor_tool_runner import SupervisorToolRunnerResult

    raw = (
        '<tool_call>read_file(path="content/products/claude-downloader.md")</tool_call>\n'
        "## Answers\n"
        "1. Use YAML frontmatter for products.\n"
        "2. Place files under content/ root.\n"
    )

    def _run_with_metrics(system_prompt, messages):
        return SupervisorToolRunnerResult(text=raw)

    fake_runner = SimpleNamespace(run_with_metrics=_run_with_metrics)
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["What format?", "Where?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    check("resolved is True", result.resolved is True)
    check(
        "answers parsed correctly",
        result.answers == ["Use YAML frontmatter for products.", "Place files under content/ root."],
        str(result.answers),
    )


test_clarity_strips_tool_call_answers()


def test_clarity_strips_tool_call_escalate():
    """GLM-5.2-style output with <tool_call> text + ## Escalate should parse."""
    from core.engine.supervisor_tool_runner import SupervisorToolRunnerResult

    raw = (
        "<tool_call>get_project_state()</tool_call>\n"
        "<tool_call>get_delegation_history()</tool_call>\n"
        "## Escalate\n"
        "Spec doesn't define the content directory structure.\n"
    )

    def _run_with_metrics(system_prompt, messages):
        return SupervisorToolRunnerResult(text=raw)

    fake_runner = SimpleNamespace(run_with_metrics=_run_with_metrics)
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Where?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    check("resolved is False (escalate)", result.resolved is False)
    check(
        "escalate_reason contains spec message",
        "Spec doesn't define" in (result.escalate_reason or ""),
        str(result.escalate_reason),
    )


test_clarity_strips_tool_call_escalate()


# ─── Fix 3: B009 — delegation timeout default raised ────────────────────────
print("\n=== Fix 3: B009 — delegation timeout default raised to 600s ===")

# Save and clear env to test the default.
_saved = os.environ.pop("MCP_CODER_DELEGATION_TIMEOUT_S", None)
try:
    default_timeout = delegation_timeout_seconds()
    check("default timeout is 600.0s", default_timeout == 600.0, str(default_timeout))
    check("default timeout > 300s (old .env value)", default_timeout > 300.0)
finally:
    if _saved is not None:
        os.environ["MCP_CODER_DELEGATION_TIMEOUT_S"] = _saved

# Verify .env override still works.
os.environ["MCP_CODER_DELEGATION_TIMEOUT_S"] = "900"
check("env override to 900s works", delegation_timeout_seconds() == 900.0)
os.environ["MCP_CODER_DELEGATION_TIMEOUT_S"] = _saved or "600"


# ─── Summary ────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
if check.failed == 0:
    print(f"\033[32mAll dogfood checks passed.\033[0m")
    sys.exit(0)
else:
    print(f"\033[31m{check.failed} check(s) failed.\033[0m")
    sys.exit(1)
