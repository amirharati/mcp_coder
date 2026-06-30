"""P15-025 — deterministic file deletion (B022/B023). Acceptance D1–D9."""

from __future__ import annotations

import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.context.package import COMPILER_VERSION, ContextPackage, PathEntry, TIER_EDIT_FULL
from core.engine.aider_engine import (
    AiderEngine,
    _apply_deterministic_deletions,
)
from core.logging.delegation_log import executor_options_audit_var


@pytest.fixture(autouse=True)
def _reset_executor_options_audit_var():
    """``_execute_delegation`` sets ``executor_options_audit_var`` (a ContextVar
    read later by ``build_delegation_record`` outside the engine call) and the
    production finally does NOT reset it (it is intentionally read post-call).
    Tests that drive ``run_context`` here set it to a dict whose ``edit_format``
    is a MagicMock (mocked ``aider.models``), which would leak across tests and
    break ``test_reasoning_buffer``'s ``json.dumps(record)``. Reset around each
    test (matches the pattern in ``test_executor_options_p10_001.py``)."""
    executor_options_audit_var.set({})
    yield
    executor_options_audit_var.set({})
from core.specs.delegation_policies import (
    DelegationPolicies,
    EDIT_SCOPE_STRICT,
    UNTRACKED_POLICY_MATERIALIZE,
    append_executor_contract_prompt_blocks,
    build_files_delete_prompt_block,
    compute_scope_violations,
    load_delegation_policies,
)
from core.specs.files_contract import parse_files_contract
from core.specs.modes import DELEGATE_MODE_IMPLEMENT
from core.workspace.gateway import apply_post_delegation_gateway
from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution


def _git_init_commit(repo: Path, files: dict[str, str]) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", name], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)


def _policies(
    *,
    files_edit: list[str],
    files_read: list[str] | None = None,
    files_delete: list[str] | None = None,
) -> DelegationPolicies:
    files_read = files_read or []
    files_delete = files_delete or []
    return DelegationPolicies(
        files_edit=files_edit,
        files_read=files_read,
        files_delete=files_delete,
        edit_scope=EDIT_SCOPE_STRICT,
        allow_create=True,
        untracked_policy=UNTRACKED_POLICY_MATERIALIZE,
        all_paths=sorted(set(files_edit + files_read + files_delete)),
    )


@pytest.fixture
def mock_aider_stack(monkeypatch):
    mock_io = MagicMock()
    mock_io.num_error_outputs = 0
    mock_buffer = MagicMock()
    mock_buffer.getvalue.return_value = ""

    mock_coder = MagicMock()
    mock_coder.run.return_value = "done"

    mock_coder_cls = MagicMock()
    mock_coder_cls.create.return_value = mock_coder

    fake_coders = MagicMock()
    fake_coders.Coder = mock_coder_cls
    fake_models = MagicMock()
    fake_models.Model.return_value = MagicMock()
    mock_observable_cls = MagicMock()
    mock_observable_cls.return_value = MagicMock()

    monkeypatch.setitem(sys.modules, "aider.coders", fake_coders)
    monkeypatch.setitem(sys.modules, "aider.models", fake_models)
    monkeypatch.setattr("core.engine.observable_model.ObservableModel", mock_observable_cls)

    monkeypatch.setattr(
        "core.engine.aider_engine.create_delegation_io",
        lambda **k: (mock_io, mock_buffer),
    )
    monkeypatch.setattr("core.engine.aider_engine.snapshot_git_dirty", lambda ws: set())
    monkeypatch.setattr(
        "core.engine.aider_engine.merged_capture",
        lambda *a: "",
    )

    @contextmanager
    def fake_block_webbrowser_open():
        yield

    @contextmanager
    def fake_isolated_stdio():
        yield MagicMock(), MagicMock()

    monkeypatch.setattr("core.engine.aider_engine.block_webbrowser_open", fake_block_webbrowser_open)
    monkeypatch.setattr("core.engine.aider_engine.isolated_stdio", fake_isolated_stdio)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    return mock_coder_cls


# --- D1: contract parse ---


def test_d1_parse_delete_subsection():
    md = """\
### Edit

- `index.ts`

### Delete

- `a.ts`
- `b.ts`
"""
    policies = load_delegation_policies({}, md)
    assert policies.files_delete == ["a.ts", "b.ts"]


def test_d1_parse_yaml_files_delete():
    policies = load_delegation_policies(
        {"files_delete": ["yaml_del.ts"]},
        "### Delete\n\n- `md_del.ts`\n",
    )
    assert policies.files_delete == ["yaml_del.ts"]


