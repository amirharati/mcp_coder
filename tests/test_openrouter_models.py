from core.config.models import provider_hint_for_model
from core.config.openrouter_models import (
    clear_openrouter_model_cache,
    validate_openrouter_model,
)


def test_validate_unknown_openrouter_model():
    clear_openrouter_model_cache()
    err = validate_openrouter_model("openrouter/google/gemini-2.0-flash-001")
    assert err is not None
    assert "not available" in err


def test_validate_known_openrouter_model():
    clear_openrouter_model_cache()
    assert validate_openrouter_model("openrouter/openai/gpt-4o-mini") is None


def test_provider_hint_includes_catalog_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    clear_openrouter_model_cache()
    hint = provider_hint_for_model("openrouter/google/gemini-2.0-flash-001")
    assert hint is not None
    assert "not available" in hint
