"""Prior failed delegation hints (P4-008)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from core.host.cursor_rules import _resolve_includes, bundled_cursor_rules_dir
from core.session.store import SessionAcquireResult, SessionStore
from core.storage.session_paths import prepare_delegation_storage
from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.prior_attempts import find_prior_failed_attempts
from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution
from server.mcp_server import delegate_to_agent


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_find_prior_failed_attempts_from_session_jsonl(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    storage = prepare_delegation_storage(ws)
    failed_id = "58bb9846-0000-0000-0000-000000000001"
    success_id = "e7dfb7cf-0000-0000-0000-000000000002"
    current_id = "29ab1276-0000-0000-0000-000000000003"
    _write_jsonl(
        storage.log_path,
        [
            {
                "delegation_id": failed_id,
                "success": False,
                "error": "spec_path must be under .mcp-coder/specs/tasks/",
                "outcome": "invalid_spec",
                "timestamp_end": "2026-06-09T10:00:00Z",
                "spec_path": "specs/tasks/foo.md",
            },
            {
                "delegation_id": success_id,
                "success": True,
                "outcome": "success",
                "timestamp_end": "2026-06-09T10:05:00Z",
            },
        ],
    )

    found = find_prior_failed_attempts(
        ws,
        spec_path=None,
        mcp_session_id=storage.mcp_session_id,
        exclude_delegation_id=current_id,
    )

    assert len(found) == 1
    assert found[0]["delegation_id"] == failed_id
    assert found[0]["success"] is False
    assert "spec_path must be under" in (found[0]["error"] or "")


def test_find_prior_failed_attempts_from_workspace_history(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    failed_id = str(uuid.uuid4())
    current_id = str(uuid.uuid4())
    spec_path = ".mcp-coder/specs/tasks/foo-v1.md"
    (ws / "m.py").write_text("a\n", encoding="utf-8")
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=failed_id,
        mcp_session_id="sess-fail",
        timestamp_start="2026-06-09T09:00:00Z",
        spec_path=spec_path,
        contract_paths=["m.py"],
    )
    (ws / "m.py").write_text("a\nb\n", encoding="utf-8")
    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["m.py"],
        edit_paths_rel=["m.py"],
        before_git=None,
        before_mtimes=None,
        delegation_id=failed_id,
    )
    db = WorkspaceHistoryDB(ws)
    db.finalize_checkpoint_metadata(
        delegation_id=failed_id,
        checkpoint_summary="bad path",
        delegate_mode="implement",
        outcome="failed",
        model="m",
        duration_ms=10,
        tokens_total=None,
        error_class="invalid_spec",
        delta_created=0,
        delta_modified=1,
        delta_deleted=0,
    )

    found = find_prior_failed_attempts(
        ws,
        spec_path="tasks/foo-v1.md",
        mcp_session_id=None,
        exclude_delegation_id=current_id,
    )

    assert len(found) == 1
    assert found[0]["delegation_id"] == failed_id
    assert found[0]["outcome"] == "failed"
    assert found[0]["error"] == "invalid_spec"


def test_delegate_second_call_surfaces_prior_failure(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "foo.py").write_text("x\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fail = ExecutionResult(
        success=False,
        output="",
        files_changed=[],
        model="m",
        error="engine failed",
        error_class="executor_error",
    )
    ok = ExecutionResult(
        success=True,
        output="ok",
        files_changed=["foo.py"],
        model="m",
        workspace_snapshot={"attribution_source": "manifest", "delta": {}},
    )
    calls = {"n": 0}

    def _run(*_args, **_kwargs):
        calls["n"] += 1
        return fail if calls["n"] == 1 else ok

    mock_engine = type("E", (), {"model_name": "m", "run": _run})()

    held: dict[str, SessionAcquireResult | None] = {"session": None}

    class ReuseSessionStore:
        def acquire(self, workspace, policy, host_hint):
            if held["session"] is None:
                held["session"] = SessionStore().acquire(workspace, policy, host_hint)
                return held["session"]
            base = held["session"]
            assert base is not None
            return SessionAcquireResult(
                project_key=base.project_key,
                mcp_session_id=base.mcp_session_id,
                session_dir=base.session_dir,
                log_path=base.log_path,
                workspace_path=base.workspace_path,
                is_new=False,
                session_action="reuse",
                session_reason="test_reuse",
                session_policy=base.session_policy,
            )

    with patch("server.mcp_server.SessionStore", ReuseSessionStore), patch(
        "server.mcp_server.get_engine", return_value=mock_engine
    ), patch(
        "core.workspace.history_query.safe_delegation_diff_dict",
        return_value=None,
    ):
        raw1 = delegate_to_agent(
            task="first try",
            target_files=["foo.py"],
            context_summary="ctx",
            backend="aider",
        )
        raw2 = delegate_to_agent(
            task="second try",
            target_files=["foo.py"],
            context_summary="ctx",
            backend="aider",
        )

    log_path = Path(json.loads(raw2)["log_path"])
    first_log = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    second = json.loads(raw2)

    assert "prior_failed_attempts" in second
    assert second["prior_failed_attempts_reminder"]
    assert second["prior_failed_attempts"][0]["delegation_id"] == first_log["delegation_id"]
    assert second["prior_failed_attempts"][0]["success"] is False


def test_bundled_rules_prior_failed_attempts_v12() -> None:
    rules_dir = bundled_cursor_rules_dir()
    for path in (
        rules_dir / "use-mcp-coder.default.mdc",
        rules_dir / "use-mcp-coder.strict.mdc",
    ):
        raw = path.read_text(encoding="utf-8")
        text = _resolve_includes(raw, rules_dir)  # compiled = what workspaces receive
        assert 'mcp_coder_rule_version: "13"' in text
        assert "prior_failed_attempts" in text
        assert "including failures" in text

    history = (rules_dir / "workspace-history.mdc").read_text(encoding="utf-8")
    assert 'mcp_coder_rule_version: "6"' in history
    assert "prior_failed_attempts" in history
