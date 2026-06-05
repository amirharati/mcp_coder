"""CLI test-model command."""

from core.cli.test_model import (
    build_test_context,
    format_resolution,
    run_test_model,
)


def test_missing_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setattr("core.cli.test_model.load_env_files", lambda: [])
    result = run_test_model(print_resolution=False)
    assert result.ok is False
    assert "OPENROUTER_API_KEY" in result.message


def test_success_mocked_aider(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")

    class _FakeModel:
        def __init__(self, name: str) -> None:
            self.name = name

        def simple_send_with_retries(self, messages):
            assert self.name == "openrouter/openai/gpt-4o-mini"
            assert messages[0]["content"] == "Reply with exactly: ok"
            return "ok"

    import aider.models

    monkeypatch.setattr(aider.models, "Model", _FakeModel)
    result = run_test_model(print_resolution=False)
    assert result.ok is True
    assert result.via == "aider"
    assert result.reply == "ok"
    assert result.latency_ms is not None


def test_success_mocked_litellm(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")

    class _Msg:
        content = "ok"

    class _Choice:
        message = _Msg()

    class _Usage:
        prompt_tokens = 5
        completion_tokens = 2
        total_tokens = 7

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    def fake_completion(**kwargs):
        assert kwargs["model"] == "openrouter/openai/gpt-4o-mini"
        return _Resp()

    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)
    result = run_test_model(via="litellm", print_resolution=False)
    assert result.ok is True
    assert result.via == "litellm"
    assert result.reply == "ok"


def test_aider_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")

    class _BoomModel:
        def __init__(self, name: str) -> None:
            self.name = name

        def simple_send_with_retries(self, messages):
            raise RuntimeError("upstream 500")

    import aider.models

    monkeypatch.setattr(aider.models, "Model", _BoomModel)
    result = run_test_model(print_resolution=False)
    assert result.ok is False
    assert "upstream 500" in result.message


def test_resolution_format(monkeypatch):
    monkeypatch.setenv("AIDER_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key-1234")
    monkeypatch.setenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
    monkeypatch.setattr("core.cli.test_model.load_env_files", lambda: [])
    monkeypatch.setattr(
        "core.cli.test_model.validate_openrouter_model",
        lambda _m: None,
    )

    ctx = build_test_context()
    text = format_resolution(ctx)
    assert "openrouter/openai/gpt-4o-mini" in text
    assert "AIDER_MODEL" in text
    assert "OPENROUTER_API_BASE" in text
    assert "sk-o" in text
