"""Spec review mode on delegate_to_agent."""

import json
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from core.specs.outcome import OUTCOME_REVIEW
from core.specs.sections import parse_sections, split_front_matter
from server.mcp_server import delegate_to_agent

TASK_SPEC = """---
spec_id: widget-step
epic: widget
revision: 1
status: draft
---

## Goal

Build widget.

## Scope

One module.

## Files

- `widget.py`

## Constraints

- none

## Done when

- [ ] widget exists
"""


def _setup(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    task = ws / ".mcp-coder" / "specs" / "tasks" / "widget-step.md"
    task.parent.mkdir(parents=True)
    task.write_text(TASK_SPEC, encoding="utf-8")
    return ws


def test_review_mode_success(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="**Questions:** None\nREADY_TO_IMPLEMENT",
        model="m",
    )

    with patch("server.mcp_server.run_spec_review", return_value=fake) as review:
        with patch("server.mcp_server.get_engine") as get_engine:
            raw = delegate_to_agent(
                task="Review this spec before we implement.",
                target_files=[],
                context_summary="",
                spec_path="tasks/widget-step.md",
                mode="review",
            )
            review.assert_called_once()
            get_engine.assert_not_called()

    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["outcome"] == OUTCOME_REVIEW
    assert payload["delegate_mode"] == "review"
    assert payload["spec_report_path"].endswith("reports/widget-step.md")

    report = ws / ".mcp-coder" / "specs" / "reports" / "widget-step.md"
    sections = parse_sections(split_front_matter(report.read_text(encoding="utf-8"))[1])
    assert "READY_TO_IMPLEMENT" in sections["Worker feedback"]
    assert (ws / ".mcp-coder/specs/tasks/widget-step.md").read_text() == TASK_SPEC


def test_review_mode_rejects_target_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    with patch("server.mcp_server.run_spec_review") as review:
        with patch("server.mcp_server.get_engine") as get_engine:
            raw = delegate_to_agent(
                task="Review",
                target_files=["widget.py"],
                context_summary="",
                spec_path="tasks/widget-step.md",
                mode="review",
            )
            review.assert_not_called()
            get_engine.assert_not_called()

    payload = json.loads(raw)
    assert payload["success"] is False
    assert "target_files=[]" in payload["output"]


def test_implement_rejects_chat_questions():
    from core.config.aider_runtime import infer_run_success

    class _Io:
        num_error_outputs = 0

    ok, err = infer_run_success(
        io=_Io(),
        output="Could you please add splitter.py to the chat?",
        partial_response=None,
    )
    assert ok is False
    assert "mode=review" in (err or "")
