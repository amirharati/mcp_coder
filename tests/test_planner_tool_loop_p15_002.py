"""P15-002 tests: planner tool-calling loop (tool-runner + one-shot fallback)."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Generator
from unittest.mock import patch

from core.context.role_rules import build_role_rules
from core.engine.supervisor_tool_runner import SupervisorToolRunnerResult
from core.engine.planner_pass_llm import (
    PlannerPassLlmResult,
    _finalize_planner_plan,
    _run_planner_one_shot,
    _run_planner_via_tool_runner,
    run_planner_pass_llm,
)
from core.state.project_key import ProjectKeyResolver
from core.engine.owned_helper_llm import OwnedHelperCompletion


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fake_planner_plan() -> str:
    return "## Planner plan\n- Step one: check files\n- Step two: edit"


def _fake_runner_result(text: str = "") -> SupervisorToolRunnerResult:
    if not text:
        text = _fake_planner_plan()
    return SupervisorToolRunnerResult(
        text=text,
        tokens={"input": 10, "output": 5, "total": 15, "source": "test"},
        llm_duration_ms=42,
        llm_calls=1,
    )


def _fake_completion(text: str = "", error: str | None = None) -> OwnedHelperCompletion:
    if not text:
        text = _fake_planner_plan()
    return OwnedHelperCompletion(
        text=text,
        model="test/planner",
        tokens={"input": 10, "output": 5, "total": 15, "source": "owned_completion"},
        duration_ms=42,
        error=error,
    )


def _make_fake_runner(
    run_with_metrics_result: SupervisorToolRunnerResult | None = None,
    run_with_metrics_raises: Exception | None = None,
) -> SimpleNamespace:
    def _run_with_metrics(system_prompt, messages):
        if run_with_metrics_raises is not None:
            raise run_with_metrics_raises
        return run_with_metrics_result

    return SimpleNamespace(run_with_metrics=_run_with_metrics)


@contextmanager
def _patched_env_config() -> Generator[None, None, None]:
    """Patch env-dependent functions so tests don't need real API keys."""
    with patch(
        "core.engine.planner_pass_llm.provider_hint_for_model", return_value=None
    ), patch(
        "core.engine.planner_pass_llm.resolve_role_model_name",
        return_value="test/planner",
    ):
        yield


# ── Slice A: tool-runner primary path ──────────────────────────────────────────


def test_planner_uses_tool_runner_when_project_key_resolvable():
    fake_runner = _make_fake_runner(run_with_metrics_result=_fake_runner_result())

    with _patched_env_config():
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
            return_value=fake_runner,
        ) as mock_build:
            result = run_planner_pass_llm(
                "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            )

    assert result.success is True
    assert result.plan.startswith("## Planner plan")
    mock_build.assert_called_once()
    call_kwargs = mock_build.call_args.kwargs
    assert call_kwargs["project_key"] == ProjectKeyResolver.from_spec_path(
        "tasks/foo.md"
    )
    assert call_kwargs["model"] == result.model


def test_planner_falls_back_to_one_shot_on_runner_exception():
    with _patched_env_config():
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
            side_effect=RuntimeError("boom"),
        ), patch(
            "core.engine.planner_pass_llm.run_owned_helper_completion",
            return_value=_fake_completion(),
        ) as mock_completion:
            result = run_planner_pass_llm(
                "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            )

    assert result.success is True
    assert result.plan.startswith("## Planner plan")
    mock_completion.assert_called_once()


def test_planner_falls_back_to_one_shot_on_empty_output():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=SupervisorToolRunnerResult(
            text="   ", tokens={}, llm_duration_ms=0, llm_calls=0,
        )
    )

    with _patched_env_config():
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
            return_value=fake_runner,
        ), patch(
            "core.engine.planner_pass_llm.run_owned_helper_completion",
            return_value=_fake_completion(),
        ) as mock_completion:
            result = run_planner_pass_llm(
                "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            )

    assert result.success is True
    mock_completion.assert_called_once()


def test_planner_falls_back_to_one_shot_when_project_key_unresolvable():
    """When spec_path is not provided, skip tool runner."""
    with _patched_env_config():
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
        ) as mock_build, patch(
            "core.engine.planner_pass_llm.run_owned_helper_completion",
            return_value=_fake_completion(),
        ) as mock_completion:
            result = run_planner_pass_llm(
                "Test prompt", workspace_path="/tmp/ws",
            )

    assert result.success is True
    mock_build.assert_not_called()
    mock_completion.assert_called_once()


