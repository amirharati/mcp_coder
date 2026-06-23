"""Tests for delegation viewer enrichment (lean JSONL pointer resolution)."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from core.cli.delegation_view_enrich import enrich_delegation_record
from core.cli.view_delegations import ViewerHandler
from core.rag.db import DelegationRagDB
from core.rag.models import DelegationIndexRow
from core.rag.workspace_db import WorkspaceRagDB
from core.rag.models import WorkspaceFileIndexRow


def test_enrich_digest_output_preview_only():
    record = {
        "delegation_id": "d1",
        "response_to_cursor": {
            "output_preview": "hello world",
            "output_sha256": "abc",
            "output_bytes": 11,
            "success": True,
            "files_changed": [],
        },
    }
    out = enrich_delegation_record(record)["output"]
    assert out["source"] == "digest_preview"
    assert out["text"] == "hello world"


def test_enrich_legacy_output():
    record = {
        "delegation_id": "d1",
        "response_to_cursor": {"output": "full body"},
    }
    out = enrich_delegation_record(record)["output"]
    assert out["source"] == "legacy_jsonl"
    assert out["text"] == "full body"


def test_enrich_trace_executor_output(tmp_path):
    session_dir = tmp_path / "session"
    traces = session_dir / "traces"
    traces.mkdir(parents=True)
    delegation_id = "trace-delegation"
    trace_path = traces / f"{delegation_id}.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "type": "llm_call",
                "role": "executor",
                "model": "test-model",
                "response_preview": "from trace file",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    record = {
        "delegation_id": delegation_id,
        "session_dir": str(session_dir),
        "trace_ref": f"traces/{delegation_id}.jsonl",
        "response_to_cursor": {"output_preview": "digest only"},
    }
    out = enrich_delegation_record(record)["output"]
    assert out["source"] == "trace_executor"
    assert out["text"] == "from trace file"


def test_enrich_context_ref_from_delegation_rag(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_WORKSPACE", str(ws))
    db = DelegationRagDB(ws)
    db.upsert(
        DelegationIndexRow(
            delegation_id="prior-d",
            workspace_path=str(ws),
            timestamp_end="2026-01-01T00:00:00Z",
            spec_path="spec.md",
            spec_report_path=None,
            checkpoint_summary="Prior delegate summary",
            task_preview="task",
            delegate_mode="implement",
            outcome="success",
            files_changed="[]",
            searchable_text="task Prior delegate summary",
        )
    )
    record = {
        "workspace_path": str(ws),
        "context_refs": [
            {
                "kind": "delegation",
                "id": "prior-d",
                "corpus": "delegation",
                "score": 0.9,
            }
        ],
    }
    resolved = enrich_delegation_record(record)["context_refs_resolved"]
    assert len(resolved) == 1
    assert resolved[0]["source"] == "delegation_rag.db"
    assert resolved[0]["snippet"] == "Prior delegate summary"


def test_enrich_context_ref_from_workspace_rag(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_WORKSPACE", str(ws))
    db = WorkspaceRagDB(ws)
    db.upsert(
        WorkspaceFileIndexRow(
            path="src/foo.py",
            sha256="deadbeef",
            llm_summary="summary of foo.py",
            symbol_list="Foo",
            searchable_text="foo summary",
            indexed_at="2026-01-01T00:00:00Z",
        )
    )
    record = {
        "workspace_path": str(ws),
        "context_refs": [
            {
                "kind": "workspace_file",
                "id": "src/foo.py",
                "corpus": "workspace_files",
                "sha256": "deadbeef",
                "score": 0.8,
            }
        ],
    }
    resolved = enrich_delegation_record(record)["context_refs_resolved"]
    assert resolved[0]["source"] == "workspace_rag.db"
    assert resolved[0]["snippet"] == "summary of foo.py"


def test_api_delegation_enrich_endpoint(tmp_path):
    record = {
        "delegation_id": "abc",
        "response_to_cursor": {"output_preview": "preview text"},
    }
    ViewerHandler.log_path = None
    ViewerHandler.workspace = None

    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/delegation/enrich",
            data=json.dumps(record).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read().decode())
        assert payload["output"]["text"] == "preview text"
        assert payload["output"]["source"] == "digest_preview"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_enrich_view_events_surface_row_level_typed_failure_fields():
    record = {
        "delegation_id": "unknown-delegation",
        "timestamp_end": "2026-01-01T00:00:00Z",
        "outcome": "needs_input",
        "error": "supervisor_loop_unknown",
        "error_detail": {
            "error_class": "unknown",
            "error_message": "supervisor_loop_unknown",
        },
        "response_to_cursor": {
            "output_preview": "",
            "output_bytes": 0,
            "output_sha256": "abc",
            "success": False,
            "files_changed": [],
        },
    }

    enriched = enrich_delegation_record(record)
    host_event = next(
        event for event in enriched["view_events"] if event.get("id") == "mcp.host.out"
    )
    assert host_event["detail"]["outcome"] == "needs_input"
    assert host_event["detail"]["error_class"] == "unknown"
    assert host_event["detail"]["error_message"] == "supervisor_loop_unknown"
