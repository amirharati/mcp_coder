"""Architect pass (P4-020)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.config.architect_pass import architect_pass_enabled
from core.context.architect_prompt import build_architect_pass_prompt
from core.context.file_picker import CandidateFilesResult
from core.engine.architect_pass_llm import ArchitectPassLlmResult, run_architect_pass_llm
from core.engine.owned_helper_llm import OwnedHelperCompletion
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
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

Do not touch database layer.

## Files

### Edit
- `pkg/cli.py`

### Read
- `pkg/core.py`
"""

STEP_SPEC_ARCH_ON = """\
---
spec_id: step-b
architect_pass: true
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

Do not touch database layer.

## Files

### Edit
- `pkg/cli.py`

### Read
- `pkg/core.py`
"""

STEP_SPEC_ARCH_OFF = """\
---
spec_id: step-b
architect_pass: false
files_edit:
  - pkg/cli.py
  - pkg/core.py
files_read:
  - pkg/core.py
edit_scope: discover
---

# Step task spec

## Goal

Refactor CLI and core integration.

## Constraints

Do not touch database layer.

## Files

### Edit
- `pkg/cli.py`
- `pkg/core.py`

### Read
- `pkg/core.py`
"""


def _write_workspace_config(workspace: Path, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def _setup_workspace(tmp_path: Path, *, spec_text: str | None = None) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-b.md").write_text(spec_text or STEP_SPEC, encoding="utf-8")
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


def _run_architect_llm(tmp_path, response: str):
    completion = OwnedHelperCompletion(
        text=response,
        model="openrouter/test/flash",
        tokens={"input": 10, "output": 5, "total": 15, "source": "owned_completion"},
        duration_ms=42,
    )
    with patch("core.engine.architect_pass_llm.provider_hint_for_model", return_value=None):
        with patch("core.engine.architect_pass_llm.run_owned_helper_completion", return_value=completion):
            return run_architect_pass_llm("prompt", workspace_path=tmp_path)


def _phase_status(phases: list[dict], phase_name: str) -> str | None:
    for item in phases:
        if item.get("phase") == phase_name:
            return item.get("status")
    return None


def _phase_detail(phases: list[dict], phase_name: str) -> str | None:
    for item in phases:
        if item.get("phase") == phase_name:
            return item.get("detail")
    return None


def test_architect_flag_default_off(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_ARCHITECT_PASS", raising=False)
    assert architect_pass_enabled(tmp_path) is False


def test_architect_flag_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_ARCHITECT_PASS", "1")
    assert architect_pass_enabled(tmp_path) is True


def test_architect_flag_yaml_disables_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_ARCHITECT_PASS", "1")
    _write_workspace_config(tmp_path, "architect_pass: false\n")
    assert architect_pass_enabled(tmp_path) is False


def test_architect_flag_yaml_enables(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_ARCHITECT_PASS", raising=False)
    _write_workspace_config(tmp_path, "architect_pass: true\n")
    assert architect_pass_enabled(tmp_path) is True


def test_architect_prompt_includes_spec_paths_and_transcript(tmp_path):
    ws = _setup_workspace(tmp_path)
    spec_read = read_task_spec(ws / ".mcp-coder/specs/tasks/step-b.md", workspace=ws)
    picker = CandidateFilesResult(
        ranked_paths=["pkg/cli.py", "pkg/core.py"],
        discovered_read=["pkg/core.py"],
        symbol_queries=["main"],
        suggested_edit_paths=["pkg/cli.py"],
        path_sources={"pkg/cli.py": "spec_edit"},
    )
    prompt = build_architect_pass_prompt(
        spec_read=spec_read,
        mechanical_brief="## Paths\n- EDIT pkg/cli.py\n- READ pkg/core.py",
        picker_result=picker,
        host_transcript="User asked to keep DB untouched",
        task="Implement CLI",
        context_summary="No DB changes",
    )
    assert "## Task spec summary" in prompt
    assert "Do not touch database layer." in prompt
    assert "## Mechanical brief paths" in prompt
    assert "## Candidate file audit" in prompt
    assert "## Recent host conversation" in prompt


def test_architect_llm_runner_success(tmp_path):
    result = _run_architect_llm(tmp_path, "## Architect plan\n- Do A then B.")
    assert result.success is True
    assert result.plan.startswith("## Architect plan")


def test_architect_llm_runner_missing_heading_fails(tmp_path):
    result = _run_architect_llm(tmp_path, "No heading")
    assert result.success is False
    assert result.error is not None


def test_architect_llm_runner_strips_reasoning_preamble(tmp_path):
    result = _run_architect_llm(
        tmp_path, "Thinking...\n\n## Architect plan\n- Step 1\n- Step 2"
    )
    assert result.success is True
    assert result.plan.startswith("## Architect plan")


def test_delegate_architect_on_adds_plan_above_brief(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_ARCH_ON)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)

    captured: dict[str, str] = {}
    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake, captured)
    arch = ArchitectPassLlmResult(
        success=True,
        plan="## Architect plan\n- Touch cli first\n- Do not change core API",
        model="cheap-model",
        duration_ms=25,
        tokens={"input": 10, "output": 5, "total": 15, "source": "architect_pass"},
    )

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "core.engine.architect_pass_llm.run_architect_pass_llm", return_value=arch
    ):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )

    payload = json.loads(raw)
    brief = captured["brief"]
    assert brief.startswith("## Architect plan")
    assert "## Builder brief" not in brief
    assert payload["model_roles"]["architect_pass"]["tokens"]["source"] == "architect_pass"
    assert _phase_status(payload["delegation_pipeline"], "architect_pass") == "ok"


