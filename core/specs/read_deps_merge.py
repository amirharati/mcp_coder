"""Merge spec files_read into effective target_files (backend-neutral)."""

from __future__ import annotations

from dataclasses import dataclass

from core.engine.git_diff import normalize_repo_path
from core.specs.files_contract import (
    _is_placeholder_path,
    build_contract_warnings,
    paths_missing_from_target,
)


@dataclass
class ReadDepsMergeResult:
    effective_target_files: list[str]
    auto_merged_read_paths: list[str]


def merge_spec_read_into_target(
    *,
    files_read: list[str],
    files_edit: list[str],
    target_files: list[str],
    enabled: bool,
) -> ReadDepsMergeResult:
    """Union planner target_files with missing read paths when enabled."""
    del files_edit  # edit paths are never auto-merged; kept for call-site clarity
    normalized_targets = {normalize_repo_path(f) for f in target_files}
    if not enabled:
        effective = sorted(normalized_targets)
        return ReadDepsMergeResult(
            effective_target_files=effective,
            auto_merged_read_paths=[],
        )

    auto_merged = sorted(
        normalize_repo_path(p)
        for p in files_read
        if not _is_placeholder_path(p)
        and normalize_repo_path(p) not in normalized_targets
    )
    effective = sorted(normalized_targets | set(auto_merged))
    return ReadDepsMergeResult(
        effective_target_files=effective,
        auto_merged_read_paths=auto_merged,
    )


def resolve_spec_read_deps(
    *,
    files_edit: list[str],
    files_read: list[str],
    all_paths: list[str],
    target_files: list[str],
    auto_merge_enabled: bool,
) -> tuple[ReadDepsMergeResult, list[str], list[str]]:
    """Merge read-deps and compute contract warnings for implement + spec."""
    merge_result = merge_spec_read_into_target(
        files_read=files_read,
        files_edit=files_edit,
        target_files=target_files,
        enabled=auto_merge_enabled,
    )
    if auto_merge_enabled:
        spec_files_missing = paths_missing_from_target(files_edit, target_files)
    else:
        spec_files_missing = paths_missing_from_target(all_paths, target_files)
    contract_warnings = build_contract_warnings(spec_files_missing)
    return merge_result, spec_files_missing, contract_warnings
