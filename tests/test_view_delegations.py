"""Tests for mcp-coder view delegations CLI."""

from __future__ import annotations

import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from core.cli.view_delegations import ViewerHandler, resolve_view_source, run_view


def test_resolve_view_source_log_file(tmp_path):
    log = tmp_path / "delegations.jsonl"
    log.write_text('{"type":"delegation"}\n')
    path, ws = resolve_view_source(str(log), None)
    assert path == log.resolve()
    assert ws is None


def test_resolve_view_source_workspace(tmp_path):
    path, ws = resolve_view_source(None, str(tmp_path))
    assert path is None
    assert ws == str(tmp_path.resolve())


def test_resolve_view_source_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, ws = resolve_view_source(None, None)
    assert path is None
    assert ws == str(tmp_path.resolve())


def test_main_view_requires_delegations_subcommand(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mcp-coder", "view"])
    from main import main

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_main_view_rejects_log_file_and_workspace_via_main(tmp_path, monkeypatch):
    log = tmp_path / "delegations.jsonl"
    log.write_text("{}\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["mcp-coder", "view", "delegations", str(log), "--workspace", str(tmp_path)],
    )
    from main import main

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_main_view_rejects_log_file_and_workspace(tmp_path):
    from core.cli.view_delegations import main_view

    log = tmp_path / "delegations.jsonl"
    log.write_text("{}\n")
    with pytest.raises(SystemExit) as exc:
        main_view([str(log), "--workspace", str(tmp_path)])
    assert exc.value.code == 2


def test_api_delegations_single_file(tmp_path):
    log = tmp_path / "delegations.jsonl"
    record = {"type": "delegation", "delegation_id": "abc", "timestamp_end": "2026-01-01T00:00:00Z"}
    log.write_text(json.dumps(record) + "\n")

    ViewerHandler.log_path = log
    ViewerHandler.workspace = None

    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/delegations") as resp:
            payload = json.loads(resp.read().decode())
        assert payload["count"] == 1
        assert payload["records"][0]["delegation_id"] == "abc"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_serves_viewer_html():
    ViewerHandler.log_path = None
    ViewerHandler.workspace = None

    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            body = resp.read().decode()
        assert "delegation" in body.lower()
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_run_view_opens_browser_when_not_no_open(monkeypatch, tmp_path):
    log = tmp_path / "delegations.jsonl"
    log.write_text('{"type":"delegation","timestamp_end":"2026-01-01T00:00:00Z"}\n')

    opened: list[str] = []
    monkeypatch.setattr(
        "core.cli.view_delegations.webbrowser.open",
        lambda url: opened.append(url) or True,
    )
    monkeypatch.setattr(
        "core.cli.view_delegations.ThreadingHTTPServer.serve_forever",
        lambda self, poll_interval=0.5: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    monkeypatch.setattr("core.cli.view_delegations.ThreadingHTTPServer.shutdown", lambda self: None)

    run_view(log_file=log, no_open=False, port=9876)
    assert opened == ["http://127.0.0.1:9876/"]


def test_main_view_no_open_flag(monkeypatch, tmp_path):
    log = tmp_path / "delegations.jsonl"
    log.write_text('{"type":"delegation","timestamp_end":"2026-01-01T00:00:00Z"}\n')

    calls: list[dict] = []

    def fake_run_view(**kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr("core.cli.view_delegations.run_view", fake_run_view)

    from core.cli.view_delegations import main_view

    assert main_view([str(log), "--no-open", "--port", "9001"]) == 0
    assert len(calls) == 1
    assert calls[0]["log_file"] == str(log)
    assert calls[0]["workspace"] is None
    assert calls[0]["port"] == 9001
    assert calls[0]["no_open"] is True
