"""Integration tests: delegate_to_agent context package path vs legacy path."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.context.package import TIER_EDIT_FULL, TIER_READ_EXCERPT, TIER_READ_FULL, ContextPackage
from core.engine.base import ExecutionResult
from core.engine.capabilities import BackendCapabilities
from server.mcp_server import delegate_to_agent


STEP_B_SPEC = """\
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
    (spec_dir / "step-b.md").write_text(STEP_B_SPEC, encoding="utf-8")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("def api(): return 1", encoding="utf-8")
    return ws


def _make_mock_engine(
    fake_result: ExecutionResult,
    captured: dict,
    *,
    caps: BackendCapabilities | None = None,
) -> object:
    from core.engine.capabilities import AIDER_CAPABILITIES

    _caps = caps if caps is not None else AIDER_CAPABILITIES

    def _run_context(self_ref, package, *, workspace_path, mcp_session_id=None, host_transcript=None):
        captured["package"] = package
        captured["called"] = "run_context"
        fake_result.prompt_used = "## Task\ntest"
        return fake_result

    def _run(self_ref, prompt, target_files, *, workspace_path, mcp_session_id=None):
        captured["called"] = "run"
        return fake_result

    def _capabilities(self_ref):
        return _caps

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


# ---------------------------------------------------------------------------
# Context package path active when spec + implement + env default
# ---------------------------------------------------------------------------


def test_run_context_called_when_spec_and_implement(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="done", files_changed=["pkg/cli.py"])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
            mode="implement",
        )

    assert captured.get("called") == "run_context", "run_context must be called on package path"
    payload = json.loads(raw)
    assert payload["success"] is True


def test_run_context_package_has_read_entry(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    pkg: ContextPackage = captured["package"]
    paths = {e.path: e for e in pkg.entries}
    assert "pkg/core.py" in paths, "read contract path must be in package even if not in target_files"
    assert paths["pkg/core.py"].tier == TIER_READ_FULL
    assert paths["pkg/core.py"].payload == "def api(): return 1"


def test_translate_does_not_put_read_path_in_fnames(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    from core.engine.aider_engine import translate_context_package

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    pkg: ContextPackage = captured["package"]
    req = translate_context_package(pkg)
    assert "pkg/core.py" not in req.fnames, "read path must NOT be in fnames"
    assert "pkg/cli.py" in req.fnames or req.fnames == [], (
        "cli.py is missing on disk (missing_paths); fnames may be empty or contain it if it exists"
    )
    assert "def api(): return 1" in req.prompt, "read payload must appear in prompt"


def test_response_has_context_package_summary(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    assert "context_package_summary" in payload
    summary = payload["context_package_summary"]
    assert summary["compiler_version"] == "0.3.0"
    assert "read_paths" in summary
    assert "pkg/core.py" in summary["read_paths"]


def test_jsonl_has_context_package_and_adapter_in(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())

    ctx = record["context"]
    assert "context_package" in ctx, "JSONL context must include context_package"
    assert "adapter_in" in ctx, "JSONL context must include adapter_in"
    assert "fnames" in ctx["adapter_in"]
    assert "read_paths_in_prompt" in ctx["adapter_in"]
    assert "pkg/core.py" in ctx["adapter_in"]["read_paths_in_prompt"]


# ---------------------------------------------------------------------------
# Legacy path when MCP_CODER_USE_CONTEXT_PACKAGE=0
# ---------------------------------------------------------------------------


def test_legacy_run_called_when_env_disabled(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    assert captured.get("called") == "run", "legacy engine.run must be called when env=0"
    payload = json.loads(raw)
    assert "context_package_summary" not in payload
    assert payload["success"] is True


def test_legacy_run_called_without_spec_path(tmp_path, monkeypatch):
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="No spec",
            target_files=["pkg/cli.py"],
            context_summary="context",
        )

    assert captured.get("called") == "run", "no spec_path → must use legacy run"
    payload = json.loads(raw)
    assert "context_package_summary" not in payload


# ---------------------------------------------------------------------------
# P2-212: capability degradation path
# ---------------------------------------------------------------------------


def test_degradation_read_full_to_read_excerpt_when_caps_false(tmp_path, monkeypatch):
    """When supports_read_only_in_chat=False, read-full entries are downgraded."""
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    no_read_caps = BackendCapabilities(
        backend_id="test",
        repo_map_source="git-tracked-only",
        chat_file_mode="full-text-in-chat",
        supports_read_only_in_chat=False,
        dynamic_add_files=True,
        dynamic_create_files=True,
        shell_default=False,
        session_continuity=False,
    )

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured, caps=no_read_caps)

    with patch("server.mcp_server.get_engine", return_value=engine):
        delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    assert captured.get("called") == "run_context"
    pkg: ContextPackage = captured["package"]
    paths = {e.path: e for e in pkg.entries}
    # core.py starts as read-full but should be degraded to read-excerpt
    assert paths["pkg/core.py"].tier == TIER_READ_EXCERPT, (
        "read-full entry must be degraded when supports_read_only_in_chat=False"
    )


def test_jsonl_has_backend_capabilities(tmp_path, monkeypatch):
    """backend_capabilities must appear in JSONL context block on every delegation."""
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert "backend_capabilities" in record["context"], (
        "backend_capabilities must be in JSONL context block"
    )
    caps_dict = record["context"]["backend_capabilities"]
    assert caps_dict["backend_id"] == "aider"
    assert caps_dict["supports_read_only_in_chat"] is True


def test_jsonl_has_backend_capabilities_on_legacy_path(tmp_path, monkeypatch):
    """backend_capabilities appears on every delegation, including legacy engine.run() path."""
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    assert captured.get("called") == "run"
    payload = json.loads(raw)
    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert "backend_capabilities" in record["context"], (
        "backend_capabilities must appear on legacy path too"
    )


def test_capability_warnings_in_jsonl_when_degraded(tmp_path, monkeypatch):
    """capability_warnings appear in JSONL when degradation occurs."""
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    no_read_caps = BackendCapabilities(
        backend_id="test",
        repo_map_source="git-tracked-only",
        chat_file_mode="full-text-in-chat",
        supports_read_only_in_chat=False,
        dynamic_add_files=True,
        dynamic_create_files=True,
        shell_default=False,
        session_continuity=False,
    )

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured, caps=no_read_caps)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert "capability_warnings" in record["context"], (
        "capability_warnings must appear in JSONL when degradation occurred"
    )
    assert any("pkg/core.py" in w for w in record["context"]["capability_warnings"])


def test_capability_warnings_on_mcp_response_when_degraded(tmp_path, monkeypatch):
    """Top-level capability_warnings mirror JSONL when degradation occurs."""
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    no_read_caps = BackendCapabilities(
        backend_id="test",
        repo_map_source="git-tracked-only",
        chat_file_mode="full-text-in-chat",
        supports_read_only_in_chat=False,
        dynamic_add_files=True,
        dynamic_create_files=True,
        shell_default=False,
        session_continuity=False,
    )

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured, caps=no_read_caps)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    assert "capability_warnings" in payload
    assert any("pkg/core.py" in w for w in payload["capability_warnings"])
    assert "capability_warnings" in payload["context_package_summary"]


