from __future__ import annotations

import json
import os
from pathlib import Path

from core.engine.base import ExecutionResult
from core.engine.supervisor_agent import SupervisorAgent
from core.state.project_state import ProjectState
from core.state.supervisor_state import SupervisorState


def _parse_iso(raw: str) -> str:
    if raw.endswith("Z"):
        return raw[:-1] + "+00:00"
    return raw


def test_load_missing_returns_empty_state(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = ProjectState.load("default")
    assert state.project_key == "default"
    assert state.decisions == []
    assert state.open_risks == []
    assert state.hot_areas == []


def test_save_is_atomic_and_round_trips(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = ProjectState(project_key="tasks/auth")
    state.add_decision("use SQLite", "d001")
    seen: dict[str, Path] = {}
    real_replace = os.replace

    def _spy_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen["src"] = Path(src)
        seen["dst"] = Path(dst)
        assert seen["src"].is_file()
        real_replace(src, dst)

    monkeypatch.setattr("core.state.project_state.os.replace", _spy_replace)
    saved_path = state.save()
    assert saved_path.is_file()
    assert seen["src"].name == "project_state.json.tmp"
    assert seen["dst"] == saved_path
    assert not seen["src"].exists()
    loaded = ProjectState.load("tasks/auth")
    assert loaded.decisions == state.decisions
    assert loaded.last_updated is not None
    assert _parse_iso(loaded.last_updated)


def test_update_hot_areas_deduplicates_and_orders():
    state = ProjectState(project_key="p")
    state.update_hot_areas(["a.py", "b.py"])
    state.update_hot_areas(["b.py", "c.py"])
    assert state.hot_areas == ["b.py", "c.py", "a.py"]


def test_update_hot_areas_respects_env_cap(monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOT_AREAS_MAX", "3")
    state = ProjectState(project_key="p")
    state.update_hot_areas(["a.py", "b.py", "c.py", "d.py"])
    assert state.hot_areas == ["a.py", "b.py", "c.py"]


def test_add_decision_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = ProjectState(project_key="my-project")
    state.add_decision("use SQLite", "d001")
    state.save()
    loaded = ProjectState.load("my-project")
    assert loaded.decisions[0]["text"] == "use SQLite"
    assert loaded.decisions[0]["delegation_id"] == "d001"
    assert _parse_iso(loaded.decisions[0]["timestamp"])


def test_add_risk_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = ProjectState(project_key="my-project")
    state.add_risk("no test coverage", "notable", "d001")
    state.save()
    loaded = ProjectState.load("my-project")
    assert loaded.open_risks[0]["text"] == "no test coverage"
    assert loaded.open_risks[0]["severity"] == "notable"
    assert loaded.open_risks[0]["source_delegation_id"] == "d001"


def test_state_path_uses_home_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "custom-home"))
    path = ProjectState.state_path("my-project")
    assert path == (tmp_path / "custom-home" / "projects" / "my-project" / "project_state.json")


def test_corrupt_json_load_returns_empty_and_logs(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    path = ProjectState.state_path("p")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        loaded = ProjectState.load("p")
    assert loaded.project_key == "p"
    assert loaded.decisions == []
    assert any("ProjectStateCorrupt" in rec.message for rec in caplog.records)


def test_supervisor_begin_emits_project_state_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    events: list[dict] = []
    agent = SupervisorAgent(
        delegation_id="d-begin",
        workspace_path=str(tmp_path),
        executor_fn=lambda _turn, _correction: ExecutionResult(success=True, output="ok"),
        event_sink=events.append,
        spec_path="tasks/auth-01.md",
        max_turns=1,
    )
    agent.begin()
    loaded = next(event for event in events if event.get("type") == "project_state_loaded")
    assert loaded["project_key"] == "tasks/auth"
    assert loaded["decisions_count"] == 0
    assert loaded["open_risks_count"] == 0
    assert loaded["hot_areas_count"] == 0


def test_supervisor_run_saves_project_state_and_sets_last_delegation(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    events: list[dict] = []
    agent = SupervisorAgent(
        delegation_id="d-save",
        workspace_path=str(tmp_path),
        executor_fn=lambda _turn, _correction: ExecutionResult(
            success=True,
            output="ok",
            files_changed=["core/a.py", "core/b.py"],
        ),
        event_sink=events.append,
        spec_path="tasks/auth-01.md",
        max_turns=1,
    )
    result = agent.run()
    assert result.outcome == "success"
    saved = next(event for event in events if event.get("type") == "project_state_saved")
    assert saved["project_key"] == "tasks/auth"
    state = ProjectState.load("tasks/auth")
    assert state.last_delegation == "d-save"
    assert state.hot_areas[:2] == ["core/a.py", "core/b.py"]


def test_supervisor_resume_loads_project_state_and_emits_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = SupervisorState.create(
        spec_path="tasks/auth-01.md",
        context_ref="d-resume",
        plan=None,
        decision_log=[],
        completed_turn_artifacts=[],
        turn_index=0,
        questions=[],
    )
    events: list[dict] = []
    agent = SupervisorAgent.resume(
        state,
        "Proceed.",
        workspace_path=str(tmp_path),
        executor_fn=lambda _turn, _correction: ExecutionResult(success=True, output="ok"),
        event_sink=events.append,
    )
    loaded = next(event for event in events if event.get("type") == "project_state_loaded")
    assert loaded["project_key"] == state.project_key
    agent.run()


def test_two_delegations_same_project_updates_last_delegation(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    for delegation_id in ("d-first", "d-second"):
        agent = SupervisorAgent(
            delegation_id=delegation_id,
            workspace_path=str(tmp_path),
            executor_fn=lambda _turn, _correction: ExecutionResult(
                success=True, output="ok", files_changed=["main.py"]
            ),
            spec_path="tasks/auth-01.md",
            max_turns=1,
            event_sink=lambda _event: None,
        )
        agent.run()
    state = ProjectState.load("tasks/auth")
    assert state.last_delegation == "d-second"


def test_project_state_full_round_trip_schema(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    state = ProjectState(
        version=1,
        project_key="proj",
        decisions=[{"text": "x", "delegation_id": "d1", "timestamp": "2026-01-01T00:00:00Z"}],
        open_risks=[{"text": "r", "severity": "advisory", "source_delegation_id": "d1", "timestamp": "2026-01-01T00:00:00Z"}],
        hot_areas=["a.py"],
        reviewer_findings_summary=[{"finding": "f", "severity": "low", "delegation_id": "d1", "spec_path": None, "date": "2026-01-01T00:00:00Z"}],
        last_delegation="d1",
        last_updated="2026-01-01T00:00:00Z",
    )
    state.save()
    loaded = ProjectState.load("proj")
    assert loaded.version == 1
    assert loaded.project_key == "proj"
    assert loaded.decisions[0]["text"] == "x"
    assert loaded.open_risks[0]["text"] == "r"
    assert loaded.hot_areas == ["a.py"]
    assert loaded.reviewer_findings_summary[0]["finding"] == "f"
    assert loaded.last_delegation == "d1"
