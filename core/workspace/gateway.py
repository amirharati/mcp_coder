from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.workspace.revert import revert_to_before
from core.workspace.snapshot import is_snapshot_enabled


@dataclass
class PostGatewayResult:
    scope_violations: list[str]
    reverted_paths: list[str]
    revert_skipped: list[str]
    gateway_applied: bool


def apply_post_delegation_gateway(
    *,
    workspace: str | Path,
    delegation_id: str,
    delegate_mode: str,
    edit_scope: str | None,
    files_changed: list[str],
    files_edit: list[str],
    files_delete: list[str] | None = None,
) -> PostGatewayResult:
    """
    Post-delegation strict gateway: compute scope violations and auto-revert when snapshot on.

    Discover mode and review mode are no-ops (no violations computed here).
    """
    from core.specs.delegation_policies import EDIT_SCOPE_STRICT, compute_scope_violations
    from core.specs.modes import DELEGATE_MODE_IMPLEMENT

    if delegate_mode != DELEGATE_MODE_IMPLEMENT or edit_scope != EDIT_SCOPE_STRICT:
        return PostGatewayResult(
            scope_violations=[],
            reverted_paths=[],
            revert_skipped=[],
            gateway_applied=False,
        )

    violations = compute_scope_violations(
        files_changed, files_edit, files_delete=files_delete
    )
    if not violations:
        return PostGatewayResult(
            scope_violations=[],
            reverted_paths=[],
            revert_skipped=[],
            gateway_applied=False,
        )

    if not is_snapshot_enabled():
        return PostGatewayResult(
            scope_violations=violations,
            reverted_paths=[],
            revert_skipped=list(violations),
            gateway_applied=False,
        )

    reverted = revert_to_before(workspace, delegation_id, violations)
    reverted_set = set(reverted)
    skipped = sorted(path for path in violations if path not in reverted_set)

    return PostGatewayResult(
        scope_violations=violations,
        reverted_paths=reverted,
        revert_skipped=skipped,
        gateway_applied=True,
    )
