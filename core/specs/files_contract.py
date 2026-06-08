"""Parse task spec Files section and compare to delegate target_files."""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.engine.git_diff import normalize_repo_path

BULLET_RE = re.compile(r"^\s*-\s+(.+?)\s*$", re.MULTILINE)
PATH_IN_BACKTICKS_RE = re.compile(r"`([^`]+)`")
EDIT_SUBSECTION_RE = re.compile(r"^###\s+Edit\b", re.MULTILINE)
READ_SUBSECTION_RE = re.compile(r"^###\s+Read\b", re.MULTILINE)
SUBSECTION_SPLIT_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)

_PLACEHOLDER_PATHS = frozenset({"(none)", "none", "n/a", "na", "-"})


@dataclass
class FilesContract:
    edit: list[str]
    read: list[str]
    all_paths: list[str]


def _is_placeholder_path(path: str) -> bool:
    """True for planner placeholders — not real repo paths."""
    normalized = path.strip().lower()
    if not normalized:
        return True
    return normalized in _PLACEHOLDER_PATHS


def _extract_path_from_bullet_line(line: str) -> str | None:
    match = BULLET_RE.match(line)
    if not match:
        return None
    content = match.group(1).strip()
    tick = PATH_IN_BACKTICKS_RE.search(content)
    if tick:
        path = normalize_repo_path(tick.group(1))
    else:
        for sep in (" — ", " - "):
            if sep in content:
                content = content.split(sep, 1)[0].strip()
                break
        path = content.strip("`").strip()
        if not path:
            return None
        path = normalize_repo_path(path)
    if _is_placeholder_path(path):
        return None
    return path


def _parse_bullet_paths(text: str) -> list[str]:
    paths: list[str] = []
    for line in text.splitlines():
        path = _extract_path_from_bullet_line(line)
        if path:
            paths.append(path)
    return paths


def parse_files_contract(files_section: str) -> FilesContract:
    """Parse ## Files section text into edit/read contract paths."""
    text = (files_section or "").strip()
    if not text:
        return FilesContract(edit=[], read=[], all_paths=[])

    has_edit = bool(EDIT_SUBSECTION_RE.search(text))
    has_read = bool(READ_SUBSECTION_RE.search(text))

    if not has_edit and not has_read:
        paths = sorted(set(_parse_bullet_paths(text)))
        return FilesContract(edit=paths, read=[], all_paths=paths)

    edit: list[str] = []
    read: list[str] = []
    parts = SUBSECTION_SPLIT_RE.split(text)
    idx = 1
    while idx < len(parts):
        title = parts[idx].strip()
        body = parts[idx + 1] if idx + 1 < len(parts) else ""
        if title.startswith("Edit"):
            edit.extend(_parse_bullet_paths(body))
        elif title.startswith("Read"):
            read.extend(_parse_bullet_paths(body))
        idx += 2

    edit_unique = sorted(set(edit))
    read_unique = sorted(set(read))
    all_paths = sorted(set(edit_unique + read_unique))
    return FilesContract(edit=edit_unique, read=read_unique, all_paths=all_paths)


def paths_missing_from_target(
    contract_paths: list[str],
    target_files: list[str],
) -> list[str]:
    """Sorted contract paths not in normalized target_files."""
    targets = {normalize_repo_path(f) for f in target_files}
    missing = [p for p in contract_paths if p not in targets]
    return sorted(missing)


def contract_paths_missing_from_target(
    contract: FilesContract,
    target_files: list[str],
) -> list[str]:
    """Sorted paths in contract.all_paths but not in normalized target_files."""
    return paths_missing_from_target(contract.all_paths, target_files)


def build_contract_warnings(missing_paths: list[str]) -> list[str]:
    if not missing_paths:
        return []
    joined = ", ".join(missing_paths)
    return [f"Spec Files lists paths not in target_files: {joined}"]
