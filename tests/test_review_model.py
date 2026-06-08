"""Unit tests for review model resolution (P2-310)."""

from __future__ import annotations

from pathlib import Path

from core.config.models import resolve_model_name
from core.config.review_model import resolve_review_model_name


def _write_workspace_config(workspace: Path, content: str) -> None:
    cfg = workspace / ".mcp-coder"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(content, encoding="utf-8")


def test_default_matches_executor_model(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    assert resolve_review_model_name(tmp_path) == resolve_model_name()


def test_env_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    monkeypatch.setenv("MCP_CODER_REVIEW_MODEL", "openrouter/test/review-model")
    assert resolve_review_model_name(tmp_path) == "openrouter/test/review-model"


def test_yaml_only(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_REVIEW_MODEL", raising=False)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    _write_workspace_config(tmp_path, "review_model: openrouter/test/yaml-review\n")
    assert resolve_review_model_name(tmp_path) == "openrouter/test/yaml-review"


def test_yaml_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_REVIEW_MODEL", "openrouter/test/env-review")
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    _write_workspace_config(tmp_path, "review_model: openrouter/test/yaml-review\n")
    assert resolve_review_model_name(tmp_path) == "openrouter/test/yaml-review"


def test_empty_env_falls_through_to_executor_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_REVIEW_MODEL", "")
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/executor-model")
    assert resolve_review_model_name(tmp_path) == resolve_model_name()
