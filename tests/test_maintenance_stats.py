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


def test_executor_turns_counted_in_stats(tmp_path):
    """executor_turns aggregates llm_call lines with role=executor executor_turn=true."""
    import json as _json

    ws = tmp_path / "repo"
    ws.mkdir()
    _write_config(ws, "rag_enabled: false\n")

    session_dir = session_folder(ws, "sess-exec")
    session_dir.mkdir(parents=True)
    traces = session_dir / "traces"
    traces.mkdir()

    # Write a trace file with 2 executor turns and 1 helper turn (should not count).
    trace_lines = [
        {"type": "trace_header", "delegation_id": "d1"},
        {"type": "llm_call", "role": "executor", "executor_turn": True},
        {"type": "llm_call", "role": "executor", "executor_turn": True},
        {"type": "llm_call", "role": "builder"},  # helper — must NOT be counted
        {"type": "action", "kind": "scope_expansion_check"},
        {"type": "tool_call", "tool": "file_write"},
    ]
    (traces / "d1.jsonl").write_text(
        "\n".join(_json.dumps(l) for l in trace_lines) + "\n",
        encoding="utf-8",
    )

    stats = collect_observability_stats(ws)
    assert stats["traces"]["executor_turns"] == 2


def test_executor_turns_zero_when_no_traces(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    _write_config(ws, "rag_enabled: false\n")

    stats = collect_observability_stats(ws)
    assert stats["traces"]["executor_turns"] == 0


def test_maintenance_stats_text_shows_executor_turns(tmp_path, capsys):
    """Text output must include 'executor turns' line."""
    import json as _json

    ws = tmp_path / "repo"
    ws.mkdir()
    _write_config(ws, "rag_enabled: false\n")

    session_dir = session_folder(ws, "sess-et")
    session_dir.mkdir(parents=True)
    traces = session_dir / "traces"
    traces.mkdir()
    exec_rec = {"type": "llm_call", "role": "executor", "executor_turn": True}
    (traces / "d2.jsonl").write_text(_json.dumps(exec_rec) + "\n", encoding="utf-8")

    rc = main_maintenance(["stats", "--workspace", str(ws)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "executor turns" in out
