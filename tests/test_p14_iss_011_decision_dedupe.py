"""P14-ISS-011: dedupe identical supervisor_turn_decision trace events.

The supervisor loop calls ``_record_decision`` every turn. P14-004 dogfood
found 135 near-identical ``supervisor_turn_decision`` events in one delegation
(the supervisor kept approving the same low-risk action). The fix: content-hash
dedupe within a loop. The first occurrence is always emitted; only exact
duplicates (same action/reason/risk_level/question_present) are suppressed.

The ``supervisor_decisions`` list and ``supervisor_decisions_count`` are NOT
deduped — they remain the source of truth for "how many turns happened".
Only the trace event stream is deduped.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from core.engine.supervisor import DelegationSupervisor, SupervisorDecision
from core.engine.supervised_io import SupervisedIO
from core.observability.context import (
    delegation_id_var,
    session_dir_var,
    workspace_var,
)


def _build_sio(delegation_id: str = "d-dedupe") -> SupervisedIO:
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = SupervisorDecision(
        decision="approve",
        reasoning="safe",
        duration_ms=5,
        risk_tier="high",
    )
    return SupervisedIO(
        output=io.StringIO(),
        supervisor=supervisor,
        target_files={"pkg/cli.py"},
        contract_paths={"pkg/cli.py"},
        delegation_id=delegation_id,
    )


def _bind_context(delegation_id: str):
    tok_d = delegation_id_var.set(delegation_id)
    tok_s = session_dir_var.set("/tmp/session")
    tok_w = workspace_var.set("/tmp/ws")
    return tok_d, tok_s, tok_w


def _unbind(tokens):
    tok_d, tok_s, tok_w = tokens
    delegation_id_var.reset(tok_d)
    session_dir_var.reset(tok_s)
    workspace_var.reset(tok_w)


def test_duplicate_decisions_are_deduped_in_trace():
    """Two identical _record_decision calls emit one trace event; count is 2."""
    sio = _build_sio()
    emitted: list[dict] = []
    tokens = _bind_context("d-dedupe")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            sio._record_decision(
                question="Apply edit to `pkg/cli.py`?",
                decision=None,
                decision_name="approve",
                reasoning="auto_approve_low_risk",
                risk_tier="low",
                duration_ms=0,
            )
            sio._record_decision(
                question="Apply edit to `pkg/cli.py`?",
                decision=None,
                decision_name="approve",
                reasoning="auto_approve_low_risk",
                risk_tier="low",
                duration_ms=0,
            )
    finally:
        _unbind(tokens)

    decision_events = [e for e in emitted if e.get("type") == "supervisor_turn_decision"]
    assert len(decision_events) == 1, (
        f"expected 1 deduped trace event, got {len(decision_events)}"
    )
    # The list + count are NOT deduped — both turns are recorded.
    assert sio.supervisor_decisions_count == 2
    assert len(sio.supervisor_decisions) == 2
    # The suppressed counter reflects the one skipped emission.
    assert sio.suppressed_duplicate_decisions == 1


def test_first_occurrence_always_emitted():
    """The first event of each (action, reason, risk, question_present) is emitted."""
    sio = _build_sio()
    emitted: list[dict] = []
    tokens = _bind_context("d-dedupe-first")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            sio._record_decision(
                question="q1",
                decision=None,
                decision_name="approve",
                reasoning="r1",
                risk_tier="low",
                duration_ms=0,
            )
    finally:
        _unbind(tokens)

    decision_events = [e for e in emitted if e.get("type") == "supervisor_turn_decision"]
    assert len(decision_events) == 1
    assert sio.suppressed_duplicate_decisions == 0


def test_changed_reason_emits_new_event():
    """When the reason changes, the hash changes and a new event is emitted."""
    sio = _build_sio()
    emitted: list[dict] = []
    tokens = _bind_context("d-dedupe-reason")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            sio._record_decision(
                question="q",
                decision=None,
                decision_name="approve",
                reasoning="first reason",
                risk_tier="low",
                duration_ms=0,
            )
            sio._record_decision(
                question="q",
                decision=None,
                decision_name="approve",
                reasoning="second reason",  # changed
                risk_tier="low",
                duration_ms=0,
            )
    finally:
        _unbind(tokens)

    decision_events = [e for e in emitted if e.get("type") == "supervisor_turn_decision"]
    assert len(decision_events) == 2, (
        f"expected 2 trace events (reason changed), got {len(decision_events)}"
    )
    assert sio.suppressed_duplicate_decisions == 0
    # Both turns still recorded in the list.
    assert sio.supervisor_decisions_count == 2


def test_changed_risk_tier_emits_new_event():
    """Risk tier change is part of the dedupe key."""
    sio = _build_sio()
    emitted: list[dict] = []
    tokens = _bind_context("d-dedupe-risk")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            sio._record_decision(
                question="q",
                decision=None,
                decision_name="approve",
                reasoning="r",
                risk_tier="low",
                duration_ms=0,
            )
            sio._record_decision(
                question="q",
                decision=None,
                decision_name="approve",
                reasoning="r",
                risk_tier="high",  # changed
                duration_ms=0,
            )
    finally:
        _unbind(tokens)

    decision_events = [e for e in emitted if e.get("type") == "supervisor_turn_decision"]
    assert len(decision_events) == 2
    assert sio.suppressed_duplicate_decisions == 0


def test_duration_ms_not_in_dedupe_key():
    """duration_ms varies turn-to-turn but is intentionally not part of the key
    (matches the spec ambiguity table: ignores duration_ms, matches 'same
    decision repeated'). Two identical decisions with different durations dedupe."""
    sio = _build_sio()
    emitted: list[dict] = []
    tokens = _bind_context("d-dedupe-dur")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            sio._record_decision(
                question="q",
                decision=None,
                decision_name="approve",
                reasoning="r",
                risk_tier="low",
                duration_ms=10,
            )
            sio._record_decision(
                question="q",
                decision=None,
                decision_name="approve",
                reasoning="r",
                risk_tier="low",
                duration_ms=999,  # different duration, same decision
            )
    finally:
        _unbind(tokens)

    decision_events = [e for e in emitted if e.get("type") == "supervisor_turn_decision"]
    assert len(decision_events) == 1, (
        f"duration_ms should not affect dedupe; expected 1 event, got {len(decision_events)}"
    )
    assert sio.suppressed_duplicate_decisions == 1
