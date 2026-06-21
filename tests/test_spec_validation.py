"""Pre-delegate spec validation (P4-009)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.spec_validation import spec_validation_enabled
from core.context.spec_validation_prompt import build_spec_validation_prompt
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.engine.owned_helper_llm import OwnedHelperCompletion
from core.engine.spec_validation_llm import (
    SpecValidationLlmResult,
    parse_spec_validation_output,
    run_spec_validation_llm,
)
from core.host.base import HostSessionHint
from core.host.cursor_transcript import TranscriptLoadResult
from core.specs.outcome import OUTCOME_NEEDS_INPUT, OUTCOME_SUCCESS
from core.specs.read import read_task_spec
from server.mcp_server import delegate_to_agent

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
    def _run_context(self_ref, package, *, workspace_path, mcp_session_id=None,
                     host_transcript=None, **kwargs):
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


def _run_spec_validation_llm(tmp_path, response: str) -> SpecValidationLlmResult:
    completion = OwnedHelperCompletion(
        text=response,
        model="openrouter/test/flash",
        tokens={"input": 10, "output": 5, "total": 15, "source": "owned_completion"},
        duration_ms=42,
    )
    with patch("core.engine.spec_validation_llm.provider_hint_for_model", return_value=None):
        with patch("core.engine.spec_validation_llm.run_owned_helper_completion", return_value=completion):
            return run_spec_validation_llm("prompt", workspace_path=tmp_path)


def _host_hint_with_transcript(tmp_path: Path) -> HostSessionHint:
    transcript = tmp_path / "chat.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": "Use JSON"}]}})
        + "\n",
        encoding="utf-8",
    )
    return HostSessionHint(
        host_kind="cursor",
        host_session_id="sess-1",
        host_transcript_path=str(transcript.resolve()),
    )


def _transcript_load_result(text: str) -> TranscriptLoadResult:
    return TranscriptLoadResult(
        text=text,
        file_bytes=len(text.encode("utf-8")),
        injected_bytes=len(text.encode("utf-8")),
        lines_parsed=1,
        lines_skipped=0,
        truncated=False,
        truncation_reason=None,
        bytes_dropped=0,
        read_error=None,
    )


def _delegate_with_transcript(
    ws: Path,
    monkeypatch,
    *,
    validation_result: SpecValidationLlmResult | None = None,
    engine_captured: dict | None = None,
    mode: str = "implement",
    spec_path: str = "tasks/step-b.md",
):
    monkeypatch.setenv("MCP_CODER_HOME", str(ws.parent / "home"))
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "0")
    monkeypatch.chdir(ws)
    _write_workspace_config(ws, "host_transcript: dump\nspec_validation: true\n")

    fake = ExecutionResult(
        success=True, output="done", files_changed=["pkg/cli.py"], model="m"
    )
    engine = _make_mock_engine(fake, engine_captured)
    hint = _host_hint_with_transcript(ws.parent)
    transcript_text = "## Cursor chat history\n\n[user]\nUse JSON files not SQLite"

    validate_patch = (
        patch(
            "core.engine.spec_validation_llm.run_spec_validation_llm",
            return_value=validation_result,
        )
        if validation_result is not None
        else patch("core.engine.spec_validation_llm.run_spec_validation_llm")
    )

    with patch("server.mcp_server.get_host_provider") as host_provider, patch(
        "server.mcp_server.load_cursor_transcript"
    ) as load_tx, patch("server.mcp_server.get_engine", return_value=engine), validate_patch:
        host_provider.return_value.resolve_active_session.return_value = hint
        load_tx.return_value = _transcript_load_result(transcript_text)
        return delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="JSON storage",
            spec_path=spec_path,
            mode=mode,
        )


# --- config ---


def test_spec_validation_default_on(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_SPEC_VALIDATION", raising=False)
    assert spec_validation_enabled(tmp_path) is True


def test_spec_validation_env_off(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "0")
    assert spec_validation_enabled(tmp_path) is False


def test_spec_validation_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "1")
    assert spec_validation_enabled(tmp_path) is True


def test_spec_validation_yaml_disables_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "1")
    _write_workspace_config(tmp_path, "spec_validation: false\n")
    assert spec_validation_enabled(tmp_path) is False


# --- prompt ---


def test_build_spec_validation_prompt_includes_spec_and_transcript(tmp_path):
    ws = _setup_workspace(tmp_path)
    spec_read = read_task_spec(ws / ".mcp-coder/specs/tasks/step-b.md", workspace=ws)
    prompt = build_spec_validation_prompt(
        spec_read=spec_read,
        host_transcript="User agreed on JSON files",
        task="Implement CLI",
        context_summary="Planner chose JSON",
    )
    assert "CLI uses core" in prompt
    assert "Use SQLite" in prompt
    assert "User agreed on JSON files" in prompt
    assert "## Validation OK" in prompt or "Validation OK" in prompt


# --- parser ---


def test_parser_validation_ok():
    passed, clarifications, err = parse_spec_validation_output(
        "Some reasoning\n\n## Validation OK\nLooks aligned."
    )
    assert passed is True
    assert clarifications == []
    assert err is None


def test_parser_clarifications_strips_preamble_and_fences():
    raw = (
        "Let me think...\n\n"
        "## Clarifications needed\n"
        "- Spec says SQLite but chat agreed JSON — which storage?\n"
        "- Which routes path?\n"
        "```python\n"
        "print('ignored')\n"
    )
    passed, clarifications, err = parse_spec_validation_output(raw)
    assert passed is False
    assert len(clarifications) == 2
    assert "SQLite" in clarifications[0]
    assert err is None


def test_parser_missing_heading_fails():
    passed, clarifications, err = parse_spec_validation_output("No headings here.")
    assert passed is None
    assert clarifications == []
    assert err is not None


# --- llm runner ---


def test_llm_runner_ok_response(tmp_path):
    result = _run_spec_validation_llm(tmp_path, "## Validation OK\nAligned.")
    assert result.success is True
    assert result.passed is True
    assert result.clarifications == []


def test_llm_runner_clarifications_response(tmp_path):
    result = _run_spec_validation_llm(
        tmp_path,
        "## Clarifications needed\n- Question one?\n- Question two?",
    )
    assert result.success is True
    assert result.passed is False
    assert len(result.clarifications) == 2


# --- integration ---


def test_delegate_runs_validation_without_transcript(tmp_path, monkeypatch):
    """spec_validation runs even when no host transcript is available (transcript is optional)."""
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "1")
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "0")
    monkeypatch.chdir(ws)

    captured: dict[str, bool] = {}
    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake, captured)

    with patch("core.engine.spec_validation_llm.run_spec_validation_llm") as validate:
        validate.return_value = MagicMock(
            passed=True,
            blocked=False,
            clarification_needed=False,
            questions=[],
            audit="Validation OK",
            error=None,
            model="m",
            duration_ms=10,
            tokens={"input": 10, "output": 5, "total": 15, "source": "spec_validation"},
            provenance=MagicMock(spec_path=None, host_transcript_path=None, context_source=None),
        )
        with patch("server.mcp_server.get_engine", return_value=engine):
            raw = delegate_to_agent(
                task="Implement CLI",
                target_files=["pkg/cli.py"],
                context_summary="",
                spec_path="tasks/step-b.md",
                mode="implement",
            )
        validate.assert_called_once()

    payload = json.loads(raw)
    assert payload["success"] is True
    assert captured.get("called") is True
    assert "clarification_needed" not in payload


def test_delegate_skips_validation_for_review_mode(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "1")
    monkeypatch.chdir(ws)

    with patch("core.engine.spec_validation_llm.run_spec_validation_llm") as validate:
        with patch(
            "server.mcp_server.run_spec_review",
            return_value=ExecutionResult(
                success=True,
                output="review ok",
                files_changed=[],
                model="m",
                tokens={"source": "unavailable"},
            ),
        ):
            delegate_to_agent(
                task="Review spec",
                target_files=[],
                context_summary="",
                spec_path="tasks/step-b.md",
                mode="review",
            )
        validate.assert_not_called()


def test_delegate_validation_ok_proceeds(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    ok = SpecValidationLlmResult(
        success=True,
        passed=True,
        clarifications=[],
        model="cheap-model",
        duration_ms=30,
    )
    raw = _delegate_with_transcript(ws, monkeypatch, validation_result=ok, engine_captured=captured)
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["spec_validation_ran"] is True
    assert payload["spec_validation_passed"] is True
    assert captured.get("called") is True
    assert "clarification_needed" not in payload


def test_delegate_validation_questions_advisory_executor_runs(tmp_path, monkeypatch):
    """When spec_validation has questions, execution proceeds and questions appear as advisory."""
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    blocked = SpecValidationLlmResult(
        success=True,
        passed=False,
        clarifications=[
            "Spec says SQLite but conversation agreed on JSON — which storage?",
            "Which routes path?",
        ],
        model="cheap-model",
        duration_ms=40,
    )
    raw = _delegate_with_transcript(
        ws, monkeypatch, validation_result=blocked, engine_captured=captured
    )
    payload = json.loads(raw)
    assert payload["spec_validation_ran"] is True
    assert payload["spec_validation_passed"] is False
    assert len(payload["clarification_needed"]) == 2
    # Execution proceeds — success from executor
    assert captured.get("called") is True


def test_delegate_validation_llm_error_proceeds(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    captured: dict[str, bool] = {}
    failed = SpecValidationLlmResult(
        success=False,
        passed=None,
        clarifications=[],
        model="cheap-model",
        error="timeout",
        duration_ms=10,
    )
    raw = _delegate_with_transcript(
        ws, monkeypatch, validation_result=failed, engine_captured=captured
    )
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload.get("outcome") in (OUTCOME_SUCCESS, "partial")
    assert captured.get("called") is True
    assert "clarification_needed" not in payload

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["spec_validation"]["ran"] is False
    assert record["context"]["spec_validation"]["error"] == "timeout"


def test_delegate_jsonl_spec_validation_audit_when_blocked(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    blocked = SpecValidationLlmResult(
        success=True,
        passed=False,
        clarifications=["Mismatch on storage?"],
        model="cheap-model",
        duration_ms=55,
    )
    raw = _delegate_with_transcript(ws, monkeypatch, validation_result=blocked)
    payload = json.loads(raw)
    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    sv = record["context"]["spec_validation"]
    assert sv["ran"] is True
    assert sv["passed"] is False
    assert sv["clarifications_count"] == 1
    assert sv["duration_ms"] == 55
    assert record["model_roles"]["spec_validation"]["model"] == "cheap-model"
