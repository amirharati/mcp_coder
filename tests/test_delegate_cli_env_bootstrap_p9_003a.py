"""Regression: delegate CLI path must bootstrap env like stdio server (P9-003a)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

import main


def test_main_delegate_shortcut_calls_env_bootstrap_before_main_delegate(monkeypatch):
    bootstrap_calls: list[str] = []

    def _track_bootstrap() -> None:
        bootstrap_calls.append("bootstrap")

    monkeypatch.setattr(main, "_bootstrap_cli_env", _track_bootstrap)

    with patch("core.cli.delegate.main_delegate", return_value=0) as delegate_mock:
        monkeypatch.setattr(sys, "argv", ["mcp-coder", "delegate", "--task", "t"])
        with pytest.raises(SystemExit) as exc:
            main.main()

    assert exc.value.code == 0
    assert bootstrap_calls == ["bootstrap"]
    delegate_mock.assert_called_once_with(["--task", "t"])


def test_main_delegate_argparse_subcommand_calls_env_bootstrap(monkeypatch):
    bootstrap_calls: list[str] = []

    def _track_bootstrap() -> None:
        bootstrap_calls.append("bootstrap")

    monkeypatch.setattr(main, "_bootstrap_cli_env", _track_bootstrap)

    with patch("core.cli.delegate.main_delegate", return_value=0) as delegate_mock:
        monkeypatch.setattr(
            sys,
            "argv",
            ["mcp-coder", "delegate", "--task", "from-argparse"],
        )
        with pytest.raises(SystemExit) as exc:
            main.main()

    assert exc.value.code == 0
    assert bootstrap_calls == ["bootstrap"]
    delegate_mock.assert_called_once()


def test_bootstrap_cli_env_loads_dotenv_for_delegate(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".env").write_text(
        "AIDER_MODEL=openrouter/test/from-dotenv\nOPENROUTER_API_KEY=sk-from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(ws)
    monkeypatch.delenv("AIDER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    prev = {
        key: os.environ.get(key)
        for key in ("AIDER_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_API_BASE")
    }
    try:
        main._bootstrap_cli_env()

        assert os.environ.get("AIDER_MODEL") == "openrouter/test/from-dotenv"
        assert os.environ.get("OPENROUTER_API_KEY") == "sk-from-dotenv"
    finally:
        for key, value in prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
