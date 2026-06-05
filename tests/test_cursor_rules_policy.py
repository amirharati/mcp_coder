"""cursor_rules_policy resolution."""

from core.host.cursor_rules_policy import (
    POLICY_STRICT,
    resolve_cursor_rules_policy,
    sync_cursor_rules_enabled,
)


def test_config_yaml_wins(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    cfg = ws / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("cursor_rules_policy: strict\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_CURSOR_RULES_POLICY", "default")

    assert resolve_cursor_rules_policy(ws) == POLICY_STRICT


def test_cursor_rules_sync_false_in_yaml(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    cfg = ws / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("cursor_rules:\n  sync: false\n", encoding="utf-8")
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)

    assert sync_cursor_rules_enabled(ws) is False
