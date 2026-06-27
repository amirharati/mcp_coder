"""Canonical + legacy alias coverage for planner_pass rename (P11-008)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.config.planner_pass import planner_pass_enabled
from core.context.role_rules import build_role_rules
from core.context.planner_prompt import build_planner_pass_prompt
from core.context.file_picker import CandidateFilesResult
from core.engine.planner_pass_llm import PlannerPassLlmResult, run_planner_pass_llm
from core.engine.owned_helper_llm import OwnedHelperCompletion
from core.engine.architect_trigger import should_run_architect_pass
from core.engine.base import ExecutionResult
from core.engine.capabilities import AIDER_CAPABILITIES
from core.config.role_models import ROLE_PLANNER, ROLE_REVIEWER
from core.config.model_registry import ROLE_PLANNER_PASS
from core.specs.read import read_task_spec
from server.mcp_server import delegate_to_agent


STEP_SPEC_PLANNER_ON = """\
---
spec_id: p11-008-test
planner_pass: true
files_edit:
  - pkg/cli.py
files_read:
  - pkg/core.py
edit_scope: discover
---

# Planner pass test spec

## Goal

CLI uses core.

## Constraints

No DB changes.

## Files

### Edit
- `pkg/cli.py`

### Read
- `pkg/core.py`
"""

STEP_SPEC_ARCH_LEGACY = """\
---
spec_id: p11-008-legacy
architect_pass: true
files_edit:
  - pkg/cli.py
files_read:
  - pkg/core.py
edit_scope: discover
---

# Legacy spec

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


def _setup_workspace(tmp_path: Path, *, spec_text: str) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step.md").write_text(spec_text, encoding="utf-8")
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


# ── 1. Canonical env enables planner pass ─────────────────────────────────────


def test_canonical_env_enables(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_PLANNER_PASS", "1")
    monkeypatch.delenv("MCP_CODER_ARCHITECT_PASS", raising=False)
    assert planner_pass_enabled(tmp_path) is True


# ── 2. Legacy env enables with warning ────────────────────────────────────────


def test_legacy_env_enables_with_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("MCP_CODER_PLANNER_PASS", raising=False)
    monkeypatch.setenv("MCP_CODER_ARCHITECT_PASS", "1")
    with caplog.at_level(logging.WARNING, logger="core.config.planner_pass"):
        result = planner_pass_enabled(tmp_path)
    assert result is True
    assert any("architect_pass" in r.message for r in caplog.records)


# ── 3. Canonical spec key planner_pass: true works ────────────────────────────


def test_canonical_spec_key_enables(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_PLANNER_PASS", raising=False)
    monkeypatch.delenv("MCP_CODER_ARCHITECT_PASS", raising=False)
    _write_workspace_config(tmp_path, "planner_pass: true\n")
    assert planner_pass_enabled(tmp_path) is True


# ── 4. Legacy spec key architect_pass still works with warning ────────────────


def test_legacy_spec_key_enables_with_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("MCP_CODER_PLANNER_PASS", raising=False)
    monkeypatch.delenv("MCP_CODER_ARCHITECT_PASS", raising=False)
    _write_workspace_config(tmp_path, "architect_pass: true\n")
    with caplog.at_level(logging.WARNING, logger="core.config.planner_pass"):
        result = planner_pass_enabled(tmp_path)
    assert result is True
    assert any("architect_pass" in r.message for r in caplog.records)


# ── 5. Pipeline reports planner_pass phase ────────────────────────────────────


def test_pipeline_reports_planner_pass_phase(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_PLANNER_ON)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)
    arch = PlannerPassLlmResult(
        success=True,
        plan="## Planner plan\n- Step one",
        model="cheap-model",
        duration_ms=20,
        tokens={"input": 5, "output": 3, "total": 8, "source": "planner_pass"},
    )

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "core.engine.planner_pass_llm.run_planner_pass_llm", return_value=arch
    ):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step.md",
            mode="implement",
        )

    payload = json.loads(raw)
    assert _phase_status(payload["delegation_pipeline"], "planner_pass") == "ok"
    assert _phase_status(payload["delegation_pipeline"], "architect_pass") is None


# ── 6. Model role usage recorded under planner_pass ───────────────────────────


