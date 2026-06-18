"""Tests for P9-013 and P9-015: enrich layer (trace events + pipeline stages)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.cli.delegation_view_enrich import (
    _aggregate_tokens,
    _annotate_pairs,
    _build_trace_events,
    _build_view_events,
    _decompose_prompt,
    _extract_request_params,
    enrich_delegation_record,
)


# ── helpers ─────────────────────────────────────────────────────────────────


def _make_proxy(step: int, call: int, model: str = "claude") -> dict:
    return {
        "type": "proxy_llm_call",
        "delegation_id": "d1",
        "step_index": step,
        "call_index": call,
        "model": model,
        "wire_latency_ms": 100,
        "status_code": 200,
        "request_received_at": "2026-01-01T00:00:00Z",
        "response_received_at": "2026-01-01T00:00:00.1Z",
    }


def _make_backend(step: int, call: int, model: str = "claude", usage: dict | None = None) -> dict:
    record: dict = {
        "type": "backend_llm_call",
        "delegation_id": "d1",
        "step_index": step,
        "call_index": call,
        "model": model,
        "call_type": "aider",
        "duration_ms": 200,
    }
    if usage:
        record["usage"] = usage
    return record


def _make_llm_call(role: str = "planner", tokens: dict | None = None) -> dict:
    record: dict = {
        "type": "llm_call",
        "delegation_id": "d1",
        "role": role,
        "model": "gpt-4",
        "call_index": 0,
        "duration_ms": 150,
    }
    if tokens:
        record["tokens"] = tokens
    return record


def _make_compile_event(stage: str = "builder_input") -> dict:
    return {
        "type": "compile_event",
        "delegation_id": "d1",
        "stage": stage,
        "verbosity": "standard",
    }


def _make_tool_call(tool: str = "file_write") -> dict:
    return {
        "type": "tool_call",
        "delegation_id": "d1",
        "step_index": 0,
        "tool": tool,
    }


def _write_trace(tmp_path: Path, delegation_id: str, lines: list[dict]) -> tuple[Path, str]:
    session_dir = tmp_path / "session"
    traces = session_dir / "traces"
    traces.mkdir(parents=True)
    trace_path = traces / f"{delegation_id}.jsonl"
    trace_path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )
    return session_dir, f"traces/{delegation_id}.jsonl"


# ── tests ────────────────────────────────────────────────────────────────────


def test_build_trace_events_all_types():
    """Trace with all 5 event types → all appear in events with correct _seq numbering."""
    lines = [
        _make_proxy(0, 0),
        _make_backend(0, 0),
        _make_llm_call(),
        _make_compile_event(),
        _make_tool_call(),
    ]
    events = _build_trace_events(lines)
    assert len(events) == 5
    types = [ev["type"] for ev in events]
    assert "proxy_llm_call" in types
    assert "backend_llm_call" in types
    assert "llm_call" in types
    assert "compile_event" in types
    assert "tool_call" in types
    # _seq must be 1-based and in order
    assert [ev["_seq"] for ev in events] == [1, 2, 3, 4, 5]


def test_build_trace_events_empty():
    """Empty trace → events: [], token_summary all None."""
    events = _build_trace_events([])
    assert events == []
    token_summary = _aggregate_tokens(events)
    assert token_summary == {"input": None, "output": None, "thinking": None}


def test_annotate_pairs_matched():
    """Proxy + backend with same step/call index → both get _pair_status='matched'."""
    proxy = dict(_make_proxy(1, 2), _pair_status=None, _pair_call_key=None, _seq=1)
    backend = dict(_make_backend(1, 2), _pair_status=None, _pair_call_key=None, _seq=2)
    events = [proxy, backend]
    paired_calls = [
        {"step_index": 1, "call_index": 2, "status": "matched"},
    ]
    _annotate_pairs(events, paired_calls)
    assert proxy["_pair_status"] == "matched"
    assert backend["_pair_status"] == "matched"
    assert proxy["_pair_call_key"] == "1:2"
    assert backend["_pair_call_key"] == "1:2"


def test_annotate_pairs_proxy_only():
    """Proxy with no matching backend → _pair_status='proxy_only'."""
    proxy = dict(_make_proxy(0, 0), _pair_status=None, _pair_call_key=None, _seq=1)
    events = [proxy]
    paired_calls = [
        {"step_index": 0, "call_index": 0, "status": "proxy_only"},
    ]
    _annotate_pairs(events, paired_calls)
    assert proxy["_pair_status"] == "proxy_only"
    assert proxy["_pair_call_key"] == "0:0"


def test_annotate_pairs_backend_only():
    """Backend with no matching proxy → _pair_status='backend_only'."""
    backend = dict(_make_backend(2, 3), _pair_status=None, _pair_call_key=None, _seq=1)
    events = [backend]
    paired_calls = [
        {"step_index": 2, "call_index": 3, "status": "backend_only"},
    ]
    _annotate_pairs(events, paired_calls)
    assert backend["_pair_status"] == "backend_only"
    assert backend["_pair_call_key"] == "2:3"


def test_annotate_pairs_non_llm_untouched():
    """compile_event and tool_call events are not annotated (remain _pair_status=None)."""
    compile_ev = dict(_make_compile_event(), _pair_status=None, _pair_call_key=None, _seq=1)
    tool_ev = dict(_make_tool_call(), _pair_status=None, _pair_call_key=None, _seq=2)
    events = [compile_ev, tool_ev]
    paired_calls = [{"step_index": 0, "call_index": 0, "status": "matched"}]
    _annotate_pairs(events, paired_calls)
    assert compile_ev["_pair_status"] is None
    assert tool_ev["_pair_status"] is None
    assert compile_ev["_pair_call_key"] is None
    assert tool_ev["_pair_call_key"] is None


def test_aggregate_tokens_sums_correctly():
    """3 backend_llm_call events with known usage → correct totals."""
    events = [
        dict(_make_backend(0, 0, usage={"input": 100, "output": 50}), _seq=1),
        dict(_make_backend(0, 1, usage={"input": 200, "output": 80, "total": 280}), _seq=2),
        dict(_make_backend(1, 0, usage={"input": 150, "output": 60}), _seq=3),
    ]
    summary = _aggregate_tokens(events)
    assert summary["input"] == 450
    assert summary["output"] == 190
    assert summary["thinking"] is None


def test_aggregate_tokens_handles_none():
    """Events with null/missing usage fields → None fields are not counted."""
    events = [
        # backend with partial usage
        dict(_make_backend(0, 0, usage={"input": 100, "output": None}), _seq=1),
        # backend with no usage at all
        dict(_make_backend(0, 1), _seq=2),
        # llm_call with tokens
        dict(_make_llm_call(tokens={"input": 50, "output": 20}), _seq=3),
    ]
    summary = _aggregate_tokens(events)
    assert summary["input"] == 150   # 100 + 50
    assert summary["output"] == 20   # only from llm_call (backend output was None)
    assert summary["thinking"] is None


def test_enrich_record_trace_shape(tmp_path):
    """enrich_delegation_record returns dict with trace.events list and trace.token_summary."""
    delegation_id = "shape-test"
    lines = [
        _make_proxy(0, 0),
        _make_backend(0, 0, usage={"input": 300, "output": 100}),
        _make_llm_call(tokens={"input": 200, "output": 80}),
    ]
    session_dir, trace_ref = _write_trace(tmp_path, delegation_id, lines)
    record = {
        "delegation_id": delegation_id,
        "session_dir": str(session_dir),
        "trace_ref": trace_ref,
    }
    enriched = enrich_delegation_record(record)
    trace = enriched["trace"]

    assert "events" in trace
    assert isinstance(trace["events"], list)
    assert len(trace["events"]) == 3
    assert trace["found"] is True

    assert "token_summary" in trace
    ts = trace["token_summary"]
    assert ts["input"] == 500   # 300 + 200
    assert ts["output"] == 180  # 100 + 80
    assert ts["thinking"] is None

    # Old llm_calls key must be gone
    assert "llm_calls" not in trace


def test_enrich_record_no_trace(tmp_path):
    """Delegation with no trace file → trace.found=False, trace.events=[]."""
    record = {
        "delegation_id": "no-trace",
        "session_dir": str(tmp_path / "empty_session"),
        "trace_ref": "traces/no-trace.jsonl",
    }
    enriched = enrich_delegation_record(record)
    trace = enriched["trace"]
    assert trace["found"] is False
    assert trace["events"] == []
    assert trace["token_summary"] == {"input": None, "output": None, "thinking": None}

# ── _build_view_events ────────────────────────────────────────────────────────


def _simple_record(task: str = "Do the thing") -> dict:
    return {
        "delegation_id": "d1",
        "mcp_request": {"task": task},
        "response_to_cursor": {"output_preview": "done", "success": True},
    }


def test_view_events_always_has_host_bookends():
    """Empty trace → still returns host→mcp and mcp→host synthetic events."""
    events = _build_view_events(_simple_record(), [])
    names = [e["name"] for e in events]
    assert names[0] == "host→mcp"
    assert names[-1] == "mcp→host"


def test_view_events_seq_is_monotonic():
    """seq field increases by 1 for every emitted event."""
    trace = [
        _make_proxy(0, 0),
        _make_backend(0, 0, usage={"input": 100, "output": 40}),
    ]
    events = _build_view_events(_simple_record(), trace)
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(len(events)))


def test_view_events_trace_header_skipped():
    """trace_header lines are not emitted as rows."""
    trace = [
        {"type": "trace_header", "delegation_id": "d1"},
        _make_proxy(0, 0),
        _make_backend(0, 0),
    ]
    events = _build_view_events(_simple_record(), trace)
    names = [e["name"] for e in events]
    assert "trace_header" not in names
    assert not any("header" in n for n in names)


def test_view_events_compile_stages_mapped():
    """compile_event stages map to canonical display names.
    final_executor_prompt becomes mcp→executor at its log timestamp.
    """
    trace = [
        {"type": "compile_event", "stage": "validation_input",  "delegation_id": "d1"},
        {"type": "compile_event", "stage": "validation_output", "delegation_id": "d1"},
        {"type": "compile_event", "stage": "architect_input",   "delegation_id": "d1"},
        {"type": "compile_event", "stage": "architect_output",  "delegation_id": "d1"},
        {"type": "compile_event", "stage": "builder_input",     "delegation_id": "d1"},
        {"type": "compile_event", "stage": "builder_output",    "delegation_id": "d1"},
        {"type": "compile_event", "stage": "final_executor_prompt", "delegation_id": "d1"},
    ]
    events = _build_view_events(_simple_record(), trace)
    names = [e["name"] for e in events]
    assert "mcp.spec_validation" in names
    assert "mcp.architect" in names
    assert "mcp.context_builder" in names
    # mcp→executor at final_executor_prompt timestamp
    assert "mcp→executor" in names
    # final_executor_prompt data is folded into mcp→executor — no separate row
    assert "final_executor_prompt" not in names
    assert "compile_event" not in names


def test_view_events_mcp_executor_at_handoff_timestamp():
    """mcp→executor appears at final_executor_prompt timestamp, not injected early."""
    trace = [
        {"type": "compile_event", "stage": "mechanical_brief", "delegation_id": "d1",
         "timestamp": "2026-01-01T10:00:01", "body": "brief"},
        {"type": "compile_event", "stage": "final_executor_prompt", "delegation_id": "d1",
         "timestamp": "2026-01-01T10:00:02", "body": "final prompt"},
        {"type": "proxy_llm_call", "step_index": 1, "call_index": 1,
         "model": "claude", "delegation_id": "d1", "request_received_at": "2026-01-01T10:00:05"},
        {"type": "backend_llm_call", "step_index": 1, "call_index": 1,
         "model": "claude", "delegation_id": "d1", "timestamp": "2026-01-01T10:00:10",
         "usage": {"input": 100, "output": 50}},
    ]
    events = _build_view_events(_simple_record(), trace)
    names = [e["name"] for e in events]
    brief_idx = names.index("mcp.brief")
    exec_idx = names.index("mcp→executor")
    llm_idx = names.index("executor→llm")
    assert brief_idx < exec_idx < llm_idx
    mcp_exec = next(e for e in events if e["name"] == "mcp→executor")
    assert mcp_exec["timestamp"] == "2026-01-01T10:00:02"
    assert mcp_exec["is_virtual"] is True


def test_view_events_mcp_executor_repositioned_when_logged_late():
    """When final_executor_prompt is logged after executor LLM, viewer moves it before."""
    trace = [
        {"type": "compile_event", "stage": "builder_output", "delegation_id": "d1",
         "timestamp": "2026-01-01T10:00:01"},
        {"type": "proxy_llm_call", "step_index": 1, "call_index": 1,
         "model": "claude", "delegation_id": "d1",
         "request_received_at": "2026-01-01T10:00:05", "raw_request": "{}"},
        {"type": "backend_llm_call", "step_index": 1, "call_index": 1,
         "model": "claude", "delegation_id": "d1", "timestamp": "2026-01-01T10:00:06",
         "usage": {"input": 100, "output": 50}},
        {"type": "compile_event", "stage": "final_executor_prompt", "delegation_id": "d1",
         "timestamp": "2026-01-01T10:00:10", "body": "final prompt", "brief": "final"},
    ]
    events = _build_view_events(_simple_record(), trace)
    names = [e["name"] for e in events]
    exec_idx = names.index("mcp→executor")
    llm_idx = names.index("executor→llm")
    assert exec_idx < llm_idx
    mcp_exec = next(e for e in events if e["name"] == "mcp→executor")
    assert mcp_exec["detail"].get("logged_after_executor") is True
    assert mcp_exec["timestamp"] == "2026-01-01T10:00:10"


def test_view_events_mechanical_brief_emitted():
    """mechanical_brief compile_event maps to mcp.brief row."""
    trace = [
        {"type": "compile_event", "stage": "mechanical_brief", "delegation_id": "d1",
         "timestamp": "2026-01-01T10:00:01", "body": "brief body", "brief": "brief"},
    ]
    events = _build_view_events(_simple_record(), trace)
    names = [e["name"] for e in events]
    assert "mcp.brief" in names


def test_view_events_executor_step_divider():
    """action event → executor.step{N} divider row."""
    trace = [
        {"type": "action", "delegation_id": "d1", "step_index": 0, "kind": "scope_expansion_check"},
    ]
    events = _build_view_events(_simple_record(), trace)
    dividers = [e for e in events if e["is_divider"]]
    assert len(dividers) == 1
    assert dividers[0]["name"] == "executor.step{0}"
    assert dividers[0]["detail"]["kind"] == "scope_expansion_check"


def test_view_events_step_divider_deduplicated():
    """Multiple action events for the same step_index → only one divider row."""
    trace = [
        {"type": "action", "delegation_id": "d1", "step_index": 0, "kind": "scope_expansion_check"},
        {"type": "action", "delegation_id": "d1", "step_index": 0, "kind": "auto_confirm"},
    ]
    events = _build_view_events(_simple_record(), trace)
    dividers = [e for e in events if e["is_divider"]]
    assert len(dividers) == 1


def test_view_events_executor_llm_pair_directions():
    """proxy → executor→llm with direction →; backend → llm→executor with direction ←."""
    trace = [
        _make_proxy(0, 1),
        _make_backend(0, 1, usage={"input": 200, "output": 80}),
    ]
    events = _build_view_events(_simple_record(), trace)
    send_ev = next(e for e in events if e["name"] == "executor→llm")
    recv_ev = next(e for e in events if e["name"] == "llm→executor")
    assert send_ev["direction"] == "→"
    assert recv_ev["direction"] == "←"
    assert send_ev["scope"] == "executor"
    assert recv_ev["scope"] == "executor"


def test_view_events_proxy_carries_backend_data():
    """executor→llm detail includes tokens_in from the matched backend record."""
    backend = _make_backend(0, 0, usage={"input": 300, "output": 100})
    trace = [_make_proxy(0, 0), backend]
    events = _build_view_events(_simple_record(), trace)
    send_ev = next(e for e in events if e["name"] == "executor→llm")
    # prompt_body was replaced by structured decomposition; tokens_in is the key check
    assert send_ev["detail"]["tokens_in"] == 300
    # prompt_format is always present (unknown when no raw_request JSON)
    assert "prompt_format" in send_ev["detail"]


def test_view_events_recv_carries_proxy_data():
    """llm→executor detail includes proxy status_code when a pair match exists."""
    proxy = _make_proxy(0, 0)
    proxy["status_code"] = 200
    proxy["raw_response"] = '{"choices": []}'
    trace = [proxy, _make_backend(0, 0)]
    events = _build_view_events(_simple_record(), trace)
    recv_ev = next(e for e in events if e["name"] == "llm→executor")
    assert recv_ev["detail"]["status_code"] == 200
    assert recv_ev["detail"]["raw_response"] == '{"choices": []}'


def test_view_events_file_write_emitted():
    """tool_call tool=file_write → executor.file_write row."""
    trace = [
        {"type": "tool_call", "delegation_id": "d1", "step_index": 0,
         "tool": "file_write", "path": "src/foo.py", "bytes_written": 512},
    ]
    events = _build_view_events(_simple_record(), trace)
    fw = next((e for e in events if e["name"] == "executor.file_write"), None)
    assert fw is not None
    assert fw["direction"] == "·"
    assert "src/foo.py" in fw["summary"]
    assert fw["detail"]["bytes_written"] == 512


def test_view_events_shell_exec_emitted():
    """tool_call tool=shell_exec → executor.shell row."""
    trace = [
        {"type": "tool_call", "delegation_id": "d1", "step_index": 0,
         "tool": "shell_exec", "command": "pytest -q", "exit_code": 0},
    ]
    events = _build_view_events(_simple_record(), trace)
    sh = next((e for e in events if e["name"] == "executor.shell"), None)
    assert sh is not None
    assert sh["detail"]["exit_code"] == 0
    assert "pytest" in sh["summary"]


def test_view_events_folded_llm_roles_not_emitted():
    """llm_call roles spec_validation, architect_pass, context_builder, executor → not emitted."""
    trace = [
        _make_llm_call(role="spec_validation"),
        _make_llm_call(role="architect_pass"),
        _make_llm_call(role="context_builder"),
        _make_llm_call(role="executor"),
    ]
    events = _build_view_events(_simple_record(), trace)
    names = [e["name"] for e in events]
    for folded in ("mcp.spec_validation_call", "mcp.architect_pass", "mcp.context_builder_call", "mcp.executor"):
        assert folded not in names


def test_view_events_workspace_summarizer_emitted():
    """llm_call role=workspace_summarizer → mcp→index row (post-delegate housekeeping)."""
    trace = [
        {
            **_make_llm_call(role="workspace_summarizer", tokens={"input": 5000, "output": 200}),
            "prompt_body": "Describe what this source file does.\nFile path: tab/cli.py\n\nSource:\n...",
        },
    ]
    events = _build_view_events(_simple_record(), trace)
    idx = next((e for e in events if e["name"] == "mcp→index"), None)
    assert idx is not None
    assert idx["detail"]["index_path"] == "tab/cli.py"
    assert idx["detail"]["housekeeping"] is True
    post = next((e for e in events if e["name"] == "mcp→post"), None)
    assert post is not None
    assert post["detail"]["index_count"] == 1


def test_view_events_executor_to_mcp_virtual():
    """When executor events exist → executor→mcp virtual row is emitted."""
    trace = [
        {"type": "action", "delegation_id": "d1", "step_index": 0, "kind": "auto_confirm"},
        _make_proxy(0, 0),
        _make_backend(0, 0),
    ]
    record = {**_simple_record(), "files_changed": ["a.py", "b.py"]}
    events = _build_view_events(record, trace)
    exec_mcp = next((e for e in events if e["name"] == "executor→mcp"), None)
    assert exec_mcp is not None
    assert exec_mcp["is_virtual"] is True
    assert "2 file(s) changed" in exec_mcp["summary"]


def test_view_events_no_executor_no_virtual_close():
    """No executor events → no executor→mcp row."""
    trace = [
        {"type": "compile_event", "stage": "validation_input", "delegation_id": "d1"},
    ]
    events = _build_view_events(_simple_record(), trace)
    names = [e["name"] for e in events]
    assert "executor→mcp" not in names


# ── _decompose_prompt ────────────────────────────────────────────────────────


def test_decompose_prompt_empty():
    result = _decompose_prompt("")
    assert result["prompt_format"] == "unknown"


def test_decompose_prompt_invalid_json():
    result = _decompose_prompt("not json at all")
    assert result["prompt_format"] == "unknown"


def test_decompose_prompt_openai_basic():
    req = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Describe the sky."},
        ],
    }
    result = _decompose_prompt(json.dumps(req))
    assert result["prompt_format"] == "openai"
    assert result["system_prompt"] == "You are a helpful assistant."
    assert result["system_chars"] == len("You are a helpful assistant.")
    assert result["task"] == "Describe the sky."
    assert result["task_chars"] == len("Describe the sky.")
    assert result["context_turns"] == 0
    assert result["context_chars"] == 0
    assert result["context"] == ""
    assert result["total_messages"] == 2


def test_decompose_prompt_openai_with_context():
    req = {
        "messages": [
            {"role": "system", "content": "System here."},
            {"role": "user",      "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user",      "content": "Second question"},
            {"role": "assistant", "content": "Second answer"},
            {"role": "user",      "content": "The actual task"},
        ],
    }
    result = _decompose_prompt(json.dumps(req))
    assert result["prompt_format"] == "openai"
    assert result["task"] == "The actual task"
    # 2 assistant replies = 2 context turns
    assert result["context_turns"] == 2
    assert "[user]\nFirst question" in result["context"]
    assert "[assistant]\nSecond answer" in result["context"]
    assert "The actual task" not in result["context"]
    assert result["total_messages"] == 6


def test_decompose_prompt_anthropic_detected():
    req = {
        "model": "claude-3",
        "system": "You are Claude.",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    result = _decompose_prompt(json.dumps(req))
    assert result["prompt_format"] == "anthropic"
    # Not fully decomposed yet — only the format flag
    assert result["system_prompt"] == ""


def test_decompose_prompt_gemini_detected():
    req = {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
    result = _decompose_prompt(json.dumps(req))
    assert result["prompt_format"] == "gemini"


def test_decompose_prompt_list_content_blocks():
    """OpenAI content as list of {type, text} blocks."""
    req = {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": "Sys block"}]},
            {"role": "user",   "content": [{"type": "text", "text": "User block"}]},
        ]
    }
    result = _decompose_prompt(json.dumps(req))
    assert result["prompt_format"] == "openai"
    assert result["system_prompt"] == "Sys block"
    assert result["task"] == "User block"


# ── executor→llm detail includes decomposed prompt ───────────────────────────


def test_view_events_executor_llm_detail_has_prompt_decomp():
    """executor→llm ViewEvent detail includes prompt_format and decomposed fields."""
    raw_req = json.dumps({
        "messages": [
            {"role": "system",    "content": "Do stuff"},
            {"role": "user",      "content": "Previous msg"},
            {"role": "assistant", "content": "Previous reply"},
            {"role": "user",      "content": "Actual task here"},
        ]
    })
    proxy = {**_make_proxy(0, 0), "raw_request": raw_req}
    backend = _make_backend(0, 0)
    trace = [proxy, backend]
    events = _build_view_events(_simple_record(), trace)
    send = next(e for e in events if e["name"] == "executor→llm")
    d = send["detail"]
    assert d["prompt_format"] == "openai"
    assert d["system_prompt"] == "Do stuff"
    assert d["task"] == "Actual task here"
    assert d["context_turns"] == 1
    assert "[user]\nPrevious msg" in d["context"]
    assert "[assistant]\nPrevious reply" in d["context"]
    assert d["total_messages"] == 4


# ── request params + policy_applied on executor→llm ──────────────────────────


def test_extract_request_params_openai():
    req = {
        "model": "claude-sonnet",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.2,
        "max_tokens": 4096,
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "write_file"}},
        ],
    }
    params = _extract_request_params(json.dumps(req))
    assert "messages" not in params
    assert "model" not in params
    assert params["temperature"] == 0.2
    assert params["max_tokens"] == 4096
    assert params["stream"] is True
    assert "read_file" in params["tools"]
    assert params["stream_options"] == '{"include_usage":true}'


def test_view_events_executor_llm_request_params_and_policy():
    raw_req = json.dumps({
        "model": "claude",
        "messages": [{"role": "user", "content": "task"}],
        "temperature": 0.1,
        "stream": True,
    })
    policy = {
        "role": "executor",
        "thinking_budget": 5000,
        "sources": {"thinking_budget": "env"},
    }
    proxy = {**_make_proxy(0, 0), "raw_request": raw_req, "attribution_source": "contextvar"}
    backend = {
        **_make_backend(0, 0),
        "policy_applied": policy,
    }
    trace = [proxy, backend]
    events = _build_view_events(_simple_record(), trace)
    send = next(e for e in events if e["name"] == "executor→llm")
    d = send["detail"]
    assert d["request_params"]["temperature"] == 0.1
    assert d["request_params"]["stream"] is True
    assert d["policy_applied"] == policy
    assert d["attribution_source"] == "contextvar"
    assert d["status_code"] == 200


# ── executor→mcp aggregate stats ─────────────────────────────────────────────


def test_view_events_executor_mcp_has_aggregate_tokens():
    """executor→mcp virtual event detail includes llm_calls and total token counts."""
    proxy0 = {**_make_proxy(0, 0), "raw_request": "{}"}
    backend0 = {**_make_backend(0, 0), "usage": {"input": 1000, "output": 200}}
    trace = [proxy0, backend0]
    record = {**_simple_record(), "files_changed": ["x.py"]}
    events = _build_view_events(record, trace)
    exec_mcp = next(e for e in events if e["name"] == "executor→mcp")
    d = exec_mcp["detail"]
    assert d["llm_calls"] == 1
    assert d["total_tokens_out"] == 200


def test_view_events_enrich_returns_view_events(tmp_path):
    """enrich_delegation_record now includes view_events key."""
    delegation_id = "ve-test"
    trace = [_make_proxy(0, 0), _make_backend(0, 0)]
    session_dir, trace_ref = _write_trace(tmp_path, delegation_id, trace)
    record = {
        "delegation_id": delegation_id,
        "session_dir": str(session_dir),
        "trace_ref": trace_ref,
        "mcp_request": {"task": "hello"},
        "response_to_cursor": {"output_preview": "done"},
    }
    enriched = enrich_delegation_record(record)
    assert "view_events" in enriched
    ve = enriched["view_events"]
    assert isinstance(ve, list)
    assert len(ve) >= 2  # at minimum host→mcp and mcp→host
    assert ve[0]["name"] == "host→mcp"
    assert any(e["name"] == "mcp→host" for e in ve)