def test_delegate_architect_error_falls_back_and_pipeline_error(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_ARCH_ON)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)

    captured: dict[str, str] = {}
    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake, captured)
    arch = ArchitectPassLlmResult(
        success=False,
        plan="",
        model="cheap-model",
        error="timeout",
        duration_ms=10,
        tokens={"input": None, "output": None, "total": None, "source": "architect_pass"},
    )

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "core.engine.architect_pass_llm.run_architect_pass_llm", return_value=arch
    ):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert not captured["brief"].startswith("## Architect plan")
    assert _phase_status(payload["delegation_pipeline"], "architect_pass") == "error"


def test_delegate_architect_heuristic_skips_trivial_single_file(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)
    _write_workspace_config(ws, "auto_merge_spec_read: false\n")

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "core.engine.architect_pass_llm.run_architect_pass_llm"
    ) as architect_llm:
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )
        architect_llm.assert_not_called()

    payload = json.loads(raw)
    phases = payload["delegation_pipeline"]
    assert _phase_status(phases, "architect_pass") == "skipped"
    assert _phase_detail(phases, "architect_pass") == "heuristic_trivial_task"


def test_delegate_architect_spec_override_true_runs_single_file(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_ARCH_ON)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)
    arch = ArchitectPassLlmResult(
        success=True,
        plan="## Architect plan\n- Step one",
        model="cheap-model",
        duration_ms=20,
    )

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "core.engine.architect_pass_llm.run_architect_pass_llm", return_value=arch
    ) as architect_llm:
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )
        architect_llm.assert_called_once()

    payload = json.loads(raw)
    assert _phase_status(payload["delegation_pipeline"], "architect_pass") == "ok"


def test_delegate_architect_spec_override_false_skips(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_ARCH_OFF)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "core.engine.architect_pass_llm.run_architect_pass_llm"
    ) as architect_llm:
        raw = delegate_to_agent(
            task="Refactor CLI and core",
            target_files=["pkg/cli.py", "pkg/core.py"],
            context_summary="",
            spec_path="tasks/step-b.md",
            mode="implement",
        )
        architect_llm.assert_not_called()

    payload = json.loads(raw)
    phases = payload["delegation_pipeline"]
    assert _phase_status(phases, "architect_pass") == "skipped"
    assert _phase_detail(phases, "architect_pass") == "spec_override_false"
