"""P15-ISS-021: downgrade false needs_input_clarification when files changed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.config.aider_runtime import (
    OUTCOME_NEEDS_INPUT_CLARIFICATION,
    OUTCOME_NEEDS_INPUT_FILES,
    OUTCOME_SUCCESS,
)


def _clarification_classification() -> dict:
    return {
        "outcome": OUTCOME_NEEDS_INPUT_CLARIFICATION,
        "message": "Aider left an open question after edits.",
        "files_requested": [],
        "executor_output_tail": "Let me know if you'd like any tweaks?",
    }


def _run_delegation_with_files_changed(files_changed: list[str]):
    """Run _execute_delegation with clarification classification; return ExecutionResult."""
    pytest.importorskip("aider")
    from core.engine.aider_engine import AiderEngine

    class _CapturingFuture:
        def __init__(self, result):
            self._result = result

        def result(self, timeout=None):
            return self._result

        def cancel(self):
            pass

    class _CapturingPool:
        def submit(self, fn, *args, **kwargs):
            return _CapturingFuture(fn(*args))

        def shutdown(self, wait=True, cancel_futures=False):
            pass

    engine = AiderEngine("test/model")
    with (
        patch("core.engine.aider_engine.os.chdir"),
        patch("core.engine.aider_engine.begin_delegation_snapshot", return_value=None),
        patch("core.engine.aider_engine.snapshot_git_dirty", return_value=set()),
        patch("core.engine.aider_engine.snapshot_mtimes", return_value={}),
        patch(
            "core.engine.aider_engine.resolve_delegation_attribution",
            return_value=(files_changed, [], {}, False, 0),
        ),
        patch(
            "core.engine.aider_engine.concurrent.futures.ThreadPoolExecutor",
            return_value=_CapturingPool(),
        ),
        patch("core.engine.observable_model.ObservableModel"),
        patch("aider.coders.Coder") as coder_cls,
        patch(
            "core.engine.aider_engine.classify_executor_outcome",
            return_value=_clarification_classification(),
        ),
        patch(
            "core.engine.aider_engine.infer_run_success",
            return_value=(False, "Aider left an open question after edits."),
        ),
    ):
        mock_coder = MagicMock()
        mock_coder.run.return_value = "done"
        coder_cls.create.return_value = mock_coder
        return engine._execute_delegation(
            prompt="do thing",
            fnames_rel=["src/foo.ts"],
            edit_paths_rel=["src/foo.ts"],
            workspace_path="/tmp/ws",
            mcp_session_id=None,
        )


def test_clarification_downgraded_to_success_when_files_changed():
    result = _run_delegation_with_files_changed(["src/foo.ts"])

    assert result.success is True
    assert result.error is None
    assert result.error_class is None


def test_clarification_preserved_when_no_files_changed():
    result = _run_delegation_with_files_changed([])

    assert result.success is False
    assert result.error_class == OUTCOME_NEEDS_INPUT_CLARIFICATION


def test_needs_input_files_not_downgraded_when_files_changed():
    """D4: OUTCOME_NEEDS_INPUT_FILES must not be softened by the guard."""
    pytest.importorskip("aider")
    from core.engine.aider_engine import AiderEngine

    files_classification = {
        "outcome": OUTCOME_NEEDS_INPUT_FILES,
        "message": "Aider needs additional files.",
        "files_requested": ["missing.py"],
        "executor_output_tail": "",
    }

    class _CapturingFuture:
        def __init__(self, result):
            self._result = result

        def result(self, timeout=None):
            return self._result

        def cancel(self):
            pass

    class _CapturingPool:
        def submit(self, fn, *args, **kwargs):
            return _CapturingFuture(fn(*args))

        def shutdown(self, wait=True, cancel_futures=False):
            pass

    engine = AiderEngine("test/model")
    with (
        patch("core.engine.aider_engine.os.chdir"),
        patch("core.engine.aider_engine.begin_delegation_snapshot", return_value=None),
        patch("core.engine.aider_engine.snapshot_git_dirty", return_value=set()),
        patch("core.engine.aider_engine.snapshot_mtimes", return_value={}),
        patch(
            "core.engine.aider_engine.resolve_delegation_attribution",
            return_value=(["src/foo.ts"], [], {}, False, 0),
        ),
        patch(
            "core.engine.aider_engine.concurrent.futures.ThreadPoolExecutor",
            return_value=_CapturingPool(),
        ),
        patch("core.engine.observable_model.ObservableModel"),
        patch("aider.coders.Coder") as coder_cls,
        patch(
            "core.engine.aider_engine.classify_executor_outcome",
            return_value=files_classification,
        ),
        patch(
            "core.engine.aider_engine.infer_run_success",
            return_value=(False, "Aider needs additional files."),
        ),
    ):
        coder_cls.create.return_value = MagicMock()
        result = engine._execute_delegation(
            prompt="do thing",
            fnames_rel=["src/foo.ts"],
            edit_paths_rel=["src/foo.ts"],
            workspace_path="/tmp/ws",
            mcp_session_id=None,
        )

    assert result.success is False
    assert result.error_class == OUTCOME_NEEDS_INPUT_FILES
    assert result.error_class != OUTCOME_SUCCESS
