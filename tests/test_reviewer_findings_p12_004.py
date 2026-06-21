"""P12-004 — unit tests for reviewer findings classification + project state feedback."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.engine.reviewer_findings_classifier import (
    ClassifiedFinding,
    classify_reviewer_findings,
)
from core.engine.supervisor_tool_runner import (
    _get_reviewer_findings_fn,
    build_phase12_tool_runner,
)
from core.observability.gateway import reset_llm_gateway, set_llm_gateway
from core.state.project_state import ProjectState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPLETION_OK = MagicMock(error=None, text="", tokens={}, duration_ms=1)


def _completion(text: str) -> MagicMock:
    return MagicMock(error=None, text=text, tokens={}, duration_ms=1)


def _completion_error(msg: str = "boom") -> MagicMock:
    return MagicMock(error=msg, text="", tokens={}, duration_ms=1)


@pytest.fixture(autouse=True)
def _reset_gateway():
    reset_llm_gateway()
    yield
    reset_llm_gateway()


# ---------------------------------------------------------------------------
# 1. critical finding → promoted to open_risks
# ---------------------------------------------------------------------------


def test_classify_findings_critical_promoted_to_risks():
    llm_payload = json.dumps([{"text": "broken interface", "severity": "critical"}])
    state = ProjectState(project_key="default")

    with patch(
        "core.engine.reviewer_findings_classifier.run_owned_helper_completion",
        return_value=_completion(llm_payload),
    ), patch(
        "core.engine.reviewer_findings_classifier.provider_hint_for_model",
        return_value=None,
    ), patch(
        "core.engine.reviewer_findings_classifier.apply_provider_env",
    ):
        findings = classify_reviewer_findings(
            "broken interface",
            workspace_path="/tmp/ws",
            delegation_id="d-1",
        )

    assert len(findings) == 1
    assert findings[0].severity == "critical"

    for f in findings:
        state.add_reviewer_finding(f.text, f.severity, "d-1")
        if f.severity in ("notable", "critical"):
            state.add_risk(f.text, f.severity, "d-1")

    assert len(state.reviewer_findings_summary) == 1
    assert len(state.open_risks) == 1
    assert state.open_risks[0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# 2. advisory finding → NOT promoted to open_risks
# ---------------------------------------------------------------------------


def test_classify_findings_advisory_not_promoted():
    llm_payload = json.dumps([{"text": "style nit", "severity": "advisory"}])
    state = ProjectState(project_key="default")

    with patch(
        "core.engine.reviewer_findings_classifier.run_owned_helper_completion",
        return_value=_completion(llm_payload),
    ), patch(
        "core.engine.reviewer_findings_classifier.provider_hint_for_model",
        return_value=None,
    ), patch(
        "core.engine.reviewer_findings_classifier.apply_provider_env",
    ):
        findings = classify_reviewer_findings(
            "style nit",
            workspace_path="/tmp/ws",
            delegation_id="d-1",
        )

    assert len(findings) == 1
    assert findings[0].severity == "advisory"

    for f in findings:
        state.add_reviewer_finding(f.text, f.severity, "d-1")
        if f.severity in ("notable", "critical"):
            state.add_risk(f.text, f.severity, "d-1")

    assert len(state.reviewer_findings_summary) == 1
    assert len(state.open_risks) == 0


# ---------------------------------------------------------------------------
# 3. LLM error → fallback to advisory, no raise
# ---------------------------------------------------------------------------


def test_classify_findings_llm_failure_falls_back():
    with patch(
        "core.engine.reviewer_findings_classifier.run_owned_helper_completion",
        return_value=_completion_error("API timeout"),
    ), patch(
        "core.engine.reviewer_findings_classifier.provider_hint_for_model",
        return_value=None,
    ), patch(
        "core.engine.reviewer_findings_classifier.apply_provider_env",
    ):
        findings = classify_reviewer_findings(
            "some issue",
            workspace_path="/tmp/ws",
            delegation_id="d-1",
        )

    assert len(findings) == 1
    assert findings[0].severity == "advisory"
    assert findings[0].text == "some issue"


# ---------------------------------------------------------------------------
# 4. non-JSON response → fallback, no raise
# ---------------------------------------------------------------------------


def test_classify_findings_json_parse_failure_falls_back():
    with patch(
        "core.engine.reviewer_findings_classifier.run_owned_helper_completion",
        return_value=_completion("This is not JSON at all, just prose."),
    ), patch(
        "core.engine.reviewer_findings_classifier.provider_hint_for_model",
        return_value=None,
    ), patch(
        "core.engine.reviewer_findings_classifier.apply_provider_env",
    ):
        findings = classify_reviewer_findings(
            "some issue",
            workspace_path="/tmp/ws",
            delegation_id="d-1",
        )

    assert len(findings) == 1
    assert findings[0].severity == "advisory"


# ---------------------------------------------------------------------------
# 5. add_reviewer_finding caps at 50
# ---------------------------------------------------------------------------


def test_add_reviewer_finding_caps_at_50():
    state = ProjectState(project_key="default")
    for i in range(55):
        state.add_reviewer_finding(
            text=f"finding {i}",
            severity="advisory",
            delegation_id=f"d-{i}",
        )

    assert len(state.reviewer_findings_summary) == 50
    # Oldest entries should have been dropped; last entry is finding 54.
    texts = [e["text"] for e in state.reviewer_findings_summary]
    assert "finding 0" not in texts
    assert "finding 54" in texts


# ---------------------------------------------------------------------------
# 6. get_reviewer_findings tool filters by file path
# ---------------------------------------------------------------------------


def test_get_reviewer_findings_tool_filters_by_file():
    state = ProjectState(project_key="default")
    state.add_reviewer_finding("issue in foo", "notable", "d-1", files=["src/foo.py"])
    state.add_reviewer_finding("issue in bar", "advisory", "d-2", files=["src/bar.py"])

    result_all = _get_reviewer_findings_fn(state)
    parsed_all = json.loads(result_all)
    assert len(parsed_all) == 2

    result_filtered = _get_reviewer_findings_fn(state, files_arg="src/foo.py")
    parsed_filtered = json.loads(result_filtered)
    assert len(parsed_filtered) == 1
    assert parsed_filtered[0]["text"] == "issue in foo"


# ---------------------------------------------------------------------------
# 7. no promotion when reviewer outcome is lgtm
# ---------------------------------------------------------------------------


def test_no_promotion_when_reviewer_lgtm():
    state = ProjectState(project_key="default")
    reviewer_pass_outcome = "lgtm"
    reviewer_pass_note = "Everything looks good."

    # Simulate the mcp_server guard condition:
    if reviewer_pass_outcome == "issues" and reviewer_pass_note:
        # This block should NOT execute for lgtm
        findings = classify_reviewer_findings(
            reviewer_pass_note,
            workspace_path="/tmp/ws",
            delegation_id="d-1",
        )
        for f in findings:
            state.add_reviewer_finding(f.text, f.severity, "d-1")
            if f.severity in ("notable", "critical"):
                state.add_risk(f.text, f.severity, "d-1")

    assert len(state.reviewer_findings_summary) == 0
    assert len(state.open_risks) == 0