def test_planner_falls_back_to_one_shot_on_default_project_key(monkeypatch):
    monkeypatch.setenv("MCP_CODER_PROJECT_KEY", "default")

    with _patched_env_config():
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
        ) as mock_build, patch(
            "core.engine.planner_pass_llm.run_owned_helper_completion",
            return_value=_fake_completion(),
        ) as mock_completion:
            result = run_planner_pass_llm(
                "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            )

    assert result.success is True
    mock_build.assert_not_called()
    mock_completion.assert_called_once()


def test_planner_final_plan_still_starts_with_heading():
    plan_text = "## Planner plan\n- Step one\n- Step two"
    fake_runner = _make_fake_runner(
        run_with_metrics_result=_fake_runner_result(text=plan_text),
    )

    with _patched_env_config():
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
            return_value=fake_runner,
        ):
            result = run_planner_pass_llm(
                "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            )

    assert result.success is True
    assert result.plan.startswith("## Planner plan")
    _, err = _finalize_planner_plan(result.plan)
    assert err is None


def test_planner_public_api_unchanged():
    with _patched_env_config():
        with patch(
            "core.engine.planner_pass_llm.run_owned_helper_completion",
            return_value=_fake_completion(),
        ):
            result = run_planner_pass_llm("p", workspace_path="/tmp/ws")
    assert result.success is True


def test_planner_one_shot_path_byte_identical():
    known = _fake_completion()
    with patch(
        "core.engine.planner_pass_llm.run_owned_helper_completion",
        return_value=known,
    ):
        one_shot = _run_planner_one_shot(
            "Test prompt", workspace_path="/tmp/ws", model="test/planner"
        )
    with _patched_env_config():
        with patch(
            "core.engine.planner_pass_llm.run_owned_helper_completion",
            return_value=known,
        ):
            public = run_planner_pass_llm(
                "Test prompt", workspace_path="/tmp/ws",
            )

    assert one_shot.success == public.success
    assert one_shot.plan == public.plan
    assert one_shot.model == public.model
    assert one_shot.tokens == public.tokens
    assert one_shot.duration_ms == public.duration_ms
    assert one_shot.raw_output == public.raw_output


def test_planner_config_error_short_circuits():
    with patch(
        "core.engine.planner_pass_llm.provider_hint_for_model",
        return_value="MISSING_API_KEY",
    ):
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
        ) as mock_build, patch(
            "core.engine.planner_pass_llm.run_owned_helper_completion",
        ) as mock_completion:
            result = run_planner_pass_llm(
                "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            )
    assert result.success is False
    assert result.error == "MISSING_API_KEY"
    mock_build.assert_not_called()
    mock_completion.assert_not_called()


# ── Slice B: trace capture (event_sink=None — see P15-ISS-*) ───────────────────


def test_planner_event_sink_is_none():
    captured_kwargs = {}

    with _patched_env_config():
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
            side_effect=lambda **kw: captured_kwargs.update(kw) or _make_fake_runner(
                run_with_metrics_result=_fake_runner_result(),
            ),
        ):
            run_planner_pass_llm(
                "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            )

    assert captured_kwargs.get("event_sink") is None


def test_planner_no_tool_calls_works():
    fake_runner = _make_fake_runner(run_with_metrics_result=_fake_runner_result())
    with _patched_env_config():
        with patch(
            "core.engine.supervisor_tool_runner.build_planner_tool_runner",
            return_value=fake_runner,
        ):
            result = run_planner_pass_llm(
                "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            )
    assert result.success is True


# ── Slice C: no prompt change (regression guard) ───────────────────────────────


def test_planner_prompt_unchanged_from_p15_000():
    rules = build_role_rules("planner")
    assert "## Planner plan" in rules
    assert "Max ~250 words" in rules
    assert "concise" in rules.lower()
    # Verify no tool-use note was added (Slice C skipped)
    assert "tools available" not in rules.lower()
    assert "read_file(" not in rules
    assert "get_project_state(" not in rules


# ── Edge cases ─────────────────────────────────────────────────────────────────


def test_planner_via_tool_runner_returns_none_when_spec_path_is_none():
    result = _run_planner_via_tool_runner(
        "Test", workspace_path="/tmp/ws", spec_path=None, model="test/planner",
    )
    assert result is None


def test_planner_via_tool_runner_returns_none_when_project_key_is_default():
    with patch.object(
        ProjectKeyResolver, "from_spec_path", return_value="default"
    ):
        result = _run_planner_via_tool_runner(
            "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            model="test/planner",
        )
    assert result is None


def test_planner_via_tool_runner_returns_none_when_runner_raises():
    fake_runner = _make_fake_runner(run_with_metrics_raises=RuntimeError("oops"))
    with patch(
        "core.engine.supervisor_tool_runner.build_planner_tool_runner",
        return_value=fake_runner,
    ):
        result = _run_planner_via_tool_runner(
            "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            model="test/planner",
        )
    assert result is None


def test_planner_via_tool_runner_returns_none_on_strip_preamble_failure():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=_fake_runner_result(
            text="Just a sentence, no heading"
        )
    )
    with patch(
        "core.engine.supervisor_tool_runner.build_planner_tool_runner",
        return_value=fake_runner,
    ):
        result = _run_planner_via_tool_runner(
            "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            model="test/planner",
        )
    assert result is None


def test_planner_via_tool_runner_returns_none_on_bad_plan_format():
    fake_runner = _make_fake_runner(
        run_with_metrics_result=_fake_runner_result(
            text="## Something else\n-not a plan"
        )
    )
    with patch(
        "core.engine.supervisor_tool_runner.build_planner_tool_runner",
        return_value=fake_runner,
    ):
        result = _run_planner_via_tool_runner(
            "Test", workspace_path="/tmp/ws", spec_path="tasks/foo.md",
            model="test/planner",
        )
    assert result is None