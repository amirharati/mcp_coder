"""Delegation outcome labels when spec_path is used."""

from __future__ import annotations

from core.specs.modes import DELEGATE_MODE_REVIEW

OUTCOME_INVALID_SPEC = "invalid_spec"
OUTCOME_SUCCESS = "success"
OUTCOME_PARTIAL = "partial"
OUTCOME_FAILED = "failed"
OUTCOME_NEEDS_INPUT = "needs_input"
OUTCOME_REVIEW = "review"
OUTCOME_SCOPE_VIOLATION = "scope_violation"


def compute_spec_outcome(
    *,
    invalid_spec: bool = False,
    success: bool = False,
    files_changed: list[str],
    blockers_written: bool = False,
    delegate_mode: str = "implement",
) -> str:
    if invalid_spec:
        return OUTCOME_INVALID_SPEC
    if delegate_mode == DELEGATE_MODE_REVIEW:
        return OUTCOME_REVIEW if success else OUTCOME_FAILED
    if success and files_changed:
        return OUTCOME_SUCCESS
    if success and not files_changed:
        return OUTCOME_PARTIAL
    if not success and blockers_written:
        return OUTCOME_NEEDS_INPUT
    return OUTCOME_FAILED


def apply_scope_outcome(
    outcome: str,
    *,
    edit_scope: str,
    scope_violations: list[str],
) -> str:
    """If strict and violations non-empty, return scope_violation; else passthrough."""
    if edit_scope == "strict" and scope_violations:
        return OUTCOME_SCOPE_VIOLATION
    return outcome
