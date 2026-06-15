from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.engine.base import ExecutionResult
from core.host.cursor import CursorHostProvider, slug_candidates
from core.host.factory import get_host_provider
from core.host.null import NullHostProvider
from server.mcp_server import delegate_to_agent


def _fake_cursor_layout(cursor_root: Path, slug: str, session_id: str, *, text: str = "hello") -> Path:
    transcript = (
        cursor_root
        / "projects"
        / slug
        / "agent-transcripts"
        / session_id
        / f"{session_id}.jsonl"
    )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "role": "user",
            "message": {"content": [{"type": "text", "text": text}]},
        }
    )
    transcript.write_text(line + "\n", encoding="utf-8")
    return transcript


def test_slug_candidates_from_path():
    slugs = slug_candidates("/Users/test/my_repo")
    assert slugs[0] == "Users-test-my_repo"
    assert "Users-test-my-repo" in slugs


def test_slug_override(monkeypatch):
    monkeypatch.setenv("MCP_CODER_CURSOR_PROJECT_SLUG", "custom-slug")
    assert slug_candidates("/any/path") == ["custom-slug"]


def test_slug_resolves_nested_transcript(tmp_path, monkeypatch):
    cursor_root = tmp_path / "cursor"
    workspace = tmp_path / "Users-test-repo"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("MCP_CODER_CURSOR_ROOT", str(cursor_root))
    monkeypatch.setenv("MCP_CODER_CURSOR_PROJECT_SLUG", "Users-test-repo")

    transcript = _fake_cursor_layout(cursor_root, "Users-test-repo", "aaa")
    hint = CursorHostProvider().resolve_active_session(workspace)
    assert hint.host_kind == "cursor"
    assert hint.host_session_id == "aaa"
    assert hint.host_transcript_path == str(transcript.resolve())
    assert hint.host_project_slug == "Users-test-repo"


def test_active_session_picks_newest_mtime(tmp_path, monkeypatch):
    cursor_root = tmp_path / "cursor"
    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_CURSOR_ROOT", str(cursor_root))
    monkeypatch.setenv("MCP_CODER_CURSOR_PROJECT_SLUG", "Users-test-repo")

    old = _fake_cursor_layout(cursor_root, "Users-test-repo", "old-id")
    new = _fake_cursor_layout(cursor_root, "Users-test-repo", "new-id")
    old.touch()
    time.sleep(0.02)
    new.touch()

    hint = CursorHostProvider().resolve_active_session(workspace)
    assert hint.host_session_id == "new-id"
    assert hint.host_resolve_method is not None


def test_missing_project_returns_empty_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CURSOR_ROOT", str(tmp_path / "cursor"))
    hint = CursorHostProvider().resolve_active_session(tmp_path / "nowhere")
    assert hint.host_kind is None
    assert hint.host_session_id is None
    assert hint.resolve_error == "cursor_project_not_found"


def test_factory_none(monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOST", "none")
    assert isinstance(get_host_provider(), NullHostProvider)


def test_delegate_to_agent_writes_host_fields(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cursor_root = tmp_path / "cursor"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_HOST", "cursor")
    monkeypatch.setenv("MCP_CODER_CURSOR_ROOT", str(cursor_root))
    monkeypatch.setenv("MCP_CODER_CURSOR_PROJECT_SLUG", "Users-test-repo")
    monkeypatch.chdir(workspace)

    _fake_cursor_layout(cursor_root, "Users-test-repo", "host-abc")

    fake_result = ExecutionResult(
        success=True,
        output="done",
        files_changed=["hello.py"],
        model="gpt-4o",
        tokens={"source": "unavailable"},
    )
    mock_engine = type(
        "MockEngine",
        (),
        {"model_name": "gpt-4o", "backend_id": "aider", "run": lambda *a, **k: fake_result},
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Add hello world",
            target_files=["hello.py"],
            context_summary="Python 3.10+",
            backend="aider",
        )

    payload = json.loads(raw)
    assert payload["host_kind"] == "cursor"
    assert payload["host_session_id"] == "host-abc"

    log_path = Path(payload["log_path"])
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["host_kind"] == "cursor"
    assert record["host_session_id"] == "host-abc"
    assert record["host_transcript_path"]
    assert record["context"]["host_transcript_file_bytes"] is not None
    assert record["context"]["host_transcript_injected_bytes"] == 0
    assert record["context"]["host_transcript_bytes"] == 0
    assert record["context"]["host_transcript_policy"] == "none"
    assert record["context_mode"] == "fallback"

    session = json.loads((log_path.parent / "session.json").read_text(encoding="utf-8"))
    assert session["host_session_id"] == "host-abc"


def test_delegate_injects_transcript_when_dump_policy(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cursor_root = tmp_path / "cursor"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_HOST", "cursor")
    monkeypatch.setenv("MCP_CODER_HOST_TRANSCRIPT", "dump")
    monkeypatch.setenv("MCP_CODER_CURSOR_ROOT", str(cursor_root))
    monkeypatch.setenv("MCP_CODER_CURSOR_PROJECT_SLUG", "Users-test-repo")
    monkeypatch.chdir(workspace)

    _fake_cursor_layout(
        cursor_root,
        "Users-test-repo",
        "host-dump",
        text="prior chat context from cursor",
    )

    fake_result = ExecutionResult(
        success=True,
        output="done",
        files_changed=["hello.py"],
        model="gpt-4o",
        tokens={"source": "unavailable"},
    )

    mock_engine = type(
        "MockEngine",
        (),
        {"model_name": "gpt-4o", "backend_id": "aider", "run": lambda *a, **k: fake_result},
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Add hello world",
            target_files=["hello.py"],
            context_summary="Python 3.10+",
            backend="aider",
        )

    payload = json.loads(raw)
    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    prompt_full = record["context"]["prompt_full"]
    assert "prior chat context from cursor" in prompt_full
    assert record["context_mode"] == "host_transcript"
    assert record["context"]["host_transcript_injected_bytes"] > 0
    assert record["context"]["host_transcript_bytes"] == record["context"]["host_transcript_injected_bytes"]
    assert record["context"]["host_transcript_hash"]
    assert record["timing"]["context_load_ms"] >= 0


def test_real_slug_for_mcp_coder_repo(monkeypatch):
    """Sanity check against live Cursor layout when present."""
    root = Path.home() / ".cursor"
    if not root.is_dir():
        pytest.skip("no ~/.cursor")
    ws = Path(__file__).resolve().parents[1]
    hint = CursorHostProvider().resolve_active_session(ws)
    slug = "Users-amir-Dropbox-CodingProjects-personal-tools-mcp-coder"
    if not (root / "projects" / slug).is_dir():
        pytest.skip("cursor project slug not found")
    assert hint.host_kind == "cursor"
    assert hint.host_session_id
    assert hint.host_transcript_path
