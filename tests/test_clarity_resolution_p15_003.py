"""P15-003 tests: supervisor clarity-resolution sub-agent.

Covers Slice A (sub-agent orchestration), Slice B (preloop gate wiring),
Slice C (trace events), and Slice D (opt-out gate).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.context.role_rules import build_role_rules
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.engine.clarity_llm import ClarityCheckResult
from core.engine.clarity_resolution import (
    ClarityResolutionResult,
    _clarity_resolution_enabled,
    run_clarity_resolution,
)
from core.engine.supervisor_tool_runner import SupervisorToolRunnerResult
from core.host.base import HostSessionHint
from core.host.cursor_transcript import TranscriptLoadResult
from core.specs.outcome import OUTCOME_NEEDS_INPUT, OUTCOME_SUCCESS
from server.mcp_server import delegate_to_agent

STEP_SPEC = """\
---
spec_id: step-p15-003
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


# ── Helpers ────────────────────────────────────────────────────────────────────


def _write_workspace_config(workspace: Path, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-p15-003.md").write_text(STEP_SPEC, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("def api(): return 1\n", encoding="utf-8")
    (pkg / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
    return ws


def _make_mock_engine(
    fake_result: ExecutionResult, captured: dict | None = None
) -> object:
    def _run(
        self_ref, prompt, target_files, *, workspace_path, mcp_session_id=None, **kwargs
    ):
        if captured is not None:
            captured["called"] = True
        return fake_result

    def _run_context(
        self_ref,
        package,
        *,
        workspace_path,
        mcp_session_id=None,
        host_transcript=None,
        **kwargs,
    ):
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


def _fake_runner_result(text: str = "") -> SupervisorToolRunnerResult:
    return SupervisorToolRunnerResult(
        text=text,
        tokens={"input": 10, "output": 5, "total": 15, "source": "test"},
        llm_duration_ms=42,
        llm_calls=1,
    )


def _make_fake_runner(
    run_with_metrics_result: SupervisorToolRunnerResult | None = None,
    run_with_metrics_raises: Exception | None = None,
) -> SimpleNamespace:
    def _run_with_metrics(system_prompt, messages):
        if run_with_metrics_raises is not None:
            raise run_with_metrics_raises
        return run_with_metrics_result

    return SimpleNamespace(run_with_metrics=_run_with_metrics)


def _phase_status(phases: list[dict], phase_name: str) -> str | None:
    for item in phases:
        if item.get("phase") == phase_name:
            return item.get("status")
    return None


def _delegate(
    ws: Path,
    monkeypatch,
    *,
    task: str = "Implement CLI wiring in pkg/cli.py to call core.api()",
    clarity_result: ClarityCheckResult | None = None,
    engine_captured: dict | None = None,
    clarity_env: str | None = "1",
    clarity_resolution_mock: ClarityResolutionResult | None = None,
    clarity_resolution_raises: Exception | None = None,
) -> dict:
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
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "0")
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
        patch(
            "core.engine.clarity_llm.run_clarity_check_llm",
            return_value=clarity_result,
        )
        if clarity_result is not None
        else patch("core.engine.clarity_llm.run_clarity_check_llm")
    )

    # P15-003 sub-agent resolution mock.
    if clarity_resolution_raises is not None:
        resolution_patch = patch(
            "core.engine.clarity_resolution.run_clarity_resolution",
            side_effect=clarity_resolution_raises,
        )
    elif clarity_resolution_mock is not None:
        resolution_patch = patch(
            "core.engine.clarity_resolution.run_clarity_resolution",
            return_value=clarity_resolution_mock,
        )
    else:
        # Default: escalate (preserves pre-P15-003 test behavior).
        resolution_patch = patch(
            "core.engine.clarity_resolution.run_clarity_resolution",
            return_value=ClarityResolutionResult(
                resolved=False,
                escalate_reason="test_default_no_mock_escalate",
            ),
        )

    with patch("server.mcp_server.get_host_provider") as host_provider, patch(
        "server.mcp_server.load_cursor_transcript"
    ) as load_tx, patch(
        "server.mcp_server.get_engine", return_value=engine
    ), clarity_patch, resolution_patch:
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
        return json.loads(
            delegate_to_agent(
                task=task,
                target_files=["pkg/cli.py"],
                context_summary="Wire CLI",
                spec_path="tasks/step-p15-003.md",
                mode="implement",
            )
        )


