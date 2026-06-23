"""P13-016 — pause/resume + host handoff semantics (ISS-014, ISS-017).

Locks in the behavior contract:

- AC1/AC2: clarity-blocked preloop is pause/handoff (``needs_input``), not
  failure. No synthetic ``supervisor_turn_end`` / ``supervisor_loop_end``
  markers are emitted when the executor loop never ran.
- AC3: clarification follow-up with an ``answer`` resumes true lineage
  (``supervisor_resumed`` + lifecycle ``resumed=true``).
- AC4: explicit ``start_fresh=True`` remains supported and is labeled as
  ``fresh_by_override`` override (distinguishable from implicit follow-up).
- AC5: no regressions in touched pause/resume/lifecycle tests (covered by
  sibling suites; this module adds the dedicated positive/negative assertions).
"""

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
spec_id: pause-handoff-step
files_edit:
  - pkg/cli.py
edit_scope: discover
---

# Pause handoff step

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
    (spec_dir / "pause-handoff-step.md").write_text(STEP_SPEC, encoding="utf-8")
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


def _delegate(
    ws: Path,
    clarity_result: ClarityCheckResult,
    *,
    answer: str | None = None,
    start_fresh: bool = False,
) -> dict:
    hint = HostSessionHint(
        host_kind="cursor",
        host_session_id="pause-handoff-session",
        host_transcript_path=str((ws.parent / "chat.jsonl").resolve()),
    )
    transcript = "## Cursor chat history\n\n[user]\nPlease continue with this task."
    with patch("server.mcp_server.get_host_provider") as host_provider, patch(
        "server.mcp_server.load_cursor_transcript"
    ) as load_tx, patch(
        "server.mcp_server.get_engine", return_value=_mock_engine()
    ), patch(
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
                spec_path="tasks/pause-handoff-step.md",
                mode="implement",
                answer=answer,
                start_fresh=start_fresh,
            )
        )


def _load_record(payload: dict) -> dict:
    return json.loads(
        Path(payload["log_path"]).read_text(encoding="utf-8").splitlines()[-1]
    )


def _trace_events(record: dict) -> list[dict]:
    trace_path = Path(record["session_dir"]) / record["trace_ref"]
    return [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _blocked_clarity() -> ClarityCheckResult:
    return ClarityCheckResult(
        success=True,
        passed=False,
        questions=["Which CLI behavior should be wired?"],
        model="clarity-model",
        duration_ms=12,
    )


def _clear_clarity() -> ClarityCheckResult:
    return ClarityCheckResult(
        success=True,
        passed=True,
        questions=[],
        model="clarity-model",
        duration_ms=10,
    )


# ── AC1 + AC2: clarity-blocked preloop is pause/handoff, not failure ──────


def test_clarity_blocked_preloop_is_pause_not_failure(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "1")
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "0")
    monkeypatch.setenv("MCP_CODER_REVIEWER_PASS", "0")
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    _SUPERVISOR_REGISTRY.clear()

    try:
        payload = _delegate(ws, _blocked_clarity())
    finally:
        _SUPERVISOR_REGISTRY.clear()

    # AC1: response payload outcome is needs_input (pause/handoff).
    assert payload["outcome"] == OUTCOME_NEEDS_INPUT
    assert payload["success"] is False

    record = _load_record(payload)
    # AC1: row outcome is needs_input.
    assert record["outcome"] == OUTCOME_NEEDS_INPUT

    events = _trace_events(record)

    # AC1: lifecycle closes once with needs_input.
    lifecycle_ends = [
        e for e in events if e.get("type") == "delegation_lifecycle_end"
    ]
    assert len(lifecycle_ends) == 1
    assert lifecycle_ends[0]["outcome"] == OUTCOME_NEEDS_INPUT

    # AC1: supervisor_paused is emitted (pause/back-to-host handoff).
    paused = [e for e in events if e.get("type") == "supervisor_paused"]
    assert len(paused) == 1
    assert paused[0]["pause_reason"] == "clarity_check"

    # AC2: no synthetic loop-failure markers — the executor loop never ran.
    turn_ends = [e for e in events if e.get("type") == "supervisor_turn_end"]
    loop_ends = [e for e in events if e.get("type") == "supervisor_loop_end"]
    loop_starts = [e for e in events if e.get("type") == "supervisor_loop_start"]
    assert turn_ends == [], (
        "clarity-blocked preloop must not emit supervisor_turn_end "
        f"(got {[t.get('worker_outcome') for t in turn_ends]})"
    )
    assert loop_ends == [], (
        "clarity-blocked preloop must not emit supervisor_loop_end "
        f"(got {[l.get('end_reason') for l in loop_ends]})"
    )
    assert loop_starts == [], (
        "clarity-blocked preloop must not emit supervisor_loop_start"
    )


# ── AC3: follow-up with answer resumes true lineage by default ────────────


