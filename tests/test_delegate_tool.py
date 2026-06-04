import json
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from server.mcp_server import delegate_to_agent


def test_delegate_to_agent_logs_and_returns(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)

    fake_result = ExecutionResult(
        success=True,
        output="done",
        files_changed=["hello.py"],
        model="gpt-4o",
        tokens={"source": "unavailable"},
    )

    mock_engine = type(
        "MockEngine",
        (),
        {"model_name": "gpt-4o", "backend_id": "aider", "run": lambda *a, **k: fake_result},
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Add hello world",
            target_files=["hello.py"],
            context_summary="Python 3.10+",
            backend="aider",
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["session_reused"] is False
    assert payload["session_policy"] == "always_new"
    assert payload["files_changed"] == ["hello.py"]
    assert "mcp_session_id" in payload
    assert "log_path" in payload

    log_path = Path(payload["log_path"])
    assert log_path.is_file()
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["success"] is True
    assert record["tool_name"] == "delegate_to_agent"
    assert record["project_key"]
    assert record["mcp_session_id"] == payload["mcp_session_id"]
    assert record["session_dir"]
    assert record["log_path"] == str(log_path.resolve())

    pointer = workspace / ".mcp-coder" / "session.json"
    assert pointer.is_file()
