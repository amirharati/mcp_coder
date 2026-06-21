"""P11-002 — supervised executor I/O."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.aider_runtime import (
    OUTCOME_NEEDS_INPUT_CLARIFICATION,
    build_needs_input_payload,
    create_delegation_io,
    supervised_execution_enabled,
)
from core.config.role_models import ROLE_SUPERVISOR, resolve_role_model_name
from core.engine.base import ExecutionResult
from core.engine.supervised_io import (
    SupervisorAbort,
    SupervisedIO,
    classify_confirm_risk,
)
from core.engine.supervisor import (
    DelegationSupervisor,
    SupervisorDecision,
    parse_supervisor_output,
)
from core.observability.context import delegation_id_var, session_dir_var, workspace_var
from core.logging.delegation_log import supervisor_audit_fields
from server.mcp_server import delegate_to_agent


def test_supervised_execution_default_on(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_SUPERVISED_EXEC", raising=False)
    assert supervised_execution_enabled(tmp_path) is True


def test_supervised_execution_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_SUPERVISED_EXEC", "1")
    assert supervised_execution_enabled(tmp_path) is True


def test_create_delegation_io_default_unchanged():
    with patch("core.engine.stdio_isolation.bind_aider_io_to_buffer"):
        with patch("aider.io.InputOutput") as io_cls:
            io_cls.return_value = MagicMock()
            create_delegation_io()
            io_cls.assert_called_once()
            assert io_cls.call_args.kwargs["yes"] is True


def test_classify_low_risk_in_target_files():
    risk = classify_confirm_risk(
        "Apply edit to `pkg/cli.py`?",
        target_files={"pkg/cli.py"},
        contract_paths={"pkg/cli.py"},
    )
    assert risk == "low"


def test_classify_high_risk_shell():
    risk = classify_confirm_risk(
        "Run this shell command: npm install",
        target_files={"pkg/cli.py"},
        contract_paths={"pkg/cli.py"},
    )
    assert risk == "high"


def test_classify_high_risk_out_of_scope_file():
    risk = classify_confirm_risk(
        "Add new file `src/other.py` to the chat?",
        target_files={"pkg/cli.py"},
        contract_paths={"pkg/cli.py"},
    )
    assert risk == "high"


def test_supervised_io_low_risk_auto_approves_without_supervisor():
    supervisor = MagicMock(spec=DelegationSupervisor)
    buf = io.StringIO()
    sio = SupervisedIO(
        output=buf,
        supervisor=supervisor,
        target_files={"pkg/cli.py"},
        contract_paths={"pkg/cli.py"},
    )
    assert sio.confirm_ask("Apply update to `pkg/cli.py`?") is True
    supervisor.evaluate.assert_not_called()
    assert sio.supervisor_decisions_count == 1
    assert sio.supervisor_decisions[0]["decision"] == "approve"


def test_supervised_io_high_risk_calls_supervisor():
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = SupervisorDecision(
        decision="approve",
        reasoning="safe command",
        duration_ms=12,
        risk_tier="high",
    )
    sio = SupervisedIO(
        output=io.StringIO(),
        supervisor=supervisor,
        target_files={"pkg/cli.py"},
        contract_paths={"pkg/cli.py"},
    )
    assert sio.confirm_ask("Run shell command: pytest tests/") is True
    supervisor.evaluate.assert_called_once()


def test_supervised_loop_events_emitted():
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = SupervisorDecision(
        decision="approve",
        reasoning="safe",
        duration_ms=5,
        risk_tier="high",
    )
    sio = SupervisedIO(
        output=io.StringIO(),
        supervisor=supervisor,
        target_files={"pkg/cli.py"},
        contract_paths={"pkg/cli.py"},
        delegation_id="d-loop",
    )

    emitted: list[dict] = []
    tok_d = delegation_id_var.set("d-loop")
    tok_s = session_dir_var.set("/tmp/session")
    tok_w = workspace_var.set("/tmp/ws")
    try:
        with patch("core.observability.trace.append_trace_record") as append:
            append.side_effect = lambda rec, **_: emitted.append(rec)
            assert sio.confirm_ask("Run shell command: pytest tests/") is True
            sio.finalize_supervisor_loop(end_reason="completed", final_decision="approve")
    finally:
        delegation_id_var.reset(tok_d)
        session_dir_var.reset(tok_s)
        workspace_var.reset(tok_w)

    types = [e.get("type") for e in emitted]
    assert "supervisor_loop_start" in types
    assert "supervisor_turn_decision" in types
    assert "supervisor_loop_end" in types


def test_supervised_io_deny_returns_false():
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = SupervisorDecision(
        decision="deny",
        reasoning="out of scope",
        duration_ms=8,
        risk_tier="unknown",
    )
    sio = SupervisedIO(
        output=io.StringIO(),
        supervisor=supervisor,
        target_files=set(),
        contract_paths=set(),
    )
    assert sio.confirm_ask("Proceed with unknown action?") is False


def test_supervised_io_abort_raises():
    supervisor = MagicMock(spec=DelegationSupervisor)
    supervisor.evaluate.return_value = SupervisorDecision(
        decision="abort",
        reasoning="unsafe deletion",
        duration_ms=9,
        risk_tier="high",
    )
    sio = SupervisedIO(
        output=io.StringIO(),
        supervisor=supervisor,
        target_files=set(),
        contract_paths=set(),
    )
    with pytest.raises(SupervisorAbort) as excinfo:
        sio.confirm_ask("Delete `pkg/core.py`?")
    assert "unsafe deletion" in str(excinfo.value.reasoning)


def test_supervisor_parse_and_fallback_abort(tmp_path):
    decision, reason, err = parse_supervisor_output(
        "## Decision: APPROVE\n## Reason\nLooks fine."
    )
    assert decision == "approve"
    assert reason == "Looks fine."
    assert err is None

    supervisor = DelegationSupervisor(
        workspace_path=tmp_path,
        delegation_id="d-1",
        spec_contract="files: pkg/cli.py",
        architect_plan=None,
        output_tail_provider=lambda: "",
    )
    with patch("core.engine.supervisor.run_owned_helper_completion") as completion:
        completion.return_value = MagicMock(
            text="garbled",
            error=None,
            tokens={"input": 1, "output": 1, "total": 2},
            duration_ms=5,
        )
        with patch("core.engine.supervisor.provider_hint_for_model", return_value=None):
            result = supervisor.evaluate(question="shell?", risk_tier="high")
    assert result.decision == "abort"
    assert result.reasoning.startswith("supervisor_error:")


def test_build_needs_input_supervisor_escalation_reason():
    payload = build_needs_input_payload(
        {
            "outcome": OUTCOME_NEEDS_INPUT_CLARIFICATION,
            "supervisor_reason": "Human must choose deployment target",
            "executor_output_tail": "tail",
        }
    )
    assert payload["reason"] == "supervisor_escalation"
    assert payload["message"] == "Human must choose deployment target"


def test_supervisor_audit_fields_optional():
    assert supervisor_audit_fields(None) == {}
    fields = supervisor_audit_fields(
        {
            "supervisor_decisions_count": 2,
            "supervisor_aborts_count": 1,
            "supervisor_last_decision": "deny",
        }
    )
    assert fields["supervisor_decisions_count"] == 2
    assert fields["supervisor_aborts_count"] == 1


def test_role_supervisor_resolver(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_SUPERVISOR_MODEL", "openrouter/test/supervisor")
    assert resolve_role_model_name(ROLE_SUPERVISOR, tmp_path) == "openrouter/test/supervisor"


def test_delegate_supervisor_escalation_payload(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(workspace)

    stall_result = ExecutionResult(
        success=False,
        output="Human must approve npm install",
        files_changed=[],
        model="openrouter/openai/gpt-4o-mini",
        error="Human must approve npm install",
        error_class=OUTCOME_NEEDS_INPUT_CLARIFICATION,
        tokens={
            "source": "unavailable",
            "stall_type": OUTCOME_NEEDS_INPUT_CLARIFICATION,
            "supervisor_reason": "Human must approve npm install",
            "supervisor_decisions_count": 1,
            "supervisor_aborts_count": 1,
            "supervisor_last_decision": "escalate",
            "supervisor_decisions": [
                {
                    "question": "Run npm install?",
                    "decision": "escalate",
                    "reasoning": "Human must approve npm install",
                    "risk_tier": "high",
                    "duration_ms": 20,
                }
            ],
            "executor_output_tail": "npm install",
        },
    )
    mock_engine = type(
        "MockEngine",
        (),
        {
            "model_name": "openrouter/openai/gpt-4o-mini",
            "backend_id": "aider",
            "run": lambda *a, **k: stall_result,
        },
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Implement feature",
            target_files=["main.py"],
            context_summary="Python project",
            backend="aider",
        )

    payload = json.loads(raw)
    assert payload["success"] is False
    assert payload["needs_input"]["reason"] == "supervisor_escalation"
    assert "npm install" in payload["needs_input"]["message"]

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["supervisor_decisions_count"] == 1
    assert record["context"]["supervisor_aborts_count"] == 1
