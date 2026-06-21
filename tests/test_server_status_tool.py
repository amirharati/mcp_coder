import json

from server.mcp_server import get_server_status


def test_get_server_status_returns_freshness_fields() -> None:
    raw = get_server_status()
    data = json.loads(raw)

    assert isinstance(data.get("pid"), int)
    assert isinstance(data.get("source_root"), str)
    assert isinstance(data.get("source_revision"), str)
    assert "stale_vs_local_changes" in data
    assert isinstance(data.get("stale_sibling_pids"), list)