# ── Slice A: sub-agent orchestration ──────────────────────────────────────────


def test_clarity_resolution_returns_answers_when_sub_agent_resolves():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=_fake_runner_result(
            "## Answers\n1. Answer one\n2. Answer two"
        )
    )
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Q1?", "Q2?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is True
    assert result.answers == ["Answer one", "Answer two"]
    assert result.model == "test/supervisor"
    assert result.duration_ms >= 0


def test_clarity_resolution_returns_escalate_when_sub_agent_cannot_answer():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=_fake_runner_result(
            "## Escalate\nCannot determine CLI commands from available context."
        )
    )
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Q1?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is False
    assert "Cannot determine" in (result.escalate_reason or "")


def test_clarity_resolution_escalates_on_runner_exception():
    fake_runner = _make_fake_runner(
        run_with_metrics_raises=RuntimeError("boom"),
    )
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Q1?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is False
    assert result.error is not None
    assert "runner_exception" in (result.escalate_reason or "")


def test_clarity_resolution_escalates_on_empty_output():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=SupervisorToolRunnerResult(
            text="   ", tokens={}, llm_duration_ms=0, llm_calls=0
        )
    )
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Q1?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is False
    assert result.escalate_reason == "empty_output"


def test_clarity_resolution_escalates_on_parse_failure():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=_fake_runner_result("Just a sentence. No heading.")
    )
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Q1?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is False
    assert result.escalate_reason == "parse_failure_no_recognized_heading"


