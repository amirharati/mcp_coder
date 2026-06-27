"""Cheap-LLM planner pass (P11-008 rename from architect_pass_llm).

Primary path: SupervisorToolRunner with bounded tool-calling loop (P15-002).
Fallback: one-shot run_owned_helper_completion call. Fails gracefully so
delegations continue with the mechanical/builder brief.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.config.models import provider_hint_for_model
from core.config.providers import apply_provider_env
from core.config.role_models import ROLE_PLANNER, resolve_role_model_name
from core.context.role_rules import build_role_rules
from core.engine.owned_helper_llm import run_owned_helper_completion

_ERROR_MARKERS = (
    "litellm.",
    "notfounderror",
    "authenticationerror",
    "ratelimiterror",
    "openrouterexception",
    "openaierror",
)

_HEADING_RE = re.compile(r"^##\s+\S", re.MULTILINE)
_CODE_FENCE_LINE_RE = re.compile(r"^```\w*\s*$", re.MULTILINE)
_PLANNER_HEADER_RE = re.compile(r"^##\s+Planner\s+plan\s*$", re.IGNORECASE)
_MAX_PLAN_CHARS = 3000


def _strip_code_fences(text: str) -> str:
    m = _CODE_FENCE_LINE_RE.search(text)
    if m is None:
        return text
    return text[: m.start()].rstrip()


def _strip_reasoning_preamble(text: str) -> str:
    m = _HEADING_RE.search(text)
    if m is None:
        return ""
    return text[m.start() :].strip()


def _finalize_planner_plan(raw_output: str) -> tuple[str, str | None]:
    narrative = _strip_code_fences(raw_output).strip()
    if not narrative:
        return "", "planner plan empty after stripping code fences"
    lines = narrative.splitlines()
    if not lines or not _PLANNER_HEADER_RE.match(lines[0].strip()):
        return "", "planner response must start with '## Planner plan'"
    lower = narrative.lower()
    if any(m in lower for m in _ERROR_MARKERS):
        return "", narrative[:2000]
    if len(narrative) > _MAX_PLAN_CHARS:
        narrative = narrative[: _MAX_PLAN_CHARS - 20] + "\n…[truncated]"
    return narrative, None


@dataclass
class PlannerPassLlmResult:
    success: bool
    plan: str
    model: str
    error: str | None = None
    tokens: dict[str, Any] = field(default_factory=lambda: {"source": "unavailable"})
    duration_ms: int = 0
    raw_output: str = ""


def _unavailable_tokens() -> dict[str, Any]:
    return {"input": None, "output": None, "total": None, "source": "unavailable"}


# ── One-shot fallback (preserves the pre-P15-002 behaviour exactly) ────────────


def _run_planner_one_shot(
    prompt: str,
    *,
    workspace_path: str | Path,
    model: str,
) -> PlannerPassLlmResult:
    """One-shot planner model call — the pre-P15-002 fallback path."""
    messages = [{"role": "user", "content": prompt}]
    completion = run_owned_helper_completion(
        messages,
        model=model,
        system_prompt=build_role_rules("planner"),
    )
    if completion.error:
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=model,
            error=completion.error,
            tokens=completion.tokens,
            duration_ms=completion.duration_ms,
        )

    output = completion.text
    duration_ms = completion.duration_ms
    tokens = completion.tokens

    if not output.strip():
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=model,
            error="Empty planner response from model",
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    clean = _strip_reasoning_preamble(output)
    if not clean:
        lower = output.lower()
        if any(m in lower for m in _ERROR_MARKERS):
            return PlannerPassLlmResult(
                success=False,
                plan="",
                model=model,
                error=output.strip()[:2000],
                tokens=tokens,
                duration_ms=duration_ms,
                raw_output=output,
            )
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=model,
            error=(
                "Planner response contained no markdown headings (reasoning leak?): "
                f"{output.strip()[:200]}"
            ),
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    plan, finalize_error = _finalize_planner_plan(clean)
    if finalize_error:
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=model,
            error=finalize_error,
            tokens=tokens,
            duration_ms=duration_ms,
            raw_output=output,
        )

    return PlannerPassLlmResult(
        success=True,
        plan=plan,
        model=model,
        error=None,
        tokens=tokens,
        duration_ms=duration_ms,
        raw_output=output,
    )


# ── Tool-runner primary path (P15-002) ─────────────────────────────────────────


def _run_planner_via_tool_runner(
    prompt: str,
    *,
    workspace_path: str | Path,
    spec_path: str | None,
    model: str,
    event_sink: Callable[[dict], None] | None = None,
) -> PlannerPassLlmResult | None:
    """Run the planner via SupervisorToolRunner with bounded tool-calling.

    Returns None on any failure so the caller falls back to one-shot.
    """
    if spec_path is None:
        return None  # cannot resolve a meaningful project_key → one-shot

    from core.engine.supervisor_tool_runner import (
        build_planner_tool_runner,
    )
    from core.state.project_key import ProjectKeyResolver
    from core.state.project_state import ProjectState

    project_key = ProjectKeyResolver.from_spec_path(spec_path)
    if not project_key or project_key == "default":
        return None

    try:
        project_state = ProjectState.load(project_key)
    except Exception:
        return None

    try:
        runner = build_planner_tool_runner(
            workspace_path=str(workspace_path),
            project_key=project_key,
            project_state=project_state,
            event_sink=event_sink,  # P15-ISS-004: wired from apply_planner_pass
            model=model,
        )
    except Exception:
        return None

    try:
        tool_result = runner.run_with_metrics(
            system_prompt=build_role_rules("planner"),
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return None

    # SupervisorToolRunnerResult has no `error` field; failure is signalled
    # by empty text. Use getattr so fake runners in tests work.
    raw = getattr(tool_result, "text", "") or ""
    if not raw.strip():
        return None

    clean = _strip_reasoning_preamble(raw)
    if not clean:
        return None

    plan, finalize_error = _finalize_planner_plan(clean)
    if finalize_error:
        return None  # let one-shot try its own finalization on the raw text

    tokens = getattr(tool_result, "tokens", None) or _unavailable_tokens()
    duration_ms = getattr(tool_result, "llm_duration_ms", 0) or 0

    return PlannerPassLlmResult(
        success=True,
        plan=plan,
        model=model,
        error=None,
        tokens=tokens,
        duration_ms=duration_ms,
        raw_output=raw,
    )


# ── Public API ─────────────────────────────────────────────────────────────────


def run_planner_pass_llm(
    prompt: str,
    *,
    workspace_path: str | Path,
    spec_path: str | None = None,
    event_sink: Callable[[dict], None] | None = None,
) -> PlannerPassLlmResult:
    """Planner model call (P15-002: tool-runner primary + one-shot fallback).

    When spec_path is provided and resolvable, the planner uses a
    SupervisorToolRunner with read_file / get_project_state /
    get_delegation_history tools (bounded to 3 tool rounds).  On any
    failure the planner falls back to the one-shot path.

    event_sink (P15-ISS-004): when provided, each tool call in the tool-runner
    path is forwarded to the sink so it lands in the delegation trace.
    """
    apply_provider_env()
    resolved = resolve_role_model_name(ROLE_PLANNER, workspace_path)

    config_error = provider_hint_for_model(resolved)
    if config_error:
        return PlannerPassLlmResult(
            success=False,
            plan="",
            model=resolved,
            error=config_error,
            tokens=_unavailable_tokens(),
        )

    try:
        result = _run_planner_via_tool_runner(
            prompt,
            workspace_path=workspace_path,
            spec_path=spec_path,
            model=resolved,
            event_sink=event_sink,
        )
        if result is not None:
            return result
    except Exception:
        # Tool runner raised → fall back to one-shot. Observability must
        # never break the planner.
        pass

    return _run_planner_one_shot(prompt, workspace_path=workspace_path, model=resolved)
