from core.config.models import DEFAULT_MODEL
from core.engine.aider_engine import AiderEngine


def test_aider_fails_fast_without_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    engine = AiderEngine(model_name=DEFAULT_MODEL)
    result = engine.run("hi", ["foo.py"], workspace_path=".")
    assert result.success is False
    assert "OPENROUTER_API_KEY" in (result.error or "")
