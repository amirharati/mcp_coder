import pytest

from core.engine import AiderEngine, get_engine, list_backends
from core.engine.aider_engine import BACKEND_ID
from core.engine.base import ExecutionEngine, ExecutionResult
from core.engine.factory import UnknownBackendError, register_engine
from core.engine.interception_profile import InterceptionProfile


def test_list_backends_includes_aider():
    assert BACKEND_ID in list_backends()


def test_get_engine_returns_aider_adapter():
    engine = get_engine("aider")
    assert isinstance(engine, AiderEngine)
    assert isinstance(engine, ExecutionEngine)
    assert engine.backend_id == "aider"


def test_get_engine_unknown_backend():
    with pytest.raises(UnknownBackendError) as exc_info:
        get_engine("not-a-real-backend")
    assert "aider" in exc_info.value.available


def test_register_engine_custom():
    class DummyEngine(ExecutionEngine):
        @property
        def backend_id(self) -> str:
            return "dummy_test"

        @property
        def interception_profile(self) -> InterceptionProfile:
            return InterceptionProfile(
                strategy="callback",
                verified_call_sites=("tests/dummy.py:1",),
                known_gaps=(),
                thinking_captured=True,
            )

        def run(self, prompt, target_files, *, workspace_path):
            return ExecutionResult(success=True, output="ok")

    register_engine("dummy_test", DummyEngine)
    engine = get_engine("dummy_test")
    assert engine.backend_id == "dummy_test"
