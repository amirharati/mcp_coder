"""Cursor rules manifest sync on MCP startup."""

from pathlib import Path

from core.host.cursor_rules import (
    bundled_use_mcp_coder_default_path,
    is_mcp_coder_source_root,
    rule_entries_for_policy,
    rule_filenames_for_policy,
    sync_workspace_cursor_rules,
    sync_workspace_delegate_rule,
    workspace_cursor_rules_dir,
    workspace_delegate_rule_path,
)


def test_default_policy_syncs_one_rule(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    ws.mkdir()
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)
    monkeypatch.delenv("MCP_CODER_CURSOR_RULES_POLICY", raising=False)

    result = sync_workspace_cursor_rules(ws)

    assert result["skipped"] is False
    assert result["policy"] == "default"
    assert len(result["rules"]) == 2
    rules_dir = workspace_cursor_rules_dir(ws)
    assert (rules_dir / "use-mcp-coder.mdc").is_file()
    assert (rules_dir / "workspace-history.mdc").is_file()
    assert not (rules_dir / "mcp-coder-delegate.mdc").exists()
    assert "mcp_coder_rules_policy: default" in (rules_dir / "use-mcp-coder.mdc").read_text()
    text = (rules_dir / "workspace-history.mdc").read_text()
    assert "list_delegations" in text
    assert "files_unexpected" in text
    assert 'mcp_coder_rule_version: "3"' in text


def test_strict_replaces_use_mcp_coder_content(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    ws.mkdir()
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)
    monkeypatch.setenv("MCP_CODER_CURSOR_RULES_POLICY", "strict")

    sync_workspace_cursor_rules(ws)
    rules_dir = workspace_cursor_rules_dir(ws)
    assert (rules_dir / "use-mcp-coder.mdc").is_file()
    assert (rules_dir / "workspace-history.mdc").is_file()
    assert not (rules_dir / "use-mcp-coder-strict.mdc").exists()
    assert not (rules_dir / "mcp-coder-delegate.mdc").exists()
    assert "mcp_coder_rules_policy: strict" in (rules_dir / "use-mcp-coder.mdc").read_text()


def test_policy_switch_updates_same_file(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    ws.mkdir()
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)

    sync_workspace_cursor_rules(ws)
    default_hash = _sha256_file(workspace_cursor_rules_dir(ws) / "use-mcp-coder.mdc")

    monkeypatch.setenv("MCP_CODER_CURSOR_RULES_POLICY", "strict")
    sync_workspace_cursor_rules(ws)
    strict_hash = _sha256_file(workspace_cursor_rules_dir(ws) / "use-mcp-coder.mdc")

    assert default_hash != strict_hash
    assert rule_filenames_for_policy("default") == rule_filenames_for_policy("strict")


def test_removes_legacy_delegate_rule(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    rules = ws / ".cursor" / "rules"
    rules.mkdir(parents=True)
    legacy = rules / "mcp-coder-delegate.mdc"
    legacy.write_text(
        "---\nmcp_coder_managed: true\n---\n# old\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)

    result = sync_workspace_cursor_rules(ws)

    assert "mcp-coder-delegate.mdc" in result["removed"]
    assert not legacy.exists()


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sync_updates_when_bundled_changes(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    ws.mkdir()
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)

    sync_workspace_cursor_rules(ws)
    bundled = bundled_use_mcp_coder_default_path()
    original = bundled.read_text(encoding="utf-8")
    bundled.write_text(original + "\n", encoding="utf-8")
    try:
        result = sync_workspace_cursor_rules(ws)
        rule = result["rules"][0]
        assert rule["updated"] is True
    finally:
        bundled.write_text(original, encoding="utf-8")


def test_sync_skips_user_owned_rule(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    ws.mkdir()
    rules = workspace_cursor_rules_dir(ws)
    rules.mkdir(parents=True)
    dest = workspace_delegate_rule_path(ws)
    dest.write_text("---\ndescription: custom\n---\n# my rule\n", encoding="utf-8")
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)

    result = sync_workspace_cursor_rules(ws)

    rule = result["rules"][0]
    assert rule["skipped"] is True
    assert rule["reason"] == "user_owned_rule"


def test_sync_disabled_by_env(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_SYNC_CURSOR_RULE", "0")

    result = sync_workspace_cursor_rules(ws)

    assert result["skipped"] is True
    assert not workspace_delegate_rule_path(ws).exists()


def test_skips_mcp_coder_source_root(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    assert is_mcp_coder_source_root(root) is True
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)

    result = sync_workspace_cursor_rules(root)

    assert result["skipped"] is True
    assert result["reason"] == "mcp_coder_source_root"


def test_delegate_wrapper_returns_rule_result(tmp_path, monkeypatch):
    ws = tmp_path / "app"
    ws.mkdir()
    monkeypatch.delenv("MCP_CODER_SYNC_CURSOR_RULE", raising=False)

    result = sync_workspace_delegate_rule(ws)

    assert result["filename"] == "use-mcp-coder.mdc"
    assert result["created"] is True


def test_rule_entries_use_dest_src_mapping():
    default = rule_entries_for_policy("default")
    strict = rule_entries_for_policy("strict")
    assert len(default) == len(strict) == 2
    assert default[0].dest == strict[0].dest == "use-mcp-coder.mdc"
    assert default[0].src != strict[0].src
    assert default[1].dest == strict[1].dest == "workspace-history.mdc"
    assert default[1].src == strict[1].src == "workspace-history.mdc"
