"""Local LLM proxy capture + observability integration (P9-003)."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urllib_request

import pytest

from core.observability.context import bind_delegation_trace_scope, delegation_context
from core.observability import reset_observability, set_observability
from core.observability.local import LocalObservability
from core.observability.null import NullObservability
from core.observability.trace import TRACE_TYPE_PROXY_LLM_CALL
from core.proxy.local_proxy import LocalLlmProxy, reset_local_llm_proxy_for_tests
from core.proxy.routing import ProviderRoute


class _UpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b""
        if b'"stream": true' in body or b'"stream":true' in body:
            payload = (
                b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
                b"data: [DONE]\n\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        response = json.dumps(
            {"choices": [{"message": {"content": "upstream-ok"}}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


@pytest.fixture
def mock_upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture(autouse=True)
def _reset_proxy():
    reset_local_llm_proxy_for_tests()
    reset_observability()
    yield
    reset_local_llm_proxy_for_tests()
    reset_observability()


def _route_to_upstream(base_url: str) -> ProviderRoute:
    return ProviderRoute(
        prefix="openrouter/",
        base_url=base_url,
        api_key_env="OPENROUTER_API_KEY",
    )


def test_proxy_emits_proxy_llm_call_record(tmp_path, monkeypatch, mock_upstream):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        "core.proxy.local_proxy.resolve_route",
        lambda model: _route_to_upstream(mock_upstream),
    )

    proxy = LocalLlmProxy()
    proxy.start()

    session_dir = tmp_path / "session"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    delegation_id = "proxy-delegation-1"

    backend = LocalObservability()
    set_observability(backend)

    body = json.dumps(
        {"model": "openrouter/test/model", "messages": [{"role": "user", "content": "hi"}]}
    ).encode("utf-8")
    req = urllib_request.Request(
        f"{proxy.base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Mcp-Delegation-Id": delegation_id,
            "X-Mcp-Step-Index": "1",
            "X-Mcp-Call-Index": "2",
            "X-Mcp-Session-Dir": str(session_dir),
            "X-Mcp-Workspace": str(workspace),
        },
        method="POST",
    )

    with delegation_context(delegation_id):
        bind_delegation_trace_scope(workspace=str(workspace), session_dir=session_dir)
        urllib_request.urlopen(req, timeout=5).read()
    time.sleep(0.2)

    trace_path = session_dir / "traces" / f"{delegation_id}.jsonl"
    assert trace_path.is_file()
    lines = [json.loads(row) for row in trace_path.read_text().splitlines() if row.strip()]
    proxy_lines = [line for line in lines if line.get("type") == TRACE_TYPE_PROXY_LLM_CALL]
    assert len(proxy_lines) == 1
    event = proxy_lines[0]
    assert event["delegation_id"] == delegation_id
    assert event["step_index"] == 1
    assert event["call_index"] == 2
    assert event["raw_request"]
    assert event["raw_response"]
    assert "upstream-ok" in event["raw_response"]
    assert event["attribution_source"] == "headers"


def test_proxy_allows_null_attribution(tmp_path, monkeypatch, mock_upstream):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        "core.proxy.local_proxy.resolve_route",
        lambda model: _route_to_upstream(mock_upstream),
    )

    proxy = LocalLlmProxy()
    proxy.start()
    session_dir = tmp_path / "session"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    backend = LocalObservability()
    set_observability(backend)

    body = json.dumps({"model": "openrouter/test/model", "messages": []}).encode("utf-8")
    req = urllib_request.Request(
        f"{proxy.base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Mcp-Session-Dir": str(session_dir),
            "X-Mcp-Workspace": str(workspace),
        },
        method="POST",
    )

    bind_delegation_trace_scope(workspace=str(workspace), session_dir=session_dir)
    urllib_request.urlopen(req, timeout=5).read()
    time.sleep(0.2)

    trace_path = session_dir / "traces" / "_proxy_unattributed.jsonl"
    assert trace_path.is_file()
    lines = [json.loads(row) for row in trace_path.read_text().splitlines() if row.strip()]
    proxy_lines = [line for line in lines if line.get("type") == TRACE_TYPE_PROXY_LLM_CALL]
    assert len(proxy_lines) == 1
    event = proxy_lines[0]
    assert event["type"] == TRACE_TYPE_PROXY_LLM_CALL
    assert event["delegation_id"] is None
    assert event["attribution_source"] == "none"


def test_proxy_streaming_capture(tmp_path, monkeypatch, mock_upstream):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        "core.proxy.local_proxy.resolve_route",
        lambda model: _route_to_upstream(mock_upstream),
    )

    proxy = LocalLlmProxy()
    proxy.start()
    session_dir = tmp_path / "session"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    backend = LocalObservability()
    set_observability(backend)

    body = json.dumps(
        {
            "model": "openrouter/test/model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        f"{proxy.base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Mcp-Session-Dir": str(session_dir),
            "X-Mcp-Workspace": str(workspace),
        },
        method="POST",
    )

    urllib_request.urlopen(req, timeout=5).read()
    time.sleep(0.2)

    trace_path = session_dir / "traces" / "_proxy_unattributed.jsonl"
    lines = [json.loads(row) for row in trace_path.read_text().splitlines() if row.strip()]
    event = next(line for line in lines if line.get("type") == TRACE_TYPE_PROXY_LLM_CALL)
    assert event["type"] == TRACE_TYPE_PROXY_LLM_CALL
    assert "data:" in event["raw_response"]


def test_null_observability_record_proxy_noop():
    NullObservability().record_proxy_llm_call(
        delegation_id=None,
        model="m",
        request_received_at="t0",
        response_received_at="t1",
        wire_latency_ms=1,
        status_code=200,
        raw_request="r",
        raw_response="s",
    )
