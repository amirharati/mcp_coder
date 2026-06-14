"""Tests for P8-005 — owned_completion shim removal + token fallback precedence."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.config.role_models import ROLE_EXECUTOR
from core.observability.context import delegation_context, role_context
from core.observability.litellm_callback import (
    litellm_success_handler,
    overlay_model_roles_from_callback,
    reset_callback_state_for_tests,
)
from core.usage.aider_tokens import resolve_executor_tokens
from core.usage.role_audit import build_role_usage_record


def test_owned_completion_shim_module_removed():
    assert not Path("core/observability/owned_completion.py").is_file()


def test_no_production_imports_of_owned_completion_shim():
    repo_root = Path(__file__).resolve().parents[1]
    hits: list[str] = []
    for path in repo_root.rglob("*.py"):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith("tests/") or rel.startswith(".venv/"):
            continue
        text = path.read_text(encoding="utf-8")
        if "observability.owned_completion" in text or "from core.observability import owned_completion" in text:
            hits.append(rel)
    assert hits == [], f"production imports of removed shim: {hits}"


def test_resolve_executor_tokens_prefers_coder_attrs_over_stdout():
    coder_tokens = {
        "input": 80,
        "output": 20,
        "total": 100,
        "source": "aider_coder",
    }
    output = "Tokens: 2.4k sent, 53 received."
    resolved = resolve_executor_tokens(coder_tokens=coder_tokens, output=output)
    assert resolved["source"] == "aider_coder"
    assert resolved["total"] == 100


def test_resolve_executor_tokens_uses_stdout_parse_as_last_resort():
    coder_tokens = {
        "input": None,
        "output": None,
        "total": None,
        "source": "unavailable",
    }
    output = "Applied edits.\nTokens: 2.4k sent, 53 received.\n"
    resolved = resolve_executor_tokens(coder_tokens=coder_tokens, output=output)
    assert resolved["source"] == "aider_output_parse"
    assert resolved["total"] == 2453


def test_overlay_prefers_callback_over_stdout_parse_fallback():
    reset_callback_state_for_tests()
    delegation_id = "p8-005-overlay-precedence"
    with delegation_context(delegation_id):
        with role_context(ROLE_EXECUTOR):
            usage = SimpleNamespace(prompt_tokens=500, completion_tokens=50, total_tokens=550)
            litellm_success_handler(
                {},
                SimpleNamespace(model="openrouter/openai/gpt-4o-mini", usage=usage),
                None,
                None,
            )

    roles = {
        ROLE_EXECUTOR: build_role_usage_record(
            role=ROLE_EXECUTOR,
            model="openrouter/openai/gpt-4o-mini",
            source="unavailable",
        ),
    }
    fallback = {
        "input": 2400,
        "output": 53,
        "total": 2453,
        "source": "aider_output_parse",
    }
    merged = overlay_model_roles_from_callback(
        roles,
        delegation_id=delegation_id,
        executor_fallback_tokens=fallback,
    )
    assert merged is not None
    assert merged[ROLE_EXECUTOR]["tokens"]["input"] == 500
    assert merged[ROLE_EXECUTOR]["tokens"]["total"] == 550
    assert merged[ROLE_EXECUTOR]["tokens"]["source"] == "litellm_callback"
