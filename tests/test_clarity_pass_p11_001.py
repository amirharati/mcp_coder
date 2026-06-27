"""Pre-delegate clarity pass (P11-001)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.config.spec_validation import clarity_pass_enabled
from core.context.role_rules import build_role_rules
from core.context.clarity_prompt import CLARITY_ROUND_CAP, build_clarity_check_prompt
from core.context.helper_llm_pipeline import apply_clarity_check
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.engine.clarity_llm import (
    ClarityCheckResult,
    parse_clarity_check_output,
    run_clarity_check_llm,
)
from core.engine.clarity_resolution import ClarityResolutionResult
from core.engine.owned_helper_llm import OwnedHelperCompletion
from core.engine.spec_validation_llm import SpecValidationLlmResult
from core.host.base import HostSessionHint
from core.host.cursor_transcript import TranscriptLoadResult
from core.logging.delegation_log import (
    CLARITY_CHECK_CLEAR,
    CLARITY_CHECK_CLARIFICATION_NEEDED,
    CLARITY_CHECK_ERROR,
    CLARITY_CHECK_SKIPPED,
    resolve_clarity_check_result,
)
from core.specs.outcome import OUTCOME_NEEDS_INPUT, OUTCOME_SUCCESS
from core.specs.read import read_task_spec
from server.mcp_server import _count_clarity_blocked_rounds, delegate_to_agent

STEP_SPEC = """\
---
spec_id: step-b
files_edit:
  - pkg/cli.py
files_read:
  - pkg/core.py
edit_scope: discover
---

# Step task spec

## Goal

CLI uses core.

## Constraints

Use SQLite.

## Files

### Edit
- `pkg/cli.py`

