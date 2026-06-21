"""Proxy trace record builder (P9-003)."""

from __future__ import annotations

from core.config.observability import VERBOSITY_LEAN, VERBOSITY_STANDARD
from core.observability.trace import (
    TRACE_TYPE_PROXY_LLM_CALL,
    build_proxy_llm_call_record,
)


def test_build_proxy_llm_call_record_shape():
    rec = build_proxy_llm_call_record(
        delegation_id="d-1",
        role="planner_pass",
        step_index=2,
        call_index=3,
        model="openrouter/test/model",
        verbosity=VERBOSITY_STANDARD,
        request_received_at="2026-06-15T00:00:00.000Z",
        response_received_at="2026-06-15T00:00:01.000Z",
        wire_latency_ms=1000,
        status_code=200,
        raw_request='{"model":"openrouter/test/model"}',
        raw_response='{"choices":[{"message":{"content":"ok"}}]}',
        attribution_source="headers",
    )
    assert rec["type"] == TRACE_TYPE_PROXY_LLM_CALL
    assert rec["delegation_id"] == "d-1"
    assert rec["step_index"] == 2
    assert rec["call_index"] == 3
    assert rec["role"] == "planner_pass"
    assert rec["provider"] == "openrouter"
    assert rec["ok"] is True
    assert rec["raw_request"]
    assert rec["raw_response"]
    assert rec["attribution_source"] == "headers"


def test_build_proxy_llm_call_write_always_at_lean():
    rec = build_proxy_llm_call_record(
        delegation_id=None,
        step_index=None,
        call_index=None,
        model="openrouter/test/model",
        verbosity=VERBOSITY_LEAN,
        request_received_at="t0",
        response_received_at="t1",
        wire_latency_ms=5,
        status_code=200,
        raw_request="req",
        raw_response="resp",
        attribution_source="none",
    )
    assert rec["raw_request"] == "req"
    assert rec["raw_response"] == "resp"
    assert rec["delegation_id"] is None
    assert rec["attribution_source"] == "none"


def test_build_proxy_llm_call_extracts_usage_from_raw_response_when_tokens_missing():
    rec = build_proxy_llm_call_record(
        delegation_id="d-2",
        role="planner_pass",
        step_index=None,
        call_index=7,
        model="openrouter/test/model",
        verbosity=VERBOSITY_STANDARD,
        request_received_at="2026-06-15T00:00:00.000Z",
        response_received_at="2026-06-15T00:00:01.000Z",
        wire_latency_ms=1000,
        status_code=200,
        raw_request='{"model":"openrouter/test/model"}',
        raw_response=(
            '{"usage":{"prompt_tokens":120,"completion_tokens":30,'
            '"completion_tokens_details":{"reasoning_tokens":11},'
            '"prompt_tokens_details":{"cached_tokens":9}}}'
        ),
        attribution_source="headers",
    )
    assert rec["tokens"]["input"] == 120
    assert rec["tokens"]["output"] == 30
    assert rec["tokens"]["total"] == 150
    assert rec["tokens"]["reasoning_tokens"] == 11
    assert rec["tokens"]["cached_tokens"] == 9
    assert rec["thinking_tokens"] == 11
