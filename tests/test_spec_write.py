from pathlib import Path

from core.specs.sections import (
    REPORT_STATUS_BLOCKED,
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


def test_run_log_includes_usage_summary(tmp_path: Path):
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
        usage_summary="- **usage:** model `gpt-4o-mini`; preflight ~100 tok; actual n/a; cost n/a",
    )

    sections = parse_sections(split_front_matter(report.read_text(encoding="utf-8"))[1])
    assert "**usage:**" in sections["Run log"]


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


# ---------------------------------------------------------------------------
# Scope expansion tests (P2-305)
# ---------------------------------------------------------------------------

def _base_kwargs(delegation_id: str = "del-1") -> dict:
    return dict(
        timestamp="2026-06-07T12:00:00Z",
        delegation_id=delegation_id,
        mcp_session_id="sess-abc",
        delegate_mode="implement",
        success=True,
        files_changed=["expense_splitter/cli.py"],
        output="done",
        error=None,
    )


def test_scope_expansion_discover_writes_section(tmp_path: Path):
    """discover + files_unexpected → Scope expansion section; Status stays delegated_ok."""
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        **_base_kwargs(),
        files_unexpected=["expense_splitter/utils.py", "expense_splitter/__init__.py"],
        edit_scope="discover",
    )

    text = report.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    sections = parse_sections(body)
    assert fm["status"] == REPORT_STATUS_DELEGATED_OK
    assert "## Scope expansion" in body
    assert "expense_splitter/utils.py" in sections["Scope expansion"]
    assert "expense_splitter/__init__.py" in sections["Scope expansion"]
    assert "discover" in sections["Scope expansion"]
    assert sections["Blockers / questions"].strip() == ""


def test_scope_expansion_strict_blocks_and_fills_sections(tmp_path: Path):
    """strict + scope_violations → blocked Status, Scope expansion with scope_violation, re-plan Blockers."""
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        **_base_kwargs(),
        scope_violations=["expense_splitter/utils.py"],
        edit_scope="strict",
    )

    text = report.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    sections = parse_sections(body)
    assert fm["status"] == REPORT_STATUS_BLOCKED
    assert f"`{REPORT_STATUS_BLOCKED}`" in sections["Status"]
    assert "## Scope expansion" in body
    assert "scope_violation" in sections["Scope expansion"]
    assert "expense_splitter/utils.py" in sections["Scope expansion"]
    assert "scope_violation" in sections["Blockers / questions"]
    assert "re-delegate" in sections["Blockers / questions"]
    assert "Re-delegate" in sections["Suggested next (hints only)"]


def test_scope_expansion_strict_includes_reverted_paths(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        **_base_kwargs(),
        scope_violations=["expense_splitter/utils.py"],
        edit_scope="strict",
        reverted_paths=["expense_splitter/utils.py"],
    )

    text = report.read_text(encoding="utf-8")
    _, body = split_front_matter(text)
    sections = parse_sections(body)
    assert "reverted" in sections["Scope expansion"]
    assert "expense_splitter/utils.py" in sections["Scope expansion"]


def test_scope_expansion_strict_revert_skipped_in_blockers(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        **_base_kwargs(),
        scope_violations=["expense_splitter/utils.py"],
        edit_scope="strict",
        revert_skipped=["expense_splitter/utils.py"],
    )

    _, body = split_front_matter(report.read_text(encoding="utf-8"))
    sections = parse_sections(body)
    assert "Revert skipped" in sections["Blockers / questions"]


def test_scope_expansion_clean_no_section(tmp_path: Path):
    """Both empty → no ## Scope expansion section at all."""
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        **_base_kwargs(),
        scope_violations=[],
        files_unexpected=[],
        edit_scope="strict",
    )

    text = report.read_text(encoding="utf-8")
    assert "## Scope expansion" not in text


def test_scope_expansion_strict_empty_violations_no_section(tmp_path: Path):
    """strict but no violations → no section; Status follows normal success."""
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        **_base_kwargs(),
        scope_violations=[],
        edit_scope="strict",
    )

    text = report.read_text(encoding="utf-8")
    fm, _ = split_front_matter(text)
    assert fm["status"] == REPORT_STATUS_DELEGATED_OK
    assert "## Scope expansion" not in text


def test_scope_expansion_discover_no_unexpected_no_section(tmp_path: Path):
    """discover with empty files_unexpected → no section."""
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        **_base_kwargs(),
        files_unexpected=[],
        edit_scope="discover",
    )

    assert "## Scope expansion" not in report.read_text(encoding="utf-8")


def test_run_log_includes_capability_warnings(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        **_base_kwargs(),
        capability_warnings=["capability_degraded:read_only_not_supported:pkg/core.py"],
    )

    sections = parse_sections(split_front_matter(report.read_text(encoding="utf-8"))[1])
    assert "**capability:**" in sections["Run log"]
    assert "capability_degraded:read_only_not_supported:pkg/core.py" in sections["Run log"]


def test_scope_expansion_idempotent(tmp_path: Path):
    """Calling twice with the same unexpected paths does not duplicate Scope expansion."""
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    kwargs = dict(
        **_base_kwargs("del-1"),
        files_unexpected=["expense_splitter/utils.py"],
        edit_scope="discover",
    )
    apply_post_delegation_report_updates(report, **kwargs)
    # Second call with same unexpected (different delegation_id to avoid run log dedup issues)
    kwargs["delegation_id"] = "del-2"
    apply_post_delegation_report_updates(report, **kwargs)

    text = report.read_text(encoding="utf-8")
    assert text.count("## Scope expansion") == 1