def test_d1_no_delete_defaults_empty():
    policies = load_delegation_policies({}, "### Edit\n\n- `x.ts`\n")
    assert policies.files_delete == []


def test_d1_files_contract_delete_subsection():
    contract = parse_files_contract(
        "### Edit\n\n- `e.ts`\n\n### Delete\n\n- `d.ts`\n"
    )
    assert contract.delete == ["d.ts"]


# --- D2: all_paths includes delete ---


def test_d2_all_paths_includes_delete():
    policies = load_delegation_policies(
        {},
        "### Edit\n\n- `a.ts`\n\n### Read\n\n- `b.ts`\n\n### Delete\n\n- `c.ts`\n",
    )
    assert policies.all_paths == ["a.ts", "b.ts", "c.ts"]


def test_d2_all_paths_unchanged_without_delete():
    policies = load_delegation_policies(
        {},
        "### Edit\n\n- `a.ts`\n\n### Read\n\n- `b.ts`\n",
    )
    assert policies.all_paths == ["a.ts", "b.ts"]


# --- D3: scope gate ---


def test_d3_scope_gate_allows_engine_deletions():
    violations = compute_scope_violations(
        ["index.ts", "a.ts"],
        ["index.ts"],
        files_delete=["a.ts"],
    )
    assert violations == []


def test_d3_post_gateway_does_not_revert_deleted_path(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "index.ts").write_text("ok\n", encoding="utf-8")
    (ws / "a.ts").write_text("gone\n", encoding="utf-8")

    result = apply_post_delegation_gateway(
        workspace=ws,
        delegation_id="del-test",
        delegate_mode=DELEGATE_MODE_IMPLEMENT,
        edit_scope=EDIT_SCOPE_STRICT,
        files_changed=["index.ts", "a.ts"],
        files_edit=["index.ts"],
        files_delete=["a.ts"],
    )
    assert result.scope_violations == []
    assert result.reverted_paths == []


# --- D4: executor prompt delete block ---


def test_d4_prompt_contains_delete_and_allowed_blocks():
    prompt = append_executor_contract_prompt_blocks(
        "Do the task.",
        contract_paths=["index.ts", "a.ts"],
        files_delete=["a.ts"],
    )
    assert "### Files to be deleted (engine-managed)" in prompt
    assert "`a.ts`" in prompt
    assert "### Allowed paths" in prompt
    assert "index.ts" in prompt


def test_d4_empty_delete_no_block():
    assert build_files_delete_prompt_block([]) is None
    prompt = append_executor_contract_prompt_blocks(
        "task",
        contract_paths=["only.ts"],
        files_delete=[],
    )
    assert "### Files to be deleted" not in prompt
    assert "### Allowed paths" in prompt


def test_d4_run_context_prompt_used(mock_aider_stack, tmp_path, monkeypatch):
    monkeypatch.setattr("core.engine.aider_engine.snapshot_mtimes", lambda ws, paths: {})
    monkeypatch.setattr("core.engine.aider_engine.begin_delegation_snapshot", lambda **k: None)
    monkeypatch.setattr(
        "core.engine.aider_engine.resolve_delegation_attribution",
        lambda **k: ([], [], None, False, 0),
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "index.ts").write_text("export {}\n", encoding="utf-8")
    pkg = ContextPackage(
        brief="update index",
        entries=[
            PathEntry(path="index.ts", tier=TIER_EDIT_FULL, payload="export {}\n"),
        ],
        policies=_policies(files_edit=["index.ts"], files_delete=["a.ts"]),
        metadata={"compiler_version": COMPILER_VERSION},
    )
    engine = AiderEngine(model_name="openrouter/openai/gpt-4o-mini")
    result = engine.run_context(pkg, workspace_path=str(ws))
    assert result.prompt_used is not None
    assert "### Files to be deleted (engine-managed)" in result.prompt_used
    assert "### Allowed paths" in result.prompt_used
    assert "`a.ts`" in result.prompt_used


# --- D5: deterministic removal + attribution ---


