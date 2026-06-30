"""Delegation policies from task spec YAML front matter + markdown Files fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.engine.git_diff import normalize_repo_path
from core.specs.files_contract import parse_files_contract

EDIT_SCOPE_DISCOVER = "discover"
EDIT_SCOPE_STRICT = "strict"
EDIT_SCOPES = frozenset({EDIT_SCOPE_DISCOVER, EDIT_SCOPE_STRICT})

UNTRACKED_POLICY_MATERIALIZE = "materialize"
UNTRACKED_POLICY_REQUIRE_DECLARED = "require_declared"
UNTRACKED_POLICY_BLOCK = "block"
UNTRACKED_POLICIES = frozenset(
    {UNTRACKED_POLICY_MATERIALIZE, UNTRACKED_POLICY_REQUIRE_DECLARED, UNTRACKED_POLICY_BLOCK}
)


class PolicyValidationError(ValueError):
    """Invalid delegation policy values in spec front matter."""


@dataclass
class DelegationPolicies:
    files_edit: list[str]
    files_read: list[str]
    files_delete: list[str]
    edit_scope: str
    allow_create: bool
    untracked_policy: str
    all_paths: list[str]

    def to_response_dict(self) -> dict[str, Any]:
        return {
            "files_edit": self.files_edit,
            "files_read": self.files_read,
            "files_delete": self.files_delete,
            "edit_scope": self.edit_scope,
            "allow_create": self.allow_create,
            "untracked_policy": self.untracked_policy,
        }


def _normalize_path_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        path = normalize_repo_path(value.strip())
        return [path] if path else []
    if isinstance(value, list):
        paths: list[str] = []
        for item in value:
            if isinstance(item, str):
                path = normalize_repo_path(item.strip())
                if path:
                    paths.append(path)
        return sorted(set(paths))
    raise PolicyValidationError(
        f"files_edit/files_read must be a list of paths (got {type(value).__name__})"
    )


def _yaml_path_list(front_matter: dict[str, Any], key: str) -> list[str] | None:
    if key not in front_matter:
        return None
    paths = _normalize_path_list(front_matter[key])
    return paths if paths else None


def _parse_bool(value: Any, *, default: bool, field: str) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    raise PolicyValidationError(f"{field} must be a boolean (got {value!r})")


def _parse_edit_scope(value: Any) -> str:
    if value is None:
        return EDIT_SCOPE_STRICT
    if not isinstance(value, str):
        raise PolicyValidationError(
            f"edit_scope must be {EDIT_SCOPE_DISCOVER!r} or {EDIT_SCOPE_STRICT!r}"
        )
    scope = value.strip().lower()
    if scope not in EDIT_SCOPES:
        raise PolicyValidationError(
            f"edit_scope must be {EDIT_SCOPE_DISCOVER!r} or {EDIT_SCOPE_STRICT!r} "
            f"(got {value!r})"
        )
    return scope


def _parse_untracked_policy(value: Any) -> str:
    if value is None:
        return UNTRACKED_POLICY_MATERIALIZE
    if not isinstance(value, str):
        raise PolicyValidationError(
            "untracked_policy must be materialize, require_declared, or block"
        )
    policy = value.strip().lower()
    if policy not in UNTRACKED_POLICIES:
        raise PolicyValidationError(
            "untracked_policy must be materialize, require_declared, or block "
            f"(got {value!r})"
        )
    return policy


def load_delegation_policies(
    front_matter: dict[str, Any],
    files_section: str,
) -> DelegationPolicies:
    """YAML lists first; markdown Files fallback; apply defaults."""
    md_contract = parse_files_contract(files_section)

    yaml_edit = _yaml_path_list(front_matter, "files_edit")
    yaml_read = _yaml_path_list(front_matter, "files_read")
    yaml_delete = _yaml_path_list(front_matter, "files_delete")

    files_edit = yaml_edit if yaml_edit is not None else md_contract.edit
    files_read = yaml_read if yaml_read is not None else md_contract.read
    files_delete = yaml_delete if yaml_delete is not None else md_contract.delete
    all_paths = sorted(set(files_edit + files_read + files_delete))

    return DelegationPolicies(
        files_edit=files_edit,
        files_read=files_read,
        files_delete=files_delete,
        edit_scope=_parse_edit_scope(front_matter.get("edit_scope")),
        allow_create=_parse_bool(
            front_matter.get("allow_create"), default=True, field="allow_create"
        ),
        untracked_policy=_parse_untracked_policy(front_matter.get("untracked_policy")),
        all_paths=all_paths,
    )


def compute_scope_violations(
    files_changed: list[str],
    files_edit: list[str],
    files_delete: list[str] | None = None,
    files_read: list[str] | None = None,
) -> list[str]:
    """Sorted normalized paths in files_changed not in files_edit ∪ files_delete ∪ files_read."""
    allowed = {normalize_repo_path(p) for p in files_edit}
    allowed.update(normalize_repo_path(p) for p in (files_delete or []))
    allowed.update(normalize_repo_path(p) for p in (files_read or []))
    violations: list[str] = []
    for path in files_changed:
        norm = normalize_repo_path(path)
        if norm and norm not in allowed:
            violations.append(norm)
    return sorted(set(violations))


def build_files_delete_prompt_block(files_delete: list[str]) -> str | None:
    """Executor prompt block listing engine-managed delete targets."""
    paths = sorted(
        {normalize_repo_path(p) for p in files_delete if normalize_repo_path(p)}
    )
    if not paths:
        return None
    lines = [
        "### Files to be deleted (engine-managed)",
        "The following files WILL be removed by the engine after you finish. Do NOT",
        "edit, empty, or rewrite them — that wastes turns. Only update references to",
        "them in your edit files (e.g. remove re-exports, imports, registrations).",
    ]
    lines.extend(f"- `{p}`" for p in paths)
    return "\n".join(lines)


def build_allowed_paths_prompt_block(contract_paths: list[str] | None) -> str | None:
    paths = sorted(
        {
            normalize_repo_path(p.replace("\\", "/").lstrip("./"))
            for p in (contract_paths or [])
            if normalize_repo_path(p.replace("\\", "/").lstrip("./"))
        }
    )
    if not paths:
        return None
    return "### Allowed paths\n" + "\n".join(f"- `{p}`" for p in paths)


def append_executor_contract_prompt_blocks(
    prompt: str,
    *,
    contract_paths: list[str] | None,
    files_delete: list[str] | None = None,
) -> str:
    """Append allowed-path and engine-managed delete blocks to the executor prompt."""
    blocks: list[str] = []
    allowed = build_allowed_paths_prompt_block(contract_paths)
    if allowed:
        blocks.append(allowed)
    delete_block = build_files_delete_prompt_block(files_delete or [])
    if delete_block:
        blocks.append(delete_block)
    if not blocks:
        return prompt
    suffix = "\n\n---\n\n" + "\n\n".join(blocks)
    return prompt + suffix if prompt.strip() else suffix.lstrip()
