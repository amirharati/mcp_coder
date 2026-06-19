"""P11-004 — mid-run human gate unit tests."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from core.engine.question_registry import QuestionRegistry
from core.engine.supervised_io import SupervisedIO, SupervisorAbort
from core.engine.supervisor import DelegationSupervisor, SupervisorDecision
from core.logging.delegation_log import human_gate_audit_fields


# ── Registry ──────────────────────────────────────────────────────────────────


def test_registry_post_and_answer():
    reg = QuestionRegistry()
    pq = reg.post("d1", "is this safe?")
    assert pq.answer is None
    assert not pq.event.is_set()
    found = reg.answer("d1", "yes")
    assert found is True
    assert pq.answer == "yes"
    assert pq.event.is_set()


def test_registry_answer_not_found():
    reg = QuestionRegistry()
    found = reg.answer("no_such_id", "yes")
    assert found is False


def test_registry_pop_removes_entry():
    reg = QuestionRegistry()
    reg.post("d2", "question?")
    reg.pop("d2")
    assert reg.get("d2") is None


def test_registry_pop_is_idempotent():
    reg = QuestionRegistry()
    reg.pop("nonexistent")  # should not raise


# ── Human gate path in SupervisedIO ──────────────────────────────────────────


def _make_supervised_io(
    *,
    registry: QuestionRegistry,
    delegation_id: str = "test-delegation",
    escalate_decision: str = "escalate",
) -> SupervisedIO:
    """Build a SupervisedIO whose supervisor always returns the given decision."""
    buf = __import__("io").StringIO()
    decision = SupervisorDecision(
        decision=escalate_decision,
        reasoning="test escalate",
        duration_ms=1,
        risk_tier="unknown",
        model="test-model",
    )
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = decision
    return SupervisedIO(
        output=buf,
        supervisor=supervisor,
        target_files=set(),
        contract_paths=set(),
        question_registry=registry,
        delegation_id=delegation_id,
    )


def test_gate_unblocks_aider_thread():
    """Answer fires before timeout → confirm_ask returns True."""
    reg = QuestionRegistry()
    sio = _make_supervised_io(registry=reg, delegation_id="d-unblock")

    result_holder: dict = {}
    exc_holder: dict = {}

    def _worker():
        try:
            result_holder["val"] = sio.confirm_ask("edit this file?")
        except Exception as e:
            exc_holder["exc"] = e

    t = threading.Thread(target=_worker)
    t.start()

    time.sleep(0.05)
    assert reg.get("d-unblock") is not None

    reg.answer("d-unblock", "yes")
    t.join(timeout=5)

    assert "exc" not in exc_holder, exc_holder.get("exc")
    assert result_holder.get("val") is True


def test_gate_answer_no_returns_false():
    """'no' answer → confirm_ask returns False."""
    reg = QuestionRegistry()
    sio = _make_supervised_io(registry=reg, delegation_id="d-no")

    result_holder: dict = {}

    def _worker():
        result_holder["val"] = sio.confirm_ask("delete file?")

    t = threading.Thread(target=_worker)
    t.start()
    time.sleep(0.05)
    reg.answer("d-no", "no")
    t.join(timeout=5)
    assert result_holder.get("val") is False


def test_gate_cleanup_after_answer():
    """Registry entry is removed after answer path completes."""
    reg = QuestionRegistry()
    sio = _make_supervised_io(registry=reg, delegation_id="d-cleanup")

    t = threading.Thread(target=lambda: sio.confirm_ask("q?"))
    t.start()
    time.sleep(0.05)
    reg.answer("d-cleanup", "yes")
    t.join(timeout=5)

    assert reg.get("d-cleanup") is None


def test_gate_timeout_falls_back_to_abort(monkeypatch):
    """If no answer arrives within timeout, raises SupervisorAbort with decision='abort'."""
    monkeypatch.setattr("core.engine.question_registry._GATE_TIMEOUT_S", 0.1)

    reg = QuestionRegistry()
    sio = _make_supervised_io(registry=reg, delegation_id="d-timeout")

    with pytest.raises(SupervisorAbort) as exc_info:
        sio.confirm_ask("risky action?")

    assert exc_info.value.decision == "abort"
    assert "timeout" in exc_info.value.reasoning


def test_gate_cleanup_on_timeout(monkeypatch):
    """Registry entry is removed even after timeout."""
    monkeypatch.setattr("core.engine.question_registry._GATE_TIMEOUT_S", 0.1)

    reg = QuestionRegistry()
    sio = _make_supervised_io(registry=reg, delegation_id="d-timeout-cleanup")

    with pytest.raises(SupervisorAbort):
        sio.confirm_ask("q?")

    assert reg.get("d-timeout-cleanup") is None


def test_no_registry_escalate_raises_immediately():
    """Without registry, escalate still raises SupervisorAbort (no regression)."""
    buf = __import__("io").StringIO()
    decision = SupervisorDecision(
        decision="escalate",
        reasoning="needs human",
        duration_ms=1,
        risk_tier="unknown",
        model="test-model",
    )
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = decision

    sio = SupervisedIO(
        output=buf,
        supervisor=supervisor,
        target_files=set(),
        contract_paths=set(),
    )
    with pytest.raises(SupervisorAbort) as exc_info:
        sio.confirm_ask("q?")
    assert exc_info.value.decision == "escalate"


# ── audit helpers ─────────────────────────────────────────────────────────────


def test_human_gate_audit_fields_empty_when_no_events():
    sio = MagicMock()
    sio.supervisor_decisions = [
        {
            "decision": "approve",
            "reasoning": "ok",
            "risk_tier": "low",
            "duration_ms": 0,
            "question": "q",
        }
    ]
    result = human_gate_audit_fields(sio)
    assert result == {}


def test_human_gate_audit_fields_answered():
    sio = MagicMock()
    sio.supervisor_decisions = [
        {
            "decision": "human_gate_opened",
            "reasoning": "r",
            "risk_tier": "unknown",
            "duration_ms": 1,
            "question": "q",
        },
        {
            "decision": "human_gate_answered",
            "reasoning": "r",
            "risk_tier": "unknown",
            "duration_ms": 1,
            "question": "q",
        },
    ]
    result = human_gate_audit_fields(sio)
    assert result["human_gate_result"] == "answered"
    assert result["human_gate_count"] == 2


def test_human_gate_audit_fields_timeout():
    sio = MagicMock()
    sio.supervisor_decisions = [
        {
            "decision": "human_gate_opened",
            "reasoning": "r",
            "risk_tier": "unknown",
            "duration_ms": 1,
            "question": "q",
        },
        {
            "decision": "human_gate_timeout",
            "reasoning": "r",
            "risk_tier": "unknown",
            "duration_ms": 1,
            "question": "q",
        },
    ]
    result = human_gate_audit_fields(sio)
    assert result["human_gate_result"] == "timeout"


def test_human_gate_audit_fields_none():
    assert human_gate_audit_fields(None) == {}


def test_answer_tool_not_found():
    import json

    from server.mcp_server import answer_delegation_question

    raw = answer_delegation_question("unknown-delegation-id", "yes")
    payload = json.loads(raw)
    assert payload["status"] == "not_found"
    assert payload["delegation_id"] == "unknown-delegation-id"
