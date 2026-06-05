"""Workspace spec template bootstrap."""

from pathlib import Path

import pytest

from core.specs.bootstrap import ensure_task_report, ensure_workspace_spec_layout
from core.specs.paths import (
    bundled_spec_epic_template_path,
    bundled_spec_report_template_path,
    bundled_spec_template_path,
    normalize_spec_path_arg,
    report_path_for_task_spec,
    resolve_spec_path,
    workspace_spec_epic_template_path,
    workspace_spec_report_template_path,
    workspace_spec_template_path,
    workspace_specs_epics_dir,
    workspace_specs_reports_dir,
    workspace_specs_tasks_dir,
)


def test_ensure_creates_template_and_specs_dirs(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    out = ensure_workspace_spec_layout(ws)

    template = workspace_spec_template_path(ws)
    epic_template = workspace_spec_epic_template_path(ws)
    report_template = workspace_spec_report_template_path(ws)
    tasks = workspace_specs_tasks_dir(ws)
    epics = workspace_specs_epics_dir(ws)
    reports = workspace_specs_reports_dir(ws)
    assert template.is_file()
    assert epic_template.is_file()
    assert report_template.is_file()
    assert tasks.is_dir()
    assert epics.is_dir()
    assert reports.is_dir()
    assert out["spec_template_created"] is True
    assert template.read_text(encoding="utf-8") == bundled_spec_template_path().read_text(
        encoding="utf-8"
    )
    assert epic_template.read_text(encoding="utf-8") == bundled_spec_epic_template_path().read_text(
        encoding="utf-8"
    )
    assert report_template.read_text(encoding="utf-8") == bundled_spec_report_template_path().read_text(
        encoding="utf-8"
    )

    out2 = ensure_workspace_spec_layout(ws)
    assert out2["spec_template_created"] is False
    assert out2["created"] == []


def test_resolve_spec_path_under_tasks_only(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    ensure_workspace_spec_layout(ws)
    rel = ".mcp-coder/specs/tasks/foo.md"
    resolved = resolve_spec_path(ws, rel)
    assert resolved.name == "foo.md"
    assert resolved.parent.name == "tasks"

    with pytest.raises(ValueError, match="step task under"):
        resolve_spec_path(ws, "../outside.md")

    with pytest.raises(ValueError, match="step task under"):
        resolve_spec_path(ws, ".mcp-coder/specs/epics/foo.md")


def test_normalize_tasks_shorthand(tmp_path: Path) -> None:
    assert (
        normalize_spec_path_arg("tasks/foo.md")
        == ".mcp-coder/specs/tasks/foo.md"
    )
    ws = tmp_path / "proj"
    ws.mkdir()
    ensure_workspace_spec_layout(ws)
    resolved = resolve_spec_path(ws, "tasks/foo.md")
    assert resolved.name == "foo.md"
    assert resolved.parent.name == "tasks"


def test_ensure_task_report_creates_parallel_file(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    ensure_workspace_spec_layout(ws)
    task = workspace_specs_tasks_dir(ws) / "demo-step.md"
    task.write_text(
        "---\nspec_id: demo-step\nepic: demo\nstatus: open\n---\n\n## Goal\n\ngo\n",
        encoding="utf-8",
    )
    report = ensure_task_report(task, workspace=ws)
    assert report == report_path_for_task_spec(task, workspace=ws)
    assert report.is_file()
    assert "task_spec" in report.read_text(encoding="utf-8")