def test_context_package_summary_includes_truncations(tmp_path, monkeypatch):
    """MCP context_package_summary includes budget truncations from compiler metadata."""
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUDGET_TOKENS", "200")
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    big_content = "\n".join(f"x{i} = {i}" for i in range(400))
    (ws / "pkg" / "core.py").write_text(big_content, encoding="utf-8")

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    summary = payload["context_package_summary"]
    assert "truncations" in summary
    assert any(t.get("path") == "pkg/core.py" for t in summary["truncations"])
    assert "entries" in summary
    assert any(e["path"] == "pkg/core.py" for e in summary["entries"])


def test_preflight_token_estimate_when_usage_report_disabled(tmp_path, monkeypatch):
    """preflight_token_estimate present on package path even when usage_report=false."""
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USAGE_REPORT", "0")
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[])
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    assert "usage" not in payload
    assert "preflight_token_estimate" in payload
    assert isinstance(payload["preflight_token_estimate"], int)
    assert payload["preflight_token_estimate"] > 0

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert "usage" in record


def test_actual_tokens_from_output_parse(tmp_path, monkeypatch):
    """usage.actual reflects aider_output_parse when engine provides parsed tokens."""
    ws = _setup_workspace(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_USE_CONTEXT_PACKAGE", raising=False)
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="Tokens: 2.4k sent, 53 received.",
        files_changed=[],
        model="mock-model",
        tokens={
            "input": 2400,
            "output": 53,
            "total": 2453,
            "source": "aider_output_parse",
        },
    )
    captured: dict = {}
    engine = _make_mock_engine(fake, captured)

    with patch("server.mcp_server.get_engine", return_value=engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["pkg/cli.py"],
            context_summary="Step 1",
            spec_path="tasks/step-b.md",
        )

    payload = json.loads(raw)
    assert payload["usage"]["actual"]["source"] == "aider_output_parse"
    assert payload["usage"]["actual"]["total"] == 2453
    assert payload["preflight_token_estimate"] == payload["usage"]["preflight_tokens_est"]
