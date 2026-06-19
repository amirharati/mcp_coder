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


def test_review_uses_review_model_and_workspace_path(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_REVIEW_MODEL", "openrouter/test/review-model")
    monkeypatch.chdir(ws)

    captured: dict = {}

    def _fake_review(prompt, *, model_name=None, workspace_path=None):
        captured["workspace_path"] = workspace_path
        from core.config.review_model import resolve_review_model_name

        resolved = (
            resolve_review_model_name(workspace_path)
            if workspace_path
            else "openrouter/test/fallback"
        )
        return ExecutionResult(
            success=True,
            output="**Questions:** None\nREADY_TO_IMPLEMENT",
            model=resolved,
        )

    with patch("server.mcp_server.run_spec_review", side_effect=_fake_review):
        raw = delegate_to_agent(
            task="Review this spec before we implement.",
            target_files=[],
            context_summary="",
            spec_path="tasks/widget-step.md",
            mode="review",
        )

    assert captured["workspace_path"] == str(ws.resolve())
    payload = json.loads(raw)
    assert payload["usage"]["model"] == "openrouter/test/review-model"


def test_implement_ignores_review_model(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_REVIEW_MODEL", "openrouter/test/review-model")
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/implement-model")
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["widget.py"],
        model="openrouter/test/implement-model",
    )
    mock_engine = type(
        "E",
        (),
        {
            "model_name": "openrouter/test/implement-model",
            "run": lambda *a, **k: fake,
        },
    )()

    with patch("server.mcp_server.run_spec_review") as review:
        with patch("server.mcp_server.get_engine", return_value=mock_engine):
            raw = delegate_to_agent(
                task="Implement widget",
                target_files=["widget.py"],
                context_summary="",
                spec_path="tasks/widget-step.md",
                mode="implement",
            )
        review.assert_not_called()

    payload = json.loads(raw)
    assert payload["usage"]["model"] == "openrouter/test/implement-model"
    assert payload["usage"]["model"] != "openrouter/test/review-model"


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
    assert "target_files" in (err or "")
