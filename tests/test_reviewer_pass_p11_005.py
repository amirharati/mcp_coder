"""Post-executor tier-1 reviewer pass (P11-005)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from core.config.spec_validation import reviewer_pass_enabled
from core.context.helper_llm_pipeline import apply_reviewer_pass
from core.context.reviewer_prompt import build_reviewer_prompt
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.engine.reviewer_llm import (
    ReviewerResult,
    parse_reviewer_output,
)
from core.host.base import HostSessionHint
from core.host.cursor_transcript import TranscriptLoadResult
from core.logging.delegation_log import (
    REVIEWER_ACTION_CONTINUE,
    REVIEWER_ACTION_NONE,
    REVIEWER_MODE_ADVISORY,
    REVIEWER_MODE_DISABLED,
    REVIEWER_PASS_ERROR,
    REVIEWER_PASS_ISSUES,
    REVIEWER_PASS_LGTM,
    REVIEWER_PASS_SKIPPED,
    resolve_reviewer_pass_result,
)
from core.specs.outcome import OUTCOME_SUCCESS
from core.specs.read import read_task_spec
from core.specs.sections import parse_sections, split_front_matter
from core.specs.write import apply_post_delegation_report_updates
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

## Done when

`pkg/cli.py` calls `core.api()`.

## Constraints

Use SQLite.

## Files

### Edit
- `pkg/cli.py`

### Read
- `pkg/core.py`
"""

REPORT_SAMPLE = """---
spec_id: demo
task_spec: .mcp-coder/specs/tasks/demo.md
status: open
---

# Delegation report

## Status

`open`

## Run log

## Worker feedback

## Blockers / questions

## Suggested next (hints only)
"""


def _write_workspace_config(workspace: Path, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def _init_git(ws: Path) -> None:
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=ws,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=ws,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=ws, check=True, capture_output=True)


def _setup_workspace(tmp_path: Path, *, with_git: bool = False) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-b.md").write_text(STEP_SPEC, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("def api(): return 1\n", encoding="utf-8")
    (pkg / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
    if with_git:
        _init_git(ws)
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


def _phase_status(phases: list[dict], phase_name: str) -> str | None:
    for item in phases:
        if item.get("phase") == phase_name:
            return item.get("status")
    return None


def _delegate(
    ws: Path,
    monkeypatch,
    *,
    reviewer_result: ReviewerResult | None = None,
    reviewer_env: str | None = None,
    engine_captured: dict | None = None,
    with_git: bool = True,
):
    if with_git and not (ws / ".git").exists():
        _init_git(ws)

    monkeypatch.setenv("MCP_CODER_HOME", str(ws.parent / "home"))
    monkeypatch.chdir(ws)
    # This test module targets reviewer behavior; disable clarity gate to avoid
    # unrelated needs_input blocks from pre-delegate questions.
    monkeypatch.setenv("MCP_CODER_CLARITY_PASS", "0")
    monkeypatch.delenv("MCP_CODER_SPEC_VALIDATION", raising=False)
    if reviewer_env is None:
        monkeypatch.delenv("MCP_CODER_REVIEWER_PASS", raising=False)
    else:
        monkeypatch.setenv("MCP_CODER_REVIEWER_PASS", reviewer_env)
    _write_workspace_config(ws, "host_transcript: dump\n")

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

    reviewer_patch = (
        patch("core.engine.reviewer_llm.run_reviewer_llm", return_value=reviewer_result)
        if reviewer_result is not None
        else patch("core.engine.reviewer_llm.run_reviewer_llm")
    )

    with patch("server.mcp_server.get_host_provider") as host_provider, patch(
        "server.mcp_server.load_cursor_transcript"
    ) as load_tx, patch("server.mcp_server.get_engine", return_value=engine), reviewer_patch:
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
            task="Wire pkg/cli.py to call core.api()",
            target_files=["pkg/cli.py"],
            context_summary="Wire CLI",
            spec_path="tasks/step-b.md",
            mode="implement",
        )


