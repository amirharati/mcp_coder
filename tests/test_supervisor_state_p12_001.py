from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import (
    SupervisorAgent,
    SupervisorTurnContext,
    SupervisorTurnDecision,
)
from core.state.project_key import ProjectKeyResolver
from core.state.supervisor_state import (
    ResumeTokenExpired,
    ResumeTokenNotFound,
    SupervisorState,
)
from server.mcp_server import _handle_resume, _response_payload, delegate_to_agent


def _parse_iso(raw: str) -> datetime:
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _state(
    *,
    spec_path: str | None = "tasks/auth-01.md",
    turn_index: int = 1,
    ttl_seconds: int = 86400,
) -> SupervisorState:
    return SupervisorState.create(
        spec_path=spec_path,
        context_ref="deleg-1",
        plan="## Planner plan\n- Do work",
        decision_log=[{"action": "done", "reason": "ok"}],
        completed_turn_artifacts=[{"files_changed": ["a.py"], "output_tail": "tail"}],
        turn_index=turn_index,
        questions=["What DB should we use?"],
        ttl_seconds=ttl_seconds,
    )


def test_project_key_from_tasks_spec():
    assert ProjectKeyResolver.from_spec_path("tasks/auth-01.md") == "tasks/auth"


def test_project_key_from_docs_tasks_spec():
    assert ProjectKeyResolver.from_spec_path("docs/tasks/auth-01.md") == "docs/tasks"


def test_project_key_from_single_file():
    assert ProjectKeyResolver.from_spec_path("auth.md") == "auth"


def test_project_key_none_defaults_to_default():
    assert ProjectKeyResolver.from_spec_path(None) == "default"


def test_project_key_env_override_wins(monkeypatch):
    monkeypatch.setenv("MCP_CODER_PROJECT_KEY", "forced/key")
    assert ProjectKeyResolver.from_spec_path("tasks/auth-01.md") == "forced/key"


def test_supervisor_state_create_uuid4_and_ttl(monkeypatch):
    monkeypatch.delenv("MCP_CODER_RESUME_TOKEN_TTL", raising=False)
    state = _state(ttl_seconds=120)
    parsed = UUID(state.resume_token, version=4)
    assert str(parsed) == state.resume_token
    delta = _parse_iso(state.expires_at) - _parse_iso(state.paused_at)
    assert int(delta.total_seconds()) == 120


