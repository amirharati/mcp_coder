"""Delegation supervisor LLM (P11-002). Aider-specific decision layer."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.config.providers import apply_provider_env
from core.config.models import provider_hint_for_model
from core.config.role_models import ROLE_SUPERVISOR, resolve_role_model_name

DecisionKind = Literal["approve", "deny", "abort", "escalate"]

_DECISION_RE = re.compile(
    r"^##\s+Decision:\s*(APPROVE|DENY|ABORT|ESCALATE)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_REASON_RE = re.compile(r"^##\s+Reason\s*$", re.MULTILINE | re.IGNORECASE)
_HEADING_RE = re.compile(r"^##\s+\S", re.MULTILINE)
_MAX_REASON_CHARS = 400
_MAX_PROMPT_CHARS = 8000
_MAX_PRIOR_DECISIONS = 8
_MAX_PRIOR_CHARS = 1200

_SUPERVISOR_PREAMBLE = """## Role: delegation supervisor

You review Aider executor confirmation prompts during an MCP delegation.
Decide whether to approve, deny, abort, or escalate to the human planner.

Rules:
- Begin IMMEDIATELY with exactly one line: `## Decision: APPROVE|DENY|ABORT|ESCALATE`
- Then `## Reason` followed by one short sentence (<= 400 chars)
- APPROVE: safe, in-spec routine action
- DENY: reject this specific action but executor may try another approach
- ABORT: stop delegation — out of scope or unsafe
- ESCALATE: human judgment required before proceeding
- No preamble, no code fences, no extra headings"""


@dataclass
class SupervisorDecision:
    decision: DecisionKind
    reasoning: str
    duration_ms: int
    risk_tier: str
    model: str = ""
    tokens: dict[str, Any] = field(default_factory=dict)


def _strip_preamble(text: str) -> str:
    m = _HEADING_RE.search(text)
    if m is None:
        return text.strip()
    return text[m.start() :].strip()


def parse_supervisor_output(raw_output: str) -> tuple[DecisionKind | None, str, str | None]:
    """Parse model output. Returns (decision, reasoning, error)."""
    narrative = _strip_preamble(raw_output.strip())
    if not narrative:
        return None, "", "empty supervisor response"

    decision_match = _DECISION_RE.search(narrative)
    if decision_match is None:
        return None, "", "missing Decision heading"

    decision_raw = decision_match.group(1).lower()
    if decision_raw not in ("approve", "deny", "abort", "escalate"):
        return None, "", f"invalid decision: {decision_raw}"

    reason_match = _REASON_RE.search(narrative, decision_match.end())
    if reason_match is None:
        return decision_raw, "", None

    body = narrative[reason_match.end() :].strip()
    first_line = body.splitlines()[0].strip() if body else ""
    if len(first_line) > _MAX_REASON_CHARS:
        first_line = first_line[: _MAX_REASON_CHARS - 3] + "..."
    return decision_raw, first_line, None


def _summarize_prior_decisions(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return "(none)"
    lines: list[str] = []
    for row in decisions[-_MAX_PRIOR_DECISIONS:]:
        q = str(row.get("question") or "")[:120]
        dec = row.get("decision") or "?"
        reason = str(row.get("reasoning") or "")[:80]
        lines.append(f"- [{dec}] {q} — {reason}")
    text = "\n".join(lines)
    if len(text) > _MAX_PRIOR_CHARS:
        return text[-_MAX_PRIOR_CHARS :]
    return text


def build_supervisor_prompt(
    *,
    question: str,
    risk_tier: str,
    spec_contract: str | None,
    architect_plan: str | None,
    prior_decisions: list[dict[str, Any]],
    output_tail: str,
) -> str:
    sections = [_SUPERVISOR_PREAMBLE, f"## Risk tier\n{risk_tier}", f"## Question\n{question.strip()}"]
    contract = (spec_contract or "").strip()
    if contract:
        sections.append(f"## Spec contract\n{contract[:2000]}")
    plan = (architect_plan or "").strip()
    if plan:
        sections.append(f"## Planner plan\n{plan[:1500]}")
    sections.append(f"## Prior decisions\n{_summarize_prior_decisions(prior_decisions)}")
    tail = (output_tail or "").strip()
    if tail:
        sections.append(f"## Executor output tail\n{tail[-500:]}")
    prompt = "\n\n".join(sections)
    if len(prompt) > _MAX_PROMPT_CHARS:
        return prompt[: _MAX_PROMPT_CHARS - 14] + "…[truncated]"
    return prompt


class DelegationSupervisor:
    """In-memory supervisor with per-delegation decision log."""

    def __init__(
        self,
        *,
        workspace_path: str | Path,
        delegation_id: str | None,
        spec_contract: str | None,
        architect_plan: str | None,
        output_tail_provider: Callable[[], str],
    ) -> None:
        self._workspace_path = workspace_path
        self._delegation_id = delegation_id
        self._spec_contract = spec_contract
        self._architect_plan = architect_plan
        self._output_tail_provider = output_tail_provider
        self._decision_log: list[dict[str, Any]] = []
        self._total_duration_ms = 0
        self._last_model = ""
        self._project_state: Any | None = None
        self._token_totals: dict[str, Any] = {"input": 0, "output": 0, "total": 0, "source": "supervisor"}

    @property
    def decision_log(self) -> list[dict[str, Any]]:
        return list(self._decision_log)

    @property
    def last_model(self) -> str:
        return self._last_model

    @property
    def usage_record(self) -> dict[str, Any]:
        return {
            "model": self._last_model,
            "input_tokens": self._token_totals.get("input"),
            "output_tokens": self._token_totals.get("output"),
            "total_tokens": self._token_totals.get("total"),
            "duration_ms": self._total_duration_ms,
            "source": "supervisor",
        }

    def evaluate(self, *, question: str, risk_tier: str) -> SupervisorDecision:
        prompt = build_supervisor_prompt(
            question=question,
            risk_tier=risk_tier,
            spec_contract=self._spec_contract,
            architect_plan=self._architect_plan,
            prior_decisions=self._decision_log,
            output_tail=self._output_tail_provider(),
        )
        apply_provider_env()
        model = resolve_role_model_name(ROLE_SUPERVISOR, self._workspace_path)
        self._last_model = model

        config_error = provider_hint_for_model(model)
        if config_error:
            return self._fallback_abort(
                risk_tier=risk_tier,
                reasoning=f"supervisor_error: {config_error}",
                model=model,
            )

        t0 = time.perf_counter()
        try:
            from core.engine.supervisor_tool_runner import build_phase12_tool_runner
            from core.state.project_key import ProjectKeyResolver

            project_key = ProjectKeyResolver.from_spec_path(self._spec_contract or None)
            if self._project_state is None:
                from core.state.project_state import ProjectState

                self._project_state = ProjectState.load(project_key)
            runner = build_phase12_tool_runner(
                workspace_path=str(self._workspace_path),
                project_key=project_key,
                project_state=self._project_state,
                event_sink=None,
                model=model,
            )
            text = runner.run(
                system_prompt="",
                messages=[{"role": "user", "content": prompt}],
            )
            completion_error: str | None = None
        except Exception as exc:
            text = ""
            completion_error = f"{type(exc).__name__}: {exc}"
        duration_ms = int((time.perf_counter() - t0) * 1000)
        self._total_duration_ms += duration_ms

        if completion_error:
            return self._fallback_abort(
                risk_tier=risk_tier,
                reasoning=f"supervisor_error: {completion_error}",
                model=model,
                duration_ms=duration_ms,
            )

        decision, reasoning, parse_error = parse_supervisor_output(text)
        if parse_error or decision is None:
            err = parse_error or "unparseable supervisor response"
            return self._fallback_abort(
                risk_tier=risk_tier,
                reasoning=f"supervisor_error: {err}",
                model=model,
                duration_ms=duration_ms,
            )

        if not reasoning:
            reasoning = f"supervisor {decision}"

        sd = SupervisorDecision(
            decision=decision,
            reasoning=reasoning,
            duration_ms=duration_ms,
            risk_tier=risk_tier,
            model=model,
            tokens={},
        )
        self._emit_llm_call_event(
            question=question,
            prompt=prompt,
            response=text or "",
            decision=sd,
        )
        return sd

    def _emit_llm_call_event(
        self,
        *,
        question: str,
        prompt: str,
        response: str,
        decision: "SupervisorDecision",
    ) -> None:
        """Emit llm_call(role=supervisor) trace event for cost/latency visibility (P11-ISS-003)."""
        try:
            from core.observability.context import (
                delegation_id_var,
                session_dir_var,
                workspace_var,
            )
            from core.observability.trace import append_trace_record, build_llm_call_record

            delegation_id = delegation_id_var.get()
            session_dir = session_dir_var.get()
            workspace = workspace_var.get()
            if not delegation_id or not session_dir:
                return

            record = build_llm_call_record(
                delegation_id=delegation_id,
                role=ROLE_SUPERVISOR,
                model=decision.model or "",
                call_index=1,
                duration_ms=decision.duration_ms,
                tokens=decision.tokens,
                verbosity="full",
                prompt_text=prompt,
                response_text=response,
            )
            record["supervisor_decision"] = decision.decision
            record["supervisor_risk_tier"] = decision.risk_tier
            record["supervisor_question_preview"] = question[:120]
            append_trace_record(
                record,
                delegation_id=delegation_id,
                session_dir=session_dir,
                workspace=workspace or "",
            )
        except Exception:
            pass  # observability must never break completions

    def _accumulate_tokens(self, tokens: dict[str, Any]) -> None:
        for key in ("input", "output", "total"):
            val = tokens.get(key)
            if isinstance(val, (int, float)):
                prev = self._token_totals.get(key) or 0
                self._token_totals[key] = int(prev) + int(val)

    def _fallback_abort(
        self,
        *,
        risk_tier: str,
        reasoning: str,
        model: str,
        duration_ms: int = 0,
    ) -> SupervisorDecision:
        return SupervisorDecision(
            decision="abort",
            reasoning=reasoning,
            duration_ms=duration_ms,
            risk_tier=risk_tier,
            model=model,
        )
