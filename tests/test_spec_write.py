from pathlib import Path

from core.specs.sections import (
    REPORT_STATUS_DELEGATED_OK,
    REPORT_STATUS_REVIEWED,
    parse_sections,
    split_front_matter,
)
from core.specs.write import apply_post_delegation_report_updates

REPORT_SAMPLE = """---
spec_id: demo
task_spec: .mcp-coder/specs/tasks/demo.md
status: open
---

# Delegation report

## Status

`open`

## Run log

## Worker feedback

## Blockers / questions

old blocker

## Suggested next (hints only)

old hint
"""


def test_apply_post_delegation_implement_success(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        timestamp="2026-06-05T12:00:00Z",
        delegation_id="abc-123",
        mcp_session_id="sess-456",
        delegate_mode="implement",
        success=True,
        files_changed=["x.py"],
        output="Applied edit",
        error=None,
        task_spec=".mcp-coder/specs/tasks/demo.md",
    )

    text = report.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    sections = parse_sections(body)
    assert f"`{REPORT_STATUS_DELEGATED_OK}`" in sections["Status"]
    assert fm["status"] == REPORT_STATUS_DELEGATED_OK
    assert "abc-123" in sections["Run log"]
    assert "**mode:** implement" in sections["Run log"]
    assert sections["Blockers / questions"].strip() == ""


def test_apply_post_delegation_review_appends_worker_feedback(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        timestamp="2026-06-05T12:00:00Z",
        delegation_id="rev-1",
        mcp_session_id="sess-456",
        delegate_mode="review",
        success=True,
        files_changed=[],
        output="**Questions:** None\n**Readiness:** READY_TO_IMPLEMENT",
        error=None,
        task_spec=".mcp-coder/specs/tasks/demo.md",
    )

    text = report.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    sections = parse_sections(body)
    assert fm["status"] == REPORT_STATUS_REVIEWED
    assert "READY_TO_IMPLEMENT" in sections["Worker feedback"]
    assert "rev-1" in sections["Worker feedback"]


def test_apply_post_delegation_failure_fills_blockers(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        timestamp="2026-06-05T12:00:00Z",
        delegation_id="fail-1",
        mcp_session_id="sess-789",
        delegate_mode="implement",
        success=False,
        files_changed=[],
        output="bad format",
        error="edit format error",
    )

    text = report.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    sections = parse_sections(body)
    assert fm["status"] == "blocked"
    assert "edit format error" in sections["Blockers / questions"]
