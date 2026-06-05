from core.context.transcript_policy import (
    POLICY_DUMP,
    POLICY_NONE,
    resolve_host_transcript_policy,
)


def test_default_policy_is_none(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    assert resolve_host_transcript_policy(workspace) == POLICY_NONE


def test_env_policy_dump(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOST_TRANSCRIPT", POLICY_DUMP)
    assert resolve_host_transcript_policy(workspace) == POLICY_DUMP


def test_workspace_yaml_overrides_env(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("host_transcript: none\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOST_TRANSCRIPT", POLICY_DUMP)
    assert resolve_host_transcript_policy(workspace) == POLICY_NONE


def test_yaml_dump_wins_over_env_none(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("host_transcript: dump\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOST_TRANSCRIPT", POLICY_NONE)
    assert resolve_host_transcript_policy(workspace) == POLICY_DUMP


def test_invalid_policy_falls_back_to_none(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOST_TRANSCRIPT", "smart")
    assert resolve_host_transcript_policy(workspace) == POLICY_NONE