### Read
- `pkg/core.py`
"""


def _write_workspace_config(workspace: Path, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-b.md").write_text(STEP_SPEC, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("def api(): return 1\n", encoding="utf-8")
    (pkg / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
    return ws


def _make_mock_engine(fake_result: ExecutionResult, captured: dict | None = None) -> object:
    def _run_context(
        self_ref, package, *, workspace_path, mcp_session_id=None, host_transcript=None, **kwargs
    ):
        if captured is not None:
            captured["called"] = True
        return fake_result

    def _run(self_ref, prompt, target_files, *, workspace_path, mcp_session_id=None, **kwargs):
        if captured is not None:
            captured["called"] = True
        return fake_result

    def _capabilities(self_ref):
        return AIDER_CAPABILITIES

    return type(
        "MockEngine",
        (),
        {
            "model_name": "mock-model",
            "backend_id": "aider",
            "run": _run,
            "run_context": _run_context,
            "capabilities": _capabilities,
        },
    )()


def _run_clarity_llm(tmp_path, response: str) -> ClarityCheckResult:
    completion = OwnedHelperCompletion(
        text=response,
        model="openrouter/test/flash",
        tokens={"input": 10, "output": 5, "total": 15, "source": "owned_completion"},
        duration_ms=42,
    )
    with patch("core.engine.clarity_llm.provider_hint_for_model", return_value=None):
        with patch(
            "core.engine.clarity_llm.run_owned_helper_completion", return_value=completion
        ):
            return run_clarity_check_llm("prompt", workspace_path=tmp_path)


def _phase_status(phases: list[dict], phase_name: str) -> str | None:
    for item in phases:
        if item.get("phase") == phase_name:
            return item.get("status")
    return None


def _load_record_from_payload(payload: dict[str, object]) -> dict[str, object]:
    log_path = Path(str(payload["log_path"]))
    line = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    return json.loads(line)


def _delegate(
    ws: Path,
    monkeypatch,
    *,
    task: str = "Implement CLI wiring in pkg/cli.py to call core.api()",
    clarity_result: ClarityCheckResult | None = None,
    validation_result: SpecValidationLlmResult | None = None,
    engine_captured: dict | None = None,
    clarity_env: str | None = "1",
    spec_validation_env: str | None = None,
):
    monkeypatch.setenv("MCP_CODER_HOME", str(ws.parent / "home"))
    monkeypatch.chdir(ws)
    # P15-ISS-008: these tests exercise clarity/planner wiring, not supervisor
    # decision-making. The default _llm_decide path escalates on the thin mock
    # engine output ("done"). Route to _policy_decide (deterministic done on
    # success=True) via the designed opt-out gate.
    monkeypatch.setenv("MCP_CODER_SUPERVISOR_LLM_DECIDE", "0")
    yaml_bits = ["host_transcript: dump\n"]
    if clarity_env is None:
        monkeypatch.delenv("MCP_CODER_CLARITY_PASS", raising=False)
    else:
        monkeypatch.setenv("MCP_CODER_CLARITY_PASS", clarity_env)
    if spec_validation_env is None:
        monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "0")  # disable unless test explicitly wants it
    else:
        monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", spec_validation_env)
        yaml_bits.append("spec_validation: true\n")
    _write_workspace_config(ws, "".join(yaml_bits))

    fake = ExecutionResult(
        success=True, output="done", files_changed=["pkg/cli.py"], model="m"
    )
    engine = _make_mock_engine(fake, engine_captured)

    hint = HostSessionHint(
        host_kind="cursor",
        host_session_id="sess-1",
        host_transcript_path=str((ws.parent / "chat.jsonl").resolve()),
    )
    transcript_text = "## Cursor chat history\n\n[user]\nUse JSON"

    clarity_patch = (
        patch("core.engine.clarity_llm.run_clarity_check_llm", return_value=clarity_result)
        if clarity_result is not None
        else patch("core.engine.clarity_llm.run_clarity_check_llm")
    )
    validate_patch = (
        patch(
            "core.engine.spec_validation_llm.run_spec_validation_llm",
            return_value=validation_result,
        )
        if validation_result is not None
        else patch("core.engine.spec_validation_llm.run_spec_validation_llm")
    )

    # P15-003: patch run_clarity_resolution to default to escalate so existing
    # tests that assert pause behavior don't try to call the real sub-agent.
    resolution_patch = patch(
        "core.engine.clarity_resolution.run_clarity_resolution",
        return_value=ClarityResolutionResult(
            resolved=False,
            escalate_reason="test_default_escalate",
        ),
    )

    with patch("server.mcp_server.get_host_provider") as host_provider, patch(
        "server.mcp_server.load_cursor_transcript"
    ) as load_tx, patch("server.mcp_server.get_engine", return_value=engine), clarity_patch, validate_patch, resolution_patch:
        host_provider.return_value.resolve_active_session.return_value = hint
        load_tx.return_value = TranscriptLoadResult(
            text=transcript_text,
            file_bytes=len(transcript_text.encode("utf-8")),
            injected_bytes=len(transcript_text.encode("utf-8")),
            lines_parsed=1,
            lines_skipped=0,
            truncated=False,
            truncation_reason=None,
            bytes_dropped=0,
            read_error=None,
        )
        return delegate_to_agent(
            task=task,
            target_files=["pkg/cli.py"],
            context_summary="Wire CLI",
            spec_path="tasks/step-b.md",
            mode="implement",
        )


# --- config ---


def test_clarity_pass_default_on(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CLARITY_PASS", raising=False)
    assert clarity_pass_enabled(tmp_path) is True


def test_clarity_pass_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "1")
    assert clarity_pass_enabled(tmp_path) is True


def test_clarity_pass_yaml_disables_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "1")
    _write_workspace_config(tmp_path, "clarity_pass: false\n")
    assert clarity_pass_enabled(tmp_path) is False


# --- prompt ---


def test_build_clarity_prompt_includes_task_and_spec(tmp_path):
    ws = _setup_workspace(tmp_path)
    spec_read = read_task_spec(ws / ".mcp-coder/specs/tasks/step-b.md", workspace=ws)
    prompt = build_clarity_check_prompt(
        task="fix the auth stuff",
        spec_read=spec_read,
        recent_delegation_titles=["Prior task about CLI"],
    )
    assert "fix the auth stuff" in prompt
    assert "CLI uses core" in prompt
    assert "pkg/cli.py" in prompt
    assert "Prior task about CLI" in prompt
    assert "## Role: clarity check" not in prompt


def test_clarity_prompt_builder_returns_no_preamble(tmp_path):
    ws = _setup_workspace(tmp_path)
    spec_read = read_task_spec(ws / ".mcp-coder/specs/tasks/step-b.md", workspace=ws)
    prompt = build_clarity_check_prompt(
        task="fix the auth stuff",
        spec_read=spec_read,
        recent_delegation_titles=[],
        prior_blocked_count=0,
    )
    assert "## Role: clarity check" not in prompt


def test_clarity_llm_passes_system_prompt(tmp_path):
    completion = OwnedHelperCompletion(
        text="## CLEAR\nSpecific enough.",
        model="openrouter/test/flash",
        tokens={"input": 10, "output": 5, "total": 15, "source": "owned_completion"},
        duration_ms=42,
    )
    with patch("core.engine.clarity_llm.provider_hint_for_model", return_value=None), patch(
        "core.engine.clarity_llm.run_owned_helper_completion", return_value=completion
    ) as run_completion:
        result = run_clarity_check_llm("## Task\nDo it", workspace_path=tmp_path)

    assert result.success is True
    run_completion.assert_called_once()
    assert run_completion.call_args.args[0] == [{"role": "user", "content": "## Task\nDo it"}]
    assert run_completion.call_args.kwargs["system_prompt"] == build_role_rules("clarity")


# --- parser ---


def test_parser_clear():
    passed, questions, err = parse_clarity_check_output("thinking\n\n## CLEAR\nGood to go.")
    assert passed is True
    assert questions == []
    assert err is None


def test_parser_unclear_bullets():
    raw = (
        "## UNCLEAR\n"
        "- Which auth module should be fixed?\n"
        "- What is the expected behavior?\n"
    )
    passed, questions, err = parse_clarity_check_output(raw)
    assert passed is False
    assert len(questions) == 2
    assert err is None


def test_parser_missing_heading_fails():
    passed, questions, err = parse_clarity_check_output("No headings here.")
    assert passed is None
    assert questions == []
    assert err is not None


# --- llm runner ---


def test_llm_runner_clear_response(tmp_path):
    result = _run_clarity_llm(tmp_path, "## CLEAR\nSpecific enough.")
    assert result.success is True
    assert result.passed is True
    assert result.questions == []


def test_llm_runner_unclear_response(tmp_path):
    result = _run_clarity_llm(
        tmp_path,
        "## UNCLEAR\n- Which file?\n- Which behavior?",
    )
    assert result.success is True
    assert result.passed is False
    assert len(result.questions) == 2


# --- resolve_clarity_check_result ---


def test_resolve_clarity_check_result_values():
    assert resolve_clarity_check_result(enabled=False, ran=None, passed=None, blocked=False) == (
        CLARITY_CHECK_SKIPPED
    )
    assert resolve_clarity_check_result(
        enabled=True, ran=True, passed=True, blocked=False
    ) == CLARITY_CHECK_CLEAR
    assert resolve_clarity_check_result(
        enabled=True, ran=True, passed=False, blocked=True
    ) == CLARITY_CHECK_CLARIFICATION_NEEDED
    assert resolve_clarity_check_result(
        enabled=True, ran=False, passed=None, blocked=False, error="timeout"
    ) == CLARITY_CHECK_ERROR


# --- integration ---


def test_delegate_clarity_blocks_vague_task(tmp_path, monkeypatch):
    """Clarity check hard-gates: execution does not proceed until questions are answered."""
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=[
            "Which auth module or file should be changed?",
            "What specific auth behavior is broken?",
        ],
        model="cheap-model",
        duration_ms=35,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix the auth stuff",
        clarity_result=unclear,
        engine_captured=captured,
    )
    payload = json.loads(raw)
    assert payload["success"] is False
    assert payload["outcome"] == OUTCOME_NEEDS_INPUT
    assert len(payload["clarity_questions"]) == 2
    assert payload["clarity_round_index"] == 1
    assert payload["clarity_round_cap"] == CLARITY_ROUND_CAP
    assert payload["clarity_auto_passed"] is False
    assert "Which auth module" in payload["output"]
    assert captured.get("called") is not True
    assert _phase_status(payload["delegation_pipeline"], "clarity_check") == "blocked"

    record = _load_record_from_payload(payload)
    assert record["context"]["clarity_check_result"] == CLARITY_CHECK_CLARIFICATION_NEEDED
    assert record["context"]["clarity_round_index"] == 1
    assert record["context"]["clarity_round_cap"] == CLARITY_ROUND_CAP
    assert record["context"]["clarity_auto_passed"] is False


def test_delegate_clarity_clear_proceeds(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    clear = ClarityCheckResult(
        success=True,
        passed=True,
        questions=[],
        model="cheap-model",
        duration_ms=30,
    )
    raw = _delegate(ws, monkeypatch, clarity_result=clear, engine_captured=captured)
    payload = json.loads(raw)
    assert payload["success"] is True
    assert captured.get("called") is True
    assert "clarification_needed" not in payload
    assert payload["clarity_round_index"] == 1
    assert payload["clarity_round_cap"] == CLARITY_ROUND_CAP
    assert payload["clarity_auto_passed"] is False
    assert _phase_status(payload["delegation_pipeline"], "clarity_check") == "ok"

    record = _load_record_from_payload(payload)
    assert record["context"]["clarity_check_result"] == CLARITY_CHECK_CLEAR


def test_delegate_clarity_default_off_no_behavior_change(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    raw = _delegate(ws, monkeypatch, clarity_env="0", engine_captured=captured)
    payload = json.loads(raw)
    assert payload["success"] is True
    assert captured.get("called") is True
    assert _phase_status(payload["delegation_pipeline"], "clarity_check") == "skipped"

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["clarity_check_result"] == CLARITY_CHECK_SKIPPED


def test_delegate_clarity_llm_error_proceeds(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    failed = ClarityCheckResult(
        success=False,
        passed=None,
        questions=[],
        model="cheap-model",
        error="timeout",
        duration_ms=10,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix the auth stuff",
        clarity_result=failed,
        engine_captured=captured,
    )
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload.get("outcome") in (OUTCOME_SUCCESS, "partial")
    assert captured.get("called") is True
    assert "clarification_needed" not in payload
    assert payload["clarity_round_index"] == 1
    assert payload["clarity_round_cap"] == CLARITY_ROUND_CAP
    assert payload["clarity_auto_passed"] is False
    assert _phase_status(payload["delegation_pipeline"], "clarity_check") == "error"

    record = _load_record_from_payload(payload)
    assert record["context"]["clarity_check_result"] == CLARITY_CHECK_ERROR
    assert record["context"]["clarity_check"]["error"] == "timeout"


def test_delegate_spec_validation_questions_advisory_execution_proceeds(tmp_path, monkeypatch):
    """When spec_validation has questions, execution still proceeds — questions are advisory."""
    ws = _setup_workspace(tmp_path)
    blocked_validation = SpecValidationLlmResult(
        success=True,
        passed=False,
        clarifications=["Spec mismatch?"],
        model="cheap-model",
        duration_ms=20,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix the auth stuff",
        clarity_result=ClarityCheckResult(
            success=True, passed=True, questions=[], model="m", duration_ms=5
        ),
        validation_result=blocked_validation,
        spec_validation_env="1",
    )
    payload = json.loads(raw)
    # Execution proceeds — clarification_needed is advisory only
    assert len(payload["clarification_needed"]) == 1
    # Success is determined by the executor, not spec_validation


def test_apply_clarity_check_pipeline_blocked(tmp_path):
    ws = _setup_workspace(tmp_path)
    spec_read = read_task_spec(ws / ".mcp-coder/specs/tasks/step-b.md", workspace=ws)
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which file?"],
        model="m",
        duration_ms=12,
    )
    with patch("core.engine.clarity_llm.run_clarity_check_llm", return_value=unclear):
        blocked, questions, ran, passed, err, audit, _record, _prov = apply_clarity_check(
            spec_read=spec_read,
            workspace=str(ws),
            task="fix stuff",
            recent_delegation_titles=[],
        )
    assert blocked is True
    assert questions == ["Which file?"]
    assert ran is True
    assert passed is False
    assert err is None
    assert audit["questions_count"] == 1
    assert audit["round_index"] == 1
    assert audit["round_cap"] == CLARITY_ROUND_CAP
    assert audit["auto_passed"] is False


def test_delegate_clarity_round_cap_autopass_emits_trace_fields(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which file should be edited?"],
        model="cheap-model",
        duration_ms=12,
    )

    with patch(
        "server.mcp_server._count_clarity_blocked_rounds",
        side_effect=[0, CLARITY_ROUND_CAP - 1, CLARITY_ROUND_CAP],
    ):
        # Round 1: blocked.
        payload_1 = json.loads(_delegate(ws, monkeypatch, task="fix auth", clarity_result=unclear))
        assert payload_1["success"] is False
        assert payload_1["clarity_round_index"] == 1
        assert payload_1["clarity_auto_passed"] is False

        # Round 2: blocked again.
        payload_2 = json.loads(_delegate(ws, monkeypatch, task="fix auth", clarity_result=unclear))
        assert payload_2["success"] is False
        assert payload_2["clarity_round_index"] == CLARITY_ROUND_CAP
        assert payload_2["clarity_auto_passed"] is False

        # Round 3: cap reached -> auto-pass; executor runs despite unclear mock.
        payload_3 = json.loads(_delegate(ws, monkeypatch, task="fix auth", clarity_result=unclear))
    assert payload_3["success"] is True
    assert payload_3["clarity_round_index"] == CLARITY_ROUND_CAP + 1
    assert payload_3["clarity_round_cap"] == CLARITY_ROUND_CAP
    assert payload_3["clarity_auto_passed"] is True
    assert _phase_status(payload_3["delegation_pipeline"], "clarity_check") == "ok"

    record = _load_record_from_payload(payload_3)
    assert record["context"]["clarity_round_index"] == CLARITY_ROUND_CAP + 1
    assert record["context"]["clarity_round_cap"] == CLARITY_ROUND_CAP
    assert record["context"]["clarity_auto_passed"] is True

    trace_path = Path(record["session_dir"]) / str(record["trace_ref"])
    trace_lines = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    clarity_events = [evt for evt in trace_lines if evt.get("type") == "clarity_result"]
    assert clarity_events
    latest = clarity_events[-1]
    assert latest["clarity_round_index"] == CLARITY_ROUND_CAP + 1
    assert latest["clarity_round_cap"] == CLARITY_ROUND_CAP
    assert latest["clarity_auto_passed"] is True


def test_count_clarity_blocked_rounds_uses_structured_field_only(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "delegations.jsonl"

    rows = [
        {
            "outcome": "needs_input",
            "context": {"clarity_check_result": "clarification_needed", "task_spec": "tasks/step-a.md"},
            "mcp_request": {"spec_path": "tasks/step-a.md"},
        },
        {
            # Legacy text that used to match fallback; should not count without structured flag.
            "outcome": "needs_input",
            "context": {"task_spec": "tasks/step-a.md"},
            "response_to_cursor": {"output_preview": "Clarity questions: please answer"},
            "mcp_request": {"spec_path": "tasks/step-a.md"},
        },
        {
            # Different needs_input reason; must not count.
            "outcome": "needs_input",
            "context": {"clarity_check_result": "skipped", "task_spec": "tasks/step-a.md"},
            "mcp_request": {"spec_path": "tasks/step-a.md"},
        },
        {
            # Not needs_input; must not count.
            "outcome": "success",
            "context": {"clarity_check_result": "clarification_needed", "task_spec": "tasks/step-a.md"},
            "mcp_request": {"spec_path": "tasks/step-a.md"},
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    assert _count_clarity_blocked_rounds(session_dir, "tasks/step-a.md") == 1


def test_count_clarity_blocked_rounds_requires_matching_spec_when_target_set(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "delegations.jsonl"

    rows = [
        {
            "outcome": "needs_input",
            "context": {"clarity_check_result": "clarification_needed", "task_spec": "tasks/step-a.md"},
            "mcp_request": {"spec_path": "tasks/step-a.md"},
        },
        {
            # Missing spec info should not be counted for scoped queries.
            "outcome": "needs_input",
            "context": {"clarity_check_result": "clarification_needed"},
        },
        {
            # Different spec should not count.
            "outcome": "needs_input",
            "context": {"clarity_check_result": "clarification_needed", "task_spec": "tasks/step-b.md"},
        },
        {
            # Path normalization + suffix matching should count.
            "outcome": "needs_input",
            "context": {
                "clarity_check_result": "clarification_needed",
                "task_spec": "./workspace/.mcp-coder/specs/tasks/step-a.md",
            },
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    assert _count_clarity_blocked_rounds(session_dir, "./tasks/step-a.md") == 2
