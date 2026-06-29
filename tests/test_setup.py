"""Tests for mcp-coder setup command and test-model --all flag."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ok_result(model: str = "openrouter/test/model"):
    from core.cli.test_model import ModelTestResult

    return ModelTestResult(ok=True, model=model, message="ok", via="aider", latency_ms=500)


def _make_fail_result(model: str = "openrouter/test/model", message: str = "upstream 500"):
    from core.cli.test_model import ModelTestResult

    return ModelTestResult(ok=False, model=model, message=message, via="aider", latency_ms=200)


def _patch_setup_basics(monkeypatch, *, env_file: Path | None = None):
    """Minimal mocks so run_setup can build an mcp-coder entry."""
    if env_file is not None:
        monkeypatch.setattr("core.cli.setup.load_env_files", lambda: [env_file])
    else:
        monkeypatch.setattr("core.cli.setup.load_env_files", lambda: [])
    monkeypatch.setattr("core.cli.setup.apply_provider_env", lambda: None)
    monkeypatch.setattr("core.cli.setup._binary_path", lambda: "/usr/local/bin/mcp-coder")
    monkeypatch.delenv("AIDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)


def _expected_mcp_server_command() -> str:
    from core.version import repo_root

    return str(repo_root() / "bin" / "mcp-coder-server")


# ---------------------------------------------------------------------------
# setup — env found
# ---------------------------------------------------------------------------


def test_setup_env_found(monkeypatch, capsys, tmp_path):
    """Env file path appears in output with (found) when load_env_files returns a path."""
    env_file = tmp_path / ".env"
    env_file.write_text("AIDER_MODEL=openrouter/test/m\n")

    monkeypatch.setattr("core.cli.setup.load_env_files", lambda: [env_file])
    monkeypatch.setattr("core.cli.setup.apply_provider_env", lambda: None)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/m")
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)

    from core.cli.setup import run_setup

    rc = run_setup()
    out = capsys.readouterr().out

    assert rc == 0
    assert "(found)" in out
    assert str(env_file) in out


# ---------------------------------------------------------------------------
# setup — env not found → advice shown
# ---------------------------------------------------------------------------


def test_setup_env_not_found(monkeypatch, capsys):
    """When no .env exists, 'not found' is printed and advice is included in output."""
    monkeypatch.setattr("core.cli.setup.load_env_files", lambda: [])
    monkeypatch.setattr("core.cli.setup.apply_provider_env", lambda: None)
    monkeypatch.delenv("AIDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)

    from core.cli.setup import run_setup

    rc = run_setup()
    out = capsys.readouterr().out

    assert rc == 0
    assert "(not found)" in out
    assert "Tip:" in out or "env" in out.lower()


# ---------------------------------------------------------------------------
# setup --init-config — creates config when absent
# ---------------------------------------------------------------------------


def test_setup_init_config_creates_file(monkeypatch, capsys, tmp_path):
    """--init-config creates .mcp-coder/config.yaml from the example template."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("core.cli.setup.load_env_files", lambda: [])
    monkeypatch.setattr("core.cli.setup.apply_provider_env", lambda: None)
    monkeypatch.delenv("AIDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)

    from core.cli.setup import run_setup

    rc = run_setup(init_config=True)
    out = capsys.readouterr().out

    config_path = tmp_path / ".mcp-coder" / "config.yaml"
    assert rc == 0
    assert config_path.is_file(), "config.yaml should have been created"
    assert "Created:" in out
    content = config_path.read_text(encoding="utf-8")
    # Sanity check: example template has session_policy in it
    assert "session_policy" in content


# ---------------------------------------------------------------------------
# setup --init-config — error when config already exists
# ---------------------------------------------------------------------------


def test_setup_init_config_errors_if_exists(monkeypatch, capsys, tmp_path):
    """--init-config exits 1 when .mcp-coder/config.yaml already exists."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("core.cli.setup.load_env_files", lambda: [])
    monkeypatch.setattr("core.cli.setup.apply_provider_env", lambda: None)
    monkeypatch.delenv("AIDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)

    # Pre-create the config file
    config_dir = tmp_path / ".mcp-coder"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("session_policy: always_new\n")

    from core.cli.setup import run_setup

    rc = run_setup(init_config=True)
    err = capsys.readouterr().err

    assert rc == 1
    assert "already exists" in err


# ---------------------------------------------------------------------------
# setup — mcp.json block contains correct absolute binary path
# ---------------------------------------------------------------------------


def test_setup_mcp_json_contains_binary_path(monkeypatch, capsys):
    """mcp.json block embeds the auto-restart server wrapper path."""
    monkeypatch.setattr("core.cli.setup.load_env_files", lambda: [])
    monkeypatch.setattr("core.cli.setup.apply_provider_env", lambda: None)
    monkeypatch.delenv("AIDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)

    monkeypatch.setattr("core.cli.setup._binary_path", lambda: "/usr/local/bin/mcp-coder")
    expected_command = _expected_mcp_server_command()

    from core.cli.setup import run_setup

    rc = run_setup()
    out = capsys.readouterr().out

    assert rc == 0
    assert expected_command in out
    assert '"command"' in out
    assert "mcpServers" in out


# ---------------------------------------------------------------------------
# test-model --all — all-pass scenario
# ---------------------------------------------------------------------------


def test_test_model_all_passes(monkeypatch, capsys):
    """--all prints a table with OK for each role when all models pass."""
    models = {
        "executor": "openrouter/test/executor",
        "context_builder": "openrouter/test/builder",
        "review": "openrouter/test/executor",  # falls back to executor
        "supervisor": "openrouter/test/supervisor",
        "planner_pass": "openrouter/test/planner",
        "reviewer_pass": "openrouter/test/reviewer",
    }

    def fake_resolve(role, ws):
        return models[role]

    monkeypatch.setattr("core.cli.test_model.load_env_files", lambda: [])
    monkeypatch.setattr("core.cli.test_model.apply_provider_env", lambda: None)
    monkeypatch.setattr(
        "core.config.role_models.resolve_role_model_name",
        fake_resolve,
    )

    call_count = {"n": 0}

    def fake_run_test_model(*, model, prompt, max_tokens, via, print_resolution):
        call_count["n"] += 1
        return _make_ok_result(model=model)

    monkeypatch.setattr("core.cli.test_model.run_test_model", fake_run_test_model)

    from core.cli.test_model import print_test_all_result, run_test_model_all

    rows = run_test_model_all()
    rc = print_test_all_result(rows)
    out = capsys.readouterr().out

    assert rc == 0
    assert call_count["n"] == 6
    assert "OK" in out
    assert "All 6 passed." in out
    assert "(fallback from executor)" in out  # review falls back


# ---------------------------------------------------------------------------
# test-model --all — one-fail scenario → exit 1
# ---------------------------------------------------------------------------


def test_test_model_all_one_fail(monkeypatch, capsys):
    """--all returns exit code 1 and marks the failing role as FAIL."""
    models = {
        "executor": "openrouter/test/executor",
        "context_builder": "openrouter/test/builder",
        "review": "openrouter/test/executor",
        "supervisor": "openrouter/test/supervisor",
        "planner_pass": "openrouter/test/planner",
        "reviewer_pass": "openrouter/test/reviewer",
    }

    def fake_resolve(role, ws):
        return models[role]

    monkeypatch.setattr("core.cli.test_model.load_env_files", lambda: [])
    monkeypatch.setattr("core.cli.test_model.apply_provider_env", lambda: None)
    monkeypatch.setattr(
        "core.config.role_models.resolve_role_model_name",
        fake_resolve,
    )

    def fake_run_test_model(*, model, prompt, max_tokens, via, print_resolution):
        if "builder" in model:
            return _make_fail_result(model=model, message="upstream 500")
        return _make_ok_result(model=model)

    monkeypatch.setattr("core.cli.test_model.run_test_model", fake_run_test_model)

    from core.cli.test_model import print_test_all_result, run_test_model_all

    rows = run_test_model_all()
    rc = print_test_all_result(rows)
    out = capsys.readouterr().out

    assert rc == 1
    assert "FAIL" in out


# ---------------------------------------------------------------------------
# test-model --all + --model → argparse error
# ---------------------------------------------------------------------------


def test_test_model_all_and_model_mutually_exclusive(capsys):
    """Passing --all and --model together raises an argparse error."""
    from core.cli.test_model import main_test_model

    with pytest.raises(SystemExit) as exc_info:
        main_test_model(["--all", "--model", "some/model"])

    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# setup — resolve_role_model_name called for all three roles (integration smoke)
# ---------------------------------------------------------------------------


def test_setup_models_section_present(monkeypatch, capsys):
    """Models section lists executor, context_builder, and review."""
    monkeypatch.setattr("core.cli.setup.load_env_files", lambda: [])
    monkeypatch.setattr("core.cli.setup.apply_provider_env", lambda: None)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/exec")
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/builder")
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)

    from core.cli.setup import run_setup

    rc = run_setup()
    out = capsys.readouterr().out

    assert rc == 0
    assert "executor:" in out
    assert "context_builder:" in out
    assert "review:" in out
    assert "openrouter/test/exec" in out
    assert "openrouter/test/builder" in out
    # review falls back
    assert "falls back to executor" in out


# ---------------------------------------------------------------------------
# setup --local / --global (P4.5-002)
# ---------------------------------------------------------------------------


def test_setup_local_creates_mcp_json(monkeypatch, capsys, tmp_path):
    """--local creates .cursor/mcp.json when absent."""
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("AIDER_MODEL=openrouter/test/m\n")
    _patch_setup_basics(monkeypatch, env_file=env_file)

    from core.cli.setup import run_setup

    rc = run_setup(write_target="local")
    out = capsys.readouterr().out
    mcp_path = tmp_path / ".cursor" / "mcp.json"

    assert rc == 0
    assert mcp_path.is_file()
    assert "Created .cursor/mcp.json" in out
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["mcp-coder"]["command"] == _expected_mcp_server_command()
    assert data["mcpServers"]["mcp-coder"]["env"]["MCP_CODER_ENV_FILE"] == str(env_file)


def test_setup_local_merges_other_servers(monkeypatch, capsys, tmp_path):
    """--local merges mcp-coder when file exists with other servers."""
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("AIDER_MODEL=openrouter/test/m\n")
    _patch_setup_basics(monkeypatch, env_file=env_file)

    mcp_path = tmp_path / ".cursor" / "mcp.json"
    mcp_path.parent.mkdir(parents=True)
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other-tool": {"command": "other", "args": []},
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    from core.cli.setup import run_setup

    rc = run_setup(write_target="local")
    out = capsys.readouterr().out
    data = json.loads(mcp_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert "other servers unchanged" in out
    assert "other-tool" in data["mcpServers"]
    assert data["mcpServers"]["other-tool"]["command"] == "other"
    assert "mcp-coder" in data["mcpServers"]


def test_setup_local_updates_existing_mcp_coder_entry(monkeypatch, capsys, tmp_path):
    """--local updates mcp-coder key when entry already present."""
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("AIDER_MODEL=openrouter/test/m\n")
    _patch_setup_basics(monkeypatch, env_file=env_file)

    mcp_path = tmp_path / ".cursor" / "mcp.json"
    mcp_path.parent.mkdir(parents=True)
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "mcp-coder": {
                        "command": "/old/path",
                        "env": {"MCP_CODER_ENV_FILE": "/old/.env"},
                    },
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    from core.cli.setup import run_setup

    rc = run_setup(write_target="local")
    out = capsys.readouterr().out
    data = json.loads(mcp_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert "mcp-coder entry updated" in out
    assert data["mcpServers"]["mcp-coder"]["command"] == _expected_mcp_server_command()
    assert data["mcpServers"]["mcp-coder"]["env"]["MCP_CODER_ENV_FILE"] == str(env_file)


def test_setup_global_writes_to_mocked_path(monkeypatch, capsys, tmp_path):
    """--global writes to mocked OS global mcp.json path."""
    global_path = tmp_path / "global" / "mcp.json"
    monkeypatch.setattr("core.cli.setup._global_mcp_json_path", lambda: global_path)
    env_file = tmp_path / ".env"
    env_file.write_text("AIDER_MODEL=openrouter/test/m\n")
    _patch_setup_basics(monkeypatch, env_file=env_file)

    from core.cli.setup import run_setup

    rc = run_setup(write_target="global")
    out = capsys.readouterr().out

    assert rc == 0
    assert global_path.is_file()
    assert "Created" in out
    data = json.loads(global_path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["mcp-coder"]["command"] == _expected_mcp_server_command()


def test_setup_global_and_local_mutually_exclusive():
    """--global and --local together raise an argparse error."""
    from core.cli.setup import main_setup

    with pytest.raises(SystemExit) as exc_info:
        main_setup(["--global", "--local"])

    assert exc_info.value.code != 0


def test_setup_local_invalid_json_exits_without_modifying(monkeypatch, capsys, tmp_path):
    """Invalid JSON in existing file → exit 1, file byte-identical after call."""
    monkeypatch.chdir(tmp_path)
    _patch_setup_basics(monkeypatch)

    mcp_path = tmp_path / ".cursor" / "mcp.json"
    mcp_path.parent.mkdir(parents=True)
    bad_content = "{ not valid json\n"
    mcp_path.write_text(bad_content, encoding="utf-8")
    before = mcp_path.read_bytes()

    from core.cli.setup import run_setup

    rc = run_setup(write_target="local")
    err = capsys.readouterr().err
    after = mcp_path.read_bytes()

    assert rc == 1
    assert "Invalid JSON" in err
    assert after == before
