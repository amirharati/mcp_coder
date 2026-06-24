"""Multi-provider reasoning capture fixtures and tests (P14-003c hardening).

Each provider returns reasoning in a slightly different shape. litellm normalizes
most of them, but the raw objects we extract from can differ. These tests pin
the extraction + trace path against recorded provider response shapes so a quirk
in one provider cannot silently drop reasoning tokens.

Providers covered:
- Anthropic (Sonnet/Haiku) — message.reasoning_content + usage.reasoning_tokens
- DeepSeek (v3/v4, R1) — message.reasoning_content + usage.reasoning_tokens
- GLM (z-ai) — message.reasoning_content (litellm-normalized)
- Gemini (2.5 flash/pro) — message.reasoning_content (litellm maps thoughtsContent)
- OpenAI o-series — usage.completion_tokens_details.reasoning_tokens
- LLaMA via OpenRouter — message.reasoning + usage.reasoning_tokens
- Non-reasoning model — no reasoning fields at all (regression guard)
- Streaming delta shape — delta.reasoning_content accumulated by ObservableModel
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.config.observability import VERBOSITY_FULL
from core.config.role_models import ROLE_CONTEXT_BUILDER, ROLE_EXECUTOR
from core.observability.context import (
    bind_delegation_trace_scope,
    delegation_context,
    role_context,
)
from core.observability.litellm_callback import (
    litellm_success_handler,
    reset_callback_state_for_tests,
)
from core.observability.trace import TRACE_TYPE_LLM_CALL
from core.storage.paths import session_trace_path
from core.storage.session_paths import prepare_delegation_storage

from core.engine.observable_model import (
    _assemble_stream_response,
    extract_thinking_from_response,
)
from core.usage.litellm_tokens import _tokens_from_usage_mapping
from core.observability.gateway import _extract_text_and_reasoning


# ── Fixtures: recorded provider response shapes ────────────────────────────


def _anthropic_sonnet_response() -> SimpleNamespace:
    """Anthropic Sonnet via OpenRouter: reasoning_content + reasoning_tokens."""
    return SimpleNamespace(
        model="openrouter/anthropic/claude-sonnet-4.5",
        usage=SimpleNamespace(
            prompt_tokens=273,
            completion_tokens=206,
            total_tokens=479,
            reasoning_tokens=203,
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="## Validation OK",
                    reasoning_content="Let me analyze the task spec...",
                )
            )
        ],
    )


def _deepseek_response() -> SimpleNamespace:
    """DeepSeek v4: reasoning_content + reasoning_tokens in usage."""
    return SimpleNamespace(
        model="openrouter/deepseek/deepseek-v4-pro",
        usage=SimpleNamespace(
            prompt_tokens=1200,
            completion_tokens=800,
            total_tokens=2000,
            reasoning_tokens=4908,
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Here is the edit...",
                    reasoning_content="Step 1: understand the file...",
                )
            )
        ],
    )


def _glm_response() -> SimpleNamespace:
    """GLM (z-ai): litellm normalizes thinking to reasoning_content."""
    return SimpleNamespace(
        model="openrouter/z-ai/glm-4.6",
        usage=SimpleNamespace(
            prompt_tokens=500,
            completion_tokens=300,
            total_tokens=800,
            reasoning_tokens=150,
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="The change is...",
                    reasoning_content="Considering the requirements...",
                )
            )
        ],
    )


def _gemini_response() -> SimpleNamespace:
    """Gemini 2.5: litellm maps thoughtsContent → reasoning_content."""
    return SimpleNamespace(
        model="openrouter/google/gemini-2.5-flash",
        usage=SimpleNamespace(
            prompt_tokens=400,
            completion_tokens=200,
            total_tokens=600,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=88),
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Append the line.",
                    reasoning_content="The file needs one trailing line.",
                )
            )
        ],
    )


def _openai_o_series_response() -> SimpleNamespace:
    """OpenAI o-series: reasoning only in completion_tokens_details."""
    return SimpleNamespace(
        model="openrouter/openai/o3-mini",
        usage=SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=412),
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="The answer is 42.",
                    reasoning_content=None,
                )
            )
        ],
    )


def _llama_response() -> SimpleNamespace:
    """LLaMA via OpenRouter: reasoning field (not reasoning_content)."""
    return SimpleNamespace(
        model="openrouter/meta-llama/llama-3.3-70b-instruct",
        usage=SimpleNamespace(
            prompt_tokens=300,
            completion_tokens=100,
            total_tokens=400,
            reasoning_tokens=55,
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Done.",
                    reasoning="I should append to the file...",
                )
            )
        ],
    )


def _openrouter_anthropic_buried_response() -> SimpleNamespace:
    """OpenRouter/Anthropic Sonnet when reasoning_effort set but thinking= is not.

    litellm drops message.reasoning_content and buries the text under
    provider_specific_fields.reasoning + reasoning_details. Our extractor must
    recover it from both locations.
    """
    return SimpleNamespace(
        model="openrouter/anthropic/claude-sonnet-4.5",
        usage=SimpleNamespace(
            prompt_tokens=61,
            completion_tokens=86,
            total_tokens=147,
            # litellm zeroes reasoning_tokens for this path; the real count lives
            # only in the raw HTTP body that the proxy sees. Token extraction
            # cannot recover it from the parsed object — this is the documented
            # P14-ISS-001/002 gap. The *text*, however, is recoverable.
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="## Validation OK",
                    reasoning_content=None,
                    reasoning=None,
                    provider_specific_fields={
                        "refusal": None,
                        "reasoning": "Let me analyze the task spec...",
                        "reasoning_details": [
                            {"type": "reasoning.text", "text": "Let me analyze the task spec..."},
                        ],
                        "reasoning_content": "Let me analyze the task spec...",
                    },
                )
            )
        ],
    )


def _non_reasoning_response() -> SimpleNamespace:
    """A non-reasoning model: no reasoning fields anywhere."""
    return SimpleNamespace(
        model="openrouter/openai/gpt-4o-mini",
        usage=SimpleNamespace(
            prompt_tokens=200,
            completion_tokens=50,
            total_tokens=250,
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="OK", reasoning_content=None)
            )
        ],
    )


def _streaming_chunks() -> list[SimpleNamespace]:
    """Streaming delta sequence with reasoning_content on deltas."""
    return [
        SimpleNamespace(
            model="openrouter/deepseek/deepseek-v4-pro",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None, reasoning_content="First ")
                )
            ],
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="Build", reasoning_content="thinking"
                    )
                )
            ],
        ),
        SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                reasoning_tokens=40,
            ),
            choices=[SimpleNamespace(delta=SimpleNamespace(content=None))],
        ),
    ]


ALL_PROVIDER_FIXTURES = [
    ("anthropic_sonnet", _anthropic_sonnet_response, 203),
    ("deepseek_v4", _deepseek_response, 4908),
    ("glm_4_6", _glm_response, 150),
    ("gemini_2_5_flash", _gemini_response, 88),
    ("openai_o3_mini", _openai_o_series_response, 412),
    ("llama_3_3_70b", _llama_response, 55),
    ("openrouter_anthropic_buried", _openrouter_anthropic_buried_response, 0),
]


# ── Storage helper (mirrors test_observability_traces) ──────────────────────


def _storage_for(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    monkeypatch.delenv("MCP_CODER_MIRROR_LOGS_TO_WORKSPACE", raising=False)
    monkeypatch.setenv("MCP_CODER_CAPTURE_REASONING", "1")
    return prepare_delegation_storage(workspace)


def _fire_one(
    *,
    storage,
    workspace_path,
    monkeypatch,
    delegation_id: str,
    role: str,
    response_obj: Any,
    model: str,
) -> Path:
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": "test prompt"}],
    }
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_FULL)
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(workspace_path), session_dir=storage.session_dir
        )
        with role_context(role):
            litellm_success_handler(kwargs, response_obj, None, None)
    return session_trace_path(workspace_path, storage.mcp_session_id, delegation_id)


def _llm_calls(path: Path) -> list[dict]:
    lines = [
        json.loads(row)
        for row in path.read_text(encoding="utf-8").strip().splitlines()
        if row.strip()
    ]
    return [line for line in lines if line.get("type") == TRACE_TYPE_LLM_CALL]


@pytest.fixture(autouse=True)
def _reset_state():
    reset_callback_state_for_tests()
    yield
    reset_callback_state_for_tests()


# ── Extraction-layer tests (pure, no trace writing) ─────────────────────────


@pytest.mark.parametrize(
    "name,build,expected_reasoning_tokens",
    ALL_PROVIDER_FIXTURES,
    ids=[f[0] for f in ALL_PROVIDER_FIXTURES],
)
def test_usage_extraction_reads_reasoning_tokens_for_each_provider(
    name, build, expected_reasoning_tokens
):
    """_tokens_from_usage_mapping must surface reasoning_tokens for every provider."""
    response = build()
    tokens = _tokens_from_usage_mapping(response.usage)
    assert tokens is not None, f"{name}: usage mapping returned None"
    assert tokens["reasoning_tokens"] == expected_reasoning_tokens, (
        f"{name}: expected reasoning_tokens={expected_reasoning_tokens}, "
        f"got {tokens['reasoning_tokens']}"
    )


@pytest.mark.parametrize(
    "name,build,expected_text_contains,expected_reasoning_contains",
    [
        ("anthropic_sonnet", _anthropic_sonnet_response, "Validation", "analyze"),
        ("deepseek_v4", _deepseek_response, "edit", "Step 1"),
        ("glm_4_6", _glm_response, "change", "Considering"),
        ("gemini_2_5_flash", _gemini_response, "Append", "trailing"),
        ("llama_3_3_70b", _llama_response, "Done", "append"),
    ],
    ids=["anthropic", "deepseek", "glm", "gemini", "llama"],
)
def test_gateway_extracts_text_and_reasoning_for_each_provider(
    name, build, expected_text_contains, expected_reasoning_contains
):
    """LlmGateway._extract_text_and_reasoning must read content + reasoning."""
    response = build()
    text, reasoning = _extract_text_and_reasoning(response)
    assert expected_text_contains.lower() in text.lower(), (
        f"{name}: text missing {expected_text_contains!r}: {text!r}"
    )
    assert reasoning is not None, f"{name}: reasoning_text is None"
    assert expected_reasoning_contains.lower() in reasoning.lower(), (
        f"{name}: reasoning missing {expected_reasoning_contains!r}: {reasoning!r}"
    )


def test_gateway_recovers_reasoning_from_provider_specific_fields():
    """The OpenRouter/Anthropic buried-reasoning bug: litellm drops
    message.reasoning_content and buries text under provider_specific_fields.
    The gateway must recover it."""
    response = _openrouter_anthropic_buried_response()
    text, reasoning = _extract_text_and_reasoning(response)
    assert "Validation OK" in text
    assert reasoning is not None, "reasoning_text must be recovered from provider_specific_fields"
    assert "analyze the task spec" in reasoning.lower()


def test_observable_model_recovers_reasoning_from_provider_specific_fields():
    """ObservableModel.extract_thinking_from_response must also recover buried reasoning."""
    response = _openrouter_anthropic_buried_response()
    text, tokens = extract_thinking_from_response(response)
    assert text is not None, "thinking_text must be recovered from provider_specific_fields"
    assert "analyze the task spec" in text.lower()
    # Tokens are 0 (litellm zeroes them for this path) — documented gap, not fixable
    # at the extraction layer without the proxy.
    assert tokens == 0


@pytest.mark.parametrize(
    "name,build,expected_reasoning_tokens",
    ALL_PROVIDER_FIXTURES,
    ids=[f[0] for f in ALL_PROVIDER_FIXTURES],
)
def test_observable_model_extracts_thinking_tokens_for_each_provider(
    name, build, expected_reasoning_tokens
):
    """ObservableModel.extract_thinking_from_response must read tokens + text."""
    response = build()
    text, tokens = extract_thinking_from_response(response)
    assert tokens == expected_reasoning_tokens, (
        f"{name}: expected {expected_reasoning_tokens}, got {tokens}"
    )
    # Reasoning text should be present for all reasoning providers.
    if name != "openai_o3_mini":  # o3-mini returns no reasoning_content text
        assert text is not None, f"{name}: reasoning text is None"
        assert text.strip(), f"{name}: reasoning text empty"


def test_non_reasoning_model_yields_no_reasoning():
    """Regression guard: a non-reasoning model must not synthesize reasoning."""
    response = _non_reasoning_response()
    tokens = _tokens_from_usage_mapping(response.usage)
    assert tokens is not None
    assert tokens["reasoning_tokens"] is None

    text, reasoning = _extract_text_and_reasoning(response)
    assert reasoning is None
    assert text == "OK"

    t_text, t_tokens = extract_thinking_from_response(response)
    assert t_tokens == 0
    assert t_text is None


def test_streaming_delta_assembles_reasoning_content():
    """_assemble_stream_response must accumulate delta.reasoning_content."""
    assembled = _assemble_stream_response(_streaming_chunks())
    assert assembled is not None
    message = assembled.choices[0].message
    assert "Build" in message.content
    # _assemble_stream_response joins thinking deltas with "\n", not "".
    assert "First" in message.reasoning_content
    assert "thinking" in message.reasoning_content
    # The final chunk's usage must be attached.
    assert assembled.usage is not None
    assert assembled.usage.reasoning_tokens == 40


# ── Trace-writing tests (full pipeline, end-to-end) ─────────────────────────


@pytest.mark.parametrize(
    "name,build,expected_reasoning_tokens",
    ALL_PROVIDER_FIXTURES,
    ids=[f[0] for f in ALL_PROVIDER_FIXTURES],
)
def test_trace_llm_call_captures_reasoning_tokens_for_each_provider(
    tmp_path, monkeypatch, name, build, expected_reasoning_tokens
):
    """End-to-end: fire litellm_success_handler and verify the llm_call trace."""
    storage = _storage_for(tmp_path, monkeypatch)
    workspace_path = tmp_path / "workspace"
    response = build()
    path = _fire_one(
        storage=storage,
        workspace_path=workspace_path,
        monkeypatch=monkeypatch,
        delegation_id=f"prov-{name}",
        role=ROLE_CONTEXT_BUILDER,
        response_obj=response,
        model=response.model,
    )
    calls = _llm_calls(path)
    assert calls, f"{name}: no llm_call trace event written"
    call = calls[0]
    tokens = call.get("tokens") or {}
    assert tokens.get("reasoning_tokens") == expected_reasoning_tokens, (
        f"{name}: trace reasoning_tokens={tokens.get('reasoning_tokens')} "
        f"expected {expected_reasoning_tokens}"
    )
    # thinking_tokens top-level alias must match.
    assert call.get("thinking_tokens") == expected_reasoning_tokens
    # reasoning_body must be present when the provider returned reasoning text.
    # o3-mini returns reasoning *tokens* (count) but no reasoning *text* — that
    # is a real provider quirk; the body is correctly absent in that case.
    o3 = name == "openai_o3_mini"
    if o3:
        assert "reasoning_body" not in call, f"{name}: reasoning_body should be absent"
    else:
        assert "reasoning_body" in call, f"{name}: reasoning_body missing"
        assert call["reasoning_body"], f"{name}: reasoning_body empty"


def test_trace_non_reasoning_model_omits_reasoning_fields_cleanly(
    tmp_path, monkeypatch
):
    """A non-reasoning model must produce a clean trace with no reasoning fields."""
    storage = _storage_for(tmp_path, monkeypatch)
    workspace_path = tmp_path / "workspace"
    response = _non_reasoning_response()
    path = _fire_one(
        storage=storage,
        workspace_path=workspace_path,
        monkeypatch=monkeypatch,
        delegation_id="prov-non-reasoning",
        role=ROLE_CONTEXT_BUILDER,
        response_obj=response,
        model=response.model,
    )
    calls = _llm_calls(path)
    assert calls
    call = calls[0]
    tokens = call.get("tokens") or {}
    # reasoning_tokens should be absent (None is not written by build_trace_record).
    assert "reasoning_tokens" not in tokens
    assert "reasoning_body" not in call
    assert "thinking_tokens" not in call


# ── Capture-reasoning gate tests (MCP_CODER_CAPTURE_REASONING=0) ─────────────


def test_capture_reasoning_disabled_strips_helper_reasoning(tmp_path, monkeypatch):
    """When MCP_CODER_CAPTURE_REASONING=0, helper reasoning must NOT appear in trace."""
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_CAPTURE_REASONING", "0")
    workspace_path = tmp_path / "workspace"
    response = _anthropic_sonnet_response()
    path = _fire_one(
        storage=storage,
        workspace_path=workspace_path,
        monkeypatch=monkeypatch,
        delegation_id="gate-disabled",
        role=ROLE_CONTEXT_BUILDER,
        response_obj=response,
        model=response.model,
    )
    calls = _llm_calls(path)
    assert calls
    call = calls[0]
    # Token count is still captured (usage is not gated); only reasoning text is.
    assert (call.get("tokens") or {}).get("reasoning_tokens") == 203
    assert "reasoning_body" not in call


def test_capture_reasoning_disabled_keeps_executor_reasoning_token_count(
    tmp_path, monkeypatch
):
    """Executor reasoning *tokens* (count) are always captured; only the text
    summary is gated. This documents the asymmetry (P14-ISS-002 adjacent)."""
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_CAPTURE_REASONING", "0")
    workspace_path = tmp_path / "workspace"
    response = _deepseek_response()
    path = _fire_one(
        storage=storage,
        workspace_path=workspace_path,
        monkeypatch=monkeypatch,
        delegation_id="gate-executor",
        role=ROLE_EXECUTOR,
        response_obj=response,
        model=response.model,
    )
    calls = _llm_calls(path)
    assert calls
    call = calls[0]
    # Executor token counts are captured regardless of the flag.
    assert (call.get("tokens") or {}).get("reasoning_tokens") == 4908
