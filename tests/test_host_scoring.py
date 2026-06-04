from __future__ import annotations

import time
from pathlib import Path

from core.host.scoring import pick_host_session_id


def _candidate(host_id: str, tmp_path: Path, mtime_offset: float = 0) -> tuple[str, Path]:
    path = tmp_path / f"{host_id}.jsonl"
    path.write_text("{}", encoding="utf-8")
    if mtime_offset:
        ts = time.time() + mtime_offset
        path.touch()
        import os

        os.utime(path, (ts, ts))
    return host_id, path


def test_pick_newest_mtime_when_no_delegations(tmp_path):
    old_id, old_path = _candidate("old", tmp_path)
    new_id, new_path = _candidate("new", tmp_path)
    old_path.touch()
    time.sleep(0.02)
    new_path.touch()

    host_id, method = pick_host_session_id(
        [(old_id, old_path), (new_id, new_path)],
        {},
        tie_window_sec=10,
    )
    assert host_id == "new"
    assert method in ("score_window_multi", "score_global", "mtime_only")


def test_delegation_activity_wins_over_older_mtime(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_HOST_TIE_WINDOW_SEC", "10")
    old_id, old_path = _candidate("old", tmp_path)
    new_id, new_path = _candidate("new", tmp_path)
    new_path.touch()
    time.sleep(0.02)
    old_path.touch()

    now = time.time()
    activity = {"old": now}

    host_id, method = pick_host_session_id(
        [(old_id, old_path), (new_id, new_path)],
        activity,
        now=now + 0.05,
        tie_window_sec=10,
    )
    assert host_id == "old"
    assert method in ("score_window_multi", "score_global")


def test_single_candidate_in_window(tmp_path):
    path = tmp_path / "only.jsonl"
    path.write_text("{}", encoding="utf-8")
    path.touch()
    now = time.time()

    host_id, method = pick_host_session_id(
        [("only", path)],
        {},
        now=now,
        tie_window_sec=10,
    )
    assert host_id == "only"
    assert method == "score_window_single"
