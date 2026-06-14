"""LlmGateway proxy — unified owned completion boundary (P7-001)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.config.observability import VERBOSITY_STANDARD
from core.config.role_models import ROLE_CONTEXT_BUILDER
from core.engine.architect_pass_llm import run_architect_pass_llm
from core.engine.context_builder_llm import run_context_builder_llm
from core.engine.owned_helper_llm import run_owned_helper_completion
from core.engine.spec_validation_llm import run_spec_validation_llm
from core.observability.context import (
    bind_delegation_trace_scope,
    delegation_context,
    role_context,
)
from core.observability.gateway import (
    GatewayCompletion,
    LlmGateway,
    NullLlmGateway,
    get_llm_gateway,
    reset_llm_gateway,
    set_llm_gateway,
)
from core.observability.litellm_callback import (
    litellm_success_handler,
    register_litellm_callbacks,
    reset_callback_state_for_tests,
)
from core.observability.local import LocalObservability
from core.observability.trace import TRACE_TYPE_LLM_CALL
from core.storage.paths import session_trace_path
from core.storage.session_paths import prepare_delegation_storage


def _storage_for(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    monkeypatch.delenv("MCP_CODER_MIRROR_LOGS_TO_WORKSPACE", raising=False)
    return prepare_delegation_storage(workspace)


def _mock_response(
    *,
    text: str = "hello",
    usage: tuple[int, int, int] = (50, 10, 60),
    model: str = "openrouter/test/flash",
) -> SimpleNamespace:
    usage_obj = SimpleNamespace(
        prompt_tokens=usage[0],
        completion_tokens=usage[1],
        total_tokens=usage[2],
    )
    return SimpleNamespace(
        model=model,
        usage=usage_obj,
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


@pytest.fixture(autouse=True)
def _reset_gateway_and_callback():
    reset_callback_state_for_tests()
    reset_llm_gateway()
    yield
    reset_callback_state_for_tests()
    reset_llm_gateway()


def test_gateway_not_set_raises():
    with pytest.raises(RuntimeError, match="LlmGateway not initialised"):
        get_llm_gateway()


def test_null_gateway_no_io(tmp_path):
    set_llm_gateway(NullLlmGateway())
    with patch("litellm.completion") as completion:
        result = get_llm_gateway().complete(
            model="openrouter/test/flash",
            messages=[{"role": "user", "content": "ping"}],
            role="context_builder",
        )
    completion.assert_not_called()
    assert isinstance(result, GatewayCompletion)
    assert result.text == ""
    assert result.tokens["source"] == "null_gateway"
    assert result.duration_ms == 0
    assert result.error is None
    traces_dir = tmp_path / "home"
    assert not any(traces_dir.rglob("traces/*.jsonl")) if traces_dir.exists() else True


def test_owned_helper_llm_via_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    set_llm_gateway(NullLlmGateway())

    with patch("litellm.completion") as completion:
        with role_context(ROLE_CONTEXT_BUILDER):
            result = run_owned_helper_completion(
                [{"role": "user", "content": "ping"}],
                model="openrouter/test/flash",
            )

    completion.assert_not_called()
    assert result.error is None
    assert result.text == ""
    assert result.tokens["source"] == "null_gateway"
    assert result.model == "openrouter/test/flash"


def test_gateway_complete_records_once(tmp_path, monkeypatch):
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_STANDARD)
    delegation_id = "gateway-dedup-1"
    messages = [{"role": "user", "content": "Build brief"}]
    response = _mock_response()

    obs = LocalObservability()
    register_litellm_callbacks()
    set_llm_gateway(LlmGateway(obs))

    def _completion_with_callback(**kwargs):
        now = datetime.now(timezone.utc)
        litellm_success_handler(kwargs, response, now, now)
        return response

    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path / "workspace"),
            session_dir=storage.session_dir,
        )
        with role_context(ROLE_CONTEXT_BUILDER):
            with patch("litellm.completion", side_effect=_completion_with_callback):
                result = get_llm_gateway().complete(
                    model="openrouter/test/flash",
                    messages=messages,
                    role=ROLE_CONTEXT_BUILDER,
                )

    assert result.error is None
    assert result.tokens["source"] == "owned_completion"
    path = session_trace_path(tmp_path / "workspace", storage.mcp_session_id, delegation_id)
    lines = [json.loads(row) for row in path.read_text(encoding="utf-8").strip().splitlines()]
    llm_calls = [line for line in lines if line.get("type") == TRACE_TYPE_LLM_CALL]
    assert len(llm_calls) == 1
    assert llm_calls[0]["tokens"]["input"] == 50


def test_run_owned_helper_completion_returns_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    response = _mock_response(text="hello")

    mock_gw = MagicMock()
    mock_gw.complete.return_value = GatewayCompletion(
        text="hello",
        model="openrouter/test/flash",
        tokens={"input": 50, "output": 10, "total": 60, "source": "owned_completion"},
        duration_ms=12,
    )
    set_llm_gateway(mock_gw)

    with role_context(ROLE_CONTEXT_BUILDER):
        result = run_owned_helper_completion(
            [{"role": "user", "content": "ping"}],
            model="openrouter/test/flash",
        )

    assert result.text == "hello"
    assert result.error is None
    assert result.tokens["source"] == "owned_completion"
    assert result.tokens["total"] == 60
    mock_gw.complete.assert_called_once()


@pytest.mark.parametrize(
    "runner,patch_target,completion_text",
    [
        (
            "context_builder",
            "core.engine.context_builder_llm.run_owned_helper_completion",
            "## Builder brief\n\nDo the thing.\n\n## Paths\n- `pkg/cli.py`",
        ),
        (
            "architect_pass",
            "core.engine.architect_pass_llm.run_owned_helper_completion",
            "## Architect plan\n\nStep one.",
        ),
        (
            "spec_validation",
            "core.engine.spec_validation_llm.run_owned_helper_completion",
            "## Validation OK\n",
        ),
    ],
)
def test_helper_tokens_unchanged(
    tmp_path,
    monkeypatch,
    runner,
    patch_target,
    completion_text,
):
    """Token dict shape from gateway-owned completion matches owned_completion contract."""
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    expected_tokens = {
        "input": 100,
        "output": 25,
        "total": 125,
        "source": "owned_completion",
    }
    from core.engine.owned_helper_llm import OwnedHelperCompletion

    completion = OwnedHelperCompletion(
        text=completion_text,
        model="openrouter/test/flash",
        tokens=expected_tokens,
        duration_ms=40,
    )

    with patch(patch_target, return_value=completion):
        if runner == "context_builder":
            with patch("core.engine.context_builder_llm.provider_hint_for_model", return_value=None):
                result = run_context_builder_llm("prompt", workspace_path=tmp_path)
        elif runner == "architect_pass":
            with patch("core.engine.architect_pass_llm.provider_hint_for_model", return_value=None):
                result = run_architect_pass_llm("prompt", workspace_path=tmp_path)
        else:
            with patch("core.engine.spec_validation_llm.provider_hint_for_model", return_value=None):
                result = run_spec_validation_llm("prompt", workspace_path=tmp_path)

    assert result.tokens == expected_tokens
