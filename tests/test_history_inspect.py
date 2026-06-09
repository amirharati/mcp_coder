"""History inspect: browse, per-file timeline, latest resolution (P3-322f)."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.history_query import (
    build_checkpoint_detail,
    build_file_history,
    list_delegations,
    resolve_delegation_id,
)
from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution
from server.mcp_server import (
    get_checkpoint_detail,
    get_delegation_diff,
    get_file_history,
    list_delegations_tool,
)


def _seed(
    ws: Path,
    home: Path,
    monkeypatch,
    *,
    delegation_id: str | None = None,
    timestamp_start: str = "2026-06-08T00:00:00Z",
    summary: str | None = None,
    spec_report_path: str | None = None,
) -> str:
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    did = delegation_id or str(uuid.uuid4())
    (ws / "src" / "foo.py").parent.mkdir(parents=True, exist_ok=True)
    (ws / "src" / "foo.py").write_text("line1\n", encoding="utf-8")
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=did,
        mcp_session_id="sess-inspect",
        timestamp_start=timestamp_start,
        spec_path="tasks/foo.md",
        contract_paths=["src/foo.py"],
    )
    (ws / "src" / "foo.py").write_text("line1\nline2\n", encoding="utf-8")
    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["src/foo.py"],
        edit_paths_rel=["src/foo.py"],
        before_git=None,
        before_mtimes=None,
        delegation_id=did,
    )
    if summary is not None:
        db = WorkspaceHistoryDB(ws)
        db.finalize_checkpoint_metadata(
            delegation_id=did,
            checkpoint_summary=summary,
            delegate_mode="implement",
            outcome="delegated_ok",
            model="test-model",
            duration_ms=100,
            tokens_total=50,
            error_class=None,
            delta_created=0,
            delta_modified=1,
            delta_deleted=0,
            spec_report_path=spec_report_path,
        )
    return did


def test_resolve_delegation_id_latest(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    older = _seed(ws, home, monkeypatch, timestamp_start="2026-06-08T00:00:00Z")
    newer = _seed(ws, home, monkeypatch, timestamp_start="2026-06-08T02:00:00Z")

    assert resolve_delegation_id(ws, latest=True) == newer
    assert resolve_delegation_id(ws, delegation_id=older) == older
    assert resolve_delegation_id(ws) is None


def test_build_checkpoint_detail_no_diffs(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed(
        ws,
        home,
        monkeypatch,
        summary="Add loader",
        spec_report_path=".mcp-coder/specs/reports/foo.md",
    )

    detail = build_checkpoint_detail(ws, did)
    assert detail is not None
    assert detail.checkpoint_summary == "Add loader"
    assert detail.spec_report_path == ".mcp-coder/specs/reports/foo.md"
    assert "src/foo.py" in detail.modified
    assert not hasattr(detail, "diffs")


def test_mcp_list_delegations_and_file_filter(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed(ws, home, monkeypatch, summary="Touch foo")
    monkeypatch.chdir(ws)

    raw = list_delegations_tool(limit=10)
    payload = json.loads(raw)
    assert payload["found"] is True
    assert len(payload["delegations"]) == 1
    assert payload["delegations"][0]["delegation_id"] == did

    raw_filtered = list_delegations_tool(file_path="src/foo.py")
    filtered = json.loads(raw_filtered)
    assert filtered["found"] is True
    assert len(filtered["delegations"]) == 1

    raw_miss = list_delegations_tool(file_path="missing.py")
    miss = json.loads(raw_miss)
    assert miss["found"] is True
    assert miss["delegations"] == []


def test_mcp_get_delegation_diff_latest_and_file_path(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed(ws, home, monkeypatch, timestamp_start="2026-06-08T00:00:00Z")
    _seed(ws, home, monkeypatch, timestamp_start="2026-06-08T02:00:00Z")
    monkeypatch.chdir(ws)

    raw = get_delegation_diff(latest=True, file_path="src/foo.py")
    payload = json.loads(raw)
    assert payload["found"] is True
    assert "src/foo.py" in payload["delegation_diff"]["diffs"]
    assert "@@" in payload["delegation_diff"]["diffs"]["src/foo.py"]
    assert payload["delegation_diff"]["modified"] == ["src/foo.py"]

    raw_err = get_delegation_diff()
    err = json.loads(raw_err)
    assert err["found"] is False
    assert "latest=true" in err["error"]


def test_mcp_get_checkpoint_detail(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed(ws, home, monkeypatch, summary="Detail test")
    monkeypatch.chdir(ws)

    raw = get_checkpoint_detail(delegation_id=did)
    payload = json.loads(raw)
    assert payload["found"] is True
    assert payload["checkpoint"]["delegation_id"] == did
    assert payload["checkpoint"]["checkpoint_summary"] == "Detail test"
    assert "diffs" not in payload["checkpoint"]

    raw_miss = get_checkpoint_detail(delegation_id="00000000-0000-0000-0000-000000000000")
    miss = json.loads(raw_miss)
    assert miss["found"] is False


def test_mcp_get_file_history(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed(ws, home, monkeypatch, timestamp_start="2026-06-08T00:00:00Z", summary="First")
    _seed(ws, home, monkeypatch, timestamp_start="2026-06-08T02:00:00Z", summary="Second")
    monkeypatch.chdir(ws)

    raw = get_file_history("src/foo.py", limit=5)
    payload = json.loads(raw)
    assert payload["found"] is True
    assert payload["file_path"] == "src/foo.py"
    assert len(payload["changes"]) == 2
    assert payload["changes"][0]["checkpoint_summary"] == "Second"
    assert payload["changes"][0]["change_type"] == "modified"
    assert "diff" in payload["changes"][0]
    assert "@@" in payload["changes"][0]["diff"]


def test_build_file_history_helper(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed(ws, home, monkeypatch, summary="One")
    changes = build_file_history(ws, "src/foo.py")
    assert len(changes) == 1
    assert changes[0]["change_type"] == "modified"


def test_list_delegations_file_filter(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed(ws, home, monkeypatch, summary="Listed")
    rows = list_delegations(ws, file_path="src/foo.py")
    assert len(rows) == 1
    assert rows[0]["delegation_id"] == did


def test_cli_history_show_latest(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed(ws, home, monkeypatch, summary="CLI show summary")
    repo = Path(__file__).resolve().parents[1]

    proc = subprocess.run(
        [sys.executable, "main.py", "history", "show", "--latest", "--workspace", str(ws)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "CLI show summary" in proc.stdout
    assert "delegation_id:" in proc.stdout


def test_cli_history_diff_latest_path(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed(ws, home, monkeypatch)
    repo = Path(__file__).resolve().parents[1]

    proc = subprocess.run(
        [
            sys.executable,
            "main.py",
            "history",
            "diff",
            "--latest",
            "--path",
            "src/foo.py",
            "--workspace",
            str(ws),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "@@" in proc.stdout
    assert "line2" in proc.stdout


def test_cli_history_file_timeline(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed(ws, home, monkeypatch, summary="Timeline row")
    repo = Path(__file__).resolve().parents[1]

    proc = subprocess.run(
        [
            sys.executable,
            "main.py",
            "history",
            "file",
            "src/foo.py",
            "--workspace",
            str(ws),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Timeline row" in proc.stdout
    assert "modified" in proc.stdout


def test_cli_history_list_file_filter(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed(ws, home, monkeypatch, summary="Filter me")
    repo = Path(__file__).resolve().parents[1]

    proc = subprocess.run(
        [
            sys.executable,
            "main.py",
            "history",
            "list",
            "--file",
            "src/foo.py",
            "--workspace",
            str(ws),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert did[:8] in proc.stdout
    assert "Filter me" in proc.stdout
