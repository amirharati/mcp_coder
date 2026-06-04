import json

from core.logging.read_delegations import (
    load_delegations,
    load_delegations_for_workspace,
    load_delegations_merged,
)
from core.storage.session_paths import prepare_delegation_storage


def test_load_delegations_newest_first(tmp_path):
    log = tmp_path / "delegations.jsonl"
    log.write_text(
        '{"delegation_id":"a","timestamp_start":"t1"}\n'
        '{"delegation_id":"b","timestamp_start":"t2"}\n',
        encoding="utf-8",
    )
    rows = load_delegations(log)
    assert rows[0]["delegation_id"] == "b"
    assert rows[1]["delegation_id"] == "a"


def test_load_delegations_merged(tmp_path):
    first = tmp_path / "s1" / "delegations.jsonl"
    second = tmp_path / "s2" / "delegations.jsonl"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text(
        '{"delegation_id":"old","timestamp_end":"2026-06-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    second.write_text(
        '{"delegation_id":"new","timestamp_end":"2026-06-02T00:00:00Z"}\n',
        encoding="utf-8",
    )
    rows = load_delegations_merged([first, second])
    assert rows[0]["delegation_id"] == "new"
    assert rows[1]["delegation_id"] == "old"


def test_load_delegations_for_workspace(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)

    storage = prepare_delegation_storage(workspace)
    storage.log_path.write_text(
        json.dumps({"delegation_id": "home-1", "timestamp_end": "2026-06-03T00:00:00Z"})
        + "\n",
        encoding="utf-8",
    )

    rows = load_delegations_for_workspace(workspace)
    assert len(rows) == 1
    assert rows[0]["delegation_id"] == "home-1"