def test_reviewer_pass_flag_default_on(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_REVIEWER_PASS", raising=False)
    assert reviewer_pass_enabled(tmp_path) is True


def test_reviewer_pass_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_REVIEWER_PASS", "1")
    assert reviewer_pass_enabled(tmp_path) is True


def test_parse_reviewer_output_lgtm():
    outcome, note, err = parse_reviewer_output("## LGTM\nImports look consistent.")
    assert outcome == "lgtm"
    assert note == "Imports look consistent."
    assert err is None


def test_parse_reviewer_output_issues_limits_three():
    raw = (
        "## ISSUES\n"
        "- Missing import\n"
        "- Wrong type hint\n"
        "- No test coverage\n"
        "- Fourth issue should drop\n"
    )
    outcome, note, err = parse_reviewer_output(raw)
    assert outcome == "issues"
    assert err is None
    assert note.count("- ") == 3
    assert "Fourth" not in note


def test_parse_reviewer_output_invalid():
    outcome, note, err = parse_reviewer_output("No headings here.")
    assert outcome is None
    assert note == ""
    assert err is not None


def test_apply_post_delegation_report_updates_writes_tier1_review(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(REPORT_SAMPLE, encoding="utf-8")

    apply_post_delegation_report_updates(
        report,
        timestamp="2026-06-05T12:00:00Z",
        delegation_id="abc-123",
        mcp_session_id="sess-456",
        delegate_mode="implement",
        success=True,
        files_changed=["x.py"],
        output="Applied edit",
        error=None,
        reviewer_note="LGTM — Looks good.",
    )

    _, body = split_front_matter(report.read_text(encoding="utf-8"))
    sections = parse_sections(body)
    assert sections["Tier-1 Review"].strip() == "LGTM — Looks good."


def test_resolve_reviewer_pass_result_mappings():
    assert resolve_reviewer_pass_result(
        enabled=False, ran=False, outcome=None
    ) == REVIEWER_PASS_SKIPPED
    assert resolve_reviewer_pass_result(
        enabled=True, ran=False, outcome=None, error="timeout"
    ) == REVIEWER_PASS_ERROR
    assert resolve_reviewer_pass_result(
        enabled=True, ran=False, outcome=None
    ) == REVIEWER_PASS_SKIPPED
    assert resolve_reviewer_pass_result(
        enabled=True, ran=True, outcome=REVIEWER_PASS_LGTM
    ) == REVIEWER_PASS_LGTM
    assert resolve_reviewer_pass_result(
        enabled=True, ran=True, outcome=REVIEWER_PASS_ISSUES
    ) == REVIEWER_PASS_ISSUES
    assert resolve_reviewer_pass_result(
        enabled=True, ran=True, outcome="unknown"
    ) == REVIEWER_PASS_ERROR


def test_delegate_reviewer_pass_skipped_without_flag(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, with_git=True)
    with patch("core.engine.reviewer_llm.run_reviewer_llm") as reviewer_llm:
        raw = _delegate(ws, monkeypatch, reviewer_env="0")
        reviewer_llm.assert_not_called()

    payload = json.loads(raw)
    assert payload["success"] is True
    assert _phase_status(payload["delegation_pipeline"], "reviewer_pass") == "skipped"
    assert payload["reviewer_mode"] == REVIEWER_MODE_DISABLED
    assert payload["reviewer_outcome"] == REVIEWER_PASS_SKIPPED
    assert payload["reviewer_action"] == REVIEWER_ACTION_NONE

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["reviewer_pass_result"] == REVIEWER_PASS_SKIPPED
    assert record["context"]["reviewer_mode"] == REVIEWER_MODE_DISABLED
    assert record["context"]["reviewer_outcome"] == REVIEWER_PASS_SKIPPED
    assert record["context"]["reviewer_action"] == REVIEWER_ACTION_NONE


def test_delegate_reviewer_pass_lgtm_appends_report_section(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, with_git=True)
    lgtm = ReviewerResult(
        success=True,
        outcome="lgtm",
        note="Imports look consistent.",
        model="cheap-model",
        duration_ms=25,
    )
    raw = _delegate(ws, monkeypatch, reviewer_env="1", reviewer_result=lgtm)
    payload = json.loads(raw)
    assert payload["success"] is True
    assert _phase_status(payload["delegation_pipeline"], "reviewer_pass") == "ok"
    assert payload["reviewer_mode"] == REVIEWER_MODE_ADVISORY
    assert payload["reviewer_outcome"] == REVIEWER_PASS_LGTM
    assert payload["reviewer_action"] == REVIEWER_ACTION_CONTINUE

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["reviewer_pass_result"] == REVIEWER_PASS_LGTM
    assert record["context"]["reviewer_mode"] == REVIEWER_MODE_ADVISORY
    assert record["context"]["reviewer_outcome"] == REVIEWER_PASS_LGTM
    assert record["context"]["reviewer_action"] == REVIEWER_ACTION_CONTINUE

    report_path = ws / ".mcp-coder" / "specs" / "reports" / "step-b.md"
    assert report_path.is_file()
    _, body = split_front_matter(report_path.read_text(encoding="utf-8"))
    sections = parse_sections(body)
    assert "LGTM" in sections["Tier-1 Review"]
    assert "Imports look consistent." in sections["Tier-1 Review"]


def test_delegate_reviewer_pass_error_non_fatal(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, with_git=True)
    failed = ReviewerResult(
        success=False,
        outcome=None,
        note="",
        model="cheap-model",
        error="timeout",
        duration_ms=10,
    )
    raw = _delegate(ws, monkeypatch, reviewer_env="1", reviewer_result=failed)
    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload.get("outcome") in (OUTCOME_SUCCESS, "partial")
    assert _phase_status(payload["delegation_pipeline"], "reviewer_pass") == "error"
    assert payload["reviewer_mode"] == REVIEWER_MODE_ADVISORY
    assert payload["reviewer_outcome"] == REVIEWER_PASS_ERROR
    assert payload["reviewer_action"] == REVIEWER_ACTION_CONTINUE

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["reviewer_pass_result"] == REVIEWER_PASS_ERROR
    assert record["context"]["reviewer_mode"] == REVIEWER_MODE_ADVISORY
    assert record["context"]["reviewer_outcome"] == REVIEWER_PASS_ERROR
    assert record["context"]["reviewer_action"] == REVIEWER_ACTION_CONTINUE
    assert record["context"]["reviewer_pass"]["error"] == "timeout"

    report_path = ws / ".mcp-coder" / "specs" / "reports" / "step-b.md"
    _, body = split_front_matter(report_path.read_text(encoding="utf-8"))
    sections = parse_sections(body)
    assert "Tier-1 Review" not in sections


def test_delegate_reviewer_pass_issues_keeps_advisory_continue(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, with_git=True)
    issues = ReviewerResult(
        success=True,
        outcome="issues",
        note="- Missing test coverage for CLI flow.",
        model="cheap-model",
        duration_ms=25,
    )
    raw = _delegate(ws, monkeypatch, reviewer_env="1", reviewer_result=issues)
    payload = json.loads(raw)
    assert payload["success"] is True
    assert _phase_status(payload["delegation_pipeline"], "reviewer_pass") == "ok"
    assert payload["reviewer_mode"] == REVIEWER_MODE_ADVISORY
    assert payload["reviewer_outcome"] == REVIEWER_PASS_ISSUES
    assert payload["reviewer_action"] == REVIEWER_ACTION_CONTINUE

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["reviewer_mode"] == REVIEWER_MODE_ADVISORY
    assert record["context"]["reviewer_outcome"] == REVIEWER_PASS_ISSUES
    assert record["context"]["reviewer_action"] == REVIEWER_ACTION_CONTINUE
