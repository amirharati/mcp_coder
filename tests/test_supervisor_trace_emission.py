from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.engine.supervisor import DelegationSupervisor
from core.observability.context import delegation_id_var, session_dir_var, workspace_var


def test_supervisor_llm_call_event_emitted_with_prompt_body(tmp_path):
    """T19: After import fix, supervisor evaluate() emits llm_call trace with prompt_body containing new sections."""
    from core.observability.trace import build_trace_record

    # Verify the import is fixed — no ImportError
    assert build_trace_record is not None

    supervisor = DelegationSupervisor(
        workspace_path=tmp_path,
        delegation_id="t19-deleg",
        spec_contract="files: foo.py",
        architect_plan="## Architect plan\n- Do X\n- Do Y",
        output_tail_provider=lambda: "",
        project_state_summary="### Recent decisions\n- Decision A (abc12345)",
        target_files={"files_edit": ["foo.py", "bar.py"], "files_read": ["doc.md"]},
    )

    # Set up trace context vars
    tok_d = delegation_id_var.set("t19-deleg")
    tok_s = session_dir_var.set(str(tmp_path))
    tok_w = workspace_var.set(str(tmp_path))

    # Create traces dir so append_trace_record doesn't fail on mkdir
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Stub the Phase-12 tool runner and provider check
        with patch(
            "core.engine.supervisor_tool_runner.build_phase12_tool_runner"
        ) as build_runner:
            mock_runner = MagicMock()
            mock_runner.run_with_metrics.return_value = MagicMock(
                text="## Decision: APPROVE\n## Reason\nLooks safe.",
                tokens={"input": 100, "output": 20, "total": 120},
            )
            build_runner.return_value = mock_runner

            with patch("core.engine.supervisor.provider_hint_for_model", return_value=None):
                result = supervisor.evaluate(question="Approve edit to foo.py?", risk_tier="unknown")

        assert result.decision == "approve"
        assert result.reasoning == "Looks safe."

        # Read the trace file
        trace_path = traces_dir / "t19-deleg.jsonl"
        assert trace_path.exists(), "Trace file should exist after emit"

        import json

        lines = trace_path.read_text().strip().splitlines()
        # The header line + one llm_call record
        records = [json.loads(l) for l in lines]
        llm_calls = [r for r in records if r.get("type") == "llm_call"]
        assert len(llm_calls) >= 1, "Should have at least one llm_call record"

        record = llm_calls[0]
        assert record.get("role") == "supervisor"
        assert record.get("supervisor_decision") == "approve"
        assert "prompt_body" in record, "prompt_body should be present"

        prompt_body = record["prompt_body"]
        assert "## Project state" in prompt_body
        assert "Decision A" in prompt_body
        assert "## Target files" in prompt_body
        assert "foo.py" in prompt_body
        assert "bar.py" in prompt_body
        assert "doc.md" in prompt_body
    finally:
        delegation_id_var.reset(tok_d)
        session_dir_var.reset(tok_s)
        workspace_var.reset(tok_w)


def test_supervisor_trace_no_build_llm_call_record_import():
    """T20: build_llm_call_record does not exist — guards against reintroducing the bad import name."""
    with pytest.raises(ImportError):
        from core.observability.trace import build_llm_call_record  # type: ignore[attr-defined]
        _ = build_llm_call_record  # unreachable