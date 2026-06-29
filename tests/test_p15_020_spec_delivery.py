"""P15-ISS-020: spec file delivered to Aider via read_only_fnames."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _run_delegation_with_coder_capture(
    *,
    workspace_path: str,
    spec_path: str | None,
    fnames_rel: list[str] | None = None,
) -> dict:
    """Run _execute_delegation with mocks; return kwargs passed to Coder.create."""
    pytest.importorskip("aider")
    from core.engine.aider_engine import AiderEngine

    create_kwargs: dict = {}

    def _capture_create(**kwargs):
        create_kwargs.update(kwargs)
        mock_coder = MagicMock()
        mock_coder.run.return_value = "ok"
        return mock_coder

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
            return_value=([], [], {}, False, 0),
        ),
        patch(
            "core.engine.aider_engine.concurrent.futures.ThreadPoolExecutor",
            return_value=_CapturingPool(),
        ),
        patch("core.engine.observable_model.ObservableModel"),
        patch("aider.coders.Coder") as coder_cls,
    ):
        coder_cls.create.side_effect = _capture_create
        engine._execute_delegation(
            prompt="do thing",
            fnames_rel=fnames_rel or ["target.py"],
            edit_paths_rel=fnames_rel or ["target.py"],
            workspace_path=workspace_path,
            mcp_session_id=None,
            spec_path=spec_path,
        )
    return create_kwargs


def test_spec_path_added_to_read_only_fnames_when_exists(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "target.py").write_text("# target\n", encoding="utf-8")
    spec_dir = ws / ".mcp-coder" / "specs"
    spec_dir.mkdir(parents=True)
    spec_file = spec_dir / "P15-020.md"
    spec_file.write_text("# spec\n", encoding="utf-8")
    rel_spec = ".mcp-coder/specs/P15-020.md"

    kwargs = _run_delegation_with_coder_capture(
        workspace_path=str(ws),
        spec_path=rel_spec,
    )

    assert kwargs.get("read_only_fnames") == [str(spec_file)]


def test_spec_path_not_added_when_file_does_not_exist(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "target.py").write_text("# target\n", encoding="utf-8")

    kwargs = _run_delegation_with_coder_capture(
        workspace_path=str(ws),
        spec_path=".mcp-coder/specs/missing.md",
    )

    assert kwargs.get("read_only_fnames") == []


def test_spec_path_not_added_when_spec_path_is_none(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "target.py").write_text("# target\n", encoding="utf-8")

    kwargs = _run_delegation_with_coder_capture(
        workspace_path=str(ws),
        spec_path=None,
    )

    assert kwargs.get("read_only_fnames") == []
