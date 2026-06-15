"""Local internal HTTP proxy for litellm → upstream capture (P9-003)."""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import error, request as urllib_request

from core.logging.delegation_log import utc_now_iso
from core.proxy.routing import (
    MCP_ATTRIBUTION_HEADERS_LOWER,
    RouteResolutionError,
    resolve_route,
    upstream_url,
)

_active_proxy: "LocalLlmProxy | None" = None
_PROXY_ENV_KEYS = (
    "OPENROUTER_API_BASE",
    "OPENAI_API_BASE",
    "ANTHROPIC_API_BASE",
)


def _parse_attribution(
    headers: dict[str, str],
) -> tuple[str | None, int | None, int | None, str | None, str | None, str]:
    lowered = {k.lower(): v for k, v in headers.items()}

    def _int_header(name: str) -> int | None:
        raw = lowered.get(name)
        if raw is None or not str(raw).strip().isdigit():
            return None
        return int(str(raw).strip())

    delegation_id = lowered.get("x-mcp-delegation-id")
    step_index = _int_header("x-mcp-step-index")
    call_index = _int_header("x-mcp-call-index")
    session_dir = lowered.get("x-mcp-session-dir")
    workspace = lowered.get("x-mcp-workspace")
    has_attribution_headers = any(
        lowered.get(name) is not None
        for name in (
            "x-mcp-delegation-id",
            "x-mcp-step-index",
            "x-mcp-call-index",
        )
    )
    attribution_source = "headers" if has_attribution_headers else "none"
    return delegation_id, step_index, call_index, session_dir, workspace, attribution_source


def _forward_headers(
    incoming: dict[str, str],
    route: ProviderRoute,
    api_key: str,
) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for key, value in incoming.items():
        lower = key.lower()
        if lower in MCP_ATTRIBUTION_HEADERS_LOWER:
            continue
        if lower in ("host", "content-length", "authorization", "x-api-key", "accept-encoding"):
            continue
        forwarded[key] = value

    forwarded["Accept-Encoding"] = "identity"

    if route.auth_prefix:
        forwarded[route.auth_header] = f"{route.auth_prefix}{api_key}"
    else:
        forwarded[route.auth_header] = api_key
    return forwarded


def _request_is_streaming(raw_body: str) -> bool:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return False
    return bool(payload.get("stream"))


def _emit_proxy_call(
    *,
    delegation_id: str | None,
    step_index: int | None,
    call_index: int | None,
    session_dir: str | None,
    workspace: str | None,
    model: str | None,
    request_received_at: str,
    response_received_at: str,
    wire_latency_ms: int,
    status_code: int,
    raw_request: str,
    raw_response: str,
    attribution_source: str,
) -> None:
    try:
        from core.observability import get_observability

        get_observability().record_proxy_llm_call(
            delegation_id=delegation_id,
            step_index=step_index,
            call_index=call_index,
            session_dir=session_dir,
            workspace=workspace,
            model=model,
            request_received_at=request_received_at,
            response_received_at=response_received_at,
            wire_latency_ms=wire_latency_ms,
            status_code=status_code,
            raw_request=raw_request,
            raw_response=raw_response,
            attribution_source=attribution_source,
        )
    except Exception:
        pass


