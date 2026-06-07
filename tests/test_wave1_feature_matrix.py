"""Wave 1 exit validation — automated feature matrix (W1-1 … W1-7).

No live OpenRouter: engine is fully mocked.  Covers P2-110/115/120/125 together.
Run: pytest tests/test_wave1_feature_matrix.py -v
"""
from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from unittest.mock import patch

import pytest

from core.engine.base import ExecutionResult
from core.specs.outcome import (
    OUTCOME_INVALID_SPEC,
    OUTCOME_SCOPE_VIOLATION,
    OUTCOME_SUCCESS,
)
from server.mcp_server import delegate_to_agent


# ---------------------------------------------------------------------------
# Shared spec fixtures
# ---------------------------------------------------------------------------

_READ_DEP_SPEC = """\
---
spec_id: cli-step
epic: expense
status: open
---

# CLI step

## Goal

Add CLI.

## Files

### Edit

- `expense_splitter/cli.py`

### Read (include in target_files)

- `expense_splitter/splitter.py`

## Done when

- [ ] CLI works
"""

_STRICT_SCOPE_SPEC = """\
---
spec_id: strict-step
files_edit:
  - app/service.py
edit_scope: strict
---

# Strict step

## Goal

Only edit app/service.py.

## Files

### Edit

- `app/service.py`

## Done when

- [ ] service updated
"""

_INVALID_SCOPE_SPEC = """\
---
spec_id: bad-scope-step
edit_scope: bananas
---

# Bad scope

## Goal

irrelevant.

## Done when

- [ ] done
"""


def _make_ws(tmp_path: Path, spec_name: str, spec_body: str) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(exist_ok=True)
    task = ws / ".mcp-coder" / "specs" / "tasks" / spec_name
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(spec_body, encoding="utf-8")
    return ws


def _mock_engine(result: ExecutionResult):
    return type("E", (), {"model_name": result.model or "m", "run": lambda *a, **k: result})()


# ---------------------------------------------------------------------------
# W1-1  P2-110 — Read-dep missing from target_files → contract_warnings present, delegation runs
# ---------------------------------------------------------------------------


def test_w1_1_read_dep_warn_delegation_still_runs(tmp_path, monkeypatch):
    """W1-1: spec lists a Read dep missing from target_files → contract_warnings non-empty,
    delegation still executes (engine called), success=True."""
    ws = _make_ws(tmp_path, "cli.md", _READ_DEP_SPEC)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["expense_splitter/cli.py"],
        model="m",
    )
    engine = _mock_engine(fake)
    engine_run_called = []

    original_run = engine.run

    def tracking_run(*a, **k):
        engine_run_called.append(True)
        return original_run(*a, **k)

    engine.run = tracking_run

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["expense_splitter/cli.py"],  # splitter.py intentionally omitted
            context_summary="step 1 done",
            spec_path="tasks/cli.md",
        )

    payload = json.loads(raw)
    assert payload["success"] is True, "delegation should still run and succeed"
    assert "contract_warnings" in payload, "contract_warnings must be present"
    assert any("splitter.py" in w for w in payload["contract_warnings"])
    assert payload["spec_files_missing_from_target"] == ["expense_splitter/splitter.py"]
    assert len(engine_run_called) == 1, "engine.run must be called"


# ---------------------------------------------------------------------------
# W1-2  P2-115 — strict spec + file edited outside files_edit → scope_violation
# ---------------------------------------------------------------------------


def test_w1_2_strict_scope_violation(tmp_path, monkeypatch):
    """W1-2: edit_scope=strict, engine edits a file outside files_edit → outcome=scope_violation."""
    ws = _make_ws(tmp_path, "strict.md", _STRICT_SCOPE_SPEC)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["app/service.py", "app/models.py"],  # models.py is out-of-scope
        model="m",
    )
    with patch("server.mcp_server.get_engine", return_value=_mock_engine(fake)):
        raw = delegate_to_agent(
            task="Update service",
            target_files=["app/service.py"],
            context_summary="",
            spec_path="tasks/strict.md",
        )

    payload = json.loads(raw)
    assert payload["outcome"] == OUTCOME_SCOPE_VIOLATION, (
        f"expected scope_violation, got {payload.get('outcome')}"
    )
    assert "scope_violations" in payload
    assert any("models.py" in v for v in payload["scope_violations"])


# ---------------------------------------------------------------------------
# W1-3  P2-115 — invalid edit_scope value → invalid_spec, engine not called
# ---------------------------------------------------------------------------


def test_w1_3_invalid_edit_scope_engine_not_called(tmp_path, monkeypatch):
    """W1-3: edit_scope has invalid value → outcome=invalid_spec, engine.run never called."""
    ws = _make_ws(tmp_path, "badscope.md", _INVALID_SCOPE_SPEC)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    with patch("server.mcp_server.get_engine") as mock_get_engine:
        raw = delegate_to_agent(
            task="do something",
            target_files=["app/service.py"],
            context_summary="",
            spec_path="tasks/badscope.md",
        )
        mock_get_engine.assert_not_called()

    payload = json.loads(raw)
    assert payload["success"] is False
    assert payload["outcome"] == OUTCOME_INVALID_SPEC


