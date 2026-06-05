from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from server.mcp_server import delegate_to_agent

OVERFLOW_PATTERN = re.compile(
    r"(?i)(context|token|length|maximum|too long|prompt|limit|exceed)"
)


def _jsonl_line(role: str, text: str) -> str:
    return json.dumps(
        {
            "role": role,
            "message": {"content": [{"type": "text", "text": text}]},
        }
    )


def _write_fat_transcript(path: Path, *, lines: int, chunk_kb: int) -> int:
    chunk = "x" * (chunk_kb * 1024)
    turns = []
    for i in range(lines):
        role = "user" if i % 2 == 0 else "assistant"
        turns.append(_jsonl_line(role, f"{role} turn {i}: {chunk}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(turns) + "\n", encoding="utf-8")
    return path.stat().st_size


def _fake_cursor_layout(cursor_root: Path, slug: str, session_id: str) -> Path:
    transcript = (
        cursor_root
        / "projects"
        / slug
        / "agent-transcripts"
        / session_id
        / f"{session_id}.jsonl"
    )
    return transcript


@pytest.mark.skipif(
    os.environ.get("MCP_CODER_OVERFLOW_TEST") != "1"
    or not os.environ.get("OPENROUTER_API_KEY"),
    reason="Set MCP_CODER_OVERFLOW_TEST=1 and OPENROUTER_API_KEY for live overflow test",
)
def test_live_transcript_overflow_fails_on_context_limit(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cursor_root = tmp_path / "cursor"
    slug = "Users-test-repo"
    session_id = "overflow-session"

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_HOST", "cursor")
    monkeypatch.setenv("MCP_CODER_HOST_TRANSCRIPT", "dump")
    monkeypatch.setenv("MCP_CODER_MAX_TRANSCRIPT_BYTES", "0")
    monkeypatch.setenv("MCP_CODER_CURSOR_ROOT", str(cursor_root))
    monkeypatch.setenv("MCP_CODER_CURSOR_PROJECT_SLUG", slug)
    monkeypatch.chdir(workspace)

    transcript = _fake_cursor_layout(cursor_root, slug, session_id)
    sizes = [(600, 3), (800, 4), (1000, 4), (1200, 4)]
    injected_bytes = 0
    for lines, chunk_kb in sizes:
        _write_fat_transcript(transcript, lines=lines, chunk_kb=chunk_kb)
        from core.host.cursor_transcript import load_cursor_transcript

        injected_bytes = load_cursor_transcript(transcript).injected_bytes
        if injected_bytes >= 500_000:
            break

    assert injected_bytes >= 500_000, f"fixture too small: {injected_bytes} bytes"

    raw = delegate_to_agent(
        task="Say hello only.",
        target_files=["hello.py"],
        context_summary="Tiny summary.",
        backend="aider",
    )
    payload = json.loads(raw)
    assert payload["success"] is False

    combined = f"{payload.get('output', '')} {payload.get('error', '')}"
    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    err_text = f"{combined} {record.get('error', '')} {record.get('output', '')}"
    assert OVERFLOW_PATTERN.search(err_text), err_text[:500]

    ctx = record["context"]
    assert record["context_mode"] == "host_transcript"
    assert ctx["host_transcript_injected_bytes"] >= 500_000
    assert ctx["prompt_tokens_est"] > 100_000

    pytest.overflow_injected_bytes = injected_bytes  # type: ignore[attr-defined]
    pytest.overflow_error_snippet = err_text[:300]  # type: ignore[attr-defined]