class _ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        request_received_at = utc_now_iso()
        t0 = time.perf_counter()
        raw_request = ""
        raw_response = ""
        status_code = 500
        model: str | None = None
        delegation_id: str | None = None
        step_index: int | None = None
        call_index: int | None = None
        session_dir: str | None = None
        workspace: str | None = None
        attribution_source = "none"

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_bytes = self.rfile.read(length) if length > 0 else b""
            raw_request = raw_bytes.decode("utf-8", errors="replace")

            incoming_headers = {k: v for k, v in self.headers.items()}
            (
                delegation_id,
                step_index,
                call_index,
                session_dir,
                workspace,
                attribution_source,
            ) = _parse_attribution(incoming_headers)

            try:
                payload = json.loads(raw_request) if raw_request else {}
            except json.JSONDecodeError as exc:
                status_code, raw_response = self._json_error(400, f"invalid JSON body: {exc}")
                return

            model = payload.get("model") if isinstance(payload, dict) else None
            try:
                route = resolve_route(model)
            except RouteResolutionError as exc:
                status_code, raw_response = self._json_error(400, str(exc))
                return

            api_key = os.environ.get(route.api_key_env, "").strip()
            upstream = upstream_url(route, self.path)
            forward_headers = _forward_headers(incoming_headers, route, api_key)
            req = urllib_request.Request(
                upstream,
                data=raw_bytes,
                headers=forward_headers,
                method="POST",
            )

            streaming = _request_is_streaming(raw_request)
            try:
                upstream_resp = urllib_request.urlopen(req, timeout=600)
            except error.HTTPError as exc:
                status_code = exc.code
                body_bytes = exc.read()
                raw_response = body_bytes.decode("utf-8", errors="replace")
                self.send_response(status_code)
                for key, value in exc.headers.items():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                if body_bytes:
                    self.wfile.write(body_bytes)
                return

            status_code = upstream_resp.status
            if streaming:
                raw_chunks: list[bytes] = []
                self.send_response(status_code)
                for key, value in upstream_resp.headers.items():
                    lower = key.lower()
                    if lower in ("content-length", "transfer-encoding", "connection"):
                        continue
                    self.send_header(key, value)
                self.end_headers()
                while True:
                    chunk = upstream_resp.read(8192)
                    if not chunk:
                        break
                    raw_chunks.append(chunk)
                    self.wfile.write(chunk)
                raw_response = b"".join(raw_chunks).decode("utf-8", errors="replace")
            else:
                body_bytes = upstream_resp.read()
                raw_response = body_bytes.decode("utf-8", errors="replace")
                self.send_response(status_code)
                for key, value in upstream_resp.headers.items():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                if body_bytes:
                    self.wfile.write(body_bytes)
        finally:
            response_received_at = utc_now_iso()
            wire_latency_ms = int((time.perf_counter() - t0) * 1000)
            if raw_request or raw_response:
                _emit_proxy_call(
                    delegation_id=delegation_id,
                    step_index=step_index,
                    call_index=call_index,
                    session_dir=session_dir,
                    workspace=workspace,
                    model=model,
                    request_received_at=request_received_at,
                    response_received_at=response_received_at,
                    wire_latency_ms=wire_latency_ms,
                    status_code=status_code,
                    raw_request=raw_request,
                    raw_response=raw_response,
                    attribution_source=attribution_source,
                )

    def _json_error(self, status_code: int, message: str) -> tuple[int, str]:
        payload = json.dumps({"error": message})
        body = payload.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return status_code, payload


class LocalLlmProxy:
    """Threaded localhost proxy for litellm traffic."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._httpd is None:
            raise RuntimeError("proxy not started")
        return f"http://{self.host}:{self.port}/v1"

    def start(self) -> None:
        if self._httpd is not None:
            return
        self._httpd = ThreadingHTTPServer((self.host, self.port), _ProxyHandler)
        self.host, self.port = self._httpd.server_address
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="local-llm-proxy",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._httpd = None
        self._thread = None


def _apply_proxy_env(base_url: str) -> None:
    normalized = base_url.rstrip("/")
    for key in _PROXY_ENV_KEYS:
        os.environ[key] = normalized


def ensure_local_llm_proxy() -> LocalLlmProxy:
    """Start proxy once per process and point provider api_base env vars at it."""
    global _active_proxy
    if _active_proxy is not None:
        return _active_proxy

    proxy = LocalLlmProxy()
    proxy.start()
    _apply_proxy_env(proxy.base_url)
    _active_proxy = proxy
    return proxy


def get_local_llm_proxy() -> LocalLlmProxy | None:
    return _active_proxy


def reset_local_llm_proxy_for_tests() -> None:
    """Stop proxy and clear process override (tests only)."""
    global _active_proxy
    if _active_proxy is not None:
        _active_proxy.stop()
        _active_proxy = None
    for key in _PROXY_ENV_KEYS:
        os.environ.pop(key, None)
