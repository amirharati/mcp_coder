"""Tests for P8-002 — backend interception contract."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.cli.maintenance import main_maintenance
from core.engine import AiderEngine, get_engine
from core.engine.base import ExecutionEngine, ExecutionResult
from core.engine.factory import register_engine
from core.engine.interception_profile import (
    AIDER_INTERCEPTION_PROFILE,
    InterceptionProfile,
)


def test_aider_interception_profile_matches_audit():
    engine = get_engine("aider")
    profile = engine.interception_profile
    assert profile is AIDER_INTERCEPTION_PROFILE
    assert profile.strategy == "subclass"
    assert profile.verified_call_sites == ("aider/models.py:970",)
    assert "warm_cache_worker" in profile.known_gaps[0]
    assert "base_coder.py:1373" in profile.known_gaps[0]
    assert profile.thinking_captured is True


def test_aider_engine_interception_profile_property():
    engine = AiderEngine("test/model")
    assert engine.interception_profile is AIDER_INTERCEPTION_PROFILE


def test_engine_without_interception_profile_cannot_instantiate():
    class IncompleteEngine(ExecutionEngine):
        @property
        def backend_id(self) -> str:
            return "incomplete"

        def run(self, prompt, target_files, *, workspace_path):
            return ExecutionResult(success=True, output="ok")

    with pytest.raises(TypeError, match="abstract"):
        IncompleteEngine()


def test_get_engine_warns_when_thinking_not_captured():
    class PartialEngine(ExecutionEngine):
        @property
        def backend_id(self) -> str:
            return "partial_p8_002"

        @property
        def interception_profile(self) -> InterceptionProfile:
            return InterceptionProfile(
                strategy="proxy",
                verified_call_sites=(),
                known_gaps=("not implemented yet",),
                thinking_captured=False,
            )

        def run(self, prompt, target_files, *, workspace_path):
            return ExecutionResult(success=True, output="ok")

    register_engine("partial_p8_002", PartialEngine)
    with patch("core.observability.get_observability") as mock_get_obs:
        mock_obs = mock_get_obs.return_value
        engine = get_engine("partial_p8_002")
        assert engine.backend_id == "partial_p8_002"
        mock_obs.warn.assert_called_once_with(
            "interception_thinking_not_captured",
            {
                "backend": "partial_p8_002",
                "strategy": "proxy",
                "known_gaps": ["not implemented yet"],
            },
        )


def test_maintenance_stats_verbose_shows_aider_interception(tmp_path, capsys):
    ws = tmp_path / "repo"
    ws.mkdir()
    cfg = ws / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text("rag_enabled: false\n", encoding="utf-8")

    rc = main_maintenance(["stats", "--workspace", str(ws), "--verbose"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Backend: aider" in out
    assert "interception.strategy:      subclass" in out
    assert "interception.thinking:      true" in out
    assert "interception.verified:      aider/models.py:970" in out
    assert "interception.known_gaps:" in out
    assert "warm_cache_worker" in out


def test_interception_profile_module_has_no_server_imports():
    import ast
    from pathlib import Path

    source = Path("core/engine/interception_profile.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("server"), alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("server"), module
