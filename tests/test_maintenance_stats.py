"""Tests for mcp-coder maintenance stats CLI."""

from __future__ import annotations

import json
from pathlib import Path

from core.cli.maintenance import main_maintenance
from core.observability.stats import collect_observability_stats
from core.storage.paths import session_folder


def _write_config(ws: Path, text: str) -> None:
    cfg = ws / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(text, encoding="utf-8")


def test_collect_observability_stats_counts_trace_and_jsonl(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    _write_config(ws, "rag_enabled: false\n")

    session_dir = session_folder(ws, "sess-1")
    session_dir.mkdir(parents=True)
    deleg_log = session_dir / "delegations.jsonl"
    deleg_log.write_text('{"type":"delegation"}\n', encoding="utf-8")

    traces = session_dir / "traces"
    traces.mkdir()
    (traces / "d1.jsonl").write_text('{"type":"trace_header"}\n', encoding="utf-8")
    (traces / "d1-training.json").write_text('{"task":"x"}\n', encoding="utf-8")

    stats = collect_observability_stats(ws)
    assert stats["sessions"]["count"] == 1
    assert stats["sessions"]["delegations_jsonl_lines"] == 1
    assert stats["traces"]["file_count"] == 1
    assert stats["traces"]["training_file_count"] == 1


def test_maintenance_stats_cli_json(tmp_path, capsys):
    ws = tmp_path / "repo"
    ws.mkdir()
    _write_config(ws, "rag_enabled: false\n")

    rc = main_maintenance(["stats", "--workspace", str(ws), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workspace"] == str(ws.resolve())
    assert "traces" in payload
