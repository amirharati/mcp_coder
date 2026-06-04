from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL_SEC = 3600
_cache_at: float = 0.0
_cache_ids: frozenset[str] | None = None


def _fetch_openrouter_model_ids() -> frozenset[str]:
    global _cache_at, _cache_ids
    now = time.time()
    if _cache_ids is not None and (now - _cache_at) < _CACHE_TTL_SEC:
        return _cache_ids

    req = urllib.request.Request(
        OPENROUTER_MODELS_URL,
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    ids = frozenset(m["id"] for m in payload.get("data", []) if m.get("id"))
    _cache_ids = ids
    _cache_at = now
    return ids


def openrouter_model_slug(model_name: str) -> str | None:
    """openrouter/google/foo -> google/foo"""
    if not model_name.startswith("openrouter/"):
        return None
    return model_name[len("openrouter/") :].strip() or None


def validate_openrouter_model(model_name: str) -> str | None:
    """
    Return an error message if model_name is not on OpenRouter, else None.
    """
    slug = openrouter_model_slug(model_name)
    if slug is None:
        return None
    try:
        ids = _fetch_openrouter_model_ids()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        return None  # skip validation if catalog unreachable

    if slug not in ids:
        suggestions = [mid for mid in ids if "gpt-4o-mini" in mid][:3]
        hint = f" Suggestions: {', '.join(f'openrouter/{s}' for s in suggestions)}" if suggestions else ""
        return (
            f"Model {model_name!r} is not available on OpenRouter (404). "
            f"Update AIDER_MODEL in .env.{hint}"
        )
    return None


def clear_openrouter_model_cache() -> None:
    """For tests."""
    global _cache_at, _cache_ids
    _cache_at = 0.0
    _cache_ids = None
