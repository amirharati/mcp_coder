"""Prompt role-rule fragment layer (P15-000)."""

from __future__ import annotations

import pytest

from core.context.role_rules import SHARED_RULES, build_role_rules


ROLES = (
    "planner",
    "reviewer",
    "clarity",
    "spec_validation",
    "builder",
    "supervisor_confirm",
    "supervisor_decision",
    "executor",
)


def test_build_role_rules_returns_shared_rules():
    for role in ROLES:
        rules = build_role_rules(role)
        for shared in SHARED_RULES:
            assert shared in rules


def test_build_role_rules_returns_role_specific_rules():
    samples = {
        "planner": "file touch order",
        "reviewer": "WEAK post-execution reviewer",
        "clarity": "genuinely catastrophic",
        "spec_validation": "advisory feedback",
        "builder": "executor-facing brief",
        "supervisor_confirm": "APPROVE|DENY|ABORT|ESCALATE",
        "supervisor_decision": "RERUN_AIDER|DONE|ESCALATE_HOST",
        "executor": "/read <path>",
    }
    for role, sample in samples.items():
        rules = build_role_rules(role)
        assert sample in rules
        for other_role in set(ROLES) - {role}:
            if other_role == "executor" and sample == "/read <path>":
                continue
            assert sample not in build_role_rules(other_role)


def test_build_role_rules_all_roles_supported():
    for role in ROLES:
        assert build_role_rules(role)


def test_build_role_rules_unknown_role_raises():
    with pytest.raises(ValueError):
        build_role_rules("cto")


def test_build_role_rules_executor_includes_pull_hint():
    rules = build_role_rules("executor")
    assert "/read" in rules
    assert "Respect the spec Files contract: edit only files in `files_edit`; do not expand edit scope." in rules


def test_build_role_rules_planner_includes_feasibility_rule():
    rules = build_role_rules("planner")
    assert (
        "Check that files mentioned in the plan exist in the candidate file list or spec Files contract before proposing them. Do not invent file paths."
        in rules
    )


def test_build_role_rules_reviewer_includes_spec_compliance_rule():
    rules = build_role_rules("reviewer")
    assert "verify the diff meets the spec Goal and Acceptance criteria" in rules
    assert "When in doubt: return `## LGTM`" in rules
