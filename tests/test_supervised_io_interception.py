"""P14-002 — supervisor_intercept trace events and structural deny."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from core.engine.supervised_io import (
    SupervisorAbort,
    SupervisedIO,
    classify_for_interception,
    classify_confirm_risk,
    InterceptClassification,
)
from core.engine.supervisor import DelegationSupervisor, SupervisorDecision
from core.observability.context import delegation_id_var, session_dir_var, workspace_var


def test_in_spec_file_approved_structurally():
    """In-spec file → approve (no LLM) + supervisor_intercept event."""
    supervisor = MagicMock(spec=DelegationSupervisor)
    buf = io.StringIO()
    sio = SupervisedIO(
        output=buf,
        supervisor=supervisor,
        target_files={"core/foo.py"},
        contract_paths=set(),
        target_files_dict={"files_edit": ["core/foo.py"], "files_read": []},
    )
    assert sio.confirm_ask("Add core/foo.py to the chat?") is True
    supervisor.evaluate.assert_not_called()
    assert sio.supervisor_decisions_count == 1
    assert sio.supervisor_decisions[0]["decision"] == "approve"


def test_out_of_scope_file_denied_structurally():
    """Clearly-out-of-scope file with add marker → deny (no LLM) + supervisor_intercept."""
    supervisor = MagicMock(spec=DelegationSupervisor)
    sio = SupervisedIO(
        output=io.StringIO(),
        supervisor=supervisor,
        target_files={"core/foo.py"},
        contract_paths=set(),
        target_files_dict={"files_edit": ["core/foo.py"], "files_read": []},
    )
    assert sio.confirm_ask("Create new file core/bar.py?") is False
    supervisor.evaluate.assert_not_called()
    assert sio.supervisor_decisions_count == 1
    assert sio.supervisor_decisions[0]["decision"] == "deny"


def test_mixed_in_and_out_of_spec_escalates():
    """Mixed paths (one in-spec, one out) → ambiguous_escalate, not deny."""
    ic = classify_for_interception(
        "Add core/foo.py and core/baz.py?",
        target_files={"files_edit": ["core/foo.py"], "files_read": []},
        contract_paths=set(),
    )
    assert ic.classification == "ambiguous_escalate"
    assert ic.decision == "escalate"
    assert ic.llm_used is True


def test_shell_marker_always_escalates_even_out_of_scope():
    """Shell marker forces escalate regardless of file scope."""
    ic = classify_for_interception(
        "Run shell command: rm -rf core/bar.py?",
        target_files={"files_edit": ["core/foo.py"], "files_read": []},
        contract_paths=set(),
    )
    assert ic.classification == "ambiguous_escalate"
    assert ic.decision == "escalate"


def test_delete_marker_escalates_not_denies():
    """Delete marker → ambiguous_escalate, not out_of_scope_deny."""
    ic = classify_for_interception(
        "Delete core/bar.py?",
        target_files={"files_edit": ["core/foo.py"], "files_read": []},
        contract_paths=set(),
    )
    assert ic.classification == "ambiguous_escalate"


def test_ambiguous_unknown_escalates_to_llm():
    """No path, no marker → ambiguous_escalate → routes to LLM."""
    ic = classify_for_interception(
        "Should I proceed?",
        target_files={"files_edit": ["core/foo.py"], "files_read": []},
        contract_paths=set(),
    )
    assert ic.classification == "ambiguous_escalate"
    assert ic.decision == "escalate"
    assert ic.llm_used is True


def test_supervisor_intercept_event_schema_fields():
    """In-spec approve → supervisor_intercept trace record has all required fields."""
    supervisor = MagicMock(spec=DelegationSupervisor)
    buf = io.StringIO()
    sio = SupervisedIO(
        output=buf,
        supervisor=supervisor,
        target_files={"core/foo.py"},
        contract_paths=set(),
        delegation_id="d-schema",
        target_files_dict={"files_edit": ["core/foo.py"], "files_read": []},
        project_state_summary="summary text",
    )

    emitted: list[dict] = []
    tok_d = delegation_id_var.set("d-schema")
    tok_s = session_dir_var.set("/tmp/session")
    tok_w = workspace_var.set("/tmp/ws")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            assert sio.confirm_ask("Add core/foo.py to the chat?") is True
    finally:
        delegation_id_var.reset(tok_d)
        session_dir_var.reset(tok_s)
        workspace_var.reset(tok_w)

    intercepts = [e for e in emitted if e.get("type") == "supervisor_intercept"]
    assert len(intercepts) == 1
    ev = intercepts[0]
    assert ev["type"] == "supervisor_intercept"
    assert ev["delegation_id"] == "d-schema"
    assert ev["classification"] == "in_spec_approve"
    assert ev["decision"] == "approve"
    assert ev["reasoning"] == "auto_approve_low_risk"
    assert "question_preview" in ev
    assert "mentioned_paths" in ev
    assert ev["llm_used"] is False
    assert ev["duration_ms"] == 0
    assert "timestamp" in ev
    cr = ev["context_ref"]
    assert "target_files_edit_count" in cr
    assert "target_files_read_count" in cr
    assert "contract_paths_count" in cr
    assert "target_files_hash" in cr
    assert "project_state_summary_hash" in cr


def test_intercept_event_emitted_exactly_once_per_confirm_ask():
    """Each confirm_ask emits exactly one supervisor_intercept event."""
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = SupervisorDecision(
        decision="approve",
        reasoning="safe",
        duration_ms=5,
        risk_tier="high",
    )
    buf = io.StringIO()
    sio = SupervisedIO(
        output=buf,
        supervisor=supervisor,
        target_files={"core/foo.py"},
        contract_paths=set(),
        delegation_id="d-once",
        target_files_dict={"files_edit": ["core/foo.py"], "files_read": []},
    )

    emitted: list[dict] = []
    tok_d = delegation_id_var.set("d-once")
    tok_s = session_dir_var.set("/tmp/session")
    tok_w = workspace_var.set("/tmp/ws")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            assert sio.confirm_ask("Apply edit to `core/foo.py`?") is True
    finally:
        delegation_id_var.reset(tok_d)
        session_dir_var.reset(tok_s)
        workspace_var.reset(tok_w)

    intercepts = [e for e in emitted if e.get("type") == "supervisor_intercept"]
    assert len(intercepts) == 1


def test_escalation_path_preserved_for_ambiguous():
    """Escalation / human-gate flow still fires after classify_for_interception."""
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = SupervisorDecision(
        decision="escalate",
        reasoning="needs human",
        duration_ms=10,
        risk_tier="unknown",
    )
    sio = SupervisedIO(
        output=io.StringIO(),
        supervisor=supervisor,
        target_files=set(),
        contract_paths=set(),
        delegation_id="d-esc",
        target_files_dict={"files_edit": [], "files_read": []},
    )
    with pytest.raises(SupervisorAbort) as excinfo:
        sio.confirm_ask("Should I do this?")
    assert excinfo.value.decision == "escalate"
    assert "needs human" in str(excinfo.value.reasoning)


def test_existing_supervisor_turn_decision_event_still_emitted():
    """supervisor_turn_decision emitted alongside supervisor_intercept (no regression)."""
    supervisor = MagicMock(spec=DelegationSupervisor)
    buf = io.StringIO()
    sio = SupervisedIO(
        output=buf,
        supervisor=supervisor,
        target_files={"core/foo.py"},
        contract_paths=set(),
        delegation_id="d-regression",
        target_files_dict={"files_edit": ["core/foo.py"], "files_read": []},
    )

    emitted: list[dict] = []
    tok_d = delegation_id_var.set("d-regression")
    tok_s = session_dir_var.set("/tmp/session")
    tok_w = workspace_var.set("/tmp/ws")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            assert sio.confirm_ask("Add core/foo.py to the chat?") is True
    finally:
        delegation_id_var.reset(tok_d)
        session_dir_var.reset(tok_s)
        workspace_var.reset(tok_w)

    types = {e.get("type") for e in emitted}
    assert "supervisor_intercept" in types
    assert "supervisor_turn_decision" in types
