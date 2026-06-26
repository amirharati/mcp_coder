"""P14-ISS-005: executor path must route temperature/top_p/max_tokens from
CallParams into the Aider Model.extra_params so they reach the litellm
completion call.

Aider's Model has no setters for these fields, but extra_params is merged
into the litellm completion kwargs as top-level keys, so this is the
supported path. EXTRA_PARAMS (the escape hatch) takes precedence — a
value supplied via extra_params is not overwritten.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.config.model_registry import CallParams
from core.engine.aider_engine import _apply_executor_model_params


def _make_model(extra_params: dict | None = None) -> SimpleNamespace:
    """Minimal Aider Model stand-in exposing the attributes the function touches."""
    return SimpleNamespace(
        extra_params=dict(extra_params) if extra_params else None,
        system_prompt_prefix=None,
    )


def test_executor_params_route_temperature_top_p_max_tokens_into_extra_params():
    params = CallParams(
        temperature=0.2,
        top_p=0.9,
        max_tokens=2048,
    )
    model = _make_model()
    _apply_executor_model_params(model, params)

    assert model.extra_params["temperature"] == 0.2
    assert model.extra_params["top_p"] == 0.9
    assert model.extra_params["max_tokens"] == 2048


def test_executor_params_do_not_overwrite_extra_params_escape_hatch():
    """If a user set the same key via EXTRA_PARAMS, that wins."""
    params = CallParams(
        temperature=0.2,
        max_tokens=2048,
        extra_params={"temperature": 0.7, "logprobs": True},
    )
    model = _make_model()
    _apply_executor_model_params(model, params)

    # temperature comes from extra_params (escape hatch), not from params.temperature
    assert model.extra_params["temperature"] == 0.7
    # max_tokens still routed (not present in extra_params)
    assert model.extra_params["max_tokens"] == 2048
    # extra_params-only key preserved
    assert model.extra_params["logprobs"] is True
    # top_p not set on params → not added
    assert "top_p" not in model.extra_params


def test_executor_params_skip_none_values():
    params = CallParams(temperature=0.2)  # top_p and max_tokens are None
    model = _make_model()
    _apply_executor_model_params(model, params)

    assert model.extra_params["temperature"] == 0.2
    assert "top_p" not in model.extra_params
    assert "max_tokens" not in model.extra_params


def test_executor_params_no_params_no_change():
    params = CallParams()
    model = _make_model(extra_params={"seed": 42})
    _apply_executor_model_params(model, params)

    # Nothing added; existing extra_params preserved.
    assert model.extra_params == {"seed": 42}
