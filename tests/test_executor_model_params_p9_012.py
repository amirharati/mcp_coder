"""P9-012 — executor applies registry CallParams to the aider Model via setters."""

from __future__ import annotations

from core.config.model_registry import CallParams
from core.engine.aider_engine import _apply_executor_model_params


class _FakeModel:
    def __init__(self):
        self.extra_params: dict = {}
        self.reasoning_effort = None
        self.thinking_budget = None
        self.weak_model_arg = None

    def set_reasoning_effort(self, effort):
        self.reasoning_effort = effort

    def set_thinking_tokens(self, num):
        self.thinking_budget = num

    def get_weak_model(self, name):
        self.weak_model_arg = name
        return name


def test_reasoning_effort_applied():
    m = _FakeModel()
    _apply_executor_model_params(m, CallParams(reasoning_effort="high"))
    assert m.reasoning_effort == "high"
    assert m.thinking_budget is None


def test_thinking_budget_applied_when_no_effort():
    m = _FakeModel()
    _apply_executor_model_params(m, CallParams(thinking_budget=8000))
    assert m.thinking_budget == 8000


def test_reasoning_effort_wins_over_thinking_budget():
    m = _FakeModel()
    _apply_executor_model_params(
        m, CallParams(reasoning_effort="low", thinking_budget=8000)
    )
    assert m.reasoning_effort == "low"
    assert m.thinking_budget is None


def test_extra_params_merged():
    m = _FakeModel()
    m.extra_params = {"extra_body": {"a": 1}}
    _apply_executor_model_params(
        m, CallParams(extra_params={"seed": 42, "extra_body": {"b": 2}})
    )
    assert m.extra_params["seed"] == 42
    assert m.extra_params["extra_body"] == {"a": 1, "b": 2}


def test_weak_model_applied():
    m = _FakeModel()
    _apply_executor_model_params(m, CallParams(weak_model="anthropic/claude-3-5-haiku-latest"))
    assert m.weak_model_arg == "anthropic/claude-3-5-haiku-latest"


def test_no_params_is_noop():
    m = _FakeModel()
    _apply_executor_model_params(m, CallParams())
    assert m.reasoning_effort is None
    assert m.thinking_budget is None
    assert m.weak_model_arg is None
    assert m.extra_params == {}


def test_setter_failure_does_not_raise():
    class _Boom:
        extra_params = {}

        def set_reasoning_effort(self, effort):
            raise RuntimeError("nope")

    # Must not propagate — best-effort application.
    _apply_executor_model_params(_Boom(), CallParams(reasoning_effort="high"))
