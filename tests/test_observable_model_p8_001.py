"""Tests for P8-001: ObservableModel inner-loop capture and backend_llm_call traces."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.config.observability import VERBOSITY_FULL, VERBOSITY_LEAN, VERBOSITY_STANDARD
from core.config.role_models import ROLE_EXECUTOR
from core.observability.context import (
    backend_stream_call_count_for_tests,
    bind_delegation_trace_scope,
    delegation_context,
    executor_step_context,
    role_context,
    step_index_var,
)
from core.observability.litellm_callback import litellm_success_handler, reset_callback_state_for_tests
from core.observability.trace import TRACE_TYPE_BACKEND_LLM_CALL, build_backend_llm_call_record
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


def _trace_records(path):
    if not path.exists():
        return []
    return [json.loads(row) for row in path.read_text().splitlines() if row.strip()]


def _mock_sync_response(
    *,
    content: str = "edited file",
    reasoning: str | None = "chain of thought",
    reasoning_tokens: int | None = 12,
) -> SimpleNamespace:
    details = (
        SimpleNamespace(reasoning_tokens=reasoning_tokens)
        if reasoning_tokens is not None
        else None
    )
    usage = SimpleNamespace(
        prompt_tokens=50,
        completion_tokens=20,
        total_tokens=70,
        reasoning_tokens=reasoning_tokens,
        completion_tokens_details=details,
    )
    return SimpleNamespace(
        model="test/model",
        usage=usage,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning,
                )
            )
        ],
    )


# ── build_backend_llm_call_record verbosity tiers ───────────────────────────


def test_build_backend_llm_call_record_lean():
    rec = build_backend_llm_call_record(
        delegation_id="d-1",
        step_index=2,
        call_type="executor_turn",
        model="m",
        verbosity=VERBOSITY_LEAN,
        prompt_text="secret sk-abcdefghijklmnopqrstuvwxyz",
        response_text="done",
        thinking_text="think",
    )
    assert rec["type"] == TRACE_TYPE_BACKEND_LLM_CALL
    assert rec["call_type"] == "executor_turn"
    assert rec["step_index"] == 2
    assert "prompt_hash" in rec
    assert "response_hash" in rec
    assert "prompt_preview" not in rec
    assert "thinking_text" in rec


def test_build_backend_llm_call_record_standard_preview_truncated():
    rec = build_backend_llm_call_record(
        delegation_id="d-1",
        step_index=None,
        call_type="cache_warm",
        model="m",
        verbosity=VERBOSITY_STANDARD,
        prompt_text="x" * 300,
        response_text="y" * 300,
    )
    assert len(rec["prompt_preview"]) <= 200
    assert len(rec["response_preview"]) <= 200
    assert "prompt_body" in rec
    assert len(rec["prompt_body"]) == 300
    assert len(rec["response_body"]) == 300


def test_build_backend_llm_call_record_full_includes_bodies():
    rec = build_backend_llm_call_record(
        delegation_id="d-1",
        step_index=1,
        call_type="executor_turn",
        model="m",
        verbosity=VERBOSITY_FULL,
        prompt_text="prompt body",
        response_text="response body",
        thinking_text="thinking body",
        usage={"input": 1, "output": 2, "total": 3},
    )
    assert rec["prompt_body"] == "prompt body"
    assert rec["response_body"] == "response body"
    assert rec["thinking_body"] == "thinking body"
    assert rec["usage"]["total"] == 3


# ── step_index_var binding ──────────────────────────────────────────────────


def test_executor_step_context_binds_step_index():
    assert step_index_var.get() is None
    with executor_step_context(3):
        assert step_index_var.get() == 3
    assert step_index_var.get() is None


# ── ObservableModel sync capture ────────────────────────────────────────────


@pytest.fixture
def observable_model_module(monkeypatch):
    import importlib
    import sys

    pytest.importorskip("aider")
    import aider.models as real_models

    monkeypatch.setitem(sys.modules, "aider.models", real_models)
    import core.engine.observable_model as observable_model

    importlib.reload(observable_model)
    return observable_model


def test_observable_model_sync_records_backend_llm_call(
    tmp_path, monkeypatch, observable_model_module
):
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_LEAN)
    delegation_id = "obs-sync-1"
    response = _mock_sync_response()

    recorded: list[dict] = []
    original_record = observable_model_module._record_backend_call

    def capture(**kwargs):
        recorded.append(kwargs)
        original_record(**kwargs)

    monkeypatch.setattr(observable_model_module, "_record_backend_call", capture)

    ObservableModel = observable_model_module.ObservableModel
    model = ObservableModel("test/model")

    with patch(
        "core.engine.observable_model.Model.send_completion",
        return_value=("hash", response),
    ):
        with delegation_context(delegation_id):
            bind_delegation_trace_scope(
                workspace=str(tmp_path / "workspace"),
                session_dir=storage.session_dir,
            )
            with executor_step_context(2):
                hash_obj, result = model.send_completion(
                    [{"role": "user", "content": "edit foo"}],
                    None,
                    False,
                )

    assert hash_obj == "hash"
    assert result is response
    assert len(recorded) == 1
    assert recorded[0]["call_type"] == "executor_turn"

    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    lines = [json.loads(row) for row in trace_path.read_text().splitlines() if row.strip()]
    backend = [line for line in lines if line.get("type") == TRACE_TYPE_BACKEND_LLM_CALL]
    assert len(backend) == 1
    assert backend[0]["call_type"] == "executor_turn"
    assert backend[0]["step_index"] == 2


def test_observable_model_stream_records_on_exhaustion(
    tmp_path, monkeypatch, observable_model_module
):
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_LEAN)
    delegation_id = "obs-stream-1"

    chunk = SimpleNamespace(
        model="test/model",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content="hello", reasoning_content="hmm")
            )
        ],
    )

    def stream_iter():
        yield chunk

    ObservableModel = observable_model_module.ObservableModel
    model = ObservableModel("test/model")

    with patch(
        "core.engine.observable_model.Model.send_completion",
        return_value=("hash", stream_iter()),
    ):
        with delegation_context(delegation_id):
            bind_delegation_trace_scope(
                workspace=str(tmp_path / "workspace"),
                session_dir=storage.session_dir,
            )
            with executor_step_context(1):
                _, wrapped = model.send_completion([{"role": "user", "content": "x"}], None, True)
                chunks = list(wrapped)

    assert len(chunks) == 1
    assert backend_stream_call_count_for_tests() == 0
    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    lines = _trace_records(trace_path)
    backend = [line for line in lines if line.get("type") == TRACE_TYPE_BACKEND_LLM_CALL]
    assert len(backend) == 1
    assert backend[0]["response_hash"]


def test_extract_thinking_from_response(observable_model_module):
    response = _mock_sync_response(reasoning="thought", reasoning_tokens=7)
    text, tokens = observable_model_module.extract_thinking_from_response(response)
    assert text == "thought"
    assert tokens == 7


# ── Dedup guard (P8-ISS-002) ───────────────────────────────────────────────


def test_litellm_callback_skips_when_backend_call_active(tmp_path, monkeypatch):
    reset_callback_state_for_tests()
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_LEAN)
    delegation_id = "dedup-1"
    kwargs = {
        "model": "test/model",
        "messages": [{"role": "user", "content": "hi"}],
    }
    response = _mock_sync_response(content="reply")

    from core.observability.context import _backend_call_active

    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path / "workspace"),
            session_dir=storage.session_dir,
        )
        with role_context(ROLE_EXECUTOR):
            token = _backend_call_active.set(True)
            try:
                litellm_success_handler(kwargs, response, None, None)
            finally:
                _backend_call_active.reset(token)

    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    if trace_path.exists():
        lines = [json.loads(row) for row in trace_path.read_text().splitlines() if row.strip()]
        llm_calls = [line for line in lines if line.get("type") == "llm_call"]
        assert llm_calls == []


def test_stream_callback_while_active_writes_only_backend_record(
    tmp_path, monkeypatch, observable_model_module
):
    reset_callback_state_for_tests()
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_LEAN)
    delegation_id = "stream-dedup-active"
    messages = [{"role": "user", "content": "stream please"}]
    kwargs = {"model": "test/model", "messages": messages}
    response = _mock_sync_response(content="hello")
    chunk = SimpleNamespace(
        model="test/model",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))],
    )

    def stream_iter():
        yield chunk

    def fake_send_completion(_self, _messages, _functions, _stream, _temperature=None):
        litellm_success_handler(kwargs, response, None, None)
        return "hash", stream_iter()

    ObservableModel = observable_model_module.ObservableModel
    model = ObservableModel("test/model")

    with patch("core.engine.observable_model.Model.send_completion", fake_send_completion):
        with delegation_context(delegation_id):
            bind_delegation_trace_scope(
                workspace=str(tmp_path / "workspace"),
                session_dir=storage.session_dir,
            )
            with role_context(ROLE_EXECUTOR), executor_step_context(1):
                _, wrapped = model.send_completion(messages, None, True)
                chunks = list(wrapped)

    assert chunks == [chunk]
    assert backend_stream_call_count_for_tests() == 0
    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    lines = _trace_records(trace_path)
    backend = [line for line in lines if line.get("type") == TRACE_TYPE_BACKEND_LLM_CALL]
    llm_calls = [line for line in lines if line.get("type") == "llm_call"]
    assert len(backend) == 1
    assert llm_calls == []


def test_stream_callback_after_send_return_writes_only_backend_record(
    tmp_path, monkeypatch, observable_model_module
):
    reset_callback_state_for_tests()
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_LEAN)
    delegation_id = "stream-dedup-after-return"
    messages = [{"role": "user", "content": "stream after return"}]
    kwargs = {"model": "test/model", "messages": messages}
    response = _mock_sync_response(content="hello")
    chunk = SimpleNamespace(
        model="test/model",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))],
    )

    def stream_iter():
        yield chunk

    ObservableModel = observable_model_module.ObservableModel
    model = ObservableModel("test/model")

    with patch(
        "core.engine.observable_model.Model.send_completion",
        return_value=("hash", stream_iter()),
    ):
        with delegation_context(delegation_id):
            bind_delegation_trace_scope(
                workspace=str(tmp_path / "workspace"),
                session_dir=storage.session_dir,
            )
            with role_context(ROLE_EXECUTOR), executor_step_context(1):
                _, wrapped = model.send_completion(messages, None, True)
                assert backend_stream_call_count_for_tests() == 1
                litellm_success_handler(kwargs, response, None, None)
                chunks = list(wrapped)

    assert chunks == [chunk]
    assert backend_stream_call_count_for_tests() == 0
    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    lines = _trace_records(trace_path)
    backend = [line for line in lines if line.get("type") == TRACE_TYPE_BACKEND_LLM_CALL]
    llm_calls = [line for line in lines if line.get("type") == "llm_call"]
    assert len(backend) == 1
    assert llm_calls == []


def test_stream_error_cleans_dedup_state(tmp_path, monkeypatch, observable_model_module):
    reset_callback_state_for_tests()
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_LEAN)
    delegation_id = "stream-error-cleanup"
    messages = [{"role": "user", "content": "stream then error"}]
    chunk = SimpleNamespace(
        model="test/model",
        usage=None,
        choices=[SimpleNamespace(delta=SimpleNamespace(content="partial"))],
    )

    def stream_iter():
        yield chunk
        raise RuntimeError("provider stream failed")

    ObservableModel = observable_model_module.ObservableModel
    model = ObservableModel("test/model")

    with patch(
        "core.engine.observable_model.Model.send_completion",
        return_value=("hash", stream_iter()),
    ):
        with delegation_context(delegation_id):
            bind_delegation_trace_scope(
                workspace=str(tmp_path / "workspace"),
                session_dir=storage.session_dir,
            )
            with role_context(ROLE_EXECUTOR), executor_step_context(1):
                _, wrapped = model.send_completion(messages, None, True)
                assert next(wrapped) is chunk
                assert backend_stream_call_count_for_tests() == 1
                with pytest.raises(RuntimeError, match="provider stream failed"):
                    next(wrapped)

    assert backend_stream_call_count_for_tests() == 0


def test_stream_close_cleans_dedup_state_without_buffering(
    tmp_path, monkeypatch, observable_model_module
):
    reset_callback_state_for_tests()
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_LEAN)
    delegation_id = "stream-close-cleanup"
    messages = [{"role": "user", "content": "stream then close"}]
    chunk = SimpleNamespace(
        model="test/model",
        usage=None,
        choices=[SimpleNamespace(delta=SimpleNamespace(content="partial"))],
    )

    def stream_iter():
        yield chunk
        yield SimpleNamespace(
            model="test/model",
            usage=None,
            choices=[SimpleNamespace(delta=SimpleNamespace(content="unread"))],
        )

    ObservableModel = observable_model_module.ObservableModel
    model = ObservableModel("test/model")

    with patch(
        "core.engine.observable_model.Model.send_completion",
        return_value=("hash", stream_iter()),
    ):
        with delegation_context(delegation_id):
            bind_delegation_trace_scope(
                workspace=str(tmp_path / "workspace"),
                session_dir=storage.session_dir,
            )
            with role_context(ROLE_EXECUTOR), executor_step_context(1):
                _, wrapped = model.send_completion(messages, None, True)
                assert next(wrapped) is chunk
                wrapped.close()

    assert backend_stream_call_count_for_tests() == 0
    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    lines = _trace_records(trace_path)
    backend = [line for line in lines if line.get("type") == TRACE_TYPE_BACKEND_LLM_CALL]
    assert backend == []


def test_litellm_callback_records_cache_warm_backend_call(tmp_path, monkeypatch):
    reset_callback_state_for_tests()
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_LEAN)
    delegation_id = "cache-warm-1"
    kwargs = {
        "model": "test/model",
        "messages": [{"role": "user", "content": "warm"}],
        "max_tokens": 1,
    }
    response = _mock_sync_response(content="")

    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path / "workspace"),
            session_dir=storage.session_dir,
        )
        with executor_step_context(4):
            litellm_success_handler(kwargs, response, None, None)

    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    lines = [json.loads(row) for row in trace_path.read_text().splitlines() if row.strip()]
    backend = [line for line in lines if line.get("type") == TRACE_TYPE_BACKEND_LLM_CALL]
    assert len(backend) == 1
    assert backend[0]["call_type"] == "cache_warm"
    assert backend[0]["step_index"] == 4
    llm_calls = [line for line in lines if line.get("type") == "llm_call"]
    assert llm_calls == []


def test_observable_model_no_crash_without_delegation_context(observable_model_module):
    ObservableModel = observable_model_module.ObservableModel
    model = ObservableModel("test/model")
    response = _mock_sync_response()

    with patch(
        "core.engine.observable_model.Model.send_completion",
        return_value=("hash", response),
    ):
        hash_obj, result = model.send_completion([{"role": "user", "content": "x"}], None, False)

    assert hash_obj == "hash"
    assert result is response


def test_aider_engine_uses_observable_model():
    pytest.importorskip("aider")
    from core.engine.aider_engine import AiderEngine

    with patch("core.engine.observable_model.ObservableModel") as mock_cls:
        mock_model = MagicMock()
        mock_cls.return_value = mock_model
        engine = AiderEngine("test/model")
        with patch("core.engine.aider_engine.os.chdir"), patch(
            "core.engine.aider_engine.begin_delegation_snapshot", return_value=None
        ), patch("core.engine.aider_engine.snapshot_git_dirty", return_value=set()), patch(
            "core.engine.aider_engine.snapshot_mtimes", return_value={}
        ), patch(
            "core.engine.aider_engine.concurrent.futures.ThreadPoolExecutor"
        ) as pool_cls, patch("aider.coders.Coder") as coder_cls:
            mock_coder = MagicMock()
            mock_coder.run.return_value = "ok"
            coder_cls.create.return_value = mock_coder
            future = MagicMock()
            future.result.return_value = (
                mock_coder,
                MagicMock(),
                "ok",
                "",
                False,
                False,
            )
            pool_cls.return_value.__enter__.return_value.submit.return_value = future
            engine._execute_delegation(
                prompt="do thing",
                fnames_rel=["a.py"],
                edit_paths_rel=["a.py"],
                workspace_path="/tmp/ws",
                mcp_session_id=None,
            )
        mock_cls.assert_called_once_with("test/model")
