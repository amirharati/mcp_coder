"""Paths for workspace task specs (.mcp-coder/specs/)."""

from __future__ import annotations

from pathlib import Path

SPEC_TEMPLATE_FILENAME = "spec-template.md"
SPEC_EPIC_TEMPLATE_FILENAME = "spec-epic-template.md"
SPEC_REPORT_TEMPLATE_FILENAME = "spec-report-template.md"
SPECS_SUBDIR = "specs"
TASKS_SUBDIR = "tasks"
EPICS_SUBDIR = "epics"
REPORTS_SUBDIR = "reports"


def workspace_mcp_coder_dir(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / ".mcp-coder"


def workspace_specs_dir(workspace: str | Path) -> Path:
    return workspace_mcp_coder_dir(workspace) / SPECS_SUBDIR


def workspace_specs_tasks_dir(workspace: str | Path) -> Path:
    return workspace_specs_dir(workspace) / TASKS_SUBDIR


def workspace_specs_epics_dir(workspace: str | Path) -> Path:
    return workspace_specs_dir(workspace) / EPICS_SUBDIR


def workspace_specs_reports_dir(workspace: str | Path) -> Path:
    return workspace_specs_dir(workspace) / REPORTS_SUBDIR


def workspace_spec_template_path(workspace: str | Path) -> Path:
    return workspace_mcp_coder_dir(workspace) / SPEC_TEMPLATE_FILENAME


def workspace_spec_epic_template_path(workspace: str | Path) -> Path:
    return workspace_mcp_coder_dir(workspace) / SPEC_EPIC_TEMPLATE_FILENAME


def workspace_spec_report_template_path(workspace: str | Path) -> Path:
    return workspace_mcp_coder_dir(workspace) / SPEC_REPORT_TEMPLATE_FILENAME


def bundled_spec_template_path() -> Path:
    from core.resources_paths import resources_dir

    return resources_dir() / SPEC_TEMPLATE_FILENAME


def bundled_spec_epic_template_path() -> Path:
    from core.resources_paths import resources_dir

    return resources_dir() / SPEC_EPIC_TEMPLATE_FILENAME


def bundled_spec_report_template_path() -> Path:
    from core.resources_paths import resources_dir

    return resources_dir() / SPEC_REPORT_TEMPLATE_FILENAME


def _expected_mcp_coder_spec_path(raw: str) -> str | None:
    """Map repo-root specs/ paths to their .mcp-coder/ counterparts."""
    norm = raw.strip().replace("\\", "/").lstrip("/")
    if norm.startswith("specs/tasks/"):
        return f".mcp-coder/{norm}"
    if norm.startswith(("specs/epics/", "specs/reports/")):
        return f".mcp-coder/{norm}"
    rest = norm.removeprefix("specs/")
    if norm.startswith("specs/") and "/" not in rest and rest.endswith(".md"):
        return f".mcp-coder/specs/tasks/{rest}"
    if norm.startswith("specs/"):
        return f".mcp-coder/{norm}"
    return None


def _spec_path_error(got: str) -> str:
    expected = _expected_mcp_coder_spec_path(got)
    if expected is not None:
        return (
            f"spec_path must be under .mcp-coder/specs/tasks/ (got: {got}). "
            f"Expected: {expected} — move the file from repo-root specs/ and retry."
        )
    return (
        f"spec_path must be under .mcp-coder/specs/tasks/ "
        f"(e.g. tasks/my-epic-01-core.md; got {got!r})"
    )


def normalize_spec_path_arg(spec_path: str | Path) -> str:
    """
    Normalize accepted spec_path forms to repo-relative under .mcp-coder/specs/tasks/.

    Accepts:
      - .mcp-coder/specs/tasks/foo.md
      - tasks/foo.md  (shorthand)
    """
    raw = str(spec_path).strip().replace("\\", "/").lstrip("/")
    if raw.startswith(".mcp-coder/specs/tasks/"):
        return raw
    if raw.startswith("tasks/"):
        return f".mcp-coder/specs/{raw}"
    if raw.startswith(".mcp-coder/specs/") and "/tasks/" in raw:
        return raw
    raise ValueError(_spec_path_error(raw))


def resolve_spec_path(workspace: str | Path, spec_path: str | Path) -> Path:
    """
    Resolve a repo-relative step task spec under .mcp-coder/specs/tasks/ only.

    Raises ValueError if the path escapes the specs tree or is not under tasks/.
    """
    ws = Path(workspace).resolve()
    normalized = normalize_spec_path_arg(spec_path)
    candidate = (ws / normalized).resolve()

    specs_root = workspace_specs_dir(ws).resolve()
    tasks_root = workspace_specs_tasks_dir(ws).resolve()
    try:
        candidate.relative_to(specs_root)
        candidate.relative_to(tasks_root)
    except ValueError as exc:
        raise ValueError(
            f"spec_path must be under {tasks_root.relative_to(ws)!s}/ "
            f"(got {spec_path!r})"
        ) from exc
    return candidate


def report_path_for_task_spec(task_spec: Path, *, workspace: str | Path) -> Path:
    """Parallel report file: specs/tasks/foo.md → specs/reports/foo.md."""
    ws = Path(workspace).resolve()
    specs_root = workspace_specs_dir(ws).resolve()
    rel = task_spec.resolve().relative_to(specs_root)
    if rel.parts[0] != TASKS_SUBDIR:
        raise ValueError(f"task spec must be under tasks/ (got {rel})")
    return specs_root / REPORTS_SUBDIR / Path(*rel.parts[1:])


def report_rel_path_for_task_spec(task_spec: Path, *, workspace: str | Path) -> str:
    report = report_path_for_task_spec(task_spec, workspace=workspace)
    return str(report.resolve().relative_to(Path(workspace).resolve()))


def resolve_epic_path(workspace: str | Path, epic_slug: str) -> Path:
    slug = epic_slug.strip().replace("\\", "/").strip("/")
    if not slug or "/" in slug or ".." in slug:
        raise ValueError(f"invalid epic slug: {epic_slug!r}")
    return workspace_specs_epics_dir(workspace) / f"{slug}.md"
