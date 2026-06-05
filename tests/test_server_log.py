import json
import os

from core.logging.server_log import (
    get_server_log,
    resolve_config,
    server_log_emit,
    server_log_path_global,
    server_log_path_project,
)
from core.storage.paths import project_key


def _setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("MCP_CODER_SERVER_LOG", "1")
    monkeypatch.setenv("MCP_CODER_SERVER_LOG_LEVEL", "info")
    monkeypatch.setenv("MCP_CODER_SERVER_LOG_SCOPE", "global")
    return workspace


def test_emit_writes_global_server_log(tmp_path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    server_log_emit("stdio_server_ready", level="info", mcp_coder_home=str(tmp_path / "home"))

    path = server_log_path_global()
    assert path.is_file()
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["type"] == "server"
    assert record["event"] == "stdio_server_ready"
    assert record["level"] == "info"
    assert record["workspace_path"] == str(workspace.resolve())
    assert record["project_key"] == project_key(workspace)


def test_disabled_skips_file_write(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_SERVER_LOG", "0")
    server_log_emit("delegation_received", level="info", delegation_id="x")
    assert not server_log_path_global().exists()


def test_level_filter_blocks_info(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_SERVER_LOG_LEVEL", "error")
    server_log_emit("delegation_received", level="info", delegation_id="x")
    server_log_emit("delegation_failed", level="error", delegation_id="y", error="boom")
    lines = server_log_path_global().read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "delegation_failed"


def test_scope_project_only(tmp_path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_SERVER_LOG_SCOPE", "project")
    server_log_emit("host_resolved", level="info", host_kind="cursor")
    assert not server_log_path_global().exists()
    project_path = server_log_path_project(workspace)
    assert project_path.is_file()


def test_scope_both_writes_duplicate(tmp_path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_SERVER_LOG_SCOPE", "both")
    server_log_emit("session_acquired", level="info", mcp_session_id="abc")
    assert server_log_path_global().is_file()
    assert server_log_path_project(workspace).is_file()
    global_line = server_log_path_global().read_text(encoding="utf-8").strip()
    project_line = server_log_path_project(workspace).read_text(encoding="utf-8").strip()
    assert global_line == project_line


def test_yaml_overrides_env(tmp_path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_SERVER_LOG_SCOPE", "global")
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text(
        "server_log_scope: project\nserver_log_level: debug\n",
        encoding="utf-8",
    )
    config = resolve_config(workspace)
    assert config.scope == "project"
    assert config.level == "debug"


def test_redacts_secrets_in_task_preview(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    server_log_emit(
        "delegation_received",
        level="info",
        task_preview="use sk-abcdefghijklmnopqrstuvwxyz1234567890 here",
    )
    record = json.loads(server_log_path_global().read_text(encoding="utf-8").strip())
    assert "sk-***" in record["task_preview"]
    assert "abcdefghijklmnopqrstuvwxyz" not in record["task_preview"]


def test_get_server_log_singleton():
    assert get_server_log() is get_server_log()
