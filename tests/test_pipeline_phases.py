"""Pipeline phase audit (P4-020)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.engine.spec_validation_llm import SpecValidationLlmResult
from core.host.base import HostSessionHint
from core.host.cursor_transcript import TranscriptLoadResult
from core.pipeline.phases import PipelineRecorder
from core.verify.runner import VerifyResult
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
            captured["brief"] = package.brief
        fake_result.prompt_used = package.brief
        return fake_result

    def _run(self_ref, prompt, target_files, *, workspace_path, mcp_session_id=None, **kwargs):
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


def _phase_status(phases: list[dict], phase_name: str) -> str | None:
    for item in phases:
        if item.get("phase") == phase_name:
            return item.get("status")
    return None


def _transcript_load_result(text: str) -> TranscriptLoadResult:
    raw = text.encode("utf-8")
    return TranscriptLoadResult(
        text=text,
        file_bytes=len(raw),
        injected_bytes=len(raw),
        lines_parsed=1,
        lines_skipped=0,
        truncated=False,
        truncation_reason=None,
        bytes_dropped=0,
        read_error=None,
    )


def test_pipeline_recorder_records_ok_phase():
    rec = PipelineRecorder()
    rec.start("executor")
    rec.end("executor")
    rows = rec.to_list()
    assert rows[0]["phase"] == "executor"
    assert rows[0]["status"] == "ok"
    assert rows[0]["duration_ms"] >= 0


def test_pipeline_recorder_skipped_phase():
    rec = PipelineRecorder()
    rec.mark("planner_pass", status="skipped", detail="disabled")
    rows = rec.to_list()
    assert rows == [
        {
            "phase": "planner_pass",
            "status": "skipped",
            "duration_ms": 0,
            "detail": "disabled",
        }
    ]


def test_pipeline_recorder_error_with_detail():
    rec = PipelineRecorder()
    rec.mark("builder_llm", status="error", detail="timeout", duration_ms=8)
    row = rec.to_list()[0]
    assert row["status"] == "error"
    assert row["duration_ms"] == 8
    assert row["detail"] == "timeout"


def test_delegate_pipeline_in_response_and_jsonl(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )

    payload = json.loads(raw)
    phases = payload["delegation_pipeline"]
    assert _phase_status(phases, "spec_read") == "ok"
    assert _phase_status(phases, "executor") == "ok"
    assert _phase_status(phases, "auto_verify") == "skipped"

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["delegation_pipeline"] == phases
    assert _phase_status(phases, "file_picker") == "skipped"
    assert _phase_status(phases, "context_assemble") == "skipped"
    assert _phase_status(phases, "builder_llm") == "skipped"


def test_delegate_pipeline_validation_blocked_no_executor(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(ws)
    _write_workspace_config(ws, "host_transcript: dump\nspec_validation: true\n")

    blocked = SpecValidationLlmResult(
        success=True,
        passed=False,
        clarifications=["Spec contradicts chat; which storage?"],
        model="cheap-model",
        duration_ms=20,
    )
    hint = HostSessionHint(
        host_kind="cursor",
        host_session_id="s1",
        host_transcript_path=str((tmp_path / "chat.jsonl").resolve()),
    )

    with patch("server.mcp_server.get_host_provider") as hp, patch(
        "server.mcp_server.load_cursor_transcript",
        return_value=_transcript_load_result("## Cursor chat history\n[user]\nUse JSON files"),
    ), patch(
        "core.engine.spec_validation_llm.run_spec_validation_llm",
        return_value=blocked,
    ), patch("server.mcp_server.get_engine") as ge:
        hp.return_value.resolve_active_session.return_value = hint
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )
        ge.assert_not_called()

    payload = json.loads(raw)
    phases = payload["delegation_pipeline"]
    assert payload["outcome"] == "needs_input"
    assert _phase_status(phases, "spec_validation") == "blocked"
    assert _phase_status(phases, "executor") is None


def test_delegate_pipeline_architect_off_skipped(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)
    _write_workspace_config(ws, "auto_merge_spec_read: false\n")

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )

    payload = json.loads(raw)
    assert _phase_status(payload["delegation_pipeline"], "planner_pass") == "skipped"


def test_delegate_pipeline_spec_validation_disabled_is_skipped(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)
    _write_workspace_config(ws, "host_transcript: dump\nspec_validation: false\n")

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )
    payload = json.loads(raw)
    assert _phase_status(payload["delegation_pipeline"], "spec_validation") == "skipped"


def test_delegate_pipeline_verify_phase_present_when_enabled(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.setenv("MCP_CODER_AUTO_VERIFY", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)
    verify = VerifyResult(
        ran=True,
        passed=True,
        command="pytest -q",
        exit_code=0,
        duration_ms=12,
    )

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "server.mcp_server.run_verify_command", return_value=verify
    ):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )

    payload = json.loads(raw)
    assert _phase_status(payload["delegation_pipeline"], "auto_verify") == "ok"