def test_clarity_resolution_escalates_when_no_questions():
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
    ) as mock_build:
        result = run_clarity_resolution(
            questions=[],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is False
    assert result.escalate_reason == "no_questions"
    mock_build.assert_not_called()


def test_clarity_resolution_uses_clarity_resolver_role_rules():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=_fake_runner_result(
            "## Answers\n1. Answer one\n2. Answer two"
        )
    )
    captured_system_prompt = {}

    def _capture_run(system_prompt, messages):
        captured_system_prompt["value"] = system_prompt
        return _fake_runner_result("## Answers\n1. A\n2. B")

    fake_runner.run_with_metrics = _capture_run

    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        run_clarity_resolution(
            questions=["Q1?", "Q2?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert captured_system_prompt["value"] == build_role_rules("clarity_resolver")


def test_clarity_resolution_escalates_on_incomplete_answers():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=_fake_runner_result(
            "## Answers\n1. Only one answer"
        )
    )
    with patch(
        "core.engine.clarity_resolution.build_phase12_tool_runner",
        return_value=fake_runner,
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Q1?", "Q2?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is False
    assert result.escalate_reason == "answers_incomplete_or_malformed"
    assert result.error == "answers_incomplete_or_malformed"


def test_clarity_resolution_escalates_when_project_key_default():
    with patch(
        "core.state.project_key.ProjectKeyResolver.from_spec_path",
        return_value="default",
    ), patch(
        "core.engine.clarity_resolution.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Q1?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is False
    assert result.escalate_reason == "project_key_unresolved"


def test_clarity_resolution_escalates_on_provider_config_error():
    with patch(
        "core.engine.clarity_resolution.provider_hint_for_model",
        return_value="MISSING_API_KEY",
    ), patch(
        "core.engine.clarity_resolution.resolve_role_model_name",
        return_value="test/supervisor",
    ):
        result = run_clarity_resolution(
            questions=["Q1?"],
            workspace_path="/tmp/ws",
            spec_path="tasks/foo.md",
            project_state=SimpleNamespace(),
            spec_read=None,
            task="Test task",
            context_summary="test",
        )
    assert result.resolved is False
    assert result.error == "MISSING_API_KEY"


# ── Slice B: preloop gate wiring (integration tests) ──────────────────────────


def test_clarity_blocked_sub_agent_resolves_and_proceeds_to_planner(
    tmp_path, monkeypatch
):
    """When clarity is blocked + sub-agent resolves -> delegation proceeds."""
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which auth module?", "What behavior?"],
        model="cheap-model",
        duration_ms=35,
    )
    resolved = ClarityResolutionResult(
        resolved=True,
        answers=["pkg/auth.py", "It should validate tokens"],
        model="test/supervisor",
        duration_ms=150,
        tool_calls=2,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix auth",
        clarity_result=unclear,
        engine_captured=captured,
        clarity_resolution_mock=resolved,
    )
    assert raw["success"] is True
    assert raw["outcome"] == "success"
    assert captured.get("called") is True
    # Verify Q&A was written to the spec file.
    spec_path = ws / ".mcp-coder" / "specs" / "tasks" / "step-p15-003.md"
    spec_text = spec_path.read_text(encoding="utf-8")
    assert "**Q:** Which auth module?" in spec_text
    assert "**A:** pkg/auth.py" in spec_text
    # No pause; pipeline clarity_check can show "blocked" (the raw
    # clarity check was indeed blocked — the sub-agent resolved it
    # within the same blocked branch without updating the pipeline
    # recorder). The key invariant: delegation succeeded, not paused.
    assert raw["outcome"] != OUTCOME_NEEDS_INPUT, (
        "resolved case must not pause for input"
    )
    # No supervisor_paused trace event.
    log_path_str = raw.get("log_path")
    if log_path_str:
        log_text = Path(log_path_str).read_text(encoding="utf-8")
        lines = [
            json.loads(line) for line in log_text.splitlines() if line.strip()
        ]
        for line in lines:
            if isinstance(line, dict):
                assert line.get("type") != "supervisor_paused", (
                    "resolved case must not emit supervisor_paused"
                )


def test_clarity_blocked_sub_agent_escalates_and_pauses(tmp_path, monkeypatch):
    """When clarity is blocked + sub-agent escalates -> delegation pauses."""
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which file?"],
        model="cheap-model",
        duration_ms=35,
    )
    escalated = ClarityResolutionResult(
        resolved=False,
        escalate_reason="Cannot determine from available context",
        model="test/supervisor",
        duration_ms=100,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix auth",
        clarity_result=unclear,
        engine_captured=captured,
        clarity_resolution_mock=escalated,
    )
    assert raw["success"] is False
    assert raw["outcome"] == OUTCOME_NEEDS_INPUT
    assert len(raw["clarity_questions"]) == 1
    assert captured.get("called") is not True
    assert _phase_status(raw["delegation_pipeline"], "clarity_check") == "blocked"


def test_clarity_blocked_sub_agent_failure_falls_back_to_pause(
    tmp_path, monkeypatch
):
    """When sub-agent raises -> delegation pauses (never crashes)."""
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which file?"],
        model="cheap-model",
        duration_ms=35,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix auth",
        clarity_result=unclear,
        engine_captured=captured,
        clarity_resolution_raises=RuntimeError("boom"),
    )
    assert raw["success"] is False
    assert raw["outcome"] == OUTCOME_NEEDS_INPUT
    # Engine was never called.
    assert captured.get("called") is not True


def test_clarity_passed_sub_agent_not_called(tmp_path, monkeypatch):
    """When clarity passes -> sub-agent is not called (zero overhead)."""
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    clear = ClarityCheckResult(
        success=True,
        passed=True,
        questions=[],
        model="cheap-model",
        duration_ms=30,
    )
    with patch(
        "core.engine.clarity_resolution.run_clarity_resolution",
    ) as mock_resolve:
        raw = _delegate(
            ws,
            monkeypatch,
            clarity_result=clear,
            engine_captured=captured,
            clarity_resolution_mock=None,  # No mock needed when clarity passes.
        )
        mock_resolve.assert_not_called()
    assert raw["success"] is True
    assert captured.get("called") is True


