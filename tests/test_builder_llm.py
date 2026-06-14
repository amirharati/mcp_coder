"""Cheap-LLM context brief (P4-001b)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.context_builder import context_builder_llm_enabled
from core.context.builder_history import BuilderHistoryContext
from core.context.builder_prompt import build_builder_llm_prompt
from core.context.file_picker import CandidateFilesResult
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES, BackendCapabilities
from core.engine.context_builder_llm import (
    BuilderLlmResult,
    _finalize_builder_brief,
    _strip_code_fences,
    _strip_reasoning_preamble,
    _strip_redundant_builder_header,
    run_context_builder_llm,
)
from core.engine.owned_helper_llm import OwnedHelperCompletion
from server.mcp_server import delegate_to_agent


def _run_builder_llm(tmp_path, response: str) -> BuilderLlmResult:
    """Invoke run_context_builder_llm with a faked owned completion (no network)."""
    completion = OwnedHelperCompletion(
        text=response,
        model="openrouter/test/flash",
        tokens={"input": 10, "output": 5, "total": 15, "source": "owned_completion"},
        duration_ms=42,
    )
    with patch("core.engine.context_builder_llm.provider_hint_for_model", return_value=None):
        with patch("core.engine.context_builder_llm.run_owned_helper_completion", return_value=completion):
            return run_context_builder_llm("prompt", workspace_path=tmp_path)


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


def _make_mock_engine(fake_result: ExecutionResult, captured: dict) -> object:
    def _run_context(self_ref, package, *, workspace_path, mcp_session_id=None,
                     host_transcript=None, **kwargs):
        captured["package"] = package
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


# --- flag ---


def test_llm_flag_default_on(tmp_path, monkeypatch):
    # D-P4-5 flipped default to True after Phase 4 dogfood (2026-06-09)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_LLM", raising=False)
    assert context_builder_llm_enabled(tmp_path) is True


def test_llm_flag_env_zero_disables(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    assert context_builder_llm_enabled(tmp_path) is False


def test_llm_flag_yaml_false_disables(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_LLM", raising=False)
    cfg = tmp_path / ".mcp-coder"
    cfg.mkdir()
    (cfg / "config.yaml").write_text("context_builder_llm: false\n", encoding="utf-8")
    assert context_builder_llm_enabled(tmp_path) is False


def test_llm_flag_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "1")
    assert context_builder_llm_enabled(tmp_path) is True


def test_llm_flag_yaml_on(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_LLM", raising=False)
    cfg = tmp_path / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("context_builder_llm: true\n", encoding="utf-8")
    assert context_builder_llm_enabled(tmp_path) is True


# --- pipeline ---


def test_llm_off_not_called(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")  # explicitly off (default is now on)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="done", files_changed=["pkg/cli.py"])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("core.engine.context_builder_llm.run_context_builder_llm") as llm:
        with patch("server.mcp_server.get_engine", return_value=engine):
            raw = delegate_to_agent(
                task="Implement CLI",
                target_files=["pkg/cli.py"],
                context_summary="Step 1",
                spec_path="tasks/step-b.md",
                mode="implement",
            )
        llm.assert_not_called()

    payload = json.loads(raw)
    assert payload.get("context_builder_llm_enabled") is False
    assert "builder_brief_applied" not in payload


def test_llm_on_updates_brief_and_model_roles(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="done", files_changed=["pkg/cli.py"])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    builder = BuilderLlmResult(
        success=True,
        brief="Enhanced narrative guidance for the executor.",
        model="openrouter/google/gemini-2.5-flash",
        tokens={"input": 500, "output": 120, "total": 620, "source": "context_builder_llm"},
        duration_ms=42,
    )

    with patch(
        "core.engine.context_builder_llm.run_context_builder_llm",
        return_value=builder,
    ) as llm:
        with patch("server.mcp_server.get_engine", return_value=engine):
            raw = delegate_to_agent(
                task="Implement CLI",
                target_files=["pkg/cli.py"],
                context_summary="Step 1",
                spec_path="tasks/step-b.md",
                mode="implement",
            )
        llm.assert_called_once()

    payload = json.loads(raw)
    assert payload["context_builder_llm_enabled"] is True
    assert payload["builder_brief_applied"] is True
    roles = payload["model_roles"]
    assert roles["context_builder"]["model"] == "openrouter/google/gemini-2.5-flash"
    assert roles["context_builder"]["tokens"]["source"] == "context_builder_llm"
    assert roles["context_builder"]["tokens"]["total"] == 620
    assert roles["executor"]["role"] == "executor"
    # Brief seen by executor includes builder narrative + mechanical brief
    assert "## Builder brief" in captured["brief"]
    assert "Enhanced narrative guidance" in captured["brief"]
    assert "## Paths" in captured["brief"]


def test_llm_failure_preserves_mechanical_brief(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="done", files_changed=["pkg/cli.py"])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    builder = BuilderLlmResult(
        success=False,
        brief="",
        model="openrouter/google/gemini-2.5-flash",
        error="RateLimitError: slow down",
        tokens={"source": "unavailable"},
        duration_ms=10,
    )

    with patch(
        "core.engine.context_builder_llm.run_context_builder_llm",
        return_value=builder,
    ):
        with patch("server.mcp_server.get_engine", return_value=engine):
            raw = delegate_to_agent(
                task="Implement CLI",
                target_files=["pkg/cli.py"],
                context_summary="Step 1",
                spec_path="tasks/step-b.md",
                mode="implement",
            )

    payload = json.loads(raw)
    assert payload["context_builder_llm_enabled"] is True
    assert payload["builder_brief_applied"] is False
    # mechanical brief preserved (no builder header)
    assert "## Builder brief" not in captured["brief"]
    # role still audited even on failure
    assert payload["model_roles"]["context_builder"]["model"] == (
        "openrouter/google/gemini-2.5-flash"
    )


def test_picker_off_skips_llm(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "1")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="done", files_changed=["pkg/cli.py"])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("core.engine.context_builder_llm.run_context_builder_llm") as llm:
        with patch("server.mcp_server.get_engine", return_value=engine):
            raw = delegate_to_agent(
                task="Implement CLI",
                target_files=["pkg/cli.py"],
                context_summary="Step 1",
                spec_path="tasks/step-b.md",
                mode="implement",
            )
        llm.assert_not_called()

    payload = json.loads(raw)
    # picker off → no context_builder_llm_enabled field (picker_result is None)
    assert "context_builder_llm_enabled" not in payload


# --- reasoning preamble stripping (P4-ISS-013 fix) ---


def test_strip_reasoning_preamble_clean_brief():
    text = "## Builder brief\nThis is the executor guidance.\n\n## Paths\n- `x.py`"
    assert _strip_reasoning_preamble(text) == text


def test_strip_reasoning_preamble_strips_leading_prose():
    prose = (
        "The user wants to fix pytest failures.\n\n"
        "The problem is:\n- ModuleNotFoundError\n\n"
    )
    brief = "## Builder brief\nHere is the actual brief.\n"
    assert _strip_reasoning_preamble(prose + brief) == brief.strip()


def test_strip_reasoning_preamble_no_headings_returns_empty():
    text = "The user wants to build a CLI.\nSome prose.\nNo headings anywhere."
    assert _strip_reasoning_preamble(text) == ""


def test_strip_reasoning_preamble_empty_input():
    assert _strip_reasoning_preamble("") == ""


def test_reasoning_leak_returns_failure(tmp_path, monkeypatch):
    """A response with only reasoning prose (no ## headings) → success=False."""
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    reasoning_only = (
        "The user wants to implement a CLI.\n"
        "This means we should modify __main__.py.\n"
        "Prior delegation shows success with core library."
    )

    result = _run_builder_llm(tmp_path, reasoning_only)

    assert result.success is False
    assert "reasoning leak" in result.error or "no markdown headings" in result.error


def test_reasoning_preamble_then_valid_brief_succeeds(tmp_path, monkeypatch):
    """Reasoning preamble before a ## heading → strip + success=True."""
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    response = (
        "The user wants to implement.\n\nSome analysis.\n\n"
        "## Builder brief\n\nHere is the clean guidance.\n\n## Paths\n- `pkg/cli.py`"
    )

    result = _run_builder_llm(tmp_path, response)

    assert result.success is True
    assert result.brief.startswith("Here is the clean guidance")
    assert "## Builder brief" not in result.brief
    assert "The user wants" not in result.brief


# --- code fence / finalize validation (P4-ISS-017) ---


def test_strip_code_fences():
    text = "## Builder brief\nGuidance.\n\n```python\ncode\n```"
    assert _strip_code_fences(text) == "## Builder brief\nGuidance."


def test_strip_redundant_builder_header():
    assert _strip_redundant_builder_header("## Builder brief\nDo X") == "Do X"
    assert _strip_redundant_builder_header("## builder brief\nDo X") == "Do X"


def test_finalize_brief_with_trailing_code():
    dogfood_like = (
        "## Builder brief\n"
        "Fix validate() to raise ValueError on bad input.\n"
        "Update tests in test_validate.py.\n\n"
        "```python\n"
        "def validate(x):\n"
        "    if not x:\n"
        "        raise ValueError('bad')\n"
        "```\n"
    )
    narrative, err = _finalize_builder_brief(dogfood_like)
    assert err is None
    assert "```" not in narrative
    assert "validate()" in narrative
    assert "def validate(x)" not in narrative


def test_error_marker_in_code_tail_not_rejected(tmp_path, monkeypatch):
    """Marker inside a trailing code block must not reject a valid narrative."""
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    response = (
        "## Builder brief\n\n"
        "Implement the export fix in validate.py.\n\n"
        "```python\n"
        "litellm.NotFoundError: model not found\n"
        "```"
    )

    result = _run_builder_llm(tmp_path, response)

    assert result.success is True
    assert "litellm." not in result.brief
    assert "export fix" in result.brief


def test_error_marker_in_narrative_still_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    response = "## Builder brief\nlitellm.NotFoundError: model missing"

    result = _run_builder_llm(tmp_path, response)

    assert result.success is False
    assert "litellm." in result.error


def test_preamble_plus_brief_plus_code(tmp_path, monkeypatch):
    """P4-ISS-013 prose + valid brief + code fence → success, both stripped."""
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    response = (
        "The user wants to fix a broken v1 export.\n\n"
        "## Builder brief\n\n"
        "Wire validate() to reject empty strings.\n\n"
        "```python\n"
        "def validate(s): pass\n"
        "```"
    )

    result = _run_builder_llm(tmp_path, response)

    assert result.success is True
    assert "The user wants" not in result.brief
    assert "```" not in result.brief
    assert "validate()" in result.brief


# --- prompt budget ---


def _picker() -> CandidateFilesResult:
    return CandidateFilesResult(
        ranked_paths=["pkg/cli.py", "pkg/core.py"],
        edit_paths=["pkg/cli.py"],
        read_paths=["pkg/core.py"],
        discovered_read=[],
        suggested_edit_paths=[],
        symbol_queries=["api"],
        path_sources={"pkg/cli.py": "spec_edit", "pkg/core.py": "spec_read"},
    )


def _dense_history(n: int) -> BuilderHistoryContext:
    def _rows(prefix: str, count: int):
        return [
            {
                "delegation_id": f"{prefix}{i}",
                "outcome": "applied",
                "checkpoint_summary": "x" * 400,
                "created_count": 1,
                "modified_count": 1,
                "delegate_mode": "implement",
                "timestamp_end": "2026-06-09T00:00:00Z",
            }
            for i in range(count)
        ]

    return BuilderHistoryContext(same_spec=_rows("s", n), project_recent=_rows("p", n))


def test_budget_truncates_history_not_contract():
    mechanical = "## Task\nbuild\n\n## Paths\n- `pkg/cli.py` — edit-full\n"
    picker = _picker()
    history = _dense_history(10)

    full = build_builder_llm_prompt(
        mechanical_brief=mechanical,
        picker_result=picker,
        package_metadata={},
        history=history,
        host_transcript=None,
        context_summary="",
        task="build",
        budget_tokens=None,
    )
    bounded = build_builder_llm_prompt(
        mechanical_brief=mechanical,
        picker_result=picker,
        package_metadata={},
        history=history,
        host_transcript=None,
        context_summary="",
        task="build",
        budget_tokens=400,
    )

    assert len(bounded) < len(full)
    # Contract + picker sections survive truncation
    assert "pkg/cli.py" in bounded
    assert "## Candidate files (from rules picker)" in bounded
    assert "## Mechanical brief" in bounded
    # Some history rows dropped
    assert bounded.count("[s") + bounded.count("[p") < 20


def test_budget_keeps_history_when_unbounded():
    mechanical = "## Task\nbuild\n"
    history = _dense_history(2)
    prompt = build_builder_llm_prompt(
        mechanical_brief=mechanical,
        picker_result=_picker(),
        package_metadata={},
        history=history,
        host_transcript=None,
        context_summary="",
        task="build",
        budget_tokens=None,
    )
    assert "## Prior delegations" in prompt
    assert prompt.count("[s") == 2
