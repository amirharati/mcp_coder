"""L2 context compiler: assemble_context() → ContextPackage."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from core.context.excerpts import (
    build_file_excerpt,
    read_full_max_bytes,
    write_excerpt_file,
)
from core.context.file_picker import CandidateFilesResult
from core.context.package import (
    COMPILER_VERSION,
    TIER_EDIT_FULL,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
)
from core.context.repo_map import build_repo_map_entries
from core.context.summary import estimate_tokens
from core.engine.git_diff import normalize_repo_path
from core.specs.delegation_policies import DelegationPolicies, load_delegation_policies
from core.specs.paths import resolve_spec_path
from core.specs.read import read_task_spec


def _normalize_path_list(paths: list[str]) -> list[str]:
    return sorted({normalize_repo_path(p) for p in paths if normalize_repo_path(p)})


def _is_git_repo(workspace: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False


def _is_path_tracked(workspace: Path, rel_path: str) -> bool | None:
    """True if tracked, False if untracked, None if git unavailable."""
    if not _is_git_repo(workspace):
        return None
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel_path],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return None


def _read_utf8_payload(abs_path: Path) -> tuple[str | None, int | None]:
    try:
        text = abs_path.read_text(encoding="utf-8")
        return text, len(text.encode("utf-8"))
    except (OSError, UnicodeDecodeError):
        return None, None


def _tier_for_path(path: str, files_edit: set[str], files_read: set[str]) -> str:
    if path in files_edit:
        return TIER_EDIT_FULL
    if path in files_read:
        return TIER_READ_FULL
    return TIER_READ_FULL


def _build_brief(
    *,
    task: str,
    context_summary: str | None,
    goal: str | None,
    constraints: str | None,
    entries: list[PathEntry],
) -> str:
    parts: list[str] = []
    task_line = task.strip()
    if task_line:
        parts.append(f"## Task\n{task_line}")
    summary = (context_summary or "").strip()
    if summary:
        parts.append(f"## Context\n{summary}")
    goal_text = (goal or "").strip()
    if goal_text:
        parts.append(f"## Goal\n{goal_text}")
    constraints_text = (constraints or "").strip()
    if constraints_text:
        parts.append(f"## Constraints\n{constraints_text}")
    if entries:
        lines = ["## Paths", ""]
        for entry in entries:
            lines.append(f"- `{entry.path}` — {entry.tier}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _bytes_by_tier(entries: list[PathEntry]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for entry in entries:
        totals[entry.tier] = totals.get(entry.tier, 0) + (entry.bytes or 0)
    return totals


def assemble_context(
    *,
    workspace: Path,
    spec_path: Path | str | None,
    target_files: list[str],
    task: str,
    context_summary: str | None,
    policies: DelegationPolicies | None,
    picker_result: CandidateFilesResult | None = None,
    include_repo_map: bool = False,
) -> ContextPackage:
    """Build a ContextPackage from workspace, optional spec, and MCP hints.

    When picker_result is set (P4-001a), discovered read paths join the
    materialized contract (read tiers only — D-P4-10), repo-map entries are
    appended when include_repo_map=True, and candidate_files audit metadata
    is added. When None, behavior is identical to the pre-picker pipeline.
    """
    ws = workspace.resolve()
    hint_paths = _normalize_path_list(target_files)
    max_full_bytes = read_full_max_bytes()

    loaded_policies: DelegationPolicies | None = None
    goal: str | None = None
    constraints: str | None = None
    tier_map: dict[str, str] = {}
    contract_paths: list[str] = []

    if spec_path is not None:
        resolved = resolve_spec_path(ws, spec_path)
        spec = read_task_spec(resolved, workspace=ws)
        loaded_policies = load_delegation_policies(
            spec.front_matter,
            spec.sections.get("Files", ""),
        )
        goal = spec.sections.get("Goal")
        constraints = spec.sections.get("Constraints")
        files_edit = set(loaded_policies.files_edit)
        files_read = set(loaded_policies.files_read)
        contract_paths = loaded_policies.all_paths
        for path in contract_paths:
            tier_map[path] = _tier_for_path(path, files_edit, files_read)
        metadata_hint_paths = sorted(set(hint_paths) - set(contract_paths))
    elif policies is not None:
        loaded_policies = policies
        files_edit = set(policies.files_edit)
        files_read = set(policies.files_read)
        contract_paths = sorted(set(policies.all_paths) | set(hint_paths))
        for path in contract_paths:
            tier_map[path] = _tier_for_path(path, files_edit, files_read)
        metadata_hint_paths = sorted(set(hint_paths) - set(policies.all_paths))
    else:
        contract_paths = hint_paths
        for path in contract_paths:
            tier_map[path] = TIER_READ_FULL
        metadata_hint_paths = hint_paths

    if picker_result is not None and picker_result.discovered_read:
        # Discovered paths are read context only — never edit-full (D-P4-10).
        extra = [p for p in picker_result.discovered_read if p not in tier_map]
        for path in extra:
            tier_map[path] = TIER_READ_FULL
        contract_paths = sorted(set(contract_paths) | set(extra))
        metadata_hint_paths = sorted(set(metadata_hint_paths) - set(extra))

    entries: list[PathEntry] = []
    missing_paths: list[str] = []
    untracked_paths: list[str] = []
    excerpt_paths: list[str] = []
    truncations: list[dict[str, Any]] = []
    git_available = _is_git_repo(ws)

    for path in sorted(contract_paths):
        tier = tier_map.get(path, TIER_READ_FULL)
        abs_path = ws / path

        if not abs_path.is_file():
            missing_paths.append(path)
            entries.append(PathEntry(path=path, tier=tier, bytes=None, payload=None))
            continue

        payload: str | None = None
        byte_count: int | None = None
        entry_excerpt_path: str | None = None

        if tier == TIER_EDIT_FULL:
            payload, byte_count = _read_utf8_payload(abs_path)
        elif tier == TIER_READ_FULL:
            file_size = abs_path.stat().st_size
            if file_size > max_full_bytes:
                result = build_file_excerpt(
                    abs_path,
                    rel_path=path,
                    max_full_bytes=max_full_bytes,
                )
                if result is not None and result.strategy != "full_small":
                    exc_rel = write_excerpt_file(ws, path, result.text)
                    tier = TIER_READ_EXCERPT
                    payload = result.text
                    byte_count = result.excerpt_bytes
                    entry_excerpt_path = exc_rel
                    excerpt_paths.append(exc_rel)
                    truncations.append(
                        {
                            "reason": "read_full_max_bytes",
                            "path": path,
                            "bytes_dropped": result.full_bytes - result.excerpt_bytes,
                        }
                    )
                else:
                    payload, byte_count = _read_utf8_payload(abs_path)
            else:
                payload, byte_count = _read_utf8_payload(abs_path)

        entries.append(
            PathEntry(
                path=path,
                tier=tier,
                bytes=byte_count,
                payload=payload,
                excerpt_path=entry_excerpt_path,
            )
        )

        if not git_available:
            untracked_paths.append(path)
        else:
            tracked = _is_path_tracked(ws, path)
            if tracked is False:
                untracked_paths.append(path)

    repo_map_entries: list[PathEntry] = []
    if picker_result is not None and include_repo_map:
        exclude = set(picker_result.ranked_paths) | {e.path for e in entries}
        repo_map_entries = build_repo_map_entries(ws, exclude_paths=exclude)

    # Brief lists contract/read entries only; map-only entries are rendered
    # by the adapter (translate_context_package) as a compact repo-map block.
    brief = _build_brief(
        task=task,
        context_summary=context_summary,
        goal=goal,
        constraints=constraints,
        entries=entries,
    )
    entries.extend(repo_map_entries)

    if picker_result is not None and picker_result.suggested_edit_paths:
        suggested = ", ".join(f"`{p}`" for p in picker_result.suggested_edit_paths)
        brief = brief.rstrip() + (
            f"\n\nSuggested edit paths (not in spec contract): {suggested}"
        )

    payload_text = "".join(e.payload or "" for e in entries)
    token_estimate = estimate_tokens(brief + payload_text)

    metadata: dict[str, Any] = {
        "bytes_by_tier": _bytes_by_tier(entries),
        "hint_paths": metadata_hint_paths,
        "missing_paths": sorted(missing_paths),
        "untracked_paths": sorted(untracked_paths),
        "excerpt_paths": excerpt_paths,
        "truncations": truncations,
        "token_estimate_preflight": token_estimate,
        "compiler_version": COMPILER_VERSION,
    }
    if picker_result is not None:
        metadata["candidate_files"] = picker_result.to_audit_dict()
        metadata["repo_map_count"] = len(repo_map_entries)
        metadata["context_builder_enabled"] = True

    return ContextPackage(
        brief=brief,
        entries=entries,
        policies=loaded_policies,
        metadata=metadata,
    )
