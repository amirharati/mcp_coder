from __future__ import annotations

# Pre-empt circular import chain by importing a module that resolves it
from core.engine.supervisor import build_supervisor_prompt  # noqa: F401

from core.state.project_state import ProjectState


def test_to_summary_empty_returns_empty_string():
    """Fresh ProjectState (all lists empty) returns empty string."""
    ps = ProjectState(project_key="test")
    assert ps.to_summary() == ""


def test_to_summary_includes_decisions_tail():
    """Last 5 decisions only; each truncated to 160 chars; delegation_id shown as first 8 chars."""
    ps = ProjectState(project_key="test")
    for i in range(7):
        ps.add_decision(f"Decision number {i} with some extra text to make it longer than needed " * 3,
                        delegation_id=f"abcdefg{i}-long-suffix")
    result = ps.to_summary()
    assert "### Recent decisions" in result
    # Decision 2-6 (the last 5 of 7) should be present
    assert "(abcdefg2)" in result
    assert "(abcdefg6)" in result
    # Decision 0 and 1 should be dropped (only last 5)
    assert "(abcdefg0)" not in result
    assert "(abcdefg1)" not in result
    # Each text should be truncated
    for line in result.splitlines():
        if line.startswith("- ") and " (abc" in line:
            # text before the " (" part
            text_part = line[2:line.rindex(" (")]
            assert len(text_part) <= 160


def test_to_summary_includes_hot_areas_capped_at_10():
    """First 10 hot areas only."""
    ps = ProjectState(project_key="test")
    ps.hot_areas = [f"path/to/file_{i}.py" for i in range(15)]
    result = ps.to_summary()
    assert "### Hot areas" in result
    assert "path/to/file_0.py" in result
    assert "path/to/file_9.py" in result
    assert "path/to/file_10.py" not in result


def test_to_summary_includes_open_risks_tail():
    """Last 5 risks, severity prefixed, text truncated to 160."""
    ps = ProjectState(project_key="test")
    for i in range(7):
        ps.add_risk(f"Risk {i}: " + ("long description " * 20),
                    severity="notable" if i % 2 == 0 else "advisory",
                    source_delegation_id=f"deleg-{i}")
    result = ps.to_summary()
    assert "### Open risks" in result
    assert "[notable]" in result
    # Risk 2-6 should be present
    assert "Risk 2:" in result
    assert "Risk 6:" in result
    # Risk 0-1 should not
    assert "Risk 0:" not in result
    assert "Risk 1:" not in result


def test_to_summary_includes_reviewer_findings_tail():
    """Last 5 findings, severity prefixed, text truncated to 160."""
    ps = ProjectState(project_key="test")
    for i in range(7):
        ps.add_reviewer_finding(f"Finding {i}: " + ("detail " * 20),
                                severity="advisory" if i % 2 == 0 else "critical",
                                delegation_id=f"deleg-{i}")
    result = ps.to_summary()
    assert "### Reviewer findings (tail)" in result
    assert "[critical]" in result
    assert "Finding 2:" in result
    assert "Finding 6:" in result
    assert "Finding 0:" not in result
    assert "Finding 1:" not in result


def test_to_summary_skips_empty_text_entries():
    """Decisions/risks/findings with empty text are skipped."""
    ps = ProjectState(project_key="test")
    ps.decisions.append({"text": "", "delegation_id": "deadbeef-long", "timestamp": "2026-01-01T00:00:00Z"})
    ps.decisions.append({"text": "real decision", "delegation_id": "cafebabe-long", "timestamp": "2026-01-02T00:00:00Z"})
    result = ps.to_summary()
    # The empty decision should be skipped, only the real one rendered
    assert "real decision" in result
    assert "(deadbeef" not in result  # empty-text decision omitted
    assert "(cafebabe" in result  # real decision present


def test_to_summary_omits_last_delegation_and_last_updated():
    """The summary should not include last_delegation or last_updated."""
    ps = ProjectState(project_key="test")
    ps.last_delegation = "deleg-123"
    ps.last_updated = "2026-06-24T00:00:00Z"
    ps.add_decision("a decision", delegation_id="deleg-abc")
    result = ps.to_summary()
    assert "deleg-123" not in result
    assert "2026-06-24" not in result


def test_to_summary_partial_content_renders_only_populated_sections():
    """If only decisions have content, only that section renders."""
    ps = ProjectState(project_key="test")
    ps.add_decision("sole decision", delegation_id="deleg-xyz")
    result = ps.to_summary()
    assert "### Recent decisions" in result
    assert "### Hot areas" not in result
    assert "### Open risks" not in result
    assert "### Reviewer findings" not in result