def test_d5_git_deletion_attribution(mock_aider_stack, tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    ws = tmp_path / "ws"
    ws.mkdir()
    _git_init_commit(
        ws,
        {"a.ts": "export const a = 1;\n", "index.ts": "export * from './a';\n"},
    )

    def _snapshot_mtimes(workspace_path, paths):
        from core.engine.git_diff import snapshot_mtimes

        return snapshot_mtimes(workspace_path, paths)

    monkeypatch.setattr("core.engine.aider_engine.snapshot_mtimes", _snapshot_mtimes)

    def _edit_index(workspace_path, paths):
        index = Path(workspace_path) / "index.ts"
        index.write_text("export {}\n", encoding="utf-8")

    mock_coder_cls = mock_aider_stack

    def _run_side_effect(prompt):
        _edit_index(ws, [])
        return "done"

    mock_coder_cls.create.return_value.run.side_effect = _run_side_effect

    pkg = ContextPackage(
        brief="remove re-export",
        entries=[
            PathEntry(path="index.ts", tier=TIER_EDIT_FULL, payload="export * from './a';\n"),
        ],
        policies=_policies(files_edit=["index.ts"], files_delete=["a.ts"]),
        metadata={"compiler_version": COMPILER_VERSION},
    )
    engine = AiderEngine(model_name="openrouter/openai/gpt-4o-mini")
    result = engine.run_context(
        pkg,
        workspace_path=str(ws),
        delegation_id="d5-del",
    )

    assert not (ws / "a.ts").exists()
    assert result.files_deleted == ["a.ts"]
    assert "a.ts" in result.files_changed
    assert "index.ts" in result.files_changed
    assert result.workspace_snapshot is not None
    assert "a.ts" in result.workspace_snapshot["delta"]["deleted"]

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ws,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "D a.ts" in status.stdout or "D  a.ts" in status.stdout


# --- D6: path-escape guard ---


def test_d6_path_escape_skipped(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (ws / "safe.ts").write_text("ok\n", encoding="utf-8")

    removed, already_gone, skipped, failed = _apply_deterministic_deletions(
        str(ws),
        [f"../{outside.name}", "/etc/passwd", "safe.ts"],
    )
    assert removed == ["safe.ts"]
    assert outside.exists()
    assert not (ws / "safe.ts").exists()
    assert len(skipped) >= 1
    assert failed == []


# --- D7: untracked / non-repo removal ---


def test_d7_non_git_os_remove(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    target = ws / "orphan.ts"
    target.write_text("x\n", encoding="utf-8")

    removed, already_gone, skipped, failed = _apply_deterministic_deletions(
        str(ws),
        ["orphan.ts"],
    )
    assert removed == ["orphan.ts"]
    assert not target.exists()
    assert already_gone == []
    assert skipped == []
    assert failed == []


def test_d7_untracked_git_os_remove(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _git_init_commit(ws, {"tracked.ts": "t\n"})
    untracked = ws / "untracked.ts"
    untracked.write_text("u\n", encoding="utf-8")

    removed, _, skipped, failed = _apply_deterministic_deletions(
        str(ws),
        ["untracked.ts"],
    )
    assert removed == ["untracked.ts"]
    assert not untracked.exists()
    assert skipped == []
    assert failed == []


# --- D8: idempotent + directory skip ---


def test_d8_already_gone_not_in_removed(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    removed, already_gone, skipped, failed = _apply_deterministic_deletions(
        str(ws),
        ["missing.ts"],
    )
    assert removed == []
    assert already_gone == ["missing.ts"]
    assert skipped == []
    assert failed == []


def test_d8_directory_skipped_not_rmtree(tmp_path, caplog):
    ws = tmp_path / "ws"
    pkg_dir = ws / "pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "keep.ts").write_text("x\n", encoding="utf-8")

    removed, already_gone, skipped, failed = _apply_deterministic_deletions(
        str(ws),
        ["pkg"],
    )
    assert removed == []
    assert already_gone == []
    assert skipped == ["pkg"]
    assert failed == []
    assert pkg_dir.exists()
    assert (pkg_dir / "keep.ts").exists()


# --- D9: no-spec run ignores delete safely ---


def test_d9_run_ignores_delete_without_crash(mock_aider_stack, tmp_path, caplog, monkeypatch):
    import logging

    monkeypatch.setattr("core.engine.aider_engine.snapshot_mtimes", lambda ws, paths: {})
    monkeypatch.setattr("core.engine.aider_engine.begin_delegation_snapshot", lambda **k: None)
    monkeypatch.setattr(
        "core.engine.aider_engine.resolve_delegation_attribution",
        lambda **k: ([], [], None, False, 0),
    )
    caplog.set_level(logging.WARNING, logger="core.engine.aider_engine")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.ts").write_text("x\n", encoding="utf-8")
    engine = AiderEngine(model_name="openrouter/openai/gpt-4o-mini")
    result = engine.run(
        "task",
        ["a.ts"],
        workspace_path=str(ws),
        delete_paths_rel=["a.ts"],
    )
    assert (ws / "a.ts").exists()
    assert result.files_deleted == []
    assert any("files_delete ignored" in r.message for r in caplog.records)


# --- D-reg helper: backward-compatible compute_scope_violations ---


def test_compute_scope_violations_two_arg_unchanged():
    assert compute_scope_violations(["other.py"], ["a.py"]) == ["other.py"]
