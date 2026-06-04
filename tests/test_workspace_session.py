import json

from core.storage.session_paths import write_workspace_pointer


def test_write_workspace_pointer_does_not_touch_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    cfg_dir = workspace / ".mcp-coder"
    cfg_dir.mkdir(parents=True)
    config_path = cfg_dir / "config.yaml"
    config_path.write_text(
        "session_policy: align_host\n",
        encoding="utf-8",
    )

    session_path = write_workspace_pointer(workspace)
    assert session_path == cfg_dir / "session.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["project_key"]
    assert "configs" not in session
    assert "align_host" in config_path.read_text()