def test_clarity_followup_with_answer_resumes_true_lineage(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "1")
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "0")
    monkeypatch.setenv("MCP_CODER_REVIEWER_PASS", "0")
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    _SUPERVISOR_REGISTRY.clear()

    try:
        blocked_payload = _delegate(ws, _blocked_clarity())
        assert blocked_payload["outcome"] == OUTCOME_NEEDS_INPUT

        followup_payload = _delegate(
            ws,
            _clear_clarity(),
            answer="Wire the CLI by adding argparse command handling.",
        )
    finally:
        _SUPERVISOR_REGISTRY.clear()

    # AC3: follow-up routes through resume path.
    assert followup_payload["session_reason"] == "resumed"
    assert followup_payload["session_policy"] == "resume"
    assert followup_payload["success"] is True
    assert followup_payload["outcome"] == "success"

    # AC3: no fresh-lineage labeling on implicit follow-up.
    assert "clarity_followup_lineage" not in followup_payload

    # P13-016 (revised): the follow-up runs the fresh preloop pipeline (clarity
    # re-runs) but carries resume lineage markers in its own trace.
    followup_record = _load_record(followup_payload)
    followup_events = _trace_events(followup_record)

    # AC3: resume markers present in the follow-up trace.
    resumed = [e for e in followup_events if e.get("type") == "supervisor_resumed"]
    assert resumed, "expected explicit supervisor_resumed event on follow-up"

    starts = [
        e for e in followup_events if e.get("type") == "delegation_lifecycle_start"
    ]
    assert any(e.get("resumed") is True for e in starts), (
        "follow-up lifecycle_start must be resumed=true (resume continuity)"
    )


# ── AC3 (negative): clarity-block + no answer re-runs clarity (round-cap) ─


def test_clarity_blocked_no_answer_re_runs_clarity_not_reminder(tmp_path, monkeypatch):
    """A clarity-block pause without an answer still resumes (re-runs clarity).

    P13-016 (revised): the host returning is the resume signal, regardless of
    whether an ``answer`` string was passed. The follow-up re-runs clarity
    (preserving the round-cap auto-pass flow) but carries resume lineage
    markers. It must NOT be treated as an escalation pause that returns a
    paused-reminder.
    """
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "1")
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "0")
    monkeypatch.setenv("MCP_CODER_REVIEWER_PASS", "0")
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    _SUPERVISOR_REGISTRY.clear()

    try:
        first = _delegate(ws, _blocked_clarity())
        assert first["outcome"] == OUTCOME_NEEDS_INPUT
        # Second delegation without an answer resumes (re-runs clarity).
        second = _delegate(ws, _clear_clarity())
    finally:
        _SUPERVISOR_REGISTRY.clear()

    # The second delegation ran the executor (clarity passed), so it succeeded.
    assert second["success"] is True
    assert second["outcome"] == "success"
    # It did NOT take the paused-reminder path.
    assert second.get("error_class") != "paused_awaiting_answer"
    assert second.get("session_reason") != "paused_reminder"
    # P13-016 (revised): no-answer follow-up is still a resume.
    assert second["session_reason"] == "resumed"
    assert second["session_policy"] == "resume"
    second_record = _load_record(second)
    second_events = _trace_events(second_record)
    assert any(e.get("type") == "supervisor_resumed" for e in second_events), (
        "no-answer follow-up after clarity block must still emit supervisor_resumed"
    )


# ── AC4: explicit start_fresh=True is labeled as override ─────────────────


def test_start_fresh_override_is_labeled_fresh_by_override(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "1")
    monkeypatch.setenv("MCP_CODER_SPEC_VALIDATION", "0")
    monkeypatch.setenv("MCP_CODER_REVIEWER_PASS", "0")
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    _SUPERVISOR_REGISTRY.clear()

    try:
        blocked_payload = _delegate(ws, _blocked_clarity())
        assert blocked_payload["outcome"] == OUTCOME_NEEDS_INPUT

        fresh_payload = _delegate(
            ws,
            _clear_clarity(),
            answer="argparse handling",
            start_fresh=True,
        )
    finally:
        _SUPERVISOR_REGISTRY.clear()

    # AC4: start_fresh=True abandons the paused state and runs fresh.
    assert fresh_payload["success"] is True
    assert fresh_payload.get("session_policy") != "resume"

    record = _load_record(fresh_payload)
    lineage = (record.get("mcp_request") or {}).get("clarity_followup_lineage")
    assert lineage is not None, (
        "start_fresh=True after a clarity block must record "
        "clarity_followup_lineage"
    )
    # AC4: override path is distinguishable from implicit follow-up.
    assert lineage["mode"] == "fresh_by_override"
    assert lineage["reason"] == "start_fresh_true"
    assert lineage["resumed"] is False
    assert lineage["prior_clarity_blocked_count"] >= 1