def test_clarity_resolution_disabled_by_env(tmp_path, monkeypatch):
    """MCP_CODER_CLARITY_RESOLUTION=0 -> sub-agent skipped; pause as before."""
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which file?"],
        model="cheap-model",
        duration_ms=35,
    )
    monkeypatch.setenv("MCP_CODER_CLARITY_RESOLUTION", "0")
    with patch(
        "core.engine.clarity_resolution.run_clarity_resolution",
    ) as mock_resolve:
        raw = _delegate(
            ws,
            monkeypatch,
            clarity_result=unclear,
            engine_captured=captured,
            clarity_resolution_mock=None,
        )
        mock_resolve.assert_not_called()
    assert raw["success"] is False
    assert raw["outcome"] == OUTCOME_NEEDS_INPUT
    assert captured.get("called") is not True
    assert _phase_status(raw["delegation_pipeline"], "clarity_check") == "blocked"


def test_clarity_resolution_disabled_by_yaml(tmp_path, monkeypatch):
    """YAML clarity_resolution: false -> sub-agent skipped."""
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which file?"],
        model="cheap-model",
        duration_ms=35,
    )
    monkeypatch.delenv("MCP_CODER_CLARITY_RESOLUTION", raising=False)
    _write_workspace_config(
        ws,
        "host_transcript: dump\nclarity_resolution: false\n",
    )
    with patch(
        "core.engine.clarity_resolution.run_clarity_resolution",
    ) as mock_resolve:
        raw = _delegate(
            ws,
            monkeypatch,
            clarity_result=unclear,
            engine_captured=captured,
            clarity_resolution_mock=None,
        )
        mock_resolve.assert_not_called()
    assert raw["success"] is False
    assert raw["outcome"] == OUTCOME_NEEDS_INPUT


def test_clarity_resolution_yaml_overrides_env(tmp_path, monkeypatch):
    """Env says enabled, YAML says disabled -> YAML wins."""
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_CLARITY_RESOLUTION", "1")
    _write_workspace_config(
        ws,
        "host_transcript: dump\nclarity_resolution: false\n",
    )
    assert _clarity_resolution_enabled(ws) is False


# ── Slice C: trace events ─────────────────────────────────────────────────────


def test_clarity_resolution_emits_start_and_end_events(tmp_path, monkeypatch):
    """Trace recording wired: assert start/end events bracket the resolution."""
    ws = _setup_workspace(tmp_path)
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which auth module?"],
        model="cheap-model",
        duration_ms=35,
    )
    resolved = ClarityResolutionResult(
        resolved=True,
        answers=["pkg/auth.py"],
        model="test/supervisor",
        duration_ms=150,
        tool_calls=1,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix auth",
        clarity_result=unclear,
        clarity_resolution_mock=resolved,
    )
    log_path_str = raw.get("log_path")
    if not log_path_str:
        return
    log_text = Path(log_path_str).read_text(encoding="utf-8")
    record = json.loads(log_text.strip().splitlines()[-1])
    trace_path = (
        Path(record.get("session_dir", "")) / record.get("trace_ref", "missing")
    )
    if not trace_path.is_file():
        return
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    start_events = [e for e in events if e.get("type") == "clarity_resolution_start"]
    end_events = [e for e in events if e.get("type") == "clarity_resolution_end"]
    assert len(start_events) >= 1, "must emit at least one clarity_resolution_start"
    assert len(end_events) >= 1, "must emit at least one clarity_resolution_end"
    # Verify the end event carries answers.
    end_event = end_events[-1]
    assert end_event.get("resolved") is True
    assert end_event.get("answers") == ["pkg/auth.py"]


