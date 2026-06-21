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
    SupervisorState,
)
from server.mcp_server import _response_payload, delegate_to_agent


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


def test_find_latest_returns_most_recent_non_expired(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    older = _state(spec_path="tasks/auth-01.md")
    newer = _state(spec_path="tasks/auth-01.md")
    old_path = older.save()
    new_path = newer.save()

    old_payload = json.loads(old_path.read_text(encoding="utf-8"))
    old_payload["paused_at"] = "2026-01-01T00:00:00Z"
    old_payload["expires_at"] = "2099-01-01T00:00:00Z"
    old_path.write_text(json.dumps(old_payload), encoding="utf-8")

    new_payload = json.loads(new_path.read_text(encoding="utf-8"))
    new_payload["paused_at"] = "2026-01-02T00:00:00Z"
    new_payload["expires_at"] = "2099-01-01T00:00:00Z"
    new_path.write_text(json.dumps(new_payload), encoding="utf-8")

    latest = SupervisorState.find_latest("tasks/auth")
    assert latest is not None
    assert latest.resume_token == newer.resume_token


def test_find_latest_returns_none_when_all_expired(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = _state(spec_path="tasks/auth-01.md")
    path = state.save()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expires_at"] = "2000-01-01T00:00:00Z"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert SupervisorState.find_latest("tasks/auth") is None


def test_find_latest_returns_none_when_directory_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    assert SupervisorState.find_latest("missing/project") is None


def test_delegate_with_answer_auto_resumes_without_token(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    paused = _state(spec_path="tasks/auth-01.md")
    with patch(
        "server.mcp_server.SupervisorState.find_latest", return_value=paused
    ) as latest_mock, patch(
        "server.mcp_server._handle_resume", return_value='{"ok": true}'
    ) as resume_mock, patch(
        "server.mcp_server._apply_clarity_check",
        side_effect=AssertionError("clarity must not run on implicit resume"),
    ), patch(
        "server.mcp_server._apply_architect_pass",
        side_effect=AssertionError("planner must not run on implicit resume"),
    ):
        raw = delegate_to_agent(
            task="Continue work",
            target_files=[],
            context_summary="",
            answer="continue",
        )
    assert json.loads(raw) == {"ok": True}
    latest_mock.assert_called_once()
    resume_mock.assert_called_once()


def test_delegate_without_answer_returns_paused_reminder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    paused = _state(spec_path="tasks/auth-01.md")
    paused.questions = ["Need DB answer?"]
    with patch(
        "server.mcp_server.SupervisorState.find_latest", return_value=paused
    ), patch(
        "server.mcp_server._apply_clarity_check",
        side_effect=AssertionError("pipeline must not run for paused reminder"),
    ), patch(
        "server.mcp_server._apply_architect_pass",
        side_effect=AssertionError("pipeline must not run for paused reminder"),
    ):
        payload = json.loads(
            delegate_to_agent(
                task="Continue work",
                target_files=[],
                context_summary="",
            )
        )
    assert payload["outcome"] == "needs_input"
    assert payload["error_class"] == "paused_awaiting_answer"
    assert payload["paused_questions"] == ["Need DB answer?"]
    assert "resume_token" not in payload


def test_delegate_start_fresh_abandons_paused_state_and_runs_fresh(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")

    paused = _state(spec_path="tasks/auth-01.md")
    paused.save()
    paused_path = (
        SupervisorState.state_dir(paused.project_key) / f"{paused.resume_token}.json"
    )
    assert paused_path.is_file()

    ok_result = ExecutionResult(
        success=True,
        output="done",
        files_changed=["main.py"],
        model="gpt-4o",
        tokens={"source": "unavailable"},
    )
    mock_engine = type(
        "MockEngine",
        (),
        {"model_name": "gpt-4o", "backend_id": "aider", "run": lambda *a, **k: ok_result},
    )()
    with patch("server.mcp_server.SupervisorState.find_latest", return_value=paused), patch(
        "server.mcp_server.get_engine", return_value=mock_engine
    ):
        payload = json.loads(
            delegate_to_agent(
                task="Do fresh work",
                target_files=["main.py"],
                context_summary="Python project",
                backend="aider",
                start_fresh=True,
            )
        )
    assert payload["success"] is True
    assert not paused_path.exists()


def test_response_payload_does_not_include_resume_token():
    payload = _response_payload(
        success=False,
        output="need input",
        files_changed=[],
        session_reused=False,
        session_reason="test",
        session_policy="test",
        outcome="needs_input",
        paused_questions=[],
    )
    assert "resume_token" not in payload
    assert payload["paused_questions"] == []