def test_supervisor_state_save_is_atomic(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = _state()
    seen: dict[str, Path] = {}
    real_replace = os.replace

    def _spy_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen["src"] = Path(src)
        seen["dst"] = Path(dst)
        assert seen["src"].is_file()
        real_replace(src, dst)

    monkeypatch.setattr("core.state.supervisor_state.os.replace", _spy_replace)
    saved_path = state.save()
    assert saved_path.is_file()
    assert seen["src"].name.endswith(".json.tmp")
    assert seen["dst"] == saved_path
    assert not seen["src"].exists()


def test_supervisor_state_load_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = _state()
    state.save()
    loaded = SupervisorState.load(state.resume_token, state.project_key)
    assert loaded.resume_token == state.resume_token
    assert loaded.project_key == state.project_key
    assert loaded.turn_index == state.turn_index
    assert loaded.plan == state.plan
    assert loaded.decision_log == state.decision_log
    assert loaded.completed_turn_artifacts == state.completed_turn_artifacts


def test_supervisor_state_load_raises_expired(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = _state()
    path = state.save()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace(
        "+00:00", "Z"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResumeTokenExpired):
        SupervisorState.load(state.resume_token, state.project_key)


def test_supervisor_state_find_and_load_scans_projects(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state_a = _state(spec_path="tasks/auth-01.md")
    state_b = _state(spec_path="docs/tasks/auth-01.md")
    state_a.save()
    state_b.save()
    loaded = SupervisorState.find_and_load(state_b.resume_token)
    assert loaded.resume_token == state_b.resume_token
    assert loaded.project_key == "docs/tasks"


def test_supervisor_finish_escalate_saves_state_and_token(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    events: list[dict] = []

    def _escalate(_ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        return SupervisorTurnDecision(action="escalate_host", reason="Need host input")

    agent = SupervisorAgent(
        delegation_id="deleg-save",
        workspace_path=str(tmp_path),
        executor_fn=lambda _turn, _correction: ExecutionResult(success=False, output=""),
        decision_fn=_escalate,
        event_sink=events.append,
        spec_path="tasks/auth-01.md",
        max_turns=2,
    )
    agent.begin()
    agent.begin_turn()
    agent.complete_turn(
        ExecutionResult(
            success=False,
            output="Should we use SQLite or Postgres?",
            files_changed=["main.py"],
            error="Need clarification",
            error_class="needs_input",
        ),
        {"outcome": "issues", "note": "Question remains"},
    )
    result = agent.finish()
    assert result.outcome == "escalated"
    assert result.resume_token
    assert result.paused_questions
    saved = SupervisorState.find_and_load(result.resume_token or "")
    assert saved.context_ref == "deleg-save"
    assert saved.turn_index == 1
    assert any(event.get("type") == "supervisor_paused" for event in events)


def test_supervisor_resume_preloads_turn_and_host_clarification(tmp_path):
    state = _state(turn_index=2)
    state.context_ref = "deleg-resume"
    calls: list[tuple[int, str | None]] = []
    events: list[dict] = []

    def _executor(turn_index: int, correction: str | None) -> ExecutionResult:
        calls.append((turn_index, correction))
        return ExecutionResult(success=True, output="done", files_changed=["main.py"])

    agent = SupervisorAgent.resume(
        state,
        "Please keep this in scope.",
        workspace_path=str(tmp_path),
        executor_fn=_executor,
        event_sink=events.append,
    )
    result = agent.run()
    assert calls[0][0] == 3
    assert "## Host clarification" in (calls[0][1] or "")
    assert "Please keep this in scope." in (calls[0][1] or "")
    assert result.turns_completed == 3
    assert len(result.decisions) >= 2
    assert any(event.get("type") == "supervisor_resumed" for event in events)


def test_delegate_resume_token_skips_pipeline_stages(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    with patch("server.mcp_server._handle_resume", return_value='{"ok": true}') as resume_mock, patch(
        "server.mcp_server._apply_clarity_check",
        side_effect=AssertionError("clarity must not run on resume"),
    ), patch(
        "server.mcp_server._apply_architect_pass",
        side_effect=AssertionError("planner must not run on resume"),
    ):
        raw = delegate_to_agent(
            task="Continue work",
            target_files=[],
            context_summary="",
            resume_token="resume-123",
            answer="continue",
        )
    assert json.loads(raw) == {"ok": True}
    resume_mock.assert_called_once()


def test_handle_resume_expired_token_returns_error_payload(monkeypatch):
    monkeypatch.setattr(
        "server.mcp_server.SupervisorState.find_and_load",
        lambda _token: (_ for _ in ()).throw(ResumeTokenExpired("2026-01-01T00:00:00Z")),
    )
    payload = json.loads(_handle_resume("expired-token", "answer", "task", None))
    assert payload["outcome"] == "error"
    assert payload["error_class"] == "resume_token_expired"
    assert "Resume token expired at 2026-01-01T00:00:00Z" in payload["error_message"]


def test_handle_resume_missing_token_returns_error_payload(monkeypatch):
    monkeypatch.setattr(
        "server.mcp_server.SupervisorState.find_and_load",
        lambda _token: (_ for _ in ()).throw(ResumeTokenNotFound("missing-token")),
    )
    payload = json.loads(_handle_resume("missing-token", "answer", "task", None))
    assert payload["outcome"] == "error"
    assert payload["error_class"] == "resume_token_not_found"
    assert "Resume token not found: missing-token" in payload["error_message"]


def test_response_payload_includes_resume_fields():
    payload = _response_payload(
        success=False,
        output="need input",
        files_changed=[],
        session_reused=False,
        session_reason="test",
        session_policy="test",
        outcome="needs_input",
        resume_token="token-1",
        paused_questions=[],
    )
    assert payload["resume_token"] == "token-1"
    assert payload["paused_questions"] == []
