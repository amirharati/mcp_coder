"""Tests for maintenance gc first slice (P9-005)."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from core.cli.maintenance import main_maintenance
from core.storage.paths import session_folder


def _setup_workspace(tmp_path: Path, monkeypatch) -> Path:
    ws = tmp_path / "repo"
    ws.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    return ws


def _session_dir(ws: Path, session_id: str = "sess-1") -> Path:
    sdir = session_folder(ws, session_id)
    sdir.mkdir(parents=True, exist_ok=True)
    return sdir


def _write_delegation_row(
    session_dir: Path,
    delegation_id: str,
    *,
    created_at: str | None = None,
    context_package_hash: str | None = None,
) -> None:
    row: dict[str, object] = {"delegation_id": delegation_id}
    if created_at is not None:
        row["created_at"] = created_at
    if context_package_hash is not None:
        row["context"] = {"context_package_hash": context_package_hash}
    path = session_dir / "delegations.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _write_trace(
    session_dir: Path,
    delegation_id: str,
    *,
    created_at: str | None = None,
    mtime: dt.datetime | None = None,
) -> Path:
    traces_dir = session_dir / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    trace = traces_dir / f"{delegation_id}.jsonl"
    header = {"type": "trace_header", "delegation_id": delegation_id}
    if created_at is not None:
        header["created_at"] = created_at
    trace.write_text(json.dumps(header) + "\n", encoding="utf-8")
    if mtime is not None:
        ts = mtime.timestamp()
        os.utime(trace, (ts, ts))
    return trace


def _write_blob(session_dir: Path, blob_hash: str, *, content: str = "{}") -> Path:
    blobs_dir = session_dir / "context_packages"
    blobs_dir.mkdir(parents=True, exist_ok=True)
    path = blobs_dir / f"{blob_hash}.json"
    path.write_text(content, encoding="utf-8")
    return path


def test_gc_dry_run_no_policy_noop(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.delenv("MCP_CODER_OBS_RETENTION", raising=False)
    rc = main_maintenance(["gc", "--workspace", str(ws), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "nothing to prune" in out


def test_gc_dry_run_forever_noop(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_RETENTION", "forever")
    rc = main_maintenance(["gc", "--workspace", str(ws), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "nothing to prune" in out


def test_gc_dry_run_reports_prunable_traces(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_RETENTION", "1_days")
    sdir = _session_dir(ws)
    old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
    _write_trace(sdir, "old-d", mtime=old_time)
    _write_trace(sdir, "new-d")

    rc = main_maintenance(["gc", "--workspace", str(ws), "--dry-run", "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["layers"]["traces"]["file_count"] == 2
    assert payload["layers"]["traces"]["prunable_count"] == 1
    assert (sdir / "traces" / "old-d.jsonl").exists()


def test_gc_dry_run_blobs_unreferenced(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_RETENTION", "1_days")
    sdir = _session_dir(ws)
    old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)

    _write_delegation_row(sdir, "live-d", context_package_hash="livehash")
    _write_trace(sdir, "live-d")
    _write_delegation_row(sdir, "old-d", context_package_hash="oldhash")
    _write_trace(sdir, "old-d", mtime=old_time)

    _write_blob(sdir, "livehash", content='{"k":"live"}')
    _write_blob(sdir, "oldhash", content='{"k":"old"}')
    _write_blob(sdir, "orphanhash", content='{"k":"orphan"}')

    rc = main_maintenance(["gc", "--workspace", str(ws), "--dry-run", "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["layers"]["blobs"]["file_count"] == 3
    assert payload["layers"]["blobs"]["prunable_count"] == 2


def test_gc_actual_prune_deletes_expired(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_RETENTION", "1_days")
    sdir = _session_dir(ws)
    old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
    trace = _write_trace(sdir, "old-d", mtime=old_time)
    assert trace.exists()

    rc = main_maintenance(["gc", "--workspace", str(ws), "--format", "json"])
    assert rc == 0
    assert not trace.exists()


def test_gc_blocked_training_file_not_pruned(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_RETENTION", "1_days")
    sdir = _session_dir(ws)
    old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
    trace = _write_trace(sdir, "old-d", mtime=old_time)
    training = sdir / "traces" / "old-d-training.json"
    training.write_text('{"export":"yes"}\n', encoding="utf-8")

    rc = main_maintenance(["gc", "--workspace", str(ws), "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["layers"]["traces"]["blocked_count"] == 1
    assert trace.exists()
    assert training.exists()


def test_gc_json_format_output(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_RETENTION", "2_days")
    sdir = _session_dir(ws)
    _write_trace(sdir, "d1")

    rc = main_maintenance(["gc", "--workspace", str(ws), "--dry-run", "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["policy"] == "2_days"
    assert payload["dry_run"] is True
    assert "layers" in payload
    assert "traces" in payload["layers"]
    assert "blobs" in payload["layers"]
    assert "rows" in payload["layers"]
    assert "pruned_count" in payload
    assert "pruned_bytes" in payload


def test_stats_includes_blob_counts(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path, monkeypatch)
    sdir = _session_dir(ws)
    _write_blob(sdir, "h1", content='{"a":1}')
    _write_blob(sdir, "h2", content='{"b":2}')

    rc = main_maintenance(["stats", "--workspace", str(ws), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["context_packages"]["file_count"] == 2
    assert payload["context_packages"]["total_bytes"] > 0
