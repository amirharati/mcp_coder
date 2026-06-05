"""Ensure workspace .mcp-coder spec layout and templates exist."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from core.specs.paths import (
    bundled_spec_epic_template_path,
    bundled_spec_report_template_path,
    bundled_spec_template_path,
    workspace_spec_epic_template_path,
    workspace_spec_report_template_path,
    workspace_spec_template_path,
    workspace_specs_dir,
    workspace_specs_epics_dir,
    workspace_specs_reports_dir,
    workspace_specs_tasks_dir,
)
from core.specs.sections import join_front_matter, split_front_matter


def _copy_template_if_missing(src: Path, dst: Path, created: list[str]) -> None:
    if dst.exists():
        return
    if not src.is_file():
        raise FileNotFoundError(f"Bundled template missing: {src}")
    shutil.copy2(src, dst)
    created.append(str(dst.resolve()))


def ensure_workspace_spec_layout(workspace: str | Path) -> dict[str, Any]:
    """
    Create <workspace>/.mcp-coder/specs/{tasks,epics,reports}/ and templates if missing.

    Templates are copied from resources/ in the mcp-coder package.
    Never overwrites existing template files.
    """
    specs_dir = workspace_specs_dir(workspace)
    tasks_dir = workspace_specs_tasks_dir(workspace)
    epics_dir = workspace_specs_epics_dir(workspace)
    reports_dir = workspace_specs_reports_dir(workspace)
    template_dst = workspace_spec_template_path(workspace)
    epic_template_dst = workspace_spec_epic_template_path(workspace)
    report_template_dst = workspace_spec_report_template_path(workspace)

    created: list[str] = []
    for d in (specs_dir, tasks_dir, epics_dir, reports_dir):
        if not d.exists():
            created.append(str(d.resolve()))
    specs_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    epics_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    _copy_template_if_missing(bundled_spec_template_path(), template_dst, created)
    _copy_template_if_missing(bundled_spec_epic_template_path(), epic_template_dst, created)
    _copy_template_if_missing(bundled_spec_report_template_path(), report_template_dst, created)

    return {
        "specs_dir": str(specs_dir.resolve()),
        "specs_tasks_dir": str(tasks_dir.resolve()),
        "specs_epics_dir": str(epics_dir.resolve()),
        "specs_reports_dir": str(reports_dir.resolve()),
        "spec_template_path": str(template_dst.resolve()),
        "spec_epic_template_path": str(epic_template_dst.resolve()),
        "spec_report_template_path": str(report_template_dst.resolve()),
        "spec_template_created": str(template_dst.resolve()) in created,
        "created": created,
    }


def ensure_task_report(
    task_spec_path: Path,
    *,
    workspace: str | Path,
) -> Path:
    """
    Return report path for a step task spec; create from template if missing.

    Reports live at specs/reports/<same-filename>.md parallel to specs/tasks/.
    """
    from core.specs.paths import report_path_for_task_spec

    ws = Path(workspace).resolve()
    report_path = report_path_for_task_spec(task_spec_path, workspace=ws)
    if report_path.is_file():
        return report_path

    template_src = bundled_spec_report_template_path()
    if not template_src.is_file():
        raise FileNotFoundError(f"Bundled report template missing: {template_src}")

    task_rel = str(task_spec_path.resolve().relative_to(ws))
    raw = template_src.read_text(encoding="utf-8")
    front_matter, body = split_front_matter(raw)
    task_fm, _ = split_front_matter(task_spec_path.read_text(encoding="utf-8"))
    spec_id = task_fm.get("spec_id") or task_spec_path.stem
    front_matter["spec_id"] = spec_id
    front_matter["task_spec"] = task_rel
    front_matter["status"] = "open"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(join_front_matter(front_matter, body), encoding="utf-8")
    return report_path
