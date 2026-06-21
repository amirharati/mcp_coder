"""P12-003 — unit tests for SupervisorToolRunner + Phase 12 built-in tools."""

from __future__ import annotations

import json

import pytest

from core.engine.supervisor_tool_runner import (
    _TOOL_RESULT_BUDGET,
    SupervisorToolRunner,
    SupervisorToolRunnerResult,
    build_phase12_tool_runner,
)
from core.observability.gateway import (
    GatewayCompletion,
    reset_llm_gateway,
    set_llm_gateway,
)
from core.state.project_state import ProjectState


class _ScriptedGateway:
    """Gateway stub that returns a scripted sequence of GatewayCompletions."""

    def __init__(self, completions: list[GatewayCompletion]) -> None:
        self._completions = list(completions)
        self.calls: list[dict] = []

    def complete(self, *, model, messages, role, max_tokens=4096, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        if self._completions:
            return self._completions.pop(0)
        return GatewayCompletion(text="", model=model, tokens={}, duration_ms=0)


def _text(text: str, tokens: dict | None = None) -> GatewayCompletion:
    return GatewayCompletion(
        text=text, model="test/model", tokens=tokens or {}, duration_ms=1
    )


def _tool_call(
    call_id: str, name: str, arguments: str, tokens: dict | None = None
) -> GatewayCompletion:
    return GatewayCompletion(
        text="",
        model="test/model",
        tokens=tokens or {},
        duration_ms=1,
        tool_calls=[{"id": call_id, "name": name, "arguments": arguments}],
    )


@pytest.fixture(autouse=True)
def _reset_gateway():
    reset_llm_gateway()
    yield
    reset_llm_gateway()


# ── 1 ────────────────────────────────────────────────────────────────────────


def test_runner_no_tools_returns_text():
    set_llm_gateway(_ScriptedGateway([_text("## Action: DONE")]))
    runner = SupervisorToolRunner(model="test/model", workspace_path="/tmp/ws")
    result = runner.run(system_prompt="sys", messages=[{"role": "user", "content": "hi"}])
    assert result == "## Action: DONE"


# ── 2 ────────────────────────────────────────────────────────────────────────


def test_runner_tool_called_and_appended():
    gw = _ScriptedGateway(
        [_tool_call("c1", "echo", '{"value": "x"}'), _text("final answer")]
    )
    set_llm_gateway(gw)
    called: list[dict] = []

    def echo(**kwargs):
        called.append(kwargs)
        return "echoed:" + kwargs.get("value", "")

    runner = SupervisorToolRunner(model="test/model", workspace_path="/tmp/ws")
    runner.register_tool("echo", "echo back", {"type": "object", "properties": {}}, echo)
    result = runner.run(system_prompt="sys", messages=[{"role": "user", "content": "go"}])

    assert result == "final answer"
    assert called == [{"value": "x"}]
    # The second call's messages should contain the appended tool result.
    second_call_messages = gw.calls[1]["messages"]
    assert any(
        m.get("role") == "tool" and m.get("content") == "echoed:x"
        for m in second_call_messages
    )


# ── 3 ────────────────────────────────────────────────────────────────────────


def test_runner_max_rounds_fallback():
    # Always return a tool call; after max_tool_rounds, a final no-tools call returns text.
    gw = _ScriptedGateway(
        [
            _tool_call("c1", "noop", "{}"),
            _tool_call("c2", "noop", "{}"),
            _text("fallback final"),
        ]
    )
    set_llm_gateway(gw)
    runner = SupervisorToolRunner(
        model="test/model", workspace_path="/tmp/ws", max_tool_rounds=2
    )
    runner.register_tool("noop", "noop", {"type": "object", "properties": {}}, lambda: "ok")
    result = runner.run(system_prompt="sys", messages=[{"role": "user", "content": "go"}])

    assert result == "fallback final"
    # Final call must pass tools=None.
    assert gw.calls[-1]["tools"] is None


# ── 4 ────────────────────────────────────────────────────────────────────────


def test_tool_result_truncated_to_budget():
    runner = SupervisorToolRunner(model="test/model", workspace_path="/tmp/ws")
    runner.register_tool(
        "big", "big", {"type": "object", "properties": {}}, lambda: "y" * 10000
    )
    result = runner._execute_tool({"id": "c1", "name": "big", "arguments": "{}"})
    assert len(result) == _TOOL_RESULT_BUDGET


# ── 5 ────────────────────────────────────────────────────────────────────────


def test_unknown_tool_returns_error():
    runner = SupervisorToolRunner(model="test/model", workspace_path="/tmp/ws")
    result = runner._execute_tool({"id": "c1", "name": "ghost", "arguments": "{}"})
    assert "[tool_error] unknown tool" in result


# ── 6 ────────────────────────────────────────────────────────────────────────


def test_read_file_traversal_rejected(tmp_path):
    runner = build_phase12_tool_runner(
        workspace_path=str(tmp_path),
        project_key="default",
        project_state=ProjectState(project_key="default"),
        event_sink=None,
        model="test/model",
    )
    result = runner._execute_tool(
        {"id": "c1", "name": "read_file", "arguments": json.dumps({"path": "../secret"})}
    )
    assert "[tool_error] path traversal" in result


# ── 7 ────────────────────────────────────────────────────────────────────────


def test_get_project_state_returns_compact_json(tmp_path):
    state = ProjectState(project_key="default")
    state.add_decision("d1", "del-1")
    state.add_decision("d2", "del-2")
    state.add_decision("d3", "del-3")
    runner = build_phase12_tool_runner(
        workspace_path=str(tmp_path),
        project_key="default",
        project_state=state,
        event_sink=None,
        model="test/model",
    )
    result = runner._execute_tool(
        {"id": "c1", "name": "get_project_state", "arguments": "{}"}
    )
    parsed = json.loads(result)
    assert "decisions" in parsed
    assert len(parsed["decisions"]) == 3


# ── 8 ────────────────────────────────────────────────────────────────────────


def test_supervisor_tool_call_event_emitted():
    gw = _ScriptedGateway([_tool_call("c1", "noop", "{}"), _text("done")])
    set_llm_gateway(gw)
    events: list[dict] = []
    runner = SupervisorToolRunner(
        model="test/model", workspace_path="/tmp/ws", event_sink=events.append
    )
    runner.register_tool("noop", "noop", {"type": "object", "properties": {}}, lambda: "ok")
    runner.run(system_prompt="sys", messages=[{"role": "user", "content": "go"}])

    tool_events = [e for e in events if e["type"] == "supervisor_tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["tool"] == "noop"
    assert tool_events[0]["result_chars"] == 2


# ── 9 (P12-ISS-004) ───────────────────────────────────────────────────────────


def test_run_with_metrics_aggregates_tokens_across_rounds():
    call1_tokens = {"input": 10, "output": 5, "total": 15}
    call2_tokens = {"input": 4, "output": 6, "total": 10}
    gw = _ScriptedGateway(
        [
            _tool_call("c1", "noop", "{}", tokens=call1_tokens),
            _text("final answer", tokens=call2_tokens),
        ]
    )
    set_llm_gateway(gw)
    runner = SupervisorToolRunner(model="test/model", workspace_path="/tmp/ws")
    runner.register_tool("noop", "noop", {"type": "object", "properties": {}}, lambda: "ok")

    result = runner.run_with_metrics(
        system_prompt="sys", messages=[{"role": "user", "content": "go"}]
    )

    assert isinstance(result, SupervisorToolRunnerResult)
    assert result.text == "final answer"
    assert result.llm_calls == 2
    assert result.tokens.get("input") == 14
    assert result.tokens.get("output") == 11
    assert result.tokens.get("total") == 25
    assert result.tokens.get("source") == "supervisor_tool_runner"


# ── 10 (P12-ISS-004) ──────────────────────────────────────────────────────────


def test_run_backcompat_returns_text_only():
    set_llm_gateway(_ScriptedGateway([_text("## Action: DONE")]))
    runner = SupervisorToolRunner(model="test/model", workspace_path="/tmp/ws")
    text_result = runner.run(
        system_prompt="sys", messages=[{"role": "user", "content": "hi"}]
    )
    # run() must equal run_with_metrics().text
    set_llm_gateway(_ScriptedGateway([_text("## Action: DONE")]))
    metrics_result = runner.run_with_metrics(
        system_prompt="sys", messages=[{"role": "user", "content": "hi"}]
    )
    assert isinstance(text_result, str)
    assert text_result == metrics_result.text
