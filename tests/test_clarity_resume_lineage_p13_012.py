"""P13-012 — clarity follow-up lineage is explicit."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.engine.clarity_llm import ClarityCheckResult
from core.host.base import HostSessionHint
from core.host.cursor_transcript import TranscriptLoadResult
from core.specs.outcome import OUTCOME_NEEDS_INPUT
from server.mcp_server import _SUPERVISOR_REGISTRY, delegate_to_agent


STEP_SPEC = """\
---
spec_id: lineage-step
files_edit:
  - pkg/cli.py
edit_scope: discover
---

# Lineage step

## Goal

Wire the CLI.

## Files

### Edit
- `pkg/cli.py`
"""


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "lineage-step.md").write_text(STEP_SPEC, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
    (ws / ".mcp-coder" / "config.yaml").write_text(
        "host_transcript: dump\n",
        encoding="utf-8",
    )
    return ws


def _mock_engine() -> object:
    result = ExecutionResult(
        success=True,
        output="done",
        files_changed=["pkg/cli.py"],
        model="mock-model",
    )

    def _run(self_ref, prompt, target_files, *, workspace_path, mcp_session_id=None, **kwargs):
        return result

    def _capabilities(self_ref):
        return AIDER_CAPABILITIES

    return type(
        "MockEngine",
        (),
        {
            "model_name": "mock-model",
            "backend_id": "aider",
            "run": _run,
            "capabilities": _capabilities,
        },
    )()


def _delegate_once(
    ws: Path,
    clarity_result: ClarityCheckResult,
    *,
    answer: str | None = None,
) -> dict:
    hint = HostSessionHint(
        host_kind="cursor",
        host_session_id="lineage-session",
        host_transcript_path=str((ws.parent / "chat.jsonl").resolve()),
    )
    transcript = "## Cursor chat history\n\n[user]\nPlease continue with this task."
    with patch("server.mcp_server.get_host_provider") as host_provider, patch(
        "server.mcp_server.load_cursor_transcript"
    ) as load_tx, patch("server.mcp_server.get_engine", return_value=_mock_engine()), patch(
        "core.engine.clarity_llm.run_clarity_check_llm",
        return_value=clarity_result,
    ):
        host_provider.return_value.resolve_active_session.return_value = hint
        load_tx.return_value = TranscriptLoadResult(
            text=transcript,
            file_bytes=len(transcript.encode("utf-8")),
            injected_bytes=len(transcript.encode("utf-8")),
            lines_parsed=1,
            lines_skipped=0,
            truncated=False,
            truncation_reason=None,
            bytes_dropped=0,
            read_error=None,
        )
        return json.loads(
            delegate_to_agent(
                task="Wire the CLI",
                target_files=["pkg/cli.py"],
                context_summary="Small Python CLI",
                spec_path="tasks/lineage-step.md",
                mode="implement",
                answer=answer,
            )
        )


def _load_record(payload: dict) -> dict:
    return json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").splitlines()[-1])


def test_clarity_followup_resumes_true_paused_lineage(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "1")
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "0")
    monkeypatch.setenv("MCP_CODER_REVIEWER_PASS", "0")
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    _SUPERVISOR_REGISTRY.clear()

    unclear = ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which CLI behavior should be wired?"],
        model="clarity-model",
        duration_ms=12,
    )
    clear = ClarityCheckResult(
        success=True,
        passed=True,
        questions=[],
        model="clarity-model",
        duration_ms=10,
    )

    try:
        blocked_payload = _delegate_once(ws, unclear)
        assert blocked_payload["outcome"] == OUTCOME_NEEDS_INPUT

        blocked_record = _load_record(blocked_payload)
        followup_payload = _delegate_once(
            ws,
            clear,
            answer="Wire the CLI by adding argparse command handling.",
        )
    finally:
        _SUPERVISOR_REGISTRY.clear()

    assert followup_payload["session_reason"] == "resumed"
    assert followup_payload["session_policy"] == "resume"
    assert followup_payload["success"] is True
    assert followup_payload["outcome"] == "success"

    # P13-016 (revised): the follow-up runs the fresh preloop pipeline (clarity
    # re-runs) but carries resume lineage markers. The resume events live in the
    # follow-up delegation's own trace.
    followup_record = _load_record(followup_payload)
    followup_trace_path = Path(followup_record["session_dir"]) / followup_record["trace_ref"]
    followup_trace_events = [
        json.loads(line)
        for line in followup_trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    starts = [
        event
        for event in followup_trace_events
        if event.get("type") == "delegation_lifecycle_start"
    ]
    resumed_events = [
        event for event in followup_trace_events
        if event.get("type") == "supervisor_resumed"
    ]

    assert any(event.get("resumed") is True for event in starts), (
        "follow-up lifecycle_start must be resumed=true (resume continuity)"
    )
    assert resumed_events, "expected explicit supervisor_resumed event on follow-up"
    assert "clarity_followup_lineage" not in (blocked_record.get("mcp_request") or {})

    # P13-016 (ISS-017): the blocked delegation's trace must not emit synthetic
    # loop-failure markers for an executor loop that never ran. The blocked
    # delegation is a pause/back-to-host handoff, not a loop failure.
    blocked_trace_path = Path(blocked_record["session_dir"]) / blocked_record["trace_ref"]
    blocked_trace_events = [
        json.loads(line)
        for line in blocked_trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert not [
        e for e in blocked_trace_events if e.get("type") == "supervisor_turn_end"
    ], "blocked preloop must not emit supervisor_turn_end"
    assert not [
        e for e in blocked_trace_events if e.get("type") == "supervisor_loop_end"
    ], "blocked preloop must not emit supervisor_loop_end"
    assert not [
        e for e in blocked_trace_events if e.get("type") == "supervisor_loop_start"
    ], "blocked preloop must not emit supervisor_loop_start"
