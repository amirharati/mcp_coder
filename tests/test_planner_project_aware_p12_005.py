"""P12-005 tests: planner project-state injection and decision write-back."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from core.context.helper_llm_pipeline import _build_project_state_section, apply_planner_pass
from core.context.package import ContextPackage
from core.state.project_state import ProjectState


def _spec_read(files_section: str = "- auth.py\n- db.py") -> SimpleNamespace:
    return SimpleNamespace(
        sections={"Goal": "Implement task", "Constraints": "", "Files": files_section},
        prompt_block="",
    )


def _context_package() -> ContextPackage:
    return ContextPackage(
        brief="## Paths\n- EDIT auth.py",
        entries=[],
        policies=None,
        metadata={},
    )


def _planner_result(*, success: bool, plan: str = "", error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        success=success,
        plan=plan,
        error=error,
        model="test/planner",
        tokens={"input": 1, "output": 1, "total": 2, "source": "planner_pass"},
        duration_ms=1,
        raw_output=plan or "",
    )


def test_project_state_section_injected_when_non_empty():
    project_state = ProjectState(project_key="proj")
    project_state.add_decision("Use auth.py middleware for session checks", "d-0")
    captured: dict[str, str] = {}

    def _run_planner(prompt: str, *, workspace_path: str):
        captured["prompt"] = prompt
        return _planner_result(success=True, plan="## Planner plan\n- Do work")

    with patch("core.engine.planner_pass_llm.run_planner_pass_llm", side_effect=_run_planner):
        apply_planner_pass(
            context_package=_context_package(),
            spec_read=_spec_read(),
            picker_result=None,
            workspace="/tmp/ws",
            task="Implement auth",
            context_summary="",
            host_transcript=None,
            project_state=project_state,
            spec_files=["auth.py"],
        )

    assert "## Project state" in captured["prompt"]


def test_project_state_section_empty_when_no_entries():
    state = ProjectState(project_key="proj")
    assert _build_project_state_section(state, ["auth.py"]) == ""


def test_file_filtering_returns_only_relevant():
    state = ProjectState(project_key="proj")
    state.decisions = [
        {"text": "Will update auth.py flow"},
        {"text": "Will modify db.py migrations"},
    ]
    state.open_risks = [
        {"text": "auth.py missing error handling", "severity": "notable", "files": ["auth.py"]},
        {"text": "db.py could break schema", "severity": "critical", "files": ["db.py"]},
    ]

    section = _build_project_state_section(state, ["auth.py"])

    assert "auth.py" in section
    assert "db.py" not in section


def test_planner_context_sources_populated():
    project_state = ProjectState(project_key="proj")
    project_state.add_decision("Use auth.py middleware for session checks", "d-0")
    planner_context_sources: list[str] = []

    with patch(
        "core.engine.planner_pass_llm.run_planner_pass_llm",
        return_value=_planner_result(success=True, plan="## Planner plan\n- Do work"),
    ):
        apply_planner_pass(
            context_package=_context_package(),
            spec_read=_spec_read(),
            picker_result=None,
            workspace="/tmp/ws",
            task="Implement auth",
            context_summary="",
            host_transcript=None,
            project_state=project_state,
            spec_files=["auth.py"],
            planner_context_sources=planner_context_sources,
        )

    assert "project_state" in planner_context_sources


def test_planner_context_sources_empty_when_no_state():
    planner_context_sources: list[str] = []

    with patch(
        "core.engine.planner_pass_llm.run_planner_pass_llm",
        return_value=_planner_result(success=True, plan="## Planner plan\n- Do work"),
    ):
        apply_planner_pass(
            context_package=_context_package(),
            spec_read=_spec_read(),
            picker_result=None,
            workspace="/tmp/ws",
            task="Implement auth",
            context_summary="",
            host_transcript=None,
            project_state=None,
            planner_context_sources=planner_context_sources,
        )

    assert planner_context_sources == []


def test_decisions_extracted_and_written_to_project_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    project_state = ProjectState(project_key="proj")
    plan_text = "## Planner plan\n1. we will use SQLite for the cache\n- done"

    with patch(
        "core.engine.planner_pass_llm.run_planner_pass_llm",
        return_value=_planner_result(success=True, plan=plan_text),
    ):
        apply_planner_pass(
            context_package=_context_package(),
            spec_read=_spec_read(),
            picker_result=None,
            workspace=str(tmp_path / "ws"),
            task="Implement cache",
            context_summary="",
            host_transcript=None,
            delegation_id="d-123",
            project_state=project_state,
            spec_files=["auth.py"],
        )

    assert any("SQLite for the cache" in d.get("text", "") for d in project_state.decisions)
    assert project_state.last_updated is not None


def test_no_decision_extraction_on_failed_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    project_state = ProjectState(project_key="proj")
    before = len(project_state.decisions)

    with patch(
        "core.engine.planner_pass_llm.run_planner_pass_llm",
        return_value=_planner_result(success=False, error="planner failure"),
    ):
        apply_planner_pass(
            context_package=_context_package(),
            spec_read=_spec_read(),
            picker_result=None,
            workspace=str(tmp_path / "ws"),
            task="Implement cache",
            context_summary="",
            host_transcript=None,
            delegation_id="d-123",
            project_state=project_state,
            spec_files=["auth.py"],
        )

    assert len(project_state.decisions) == before
    assert project_state.last_updated is None
