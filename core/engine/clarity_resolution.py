"""Supervisor clarity-resolution sub-agent (P15-003).

When the clarity check returns ## UNCLEAR with questions, this sub-agent
investigates them using bounded tool-calling (SupervisorToolRunner) before
pausing for the human. If it can answer from available context (spec, files,
project state, delegation history, reviewer findings), it returns structured
answers; the caller writes them to the spec's ## Q&A section and the
delegation proceeds. If it can't answer, it escalates and the caller pauses
(current behavior).

The sub-agent is a proper sub-loop: its own SupervisorToolRunner instance,
its own message history. Isolated from the main supervisor loop (which hasn't
started yet -- clarity runs in preloop). Bounded to 3 tool rounds + 1 final
toolless call (the runner's existing behavior, same as the planner in P15-002).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.config.models import provider_hint_for_model
from core.config.providers import apply_provider_env
from core.config.role_models import ROLE_SUPERVISOR, resolve_role_model_name
from core.context.role_rules import build_role_rules
from core.engine.supervisor_tool_runner import build_phase12_tool_runner


@dataclass
class ClarityResolutionResult:
    """Outcome of one clarity-resolution sub-agent run.

    On ANY failure (exception, empty output, parse failure): resolved=False
    (escalate). The sub-agent must never break the delegation -- escalating
    to the human is always the safe fallback.
    """

    resolved: bool
    answers: list[str] = field(default_factory=list)
    escalate_reason: str | None = None
    model: str = ""
    tokens: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    tool_calls: int = 0
    raw_output: str = ""
    error: str | None = None


_ANSWERS_HEADING_RE = re.compile(r"^##\s+Answers\s*$", re.IGNORECASE | re.MULTILINE)
_ESCALATE_HEADING_RE = re.compile(r"^##\s+Escalate\s*$", re.IGNORECASE | re.MULTILINE)
_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")


def _parse_answers_block(body: str, expected_count: int) -> list[str]:
    """Parse numbered answers (1. ... 2. ...) from a ## Answers body.

    Returns answers in question order. Extra answers beyond expected_count
    are ignored.
    """
    answers: list[str] = []
    for line in body.splitlines():
        m = _NUMBERED_LINE_RE.match(line)
        if m:
            idx = int(m.group(1))
            text = m.group(2).strip()
            while len(answers) < idx:
                answers.append("")
            if idx >= 1:
                answers[idx - 1] = text
    return answers[:expected_count] if expected_count > 0 else answers


def _build_user_prompt(
    *,
    questions: list[str],
    spec_read: Any,
    task: str,
    context_summary: str,
) -> str:
    """Assemble the user prompt for the clarity-resolver sub-agent."""
    q_block = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    spec_text = ""
    if spec_read is not None:
        raw = getattr(spec_read, "raw_text", None) or ""
        # Bound to ~4000 chars to keep the prompt compact.
        spec_text = raw[:4000] if raw else ""
    sections = [
        "## Clarity questions to resolve",
        q_block,
        "## Task",
        task or "(none)",
        "## Context summary",
        context_summary or "(none)",
    ]
    if spec_text:
        sections.extend(["## Spec (read-only context)", spec_text])
    sections.append(
        "## Instruction\n"
        "For each numbered question above, either provide a concrete answer based on "
        "your investigation (use the available tools: read_file, get_project_state, "
        "get_delegation_history, get_reviewer_findings), or state `ESCALATE` if you "
        "genuinely cannot answer from available context.\n\n"
        "Format your final response EXACTLY as one of:\n"
        "- `## Answers` followed by numbered answers (1. ..., 2. ...) matching the questions.\n"
        "- `## Escalate` followed by a one-line reason.\n\n"
        "If you cannot answer ANY question, return `## Escalate`. Do not mix."
    )
    return "\n\n".join(sections)


def run_clarity_resolution(
    questions: list[str],
    *,
    workspace_path: str | Path,
    spec_path: str | None,
    project_state: Any,
    spec_read: Any,
    task: str,
    context_summary: str,
    event_sink: Callable[[dict], None] | None = None,
) -> ClarityResolutionResult:
    """Run the supervisor clarity-resolution sub-agent.

    See module docstring. Bounded to 3 tool rounds + 1 final toolless call.
    Falls back to escalate (resolved=False) on any failure.
    """
    # Fallback: no questions -> nothing to resolve -> escalate.
    if not questions:
        return ClarityResolutionResult(
            resolved=False,
            escalate_reason="no_questions",
        )

    # Resolve model (supervisor role -- clarity resolver is a supervisor sub-agent).
    try:
        apply_provider_env()
        model = resolve_role_model_name(ROLE_SUPERVISOR, str(workspace_path))
    except Exception as exc:
        return ClarityResolutionResult(
            resolved=False,
            escalate_reason=f"model_resolve_failed: {exc}",
            error=str(exc),
        )

    config_error = provider_hint_for_model(model)
    if config_error:
        return ClarityResolutionResult(
            resolved=False,
            escalate_reason=f"provider_config: {config_error}",
            error=config_error,
        )

    # Resolve project_key for the tool runner.
    try:
        from core.state.project_key import ProjectKeyResolver

        project_key = ProjectKeyResolver.from_spec_path(spec_path) if spec_path else ""
    except Exception:
        project_key = ""
    if not project_key or project_key == "default":
        # No project context -> can't run tools meaningfully -> escalate.
        return ClarityResolutionResult(
            resolved=False,
            escalate_reason="project_key_unresolved",
        )

    # Build the tool runner (reuses the supervisor's 4 tools).
    try:
        runner = build_phase12_tool_runner(
            workspace_path=str(workspace_path),
            project_key=project_key,
            project_state=project_state,
            event_sink=event_sink,
            model=model,
        )
    except Exception as exc:
        return ClarityResolutionResult(
            resolved=False,
            escalate_reason=f"runner_build_failed: {exc}",
            error=str(exc),
        )

    user_prompt = _build_user_prompt(
        questions=questions,
        spec_read=spec_read,
        task=task,
        context_summary=context_summary,
    )

    t0 = time.perf_counter()
    try:
        tool_result = runner.run_with_metrics(
            system_prompt=build_role_rules("clarity_resolver"),
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        return ClarityResolutionResult(
            resolved=False,
            escalate_reason=f"runner_exception: {exc}",
            error=str(exc),
            model=model,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
    duration_ms = int((time.perf_counter() - t0) * 1000)

    raw = getattr(tool_result, "text", "") or ""
    tokens = getattr(tool_result, "tokens", {}) or {}
    llm_calls = getattr(tool_result, "llm_calls", 0) or 0
    # tool_calls count is approximate: each round with tool_calls counts as 1; we
    # don't have a per-call counter exposed on SupervisorToolRunnerResult. Use
    # llm_calls as a proxy (matches what the planner does). See P15-ISS-* for a
    # future richer metric.
    tool_calls = llm_calls

    if not raw.strip():
        return ClarityResolutionResult(
            resolved=False,
            escalate_reason="empty_output",
            model=model,
            tokens=tokens,
            duration_ms=duration_ms,
            tool_calls=tool_calls,
            raw_output=raw,
        )

    # Parse output.
    answers_match = _ANSWERS_HEADING_RE.search(raw)
    escalate_match = _ESCALATE_HEADING_RE.search(raw)

    if answers_match and (
        escalate_match is None or answers_match.start() < escalate_match.start()
    ):
        # ## Answers branch.
        body = raw[answers_match.end() :].strip()
        answers = _parse_answers_block(body, expected_count=len(questions))
        # Validate: we got at least one non-empty answer for each question.
        if len(answers) < len(questions) or any(not a.strip() for a in answers):
            # Parse failure -- escalate.
            return ClarityResolutionResult(
                resolved=False,
                escalate_reason="answers_incomplete_or_malformed",
                model=model,
                tokens=tokens,
                duration_ms=duration_ms,
                tool_calls=tool_calls,
                raw_output=raw,
                error="answers_incomplete_or_malformed",
            )
        return ClarityResolutionResult(
            resolved=True,
            answers=answers,
            model=model,
            tokens=tokens,
            duration_ms=duration_ms,
            tool_calls=tool_calls,
            raw_output=raw,
        )

    if escalate_match:
        body = raw[escalate_match.end() :].strip()
        reason = body.splitlines()[0].strip() if body else "escalated"
        return ClarityResolutionResult(
            resolved=False,
            escalate_reason=reason[:300],
            model=model,
            tokens=tokens,
            duration_ms=duration_ms,
            tool_calls=tool_calls,
            raw_output=raw,
        )

    # No recognizable heading -> parse failure -> escalate.
    return ClarityResolutionResult(
        resolved=False,
        escalate_reason="parse_failure_no_recognized_heading",
        model=model,
        tokens=tokens,
        duration_ms=duration_ms,
        tool_calls=tool_calls,
        raw_output=raw,
        error="parse_failure_no_recognized_heading",
    )


def _clarity_resolution_enabled(workspace: str | Any) -> bool:
    """Whether the supervisor clarity-resolution sub-agent should run.

    Default: True (enabled). Disable with:
    - Env ``MCP_CODER_CLARITY_RESOLUTION=0``
    - Yaml ``clarity_resolution: false`` (later wins).

    Mirrors ``_supervisor_llm_decide_enabled`` (core/engine/supervisor_agent.py:149).
    """
    import os

    env_raw = os.environ.get("MCP_CODER_CLARITY_RESOLUTION", "").strip()
    if env_raw == "0":
        return False
    try:
        from core.storage.workspace_config import load_workspace_config

        ws_value = load_workspace_config(workspace).get("clarity_resolution")
        if ws_value is not None:
            return bool(ws_value)
    except Exception:
        pass
    return True