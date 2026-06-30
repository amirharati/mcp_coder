"""P15-ISS-017 (B009) regression: no-spec delegations must not NameError.

Root cause (Epic 5 dogfood, ``dacd277``): the ``6dd0423`` fix moved the
allowed-paths contract binding (then named ``legacy_contract``) INTO the
``elif _use_pkg:`` branch of ``delegate_to_agent``. The no-spec outer
``else:`` branch still built an executor closure referencing that variable,
so a no-spec delegation walked into the ``else:``, called its closure, and
hit ``NameError: cannot access free variable 'legacy_contract'``. Epic 5
delegations ``9e6b67f2`` and ``ca1c548f`` (``spec_path: null``) both failed
this way.

Fix: bind ``allowed_paths`` BEFORE the ``if REVIEW / elif _use_pkg / else``
branch split so all three paths see it bound; rename ``legacy_contract`` →
``allowed_paths`` (it is the spec's file contract, not legacy code).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from server.mcp_server import delegate_to_agent

SPEC_BODY = """---
spec_id: b009-test
epic: b009-epic
status: open
---

# Step task spec

## Goal

Write a.py.

## Files

- `a.py`

## Done when

- [ ] File exists
"""


def _no_spec_delegate(monkeypatch, tmp_path: Path) -> dict:
    """Run a no-spec delegation with a mock engine; return the parsed payload."""
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True, output="ok", files_changed=["a.py"], model="m"
    )
    mock_engine = type(
        "E",
        (),
        {"model_name": "m", "run": lambda *a, **k: fake},
    )()
    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="t",
            target_files=["a.py"],
            context_summary="c",
        )
    return json.loads(raw)


def test_no_spec_delegation_does_not_nameerror(monkeypatch, tmp_path):
    """No-spec path must reach the executor and succeed (no NameError)."""
    payload = _no_spec_delegate(monkeypatch, tmp_path)
    # Pre-fix this was success=False, error_class="unknown" (NameError caught).
    assert payload["success"] is True
    assert payload.get("error_class") is None


def test_no_spec_delegation_no_outcome_key(monkeypatch, tmp_path):
    """A successful no-spec delegation returns no outcome field (legacy shape)."""
    payload = _no_spec_delegate(monkeypatch, tmp_path)
    assert "outcome" not in payload


def test_allowed_paths_bound_before_branch_split():
    """Structural guard: ``allowed_paths`` must be bound before the executor
    if/elif/else chain so the no-spec ``else:`` closure can't hit an unbound
    free variable (the B009 class of bug)."""
    from core.version import repo_root

    src = (repo_root() / "server" / "mcp_server.py").read_text(encoding="utf-8")
    # The binding must exist and use the honest name.
    assert "allowed_paths: list[str] | None = None" in src
    # The old misleading name must be gone entirely.
    assert "legacy_contract" not in src
    # The branch split must come AFTER the binding (the binding may not be the
    # first match for its line, and `delegate_mode == REVIEW` appears elsewhere
    # too, so search within the slice that follows the binding).
    bind_idx = src.index("allowed_paths: list[str] | None = None")
    rest = src[bind_idx:]
    assert "if delegate_mode == DELEGATE_MODE_REVIEW:" in rest
    assert "elif _use_pkg:" in rest
    review_idx = rest.index("if delegate_mode == DELEGATE_MODE_REVIEW:")
    use_pkg_idx = rest.index("elif _use_pkg:")
    assert review_idx < use_pkg_idx


def test_spec_backed_delegation_still_succeeds(monkeypatch, tmp_path):
    """Spec-backed path (``_use_pkg`` → ``run_context``) must still work after
    the rename/move — guards against regressing the working path."""
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    specs = ws / ".mcp-coder" / "specs" / "tasks"
    specs.mkdir(parents=True)
    (specs / "b009.md").write_text(SPEC_BODY, encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True, output="ok", files_changed=["a.py"], model="m"
    )
    # Spec-backed path calls engine.run_context (not engine.run).
    mock_engine = type(
        "E",
        (),
        {
            "model_name": "m",
            "run": lambda *a, **k: fake,
            "run_context": lambda *a, **k: fake,
        },
    )()
    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="t",
            target_files=["a.py"],
            context_summary="c",
            spec_path="tasks/b009.md",
        )
    payload = json.loads(raw)
    assert payload["success"] is True
