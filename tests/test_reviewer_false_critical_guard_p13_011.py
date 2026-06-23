"""P13-011 — reviewer false-critical guard for risk promotion."""

from __future__ import annotations

from core.engine.reviewer_findings_classifier import (
    ClassifiedFinding,
    should_promote_finding_to_risk,
)
from core.state.project_state import ProjectState


def _apply_promotion(state: ProjectState, finding: ClassifiedFinding) -> None:
    changed_file_contents = {
        "habit_cli/models.py": (
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class Habit:\n"
            "    name: str\n"
        )
    }
    state.add_reviewer_finding(
        finding.text,
        finding.severity,
        "d-p13-011",
        files=list(changed_file_contents),
    )
    if should_promote_finding_to_risk(
        finding,
        changed_file_contents=changed_file_contents,
    ):
        state.add_risk(finding.text, finding.severity, "d-p13-011")


def test_false_missing_habit_critical_is_kept_in_summary_but_not_risks():
    state = ProjectState(project_key="tasks/p13-habit")
    finding = ClassifiedFinding(
        text="Habit dataclass not present in habit_cli/models.py",
        severity="critical",
    )

    _apply_promotion(state, finding)

    assert len(state.reviewer_findings_summary) == 1
    assert state.reviewer_findings_summary[0]["text"] == finding.text
    assert state.reviewer_findings_summary[0]["severity"] == "critical"
    assert state.open_risks == []


def test_real_critical_finding_still_promotes_to_risks():
    state = ProjectState(project_key="tasks/p13-habit")
    finding = ClassifiedFinding(
        text="CLI writes malformed JSON and breaks the public command contract",
        severity="critical",
    )

    _apply_promotion(state, finding)

    assert len(state.reviewer_findings_summary) == 1
    assert len(state.open_risks) == 1
    assert state.open_risks[0]["text"] == finding.text
    assert state.open_risks[0]["severity"] == "critical"


def test_missing_error_handling_phrase_is_not_treated_as_absent_symbol():
    finding = ClassifiedFinding(
        text="Missing error handling in Habit CLI flow",
        severity="notable",
    )

    assert should_promote_finding_to_risk(
        finding,
        changed_file_contents={
            "habit_cli/models.py": "class Habit:\n    name: str\n",
        },
    )
