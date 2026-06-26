"""P14-004 contextvar leak fixture: asserts delegation_id_var / session_dir_var / workspace_var
reset correctly between two sequential delegations in the same process.

Per the master's ruling: uses the lighter form with two bind_delegation calls
(unit-test semantics), not full two-delegation pipeline harness.
"""

from __future__ import annotations

from pathlib import Path

from core.observability.context import (
    bind_delegation,
    bind_delegation_trace_scope,
    clear_delegation_context,
    delegation_id_var,
    session_dir_var,
    workspace_var,
)


def test_contextvar_leak_between_delegations() -> None:
    """Two bind_delegation calls should not leak state into each other."""
    clear_delegation_context()

    assert delegation_id_var.get() is None
    assert session_dir_var.get() is None
    assert workspace_var.get() is None

    # First delegation
    token1 = bind_delegation("deleg-aaa")
    bind_delegation_trace_scope(
        workspace="/tmp/ws1",
        session_dir=Path("/tmp/ws1/sessions/sess-aaa"),
    )
    assert delegation_id_var.get() == "deleg-aaa"
    assert session_dir_var.get() == "/tmp/ws1/sessions/sess-aaa"
    assert workspace_var.get() == "/tmp/ws1"

    # Reset
    delegation_id_var.reset(token1)
    clear_delegation_context()

    assert delegation_id_var.get() is None
    assert session_dir_var.get() is None
    assert workspace_var.get() is None

    # Second delegation
    token2 = bind_delegation("deleg-bbb")
    bind_delegation_trace_scope(
        workspace="/tmp/ws2",
        session_dir=Path("/tmp/ws2/sessions/sess-bbb"),
    )
    assert delegation_id_var.get() == "deleg-bbb", "delegation_id leaked from deleg-aaa"
    assert session_dir_var.get() == "/tmp/ws2/sessions/sess-bbb", "session_dir leaked from deleg-aaa"
    assert workspace_var.get() == "/tmp/ws2", "workspace leaked from deleg-aaa"

    # Reset
    delegation_id_var.reset(token2)
    clear_delegation_context()

    assert delegation_id_var.get() is None
    assert session_dir_var.get() is None
    assert workspace_var.get() is None