"""Workspace task specs under .mcp-coder/specs/ (experimental)."""

from core.specs.bootstrap import ensure_task_report, ensure_workspace_spec_layout
from core.specs.paths import (
    bundled_spec_epic_template_path,
    bundled_spec_report_template_path,
    bundled_spec_template_path,
    normalize_spec_path_arg,
    report_path_for_task_spec,
    report_rel_path_for_task_spec,
    resolve_epic_path,
    resolve_spec_path,
    workspace_spec_epic_template_path,
    workspace_spec_report_template_path,
    workspace_spec_template_path,
    workspace_specs_dir,
    workspace_specs_epics_dir,
    workspace_specs_reports_dir,
    workspace_specs_tasks_dir,
)
from core.specs.files_contract import (
    FilesContract,
    build_contract_warnings,
    contract_paths_missing_from_target,
    parse_files_contract,
)
from core.specs.read import read_task_spec
from core.specs.write import (
    apply_post_delegation_report_updates,
    apply_post_delegation_spec_updates,
)

__all__ = [
    "FilesContract",
    "apply_post_delegation_report_updates",
    "build_contract_warnings",
    "contract_paths_missing_from_target",
    "apply_post_delegation_spec_updates",
    "bundled_spec_epic_template_path",
    "bundled_spec_report_template_path",
    "bundled_spec_template_path",
    "ensure_task_report",
    "ensure_workspace_spec_layout",
    "normalize_spec_path_arg",
    "parse_files_contract",
    "read_task_spec",
    "report_path_for_task_spec",
    "report_rel_path_for_task_spec",
    "resolve_epic_path",
    "resolve_spec_path",
    "workspace_spec_epic_template_path",
    "workspace_spec_report_template_path",
    "workspace_spec_template_path",
    "workspace_specs_dir",
    "workspace_specs_epics_dir",
    "workspace_specs_reports_dir",
    "workspace_specs_tasks_dir",
]
