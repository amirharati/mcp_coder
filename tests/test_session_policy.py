import json

from core.session.policy import (
    POLICY_ALIGN_HOST,
    POLICY_ALWAYS_NEW,
    resolve_session_policy,
)


def test_default_policy_is_always_new(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    assert resolve_session_policy(workspace) == POLICY_ALWAYS_NEW


def test_env_policy(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_SESSION_POLICY", POLICY_ALIGN_HOST)
    assert resolve_session_policy(workspace) == POLICY_ALIGN_HOST


def test_workspace_yaml_config_overrides_env(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text(
        "# comment\nsession_policy: always_new\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MCP_CODER_SESSION_POLICY", POLICY_ALIGN_HOST)
    assert resolve_session_policy(workspace) == POLICY_ALWAYS_NEW


def test_yaml_wins_over_legacy_json(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("session_policy: always_new\n", encoding="utf-8")
    (cfg / "config.json").write_text(
        json.dumps({"session_policy": POLICY_ALIGN_HOST}),
        encoding="utf-8",
    )
    monkeypatch.delenv("MCP_CODER_SESSION_POLICY", raising=False)
    assert resolve_session_policy(workspace) == POLICY_ALWAYS_NEW


def test_legacy_json_config_still_works(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.json").write_text(
        json.dumps({"session_policy": POLICY_ALIGN_HOST}),
        encoding="utf-8",
    )
    monkeypatch.delenv("MCP_CODER_SESSION_POLICY", raising=False)
    assert resolve_session_policy(workspace) == POLICY_ALIGN_HOST


def test_invalid_policy_falls_back_to_always_new(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_SESSION_POLICY", "invalid")
    assert resolve_session_policy(workspace) == POLICY_ALWAYS_NEW


def test_deprecated_fallback_session_maps_to_always_new(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_FALLBACK_SESSION", "always_new")
    assert resolve_session_policy(workspace) == POLICY_ALWAYS_NEW


def test_env_policy_wins_over_deprecated_fallback(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_SESSION_POLICY", POLICY_ALIGN_HOST)
    monkeypatch.setenv("MCP_CODER_FALLBACK_SESSION", "always_new")
    assert resolve_session_policy(workspace) == POLICY_ALIGN_HOST
