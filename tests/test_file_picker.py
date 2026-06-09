"""Rules-based file picker (P4-001a)."""

from __future__ import annotations

from pathlib import Path

import core.context.file_picker as fp
from core.config.context_builder import context_builder_enabled
from core.context.file_picker import (
    extract_symbol_queries,
    pick_candidate_files,
)
from core.specs.delegation_policies import (
    EDIT_SCOPE_DISCOVER,
    EDIT_SCOPE_STRICT,
    DelegationPolicies,
)


def _policies(
    *,
    files_edit: list[str] | None = None,
    files_read: list[str] | None = None,
    edit_scope: str = EDIT_SCOPE_DISCOVER,
) -> DelegationPolicies:
    edit = files_edit or []
    read = files_read or []
    return DelegationPolicies(
        files_edit=edit,
        files_read=read,
        edit_scope=edit_scope,
        allow_create=True,
        untracked_policy="materialize",
        all_paths=sorted(set(edit + read)),
    )


def _write(workspace: Path, rel: str, text: str) -> None:
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- enable flag ---


def test_context_builder_enabled_default_on(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", raising=False)
    assert context_builder_enabled(tmp_path) is True


def test_context_builder_env_disables(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    assert context_builder_enabled(tmp_path) is False


def test_context_builder_yaml_disables(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", raising=False)
    cfg = tmp_path / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("context_builder: false\n", encoding="utf-8")
    assert context_builder_enabled(tmp_path) is False


def test_context_builder_yaml_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    cfg = tmp_path / ".mcp-coder"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("context_builder: true\n", encoding="utf-8")
    assert context_builder_enabled(tmp_path) is True


# --- symbol extraction ---


def test_extract_symbols_backticks_and_def_class():
    task = "Refactor `resolve_widget` and add `WidgetStore` support"
    spec = "## Goal\n\nUse def build_widget and class WidgetBase as anchors."
    symbols = fp.extract_symbol_queries(task, spec)
    assert "resolve_widget" in symbols
    assert "WidgetStore" in symbols
    assert "build_widget" in symbols
    assert "WidgetBase" in symbols


def test_extract_symbols_filters_stopwords_short_and_paths():
    symbols = extract_symbol_queries(
        "Fix `the` `ab` `core/config/foo.py` `setup.py` issue", None
    )
    assert symbols == []


def test_extract_symbols_capped_at_20():
    task = " ".join(f"`symbol_{i:02d}`" for i in range(40))
    assert len(extract_symbol_queries(task, None)) == 20


# --- picker (Python fallback scan — force no rg for CI determinism) ---


def test_spec_contract_first_in_ranked_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    policies = _policies(files_edit=["src/app.py"], files_read=["src/util.py"])
    result = pick_candidate_files(
        workspace=tmp_path,
        task="No symbols here",
        spec_text=None,
        policies=policies,
        target_files=["src/hint.py"],
    )
    assert result.ranked_paths[:2] == ["src/app.py", "src/util.py"]
    assert "src/hint.py" in result.ranked_paths
    assert result.path_sources["src/app.py"] == "spec_edit"
    assert result.path_sources["src/util.py"] == "spec_read"
    assert result.path_sources["src/hint.py"] == "hint"


def test_discover_mode_finds_symbol_via_fallback_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    _write(tmp_path, "lib/helpers.py", "def resolve_widget():\n    pass\n")
    _write(tmp_path, "lib/other.py", "x = 1\n")
    policies = _policies(files_edit=["src/app.py"])
    result = pick_candidate_files(
        workspace=tmp_path,
        task="Wire up `resolve_widget` in the app",
        spec_text=None,
        policies=policies,
        target_files=[],
    )
    assert "lib/helpers.py" in result.discovered_read
    assert "lib/other.py" not in result.discovered_read
    assert "resolve_widget" in result.symbol_queries
    assert result.path_sources["lib/helpers.py"] == "symbol_scan"
    assert result.ranked_paths[-1] == "lib/helpers.py"


def test_strict_mode_no_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    _write(tmp_path, "lib/helpers.py", "def resolve_widget():\n    pass\n")
    policies = _policies(files_edit=["src/app.py"], edit_scope=EDIT_SCOPE_STRICT)
    result = pick_candidate_files(
        workspace=tmp_path,
        task="Wire up `resolve_widget`",
        spec_text=None,
        policies=policies,
        target_files=[],
    )
    assert result.discovered_read == []
    assert result.suggested_edit_paths == []
    assert result.symbol_queries == []
    assert result.ranked_paths == ["src/app.py"]


def test_suggested_edit_paths_under_edit_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    _write(tmp_path, "src/sibling.py", "def resolve_widget():\n    pass\n")
    _write(tmp_path, "lib/reader.py", "resolve_widget = None\n")
    policies = _policies(files_edit=["src/app.py"])
    result = pick_candidate_files(
        workspace=tmp_path,
        task="Use `resolve_widget`",
        spec_text=None,
        policies=policies,
        target_files=[],
    )
    # Same dir as files_edit → edit-like; other dir → read-only discovery
    assert result.suggested_edit_paths == ["src/sibling.py"]
    assert "lib/reader.py" in result.discovered_read
    assert "lib/reader.py" not in result.suggested_edit_paths


def test_discovered_capped_by_env(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    monkeypatch.setenv("MCP_CODER_PICKER_MAX_DISCOVERED", "2")
    for i in range(5):
        _write(tmp_path, f"lib/mod_{i}.py", "def resolve_widget():\n    pass\n")
    policies = _policies(files_edit=["src/app.py"])
    result = pick_candidate_files(
        workspace=tmp_path,
        task="Use `resolve_widget`",
        spec_text=None,
        policies=policies,
        target_files=[],
    )
    assert len(result.discovered_read) == 2


def test_contract_paths_never_in_discovered(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    _write(tmp_path, "src/app.py", "def resolve_widget():\n    pass\n")
    policies = _policies(files_edit=["src/app.py"])
    result = pick_candidate_files(
        workspace=tmp_path,
        task="Use `resolve_widget`",
        spec_text=None,
        policies=policies,
        target_files=[],
    )
    assert result.discovered_read == []
    assert result.ranked_paths == ["src/app.py"]


# --- assemble_context integration ---


SPEC_TEXT = """---
spec_id: widget-step
epic: widget
revision: 1
status: draft
---

## Goal

Wire `resolve_widget` into the app.

## Scope

One module.

## Files

### Edit

- `src/app.py`

### Read

- `src/util.py`

## Constraints

- none

## Done when

- [ ] done
"""


def _setup_spec_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    _write(ws, ".mcp-coder/specs/tasks/widget-step.md", SPEC_TEXT)
    _write(ws, "src/app.py", "def main():\n    pass\n")
    _write(ws, "src/util.py", "def helper():\n    pass\n")
    _write(ws, "lib/helpers.py", "def resolve_widget():\n    pass\n")
    _write(ws, "lib/extra.py", "def unrelated():\n    pass\n")
    return ws


def test_assemble_context_with_picker_materializes_discovered(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    from core.context.assemble import assemble_context
    from core.context.package import TIER_EDIT_FULL, TIER_MAP_ONLY

    ws = _setup_spec_workspace(tmp_path)
    spec_rel = ".mcp-coder/specs/tasks/widget-step.md"
    from core.specs.delegation_policies import load_delegation_policies
    from core.specs.read import read_task_spec

    spec_read = read_task_spec(ws / spec_rel, workspace=ws)
    policies = load_delegation_policies(
        spec_read.front_matter, spec_read.sections.get("Files", "")
    )
    picker = pick_candidate_files(
        workspace=ws,
        task="Wire `resolve_widget` into app",
        spec_text=spec_read.raw_text,
        policies=policies,
        target_files=["src/app.py", "src/util.py"],
    )
    assert "lib/helpers.py" in picker.discovered_read

    package = assemble_context(
        workspace=ws,
        spec_path=spec_rel,
        target_files=["src/app.py", "src/util.py"],
        task="Wire `resolve_widget` into app",
        context_summary="",
        policies=policies,
        picker_result=picker,
        include_repo_map=True,
    )

    by_path = {e.path: e for e in package.entries}
    # Edit tier invariant (D-P4-10): only spec files_edit get edit-full
    assert by_path["src/app.py"].tier == TIER_EDIT_FULL
    assert by_path["lib/helpers.py"].tier != TIER_EDIT_FULL
    assert by_path["lib/helpers.py"].payload is not None
    # Repo map covers remaining workspace files
    assert by_path["lib/extra.py"].tier == TIER_MAP_ONLY
    meta = package.metadata
    assert meta["context_builder_enabled"] is True
    assert "lib/helpers.py" in meta["candidate_files"]["discovered_read"]
    assert meta["repo_map_count"] >= 1


def test_assemble_context_without_picker_unchanged(tmp_path):
    from core.context.assemble import assemble_context

    ws = _setup_spec_workspace(tmp_path)
    spec_rel = ".mcp-coder/specs/tasks/widget-step.md"
    package = assemble_context(
        workspace=ws,
        spec_path=spec_rel,
        target_files=["src/app.py", "src/util.py"],
        task="Wire it",
        context_summary="",
        policies=None,
    )
    assert "candidate_files" not in package.metadata
    assert "context_builder_enabled" not in package.metadata
    paths = [e.path for e in package.entries]
    assert "lib/extra.py" not in paths


def test_brief_lists_suggested_edit_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    from core.context.assemble import assemble_context

    ws = _setup_spec_workspace(tmp_path)
    _write(ws, "src/sibling.py", "def resolve_widget():\n    pass\n")
    spec_rel = ".mcp-coder/specs/tasks/widget-step.md"
    from core.specs.delegation_policies import load_delegation_policies
    from core.specs.read import read_task_spec

    spec_read = read_task_spec(ws / spec_rel, workspace=ws)
    policies = load_delegation_policies(
        spec_read.front_matter, spec_read.sections.get("Files", "")
    )
    picker = pick_candidate_files(
        workspace=ws,
        task="Wire `resolve_widget`",
        spec_text=spec_read.raw_text,
        policies=policies,
        target_files=[],
    )
    assert "src/sibling.py" in picker.suggested_edit_paths

    package = assemble_context(
        workspace=ws,
        spec_path=spec_rel,
        target_files=[],
        task="Wire `resolve_widget`",
        context_summary="",
        policies=policies,
        picker_result=picker,
        include_repo_map=False,
    )
    assert "Suggested edit paths (not in spec contract)" in package.brief
    assert "src/sibling.py" in package.brief


def test_adapter_renders_repo_map_block(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    from core.context.assemble import assemble_context
    from core.engine.aider_engine import translate_context_package

    ws = _setup_spec_workspace(tmp_path)
    spec_rel = ".mcp-coder/specs/tasks/widget-step.md"
    from core.specs.delegation_policies import load_delegation_policies
    from core.specs.read import read_task_spec

    spec_read = read_task_spec(ws / spec_rel, workspace=ws)
    policies = load_delegation_policies(
        spec_read.front_matter, spec_read.sections.get("Files", "")
    )
    picker = pick_candidate_files(
        workspace=ws,
        task="No symbols",
        spec_text=None,
        policies=policies,
        target_files=[],
    )
    package = assemble_context(
        workspace=ws,
        spec_path=spec_rel,
        target_files=[],
        task="No symbols",
        context_summary="",
        policies=policies,
        picker_result=picker,
        include_repo_map=True,
    )
    req = translate_context_package(package)
    assert "## Repo map (symbols only" in req.prompt
    assert "`lib/extra.py` (map-only)" in req.prompt
    assert "def unrelated():" in req.prompt
    # fnames stay edit-full only (D-P4-9)
    assert req.fnames == ["src/app.py"]


def test_inspect_context_includes_candidate_files(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "_rg_available", lambda: False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", raising=False)
    from core.context.inspect import inspect_context_package

    ws = _setup_spec_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="Wire `resolve_widget` into app",
        target_files=["src/app.py", "src/util.py"],
        context_summary="",
        spec_path="tasks/widget-step.md",
    )
    assert result["ok"] is True
    meta = result["context_package"]["metadata"]
    assert meta["context_builder_enabled"] is True
    assert "lib/helpers.py" in meta["candidate_files"]["discovered_read"]
    assert meta["repo_map_count"] >= 1


def test_inspect_context_disabled_flag_no_picker(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_ENABLED", "0")
    from core.context.inspect import inspect_context_package

    ws = _setup_spec_workspace(tmp_path)
    result = inspect_context_package(
        workspace=ws,
        task="Wire `resolve_widget` into app",
        target_files=["src/app.py", "src/util.py"],
        context_summary="",
        spec_path="tasks/widget-step.md",
    )
    assert result["ok"] is True
    meta = result["context_package"]["metadata"]
    assert "candidate_files" not in meta
    assert "context_builder_enabled" not in meta
