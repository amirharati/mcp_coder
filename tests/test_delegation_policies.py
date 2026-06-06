"""Unit tests for delegation policy parsing and scope checks."""

import pytest

from core.specs.delegation_policies import (
    PolicyValidationError,
    compute_scope_violations,
    load_delegation_policies,
)
from core.specs.outcome import (
    OUTCOME_SCOPE_VIOLATION,
    OUTCOME_SUCCESS,
    apply_scope_outcome,
)
from core.specs.sections import split_front_matter

MARKDOWN_FILES = """\
### Edit

- `pkg/a.py`

### Read (include in target_files)

- `pkg/b.py`
"""

YAML_LISTS = {
    "files_edit": ["expense_splitter/cli.py", "expense_splitter/__init__.py"],
    "files_read": ["expense_splitter/splitter.py"],
    "edit_scope": "strict",
    "allow_create": False,
    "untracked_policy": "materialize",
}


def test_load_from_yaml_lists():
    policies = load_delegation_policies(YAML_LISTS, "")
    assert policies.files_edit == [
        "expense_splitter/__init__.py",
        "expense_splitter/cli.py",
    ]
    assert policies.files_read == ["expense_splitter/splitter.py"]
    assert policies.edit_scope == "strict"
    assert policies.allow_create is False
    assert policies.untracked_policy == "materialize"
    assert policies.all_paths == [
        "expense_splitter/__init__.py",
        "expense_splitter/cli.py",
        "expense_splitter/splitter.py",
    ]


def test_load_from_markdown_only():
    policies = load_delegation_policies({}, MARKDOWN_FILES)
    assert policies.files_edit == ["pkg/a.py"]
    assert policies.files_read == ["pkg/b.py"]
    assert policies.edit_scope == "discover"
    assert policies.allow_create is True
    assert policies.untracked_policy == "materialize"


def test_yaml_overrides_markdown():
    policies = load_delegation_policies(
        {"files_edit": ["yaml_only.py"]},
        MARKDOWN_FILES,
    )
    assert policies.files_edit == ["yaml_only.py"]
    assert policies.files_read == ["pkg/b.py"]


def test_yaml_inline_flow_style():
    fm, _ = split_front_matter(
        "---\nfiles_edit: [a.py, b.py]\nfiles_read: [c.py]\n---\n"
    )
    policies = load_delegation_policies(fm, "")
    assert policies.files_edit == ["a.py", "b.py"]
    assert policies.files_read == ["c.py"]


def test_defaults_when_omitted():
    policies = load_delegation_policies({}, "")
    assert policies.edit_scope == "discover"
    assert policies.allow_create is True
    assert policies.untracked_policy == "materialize"
    assert policies.all_paths == []


def test_invalid_edit_scope():
    with pytest.raises(PolicyValidationError, match="edit_scope"):
        load_delegation_policies({"edit_scope": "tight"}, "")


def test_invalid_untracked_policy():
    with pytest.raises(PolicyValidationError, match="untracked_policy"):
        load_delegation_policies({"untracked_policy": "ignore"}, "")


def test_compute_scope_violations():
    violations = compute_scope_violations(
        ["pkg/a.py", "pkg/other.py"],
        ["pkg/a.py"],
    )
    assert violations == ["pkg/other.py"]


def test_compute_scope_violations_none_when_in_edit_set():
    assert compute_scope_violations(["pkg/a.py"], ["pkg/a.py"]) == []


def test_apply_scope_outcome_strict_with_violations():
    result = apply_scope_outcome(
        OUTCOME_SUCCESS,
        edit_scope="strict",
        scope_violations=["other.py"],
    )
    assert result == OUTCOME_SCOPE_VIOLATION


def test_apply_scope_outcome_discover_passthrough():
    result = apply_scope_outcome(
        OUTCOME_SUCCESS,
        edit_scope="discover",
        scope_violations=["other.py"],
    )
    assert result == OUTCOME_SUCCESS
