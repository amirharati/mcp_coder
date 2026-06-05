"""MCP startup creates workspace spec layout (same as delegate path)."""

from pathlib import Path

from core.specs.bootstrap import ensure_workspace_spec_layout
from core.specs.paths import workspace_spec_template_path, workspace_specs_tasks_dir


def test_startup_bootstrap_creates_layout(tmp_path, monkeypatch):
    """main.py calls ensure_workspace_spec_layout(ws) before run_stdio."""
    ws = tmp_path / "consumer-repo"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_WORKSPACE", str(ws))

    ensure_workspace_spec_layout(ws)

    assert workspace_spec_template_path(ws).is_file()
    assert workspace_specs_tasks_dir(ws).is_dir()
