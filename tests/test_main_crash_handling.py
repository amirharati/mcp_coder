"""B012/B011/P15-ISS-012: server crash handling for benign client disconnects.

When a long delegation times out on the Cursor side, Cursor closes the stdio
pipe. The MCP SDK raises BrokenResourceError (wrapped in an ExceptionGroup).
This is NOT a server bug — the server should exit gracefully (SystemExit(0))
and write a crash marker so the next session can detect orphaned writes.

Real errors (e.g. NameError, RuntimeError) must still re-raise and fail loudly.
"""

import json
from pathlib import Path

import anyio

# Match real runtime import order: server.mcp_server pulls in the full graph
# first, resolving the circular import between core.storage.paths and
# core.logging.server_log. Importing main or core.storage.paths directly
# without this precondition fails (pre-existing test-harness quirk).
import server.mcp_server  # noqa: F401
import main
from main import _flush_inflight_delegation_state, _is_client_disconnect


def test_direct_broken_resource_error_is_disconnect():
    """A bare anyio.BrokenResourceError is a benign client disconnect."""
    exc = anyio.BrokenResourceError()
    assert _is_client_disconnect(exc) is True


def test_exception_group_wrapping_broken_resource_is_disconnect():
    """The real crash pattern: ExceptionGroup wraps BrokenResourceError."""
    inner = anyio.BrokenResourceError()
    exc = ExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [inner])
    assert _is_client_disconnect(exc) is True


def test_nested_exception_group_wrapping_broken_resource_is_disconnect():
    """Nested ExceptionGroups still detect the disconnect."""
    inner = anyio.BrokenResourceError()
    mid = ExceptionGroup("inner", [inner])
    outer = ExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [mid])
    assert _is_client_disconnect(outer) is True


def test_real_value_error_is_not_disconnect():
    """Real bugs must NOT be silenced as disconnects."""
    assert _is_client_disconnect(ValueError("genuine bug")) is False


def test_nameerror_is_not_disconnect():
    """The legacy_contract NameError (B009) must NOT be treated as benign."""
    assert _is_client_disconnect(NameError("legacy_contract")) is False


def test_runtime_error_is_not_disconnect():
    """Generic runtime errors must propagate."""
    assert _is_client_disconnect(RuntimeError("legacy_contract not defined")) is False


def test_exception_group_with_real_error_is_not_disconnect():
    """An ExceptionGroup wrapping a real bug is NOT a disconnect."""
    inner = RuntimeError("genuine bug")
    exc = ExceptionGroup("task group error", [inner])
    assert _is_client_disconnect(exc) is False


def test_string_fallback_detects_broken_resource_in_message():
    """If anyio isn't importable, fall back to string matching."""
    exc = Exception("ConnectionResetError: BrokenResourceError occurred")
    assert _is_client_disconnect(exc) is True


def test_string_fallback_detects_broken_pipe():
    """Lower-level broken pipe errors are also benign disconnects."""
    exc = Exception("[Errno 32] Broken pipe")
    assert _is_client_disconnect(exc) is True


def test_flush_inflight_state_writes_crash_marker(tmp_path, monkeypatch):
    """Crash marker is written to the project's home dir with useful context."""
    import core.storage.paths

    fake_home = tmp_path / "mcp-coder-home"
    monkeypatch.setattr(core.storage.paths, "mcp_coder_home", lambda: str(fake_home))

    workspace = str(tmp_path / "consumer-repo")
    _flush_inflight_delegation_state(workspace)

    # Find the marker under projects/<key>/last_crash.json
    projects_dir = fake_home / "projects"
    markers = list(projects_dir.rglob("last_crash.json"))
    assert len(markers) == 1, f"expected 1 marker, found {len(markers)}"

    marker_data = json.loads(markers[0].read_text())
    assert marker_data["reason"] == "client_disconnect"
    assert marker_data["workspace"] == workspace
    assert "timestamp" in marker_data
    assert "pid" in marker_data


def test_flush_inflight_state_does_not_raise_on_failure(tmp_path, monkeypatch):
    """Marker write failures must never crash the exit handler."""
    import core.storage.paths

    # Make mcp_coder_home raise — the helper should swallow and continue.
    def boom():
        raise OSError("disk full")

    monkeypatch.setattr(core.storage.paths, "mcp_coder_home", boom)

    # Should not raise.
    _flush_inflight_delegation_state(str(tmp_path))
