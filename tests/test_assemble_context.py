"""Unit tests for L2 assemble_context() and ContextPackage."""

import json
import subprocess
from pathlib import Path

from core.context.assemble import assemble_context
from core.context.package import TIER_EDIT_FULL, TIER_READ_FULL
from core.specs.delegation_policies import DelegationPolicies


STEP_A_SPEC = """\
---
spec_id: step-a
files_edit:
  - pkg/cli.py
files_read:
  - pkg/core.py
edit_scope: discover
---

# Step task spec

## Goal

Wire CLI to core API.

## Files

### Edit
- `pkg/cli.py`

### Read
- `pkg/core.py`

## Constraints

- Python 3.11+
"""


def _write_step_a_fixture(tmp_path: Path) -> None:
    spec_dir = tmp_path / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    (spec_dir / "step-a.md").write_text(STEP_A_SPEC, encoding="utf-8")
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "core.py").write_text("def api(): return 1", encoding="utf-8")


def _entry_by_path(pkg, path: str):
    for entry in pkg.entries:
        if entry.path == path:
            return entry
    return None


def test_spec_edit_read_tiers_and_contract_wins_over_hint(tmp_path):
    _write_step_a_fixture(tmp_path)

    pkg = assemble_context(
        workspace=tmp_path,
        spec_path="tasks/step-a.md",
        target_files=["pkg/cli.py"],
        task="Implement CLI",
        context_summary="Step 1",
        policies=None,
    )

    cli = _entry_by_path(pkg, "pkg/cli.py")
    core = _entry_by_path(pkg, "pkg/core.py")

    assert cli is not None
    assert cli.tier == TIER_EDIT_FULL
    assert cli.payload is None
    assert cli.bytes is None

    assert core is not None
    assert core.tier == TIER_READ_FULL
    assert core.payload == "def api(): return 1"
    assert core.bytes == len("def api(): return 1".encode("utf-8"))

    assert pkg.metadata["hint_paths"] == []
    assert pkg.metadata["missing_paths"] == ["pkg/cli.py"]
    assert pkg.metadata["untracked_paths"] == ["pkg/core.py"]
    assert pkg.metadata["compiler_version"] == "0.1.0"
    assert pkg.metadata["truncations"] == []

    assert "Implement CLI" in pkg.brief
    assert "Wire CLI to core API." in pkg.brief
    assert "Python 3.11+" in pkg.brief
    assert "`pkg/cli.py` — edit-full" in pkg.brief
    assert "`pkg/core.py` — read-full" in pkg.brief

    assert pkg.policies is not None
    assert pkg.policies.files_edit == ["pkg/cli.py"]
    assert pkg.policies.files_read == ["pkg/core.py"]


def test_no_spec_target_files_only_read_full(tmp_path):
    (tmp_path / "foo.py").write_text("x = 1\n", encoding="utf-8")

    pkg = assemble_context(
        workspace=tmp_path,
        spec_path=None,
        target_files=["foo.py", "missing.py"],
        task="Do foo",
        context_summary=None,
        policies=None,
    )

    foo = _entry_by_path(pkg, "foo.py")
    missing = _entry_by_path(pkg, "missing.py")

    assert foo.tier == TIER_READ_FULL
    assert foo.payload == "x = 1\n"
    assert missing.tier == TIER_READ_FULL
    assert missing.payload is None
    assert pkg.metadata["hint_paths"] == ["foo.py", "missing.py"]
    assert pkg.metadata["missing_paths"] == ["missing.py"]
    assert pkg.policies is None


def test_no_spec_with_explicit_policies(tmp_path):
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b\n", encoding="utf-8")

    policies = DelegationPolicies(
        files_edit=["a.py"],
        files_read=["b.py"],
        edit_scope="discover",
        allow_create=True,
        untracked_policy="materialize",
        all_paths=["a.py", "b.py"],
    )

    pkg = assemble_context(
        workspace=tmp_path,
        spec_path=None,
        target_files=["a.py"],
        task="Edit a",
        context_summary=None,
        policies=policies,
    )

    assert _entry_by_path(pkg, "a.py").tier == TIER_EDIT_FULL
    assert _entry_by_path(pkg, "b.py").tier == TIER_READ_FULL
    assert pkg.metadata["hint_paths"] == []
    assert pkg.policies is policies


def test_untracked_path_included_when_tracked_in_git(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "tracked.py").write_text("ok\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "tracked.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "new.py").write_text("new\n", encoding="utf-8")

    pkg = assemble_context(
        workspace=tmp_path,
        spec_path=None,
        target_files=["tracked.py", "new.py"],
        task="t",
        context_summary=None,
        policies=None,
    )

    assert "new.py" in pkg.metadata["untracked_paths"]
    assert "tracked.py" not in pkg.metadata["untracked_paths"]
    assert _entry_by_path(pkg, "new.py").payload == "new\n"


def test_token_estimate_and_bytes_by_tier(tmp_path):
    _write_step_a_fixture(tmp_path)

    pkg = assemble_context(
        workspace=tmp_path,
        spec_path="tasks/step-a.md",
        target_files=["pkg/cli.py"],
        task="Implement CLI",
        context_summary="Step 1",
        policies=None,
    )

    assert pkg.metadata["bytes_by_tier"]["read-full"] == len(
        "def api(): return 1".encode("utf-8")
    )
    assert pkg.metadata["bytes_by_tier"].get("edit-full", 0) == 0
    assert pkg.metadata["token_estimate_preflight"] >= 1


def test_sample_package_json_for_results(tmp_path):
    """Captures representative package shape for P2-200 § Results."""
    _write_step_a_fixture(tmp_path)

    pkg = assemble_context(
        workspace=tmp_path,
        spec_path="tasks/step-a.md",
        target_files=["pkg/cli.py"],
        task="Implement CLI",
        context_summary="Step 1",
        policies=None,
    )

    sample = {
        "brief": pkg.brief,
        "entries": [
            {
                "path": e.path,
                "tier": e.tier,
                "bytes": e.bytes,
                "payload": e.payload,
            }
            for e in pkg.entries
        ],
        "metadata": pkg.metadata,
    }
    assert sample["entries"][0]["path"] in ("pkg/cli.py", "pkg/core.py")
    json.dumps(sample)