# ---------------------------------------------------------------------------
# W1-4  P2-120 — usage_report=true → response contains usage
# ---------------------------------------------------------------------------


def test_w1_4_usage_report_present_when_enabled(tmp_path, monkeypatch):
    """W1-4: usage_report enabled (default) → response payload includes 'usage' dict."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USAGE_REPORT", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["foo.py"],
        model="openrouter/openai/gpt-4o-mini",
        tokens={"input": 100, "output": 50, "total": 150, "source": "aider_coder"},
    )
    with patch("server.mcp_server.get_engine", return_value=_mock_engine(fake)):
        raw = delegate_to_agent(
            task="write foo",
            target_files=["foo.py"],
            context_summary="context here",
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert "usage" in payload, "usage key must be present when report enabled"
    assert isinstance(payload["usage"], dict)


# ---------------------------------------------------------------------------
# W1-5  P2-120 — usage_report=false → no 'usage' in response; JSONL still has it
# ---------------------------------------------------------------------------


def test_w1_5_usage_report_absent_when_disabled(tmp_path, monkeypatch):
    """W1-5: usage_report disabled via env → 'usage' absent from MCP response, JSONL still has it."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USAGE_REPORT", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["foo.py"],
        model="openrouter/openai/gpt-4o-mini",
        tokens={"input": 100, "output": 50, "total": 150, "source": "aider_coder"},
    )
    with patch("server.mcp_server.get_engine", return_value=_mock_engine(fake)):
        raw = delegate_to_agent(
            task="write foo",
            target_files=["foo.py"],
            context_summary="context here",
        )

    payload = json.loads(raw)
    assert "usage" not in payload, "usage must be absent from response when report disabled"

    # JSONL still records usage for forensics
    log_path = Path(payload["log_path"])
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert "usage" in record, "JSONL delegation record must always contain usage"


# ---------------------------------------------------------------------------
# W1-6  P2-125 — mocked upstream 500 → error_class=upstream_5xx, sanitized short output
# ---------------------------------------------------------------------------

_P1_ISS_012_ERROR = (
    "litellm.OpenrouterException: Invalid response object\n"
    "finish_reason: 'error'\n"
    "permissions-policy: payment=(self \"https://checkout.stripe.com\")\n"
    "cf-ray: 123abc-SJC\n"
    "For more details see: https://errors.pydantic.dev/2.12/v/literal_error\n"
)


def test_w1_6_upstream_500_returns_error_class(tmp_path, monkeypatch):
    """W1-6: engine returns upstream 500 text → error_class=upstream_5xx in response,
    output is short (sanitized, no stripe.com)."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=False,
        output=_P1_ISS_012_ERROR,
        files_changed=[],
        model="openrouter/qwen/qwen-2.5-coder-32b-instruct",
        error=_P1_ISS_012_ERROR,
        error_class="upstream_5xx",
    )
    with patch("server.mcp_server.get_engine", return_value=_mock_engine(fake)):
        raw = delegate_to_agent(
            task="do something",
            target_files=["app.py"],
            context_summary="use cheap model",
        )

    payload = json.loads(raw)
    assert payload["success"] is False
    assert payload.get("error_class") == "upstream_5xx", (
        f"expected upstream_5xx, got {payload.get('error_class')!r}"
    )
    assert "error_message" in payload
    assert len(payload.get("output", "")) <= 2100, "output to Cursor must be short/sanitized"

    # JSONL records error_detail
    log_path = Path(payload["log_path"])
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record.get("error_detail", {}).get("error_class") == "upstream_5xx"


# ---------------------------------------------------------------------------
# W1-7  P2-125 — webbrowser.open NOT called on error path (guard active)
# ---------------------------------------------------------------------------


def test_w1_7_webbrowser_not_opened_on_error(tmp_path, monkeypatch):
    """W1-7: even if engine output contains URLs, webbrowser.open must not be invoked."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    opened_urls: list[str] = []

    def spy_open(url, *a, **k):
        opened_urls.append(url)
        return True

    # Patch at module level so our spy is callable
    with patch("webbrowser.open", spy_open):
        fake = ExecutionResult(
            success=False,
            output=_P1_ISS_012_ERROR,
            files_changed=[],
            model="m",
            error=_P1_ISS_012_ERROR,
            error_class="upstream_5xx",
        )
        with patch("server.mcp_server.get_engine", return_value=_mock_engine(fake)):
            delegate_to_agent(
                task="do something",
                target_files=["app.py"],
                context_summary="",
            )

    assert len(opened_urls) == 0, (
        f"webbrowser.open must not be called on error path; got {opened_urls}"
    )
