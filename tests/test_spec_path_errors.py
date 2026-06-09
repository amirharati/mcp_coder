"""Actionable errors for repo-root specs/ paths."""

import re

import pytest

from core.host.cursor_rules import _resolve_includes, bundled_cursor_rules_dir
from core.specs.paths import normalize_spec_path_arg


def _has_bare_canonical_specs_path(text: str) -> bool:
    """True when a table or example uses repo-root specs/ as the canonical location."""
    bare = re.compile(r"(?<!\.mcp-coder/)specs/(tasks|epics|reports)/")
    for line in text.splitlines():
        if "repo root" in line.lower():
            continue
        if bare.search(line):
            return True
    return False


def test_repo_root_specs_tasks_raises_actionable_error() -> None:
    bad = "specs/tasks/tip-calc-01-core-v1.md"
    with pytest.raises(ValueError) as exc:
        normalize_spec_path_arg(bad)
    msg = str(exc.value)
    assert ".mcp-coder/specs/tasks/tip-calc-01-core-v1.md" in msg
    assert "move" in msg.lower()


def test_repo_root_specs_epics_raises_actionable_error() -> None:
    bad = "specs/epics/my-epic.md"
    with pytest.raises(ValueError) as exc:
        normalize_spec_path_arg(bad)
    msg = str(exc.value)
    assert ".mcp-coder/specs/epics/my-epic.md" in msg
    assert "move" in msg.lower()


def test_bare_repo_root_specs_file_suggests_tasks_path() -> None:
    bad = "specs/foo-step-v1.md"
    with pytest.raises(ValueError) as exc:
        normalize_spec_path_arg(bad)
    msg = str(exc.value)
    assert ".mcp-coder/specs/tasks/foo-step-v1.md" in msg
    assert "move" in msg.lower()


def test_tasks_shorthand_still_normalizes() -> None:
    assert (
        normalize_spec_path_arg("tasks/foo.md")
        == ".mcp-coder/specs/tasks/foo.md"
    )


def test_bundled_rules_use_mcp_coder_spec_paths() -> None:
    rules_dir = bundled_cursor_rules_dir()
    for path in (
        rules_dir / "use-mcp-coder.default.mdc",
        rules_dir / "use-mcp-coder.strict.mdc",
    ):
        raw = path.read_text(encoding="utf-8")
        text = _resolve_includes(raw, rules_dir)  # compiled = what workspaces receive
        assert 'mcp_coder_rule_version: "13"' in text
        assert ".mcp-coder/specs/tasks/" in text
        assert "Never" in text and "repo root" in text
        assert not _has_bare_canonical_specs_path(text)
        assert "`reports/<same-name>" not in text


def test_bundled_workspace_history_version_and_paths() -> None:
    text = (bundled_cursor_rules_dir() / "workspace-history.mdc").read_text(
        encoding="utf-8"
    )
    assert 'mcp_coder_rule_version: "6"' in text
    assert ".mcp-coder/specs/tasks/calc-02-cli-v1.md" in text
    assert not _has_bare_canonical_specs_path(text)
