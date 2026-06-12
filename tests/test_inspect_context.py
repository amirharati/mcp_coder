"""Tests for inspect_context dry-run (CLI + MCP + shared inspect module)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.cli.inspect_context import main_inspect_context
from core.context.inspect import inspect_context_package
from core.engine.architect_pass_llm import ArchitectPassLlmResult
from core.engine.context_builder_llm import BuilderLlmResult
from core.engine.spec_validation_llm import SpecValidationLlmResult
from server.mcp_server import inspect_context


STEP_5B_SPEC = """\
---
spec_id: step-5b
files_edit:
  - expense_splitter/models.py
files_read:
  - expense_splitter/loader.py
edit_scope: discover
---

# Step 5b

## Goal

Add comment above Expense.

## Files

### Edit

- `expense_splitter/models.py`

### Read

- `expense_splitter/loader.py`
"""


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-5b.md").write_text(STEP_5B_SPEC, encoding="utf-8")

    pkg = ws / "expense_splitter"
    pkg.mkdir()
    (pkg / "models.py").write_text("class Expense:\n    pass\n", encoding="utf-8")
    (pkg / "loader.py").write_text("def load():\n    return []\n", encoding="utf-8")
    return ws


def test_read_dep_omitted_from_target_files(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="Add comment above Expense",
        target_files=["expense_splitter/models.py"],
        context_summary="Step 5b read-context test",
        spec_path="tasks/step-5b.md",
    )

    assert result["ok"] is True
    assert result["compiler_version"] == "0.3.0"
    assert result["auto_merged_read_paths"] == ["expense_splitter/loader.py"]
    assert result["auto_merge_spec_read"] is True
    assert "contract_warnings" not in result
    assert "spec_files_missing_from_target" not in result

    preview = result["adapter_preview"]
    assert "expense_splitter/models.py" in preview["fnames"]
    assert "expense_splitter/loader.py" not in preview["fnames"]
    assert "expense_splitter/loader.py" in preview["read_paths_in_prompt"]
    assert preview["prompt_chars"] > 0
    assert preview["prompt_tokens_est"] > 0
    assert preview["prompt_hash"]


def test_no_spec_path_no_contract_warnings(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="Read models",
        target_files=["expense_splitter/models.py"],
        context_summary="hint only",
    )

    assert result["ok"] is True
    assert "contract_warnings" not in result
    assert "spec_files_missing_from_target" not in result
    paths = [e["path"] for e in result["context_package"]["entries"]]
    assert "expense_splitter/models.py" in paths


def test_invalid_spec_path_returns_error(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        context_summary="",
        spec_path="tasks/missing.md",
    )

    assert result["ok"] is False
    assert "error" in result
    assert "spec-template.md" in result["error"]


def test_cli_invalid_spec_exit_code_one(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    code = main_inspect_context(
        [
            "--task",
            "t",
            "--target-files",
            "expense_splitter/models.py",
            "--spec",
            "tasks/missing.md",
        ]
    )
    assert code == 1


def test_include_payloads_false_omits_payload_key(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        context_summary="",
        spec_path="tasks/step-5b.md",
        include_payloads=False,
    )

    assert result["ok"] is True
    for entry in result["context_package"]["entries"]:
        assert "payload" not in entry


def test_include_payloads_true_includes_payload(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        context_summary="",
        spec_path="tasks/step-5b.md",
        include_payloads=True,
    )

    assert result["ok"] is True
    by_path = {e["path"]: e for e in result["context_package"]["entries"]}
    assert "def load" in (by_path["expense_splitter/loader.py"].get("payload") or "")
    assert "class Expense" in (by_path["expense_splitter/models.py"].get("payload") or "")


def test_mcp_tool_returns_parseable_json(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    raw = inspect_context(
        task="Add comment",
        target_files=["expense_splitter/models.py"],
        context_summary="ctx",
        spec_path="tasks/step-5b.md",
    )
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert "adapter_preview" in payload
    assert payload["context_package"]["summary"]["compiler_version"] == "0.3.0"


def test_no_engine_called(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    def _boom(*args, **kwargs):
        raise AssertionError("get_engine must not be called during inspect")

    with patch("server.mcp_server.get_engine", side_effect=_boom):
        result = inspect_context_package(
            workspace=ws,
            task="t",
            target_files=["expense_splitter/models.py"],
            context_summary="",
            spec_path="tasks/step-5b.md",
        )
    assert result["ok"] is True


def test_no_adapter_preview_when_disabled(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        context_summary="",
        spec_path="tasks/step-5b.md",
        include_adapter_preview=False,
    )

    assert result["ok"] is True
    assert "adapter_preview" not in result


def test_cli_success_exit_code_zero(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    code = main_inspect_context(
        [
            "--task",
            "Add comment",
            "--target-files",
            "expense_splitter/models.py",
            "--context-summary",
            "ctx",
            "--spec",
            "tasks/step-5b.md",
            "--pretty",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True


def test_cli_target_files_comma_separated(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)

    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py", "expense_splitter/loader.py"],
        context_summary="",
        spec_path="tasks/step-5b.md",
    )
    assert result["ok"] is True
    assert "contract_warnings" not in result


def _write_workspace_config(workspace: Path, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def test_helper_phases_present_by_default(tmp_path):
    ws = _setup_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="t",
        target_files=["expense_splitter/models.py"],
        spec_path="tasks/step-5b.md",
    )
    assert result["ok"] is True
    assert "helper_phases" in result
    assert result["helper_phases"]["builder_llm"]["ran"] is False


def test_run_builder_llm_flag_applies_brief(tmp_path):
    ws = _setup_workspace(tmp_path)
    builder = BuilderLlmResult(
        success=True,
        brief="Focus on the Expense class docstring.",
        model="cheap-model",
        duration_ms=12,
        tokens={"input": 1, "output": 2, "total": 3, "source": "context_builder_llm"},
    )
    with patch(
        "core.engine.context_builder_llm.run_context_builder_llm", return_value=builder
    ):
        result = inspect_context_package(
            workspace=ws,
            task="Add comment",
            target_files=["expense_splitter/models.py"],
            spec_path="tasks/step-5b.md",
            run_builder_llm=True,
        )
    assert result["ok"] is True
    assert "## Builder brief" in result["context_package"]["brief"]
    assert result["helper_phases"]["builder_llm"]["applied"] is True
    assert result["helper_phases"]["builder_llm"]["model"] == "cheap-model"


def test_env_run_builder_llm_backward_compat(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_INSPECT_RUN_BUILDER_LLM", "1")
    builder = BuilderLlmResult(
        success=True,
        brief="Narrative from env.",
        model="cheap-model",
    )
    with patch(
        "core.engine.context_builder_llm.run_context_builder_llm", return_value=builder
    ):
        result = inspect_context_package(
            workspace=ws,
            task="t",
            target_files=["expense_splitter/models.py"],
            spec_path="tasks/step-5b.md",
        )
    assert result["helper_phases"]["builder_llm"]["applied"] is True


def test_run_architect_merges_plan_above_brief(tmp_path):
    ws = _setup_workspace(tmp_path)
    _write_workspace_config(ws, "architect_pass: true\n")
    arch = ArchitectPassLlmResult(
        success=True,
        plan="## Architect plan\n- Step one\n- Step two",
        model="cheap-model",
    )
    with patch("core.engine.architect_pass_llm.run_architect_pass_llm", return_value=arch):
        result = inspect_context_package(
            workspace=ws,
            task="Add comment",
            target_files=["expense_splitter/models.py"],
            spec_path="tasks/step-5b.md",
            run_architect=True,
        )
    brief = result["context_package"]["brief"]
    assert brief.startswith("## Architect plan")
    assert result["helper_phases"]["architect_pass"]["applied"] is True


def test_architect_above_builder_order(tmp_path):
    ws = _setup_workspace(tmp_path)
    _write_workspace_config(ws, "architect_pass: true\n")
    arch = ArchitectPassLlmResult(
        success=True,
        plan="## Architect plan\n- Plan first",
        model="cheap-model",
    )
    builder = BuilderLlmResult(
        success=True,
        brief="Builder narrative.",
        model="cheap-model",
    )
    with patch("core.engine.architect_pass_llm.run_architect_pass_llm", return_value=arch), patch(
        "core.engine.context_builder_llm.run_context_builder_llm", return_value=builder
    ):
        result = inspect_context_package(
            workspace=ws,
            task="Add comment",
            target_files=["expense_splitter/models.py"],
            spec_path="tasks/step-5b.md",
            run_architect=True,
            run_builder_llm=True,
        )
    brief = result["context_package"]["brief"]
    assert brief.startswith("## Architect plan")
    arch_pos = brief.index("## Architect plan")
    builder_pos = brief.index("## Builder brief")
    assert arch_pos < builder_pos


def test_spec_validation_would_block_but_inspect_ok(tmp_path):
    ws = _setup_workspace(tmp_path)
    _write_workspace_config(ws, "spec_validation: true\n")
    transcript = "User: please add logging\nAssistant: which module?"
    validation = SpecValidationLlmResult(
        success=True,
        passed=False,
        clarifications=["Which log level?", "Stdout or file?"],
        model="cheap-model",
    )
    with patch(
        "core.engine.spec_validation_llm.run_spec_validation_llm", return_value=validation
    ):
        result = inspect_context_package(
            workspace=ws,
            task="Add logging",
            target_files=["expense_splitter/models.py"],
            spec_path="tasks/step-5b.md",
            host_transcript=transcript,
            run_spec_validation=True,
        )
    assert result["ok"] is True
    sv = result["helper_phases"]["spec_validation"]
    assert sv["ran"] is True
    assert sv["passed"] is False
    assert sv["would_block_delegate"] is True
    assert sv["clarification_needed"] == ["Which log level?", "Stdout or file?"]


def test_force_helpers_runs_architect_when_disabled(tmp_path):
    ws = _setup_workspace(tmp_path)
    _write_workspace_config(ws, "architect_pass: false\n")
    arch = ArchitectPassLlmResult(
        success=True,
        plan="## Architect plan\n- Forced run",
        model="cheap-model",
    )
    with patch("core.engine.architect_pass_llm.run_architect_pass_llm", return_value=arch):
        result = inspect_context_package(
            workspace=ws,
            task="t",
            target_files=["expense_splitter/models.py"],
            spec_path="tasks/step-5b.md",
            run_architect=True,
            force_helpers=True,
        )
    assert result["helper_phases"]["architect_pass"]["applied"] is True


def test_cli_fail_on_validation_block_exit_two(tmp_path, monkeypatch, capsys):
    ws = _setup_workspace(tmp_path)
    monkeypatch.chdir(ws)
    _write_workspace_config(ws, "spec_validation: true\n")
    transcript_path = ws / "transcript.txt"
    transcript_path.write_text("User: clarify scope", encoding="utf-8")
    validation = SpecValidationLlmResult(
        success=True,
        passed=False,
        clarifications=["Need more detail"],
        model="cheap-model",
    )
    with patch(
        "core.engine.spec_validation_llm.run_spec_validation_llm", return_value=validation
    ):
        code = main_inspect_context(
            [
                "--task",
                "t",
                "--target-files",
                "expense_splitter/models.py",
                "--spec",
                "tasks/step-5b.md",
                "--run-spec-validation",
                "--host-transcript-file",
                str(transcript_path),
                "--fail-on-validation-block",
            ]
        )
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["helper_phases"]["spec_validation"]["would_block_delegate"] is True


def test_delegate_uses_shared_helper_llm_pipeline(tmp_path, monkeypatch):
    from core.engine.base import ExecutionResult
    from server.mcp_server import delegate_to_agent

    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_LLM", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[], model="m")
    engine = MagicMock()
    engine.model_name = "m"
    engine.capabilities.return_value = MagicMock()
    engine.run_context.return_value = fake

    def _fake_builder(**kwargs):
        pkg = kwargs["context_package"]
        return pkg, True, None, {"model": "cheap-model", "role": "context_builder"}

    shared_builder = MagicMock(side_effect=_fake_builder)
    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "server.mcp_server._shared_apply_builder_llm", shared_builder
    ):
        delegate_to_agent(
            task="t",
            target_files=["expense_splitter/models.py"],
            context_summary="ctx",
            spec_path="tasks/step-5b.md",
            mode="implement",
        )
    shared_builder.assert_called_once()


def test_main_py_inspect_context_subcommand(tmp_path):
    ws = _setup_workspace(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            "main.py",
            "inspect-context",
            "--workspace",
            str(ws),
            "--task",
            "t",
            "--target-files",
            "expense_splitter/models.py",
            "--spec",
            "tasks/step-5b.md",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True


def test_main_py_passes_helper_flags_to_inspect_cli(tmp_path):
    ws = _setup_workspace(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            "main.py",
            "inspect-context",
            "--workspace",
            str(ws),
            "--task",
            "t",
            "--target-files",
            "expense_splitter/models.py",
            "--spec",
            "tasks/step-5b.md",
            "--run-builder-llm",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        env={
            **dict(__import__("os").environ),
            "PYTHONPATH": str(repo_root),
        },
    )
    assert proc.returncode != 2, proc.stderr
    assert "unrecognized arguments" not in proc.stderr