def test_model_role_usage_under_planner_pass(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_PLANNER_ON)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)
    arch = PlannerPassLlmResult(
        success=True,
        plan="## Planner plan\n- Step one",
        model="cheap-model",
        duration_ms=20,
        tokens={"input": 5, "output": 3, "total": 8, "source": "planner_pass"},
    )

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "core.engine.planner_pass_llm.run_planner_pass_llm", return_value=arch
    ):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step.md",
            mode="implement",
        )

    payload = json.loads(raw)
    assert "planner_pass" in payload["model_roles"]
    assert payload["model_roles"]["planner_pass"]["tokens"]["source"] == "planner_pass"
    assert "architect_pass" not in payload["model_roles"]


# ── 7. Legacy spec key still triggers planner pass (alias works) ──────────────


def test_legacy_spec_key_still_triggers_planner_pass(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_ARCH_LEGACY)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["pkg/cli.py"], model="m")
    engine = _make_mock_engine(fake)
    arch = PlannerPassLlmResult(
        success=True,
        plan="## Planner plan\n- Step one",
        model="cheap-model",
        duration_ms=20,
        tokens={"input": 5, "output": 3, "total": 8, "source": "planner_pass"},
    )

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "core.engine.planner_pass_llm.run_planner_pass_llm", return_value=arch
    ) as planner_llm:
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="",
            spec_path="tasks/step.md",
            mode="implement",
        )
        planner_llm.assert_called_once()

    payload = json.loads(raw)
    assert _phase_status(payload["delegation_pipeline"], "planner_pass") == "ok"


# ── 8. Role constants exist ────────────────────────────────────────────────────


def test_role_constants():
    assert ROLE_PLANNER == "planner_pass"
    assert ROLE_REVIEWER == "reviewer_pass"
    assert ROLE_PLANNER_PASS == "planner_pass"


# ── 9. Planner pass prompt contains ## Planner plan heading ───────────────────


def test_planner_pass_prompt_heading(tmp_path):
    from core.specs.read import read_task_spec as _rts

    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_PLANNER_ON)
    spec_read = _rts(ws / ".mcp-coder/specs/tasks/step.md", workspace=ws)
    prompt = build_planner_pass_prompt(
        spec_read=spec_read,
        mechanical_brief="## Paths\n- EDIT pkg/cli.py",
        picker_result=None,
        host_transcript=None,
        task="Implement CLI",
        context_summary="",
    )
    assert "## Role: task planner" not in prompt
    assert "## Planner plan" in build_role_rules("planner")
    assert "## Task spec summary" in prompt


def test_planner_prompt_builder_returns_no_preamble(tmp_path):
    from core.specs.read import read_task_spec as _rts

    ws = _setup_workspace(tmp_path, spec_text=STEP_SPEC_PLANNER_ON)
    spec_read = _rts(ws / ".mcp-coder/specs/tasks/step.md", workspace=ws)
    prompt = build_planner_pass_prompt(
        spec_read=spec_read,
        mechanical_brief="## Paths\n- EDIT pkg/cli.py",
        picker_result=None,
        host_transcript=None,
        task="Implement CLI",
        context_summary="",
    )
    assert "## Role: task planner" not in prompt
    assert "## Task spec summary" in prompt


def test_planner_llm_passes_system_prompt(tmp_path):
    completion = OwnedHelperCompletion(
        text="## Planner plan\n- Do the work.",
        model="openrouter/test/planner",
        tokens={"input": 10, "output": 5, "total": 15, "source": "owned_completion"},
        duration_ms=42,
    )
    with patch("core.engine.planner_pass_llm.provider_hint_for_model", return_value=None), patch(
        "core.engine.planner_pass_llm.run_owned_helper_completion", return_value=completion
    ) as run_completion:
        result = run_planner_pass_llm("## Task spec summary\nDo it", workspace_path=tmp_path)

    assert result.success is True
    run_completion.assert_called_once()
    assert run_completion.call_args.args[0] == [
        {"role": "user", "content": "## Task spec summary\nDo it"}
    ]
    assert run_completion.call_args.kwargs["system_prompt"] == build_role_rules("planner")


# ── 10. planner_pass key in architect_trigger takes precedence ────────────────


def test_trigger_planner_key_precedence_over_architect_key():
    from dataclasses import dataclass

    @dataclass
    class _Spec:
        meta: dict

    spec = _Spec(meta={"planner_pass": True, "architect_pass": False})
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="tiny",
        target_files=["a.py"],
        spec_read=spec,
    )
    assert run is True