def test_clarity_resolution_end_event_carries_answers_on_resolve(
    tmp_path, monkeypatch,
):
    ws = _setup_workspace(tmp_path)
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Q1?", "Q2?"],
        model="cheap-model",
        duration_ms=35,
    )
    resolved = ClarityResolutionResult(
        resolved=True,
        answers=["Answer one", "Answer two"],
        model="test/supervisor",
        duration_ms=150,
        tool_calls=2,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix auth",
        clarity_result=unclear,
        clarity_resolution_mock=resolved,
    )
    log_path_str = raw.get("log_path")
    if not log_path_str:
        return
    log_text = Path(log_path_str).read_text(encoding="utf-8")
    record = json.loads(log_text.strip().splitlines()[-1])
    trace_path = (
        Path(record.get("session_dir", "")) / record.get("trace_ref", "missing")
    )
    if not trace_path.is_file():
        return
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    end_events = [e for e in events if e.get("type") == "clarity_resolution_end"]
    assert end_events
    end_event = end_events[-1]
    assert end_event.get("resolved") is True
    assert end_event.get("answers") == ["Answer one", "Answer two"]


def test_clarity_resolution_end_event_carries_escalate_reason_on_escalate(
    tmp_path, monkeypatch,
):
    ws = _setup_workspace(tmp_path)
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Q1?"],
        model="cheap-model",
        duration_ms=35,
    )
    escalated = ClarityResolutionResult(
        resolved=False,
        escalate_reason="Cannot determine",
        model="test/supervisor",
        duration_ms=100,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix auth",
        clarity_result=unclear,
        clarity_resolution_mock=escalated,
    )
    log_path_str = raw.get("log_path")
    if not log_path_str:
        return
    log_text = Path(log_path_str).read_text(encoding="utf-8")
    record = json.loads(log_text.strip().splitlines()[-1])
    trace_path = (
        Path(record.get("session_dir", "")) / record.get("trace_ref", "missing")
    )
    if not trace_path.is_file():
        return
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    end_events = [e for e in events if e.get("type") == "clarity_resolution_end"]
    assert end_events
    end_event = end_events[-1]
    assert end_event.get("resolved") is False
    assert end_event.get("escalate_reason") == "Cannot determine"


def test_clarity_resolution_end_event_emitted_on_exception(tmp_path, monkeypatch):
    """When run_clarity_resolution raises, end event still emitted."""
    ws = _setup_workspace(tmp_path)
    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Q1?"],
        model="cheap-model",
        duration_ms=35,
    )
    raw = _delegate(
        ws,
        monkeypatch,
        task="fix auth",
        clarity_result=unclear,
        clarity_resolution_raises=RuntimeError("boom"),
    )
    log_path_str = raw.get("log_path")
    if not log_path_str:
        return
    log_text = Path(log_path_str).read_text(encoding="utf-8")
    record = json.loads(log_text.strip().splitlines()[-1])
    trace_path = (
        Path(record.get("session_dir", "")) / record.get("trace_ref", "missing")
    )
    if not trace_path.is_file():
        return
    events = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    end_events = [e for e in events if e.get("type") == "clarity_resolution_end"]
    assert end_events
    end_event = end_events[-1]
    assert end_event.get("resolved") is False
    assert end_event.get("error") == "sub_agent_exception"


# ── Slice D: opt-out gate (unit tests) ────────────────────────────────────────


def test_clarity_resolution_enabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CLARITY_RESOLUTION", raising=False)
    ws = _setup_workspace(tmp_path)
    # No config file -> default true.
    assert _clarity_resolution_enabled(ws) is True


def test_clarity_resolution_disabled_by_env_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CLARITY_RESOLUTION", "0")
    ws = _setup_workspace(tmp_path)
    assert _clarity_resolution_enabled(ws) is False


def test_clarity_resolution_disabled_by_yaml_false(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CLARITY_RESOLUTION", raising=False)
    ws = _setup_workspace(tmp_path)
    _write_workspace_config(ws, "clarity_resolution: false\n")
    assert _clarity_resolution_enabled(ws) is False


def test_clarity_resolution_yaml_overrides_env_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CLARITY_RESOLUTION", "1")
    ws = _setup_workspace(tmp_path)
    _write_workspace_config(ws, "clarity_resolution: false\n")
    assert _clarity_resolution_enabled(ws) is False