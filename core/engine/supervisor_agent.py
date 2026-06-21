"""Unified supervisor agent loop (P12-001, BL-533).

`SupervisorAgent` owns *all* post-planning control flow for a delegation:

    supervisor_loop_start
      turn 1:  supervisor_turn_start → run worker (Aider) → run checks (reviewer)
               → supervisor_turn_end → supervisor_decision (rerun_aider|done|escalate_host)
      turn 2..N (only when the decision is `rerun_aider` and turns remain)
    supervisor_loop_end

This replaces the previous dual-loop topology:
- ``supervisor_outer_loop_*`` (emitted inline by ``server/mcp_server.py``)
- ``supervisor_loop_*`` (emitted by ``core/engine/supervised_io.py``)

``SupervisedIO`` keeps owning *intra-run* confirm-ask micro-decisions; this agent owns
the *inter-turn* decisions (rerun / done / escalate). They operate at different
granularities.

Backend-neutral: this module never imports Aider APIs. The worker is injected as a
callable producing an :class:`ExecutionResult`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from core.engine.base import ExecutionResult

SupervisorAction = Literal["rerun_aider", "done", "escalate_host"]
SupervisorOutcome = Literal["success", "escalated", "error"]

# Worker: given (turn_index, correction_note) produce an ExecutionResult.
ExecutorFn = Callable[[int, "str | None"], ExecutionResult]
# Checks: given (turn_index, result) produce a compact check summary (or None).
ReviewerFn = Callable[[int, ExecutionResult], "dict[str, Any] | None"]
# Event sink: receives each canonical trace record (used by tests / custom routing).
EventSink = Callable[["dict[str, Any]"], None]


@dataclass
class SupervisorTurnDecision:
    """One inter-turn decision produced after a worker run + checks."""

    action: SupervisorAction
    reason: str
    model: str = ""
    tokens: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class SupervisorTurnContext:
    """Compact inputs handed to a decision function for one turn."""

    turn_index: int
    max_turns: int
    turns_remaining: int
    result: ExecutionResult
    checks: dict[str, Any] | None
    prior_decisions: list[SupervisorTurnDecision]


@dataclass
class SupervisorAgentResult:
    """Final outcome of the supervisor loop, returned to the MCP server."""

    outcome: SupervisorOutcome
    turns_completed: int
    final_action: str
    end_reason: str
    executor_result: ExecutionResult | None
    decisions: list[SupervisorTurnDecision]
    loop_id: str


# Decision function override (e.g. injected by tests, or an LLM-backed callable).
DecisionFn = Callable[[SupervisorTurnContext], SupervisorTurnDecision]


_DECISION_PREAMBLE = """## Role: delegation supervisor (inter-turn)

A coding worker (Aider) just finished one turn of an MCP delegation. Decide the next step.

Rules:
- Begin IMMEDIATELY with exactly one line: `## Action: RERUN_AIDER|DONE|ESCALATE_HOST`
- Then `## Reason` followed by one short sentence (<= 200 chars)
- DONE: quality is sufficient — stop the loop
- RERUN_AIDER: a fixable issue was found — re-run the worker with a correction note
- ESCALATE_HOST: human judgement is required (no policy answer available)
- No preamble, no code fences, no extra headings"""


def resolve_supervisor_max_turns(workspace: str | Any) -> int:
    """Resolve max supervisor turns.

    Precedence: default(1) → env ``MCP_CODER_SUPERVISOR_MAX_TURNS`` → yaml
    ``supervisor_max_turns`` (later wins). Clamped to ``[1, 5]``.

    Default ``1`` keeps behaviour functionally identical to the pre-P12 pipeline
    (single worker run, no autonomous rerun).
    """
    import os

    resolved = 1
    env_raw = os.environ.get("MCP_CODER_SUPERVISOR_MAX_TURNS", "").strip()
    if env_raw:
        try:
            resolved = int(env_raw)
        except ValueError:
            resolved = 1
    try:
        from core.storage.workspace_config import load_workspace_config

        ws_value = load_workspace_config(workspace).get("supervisor_max_turns")
        if ws_value is not None:
            resolved = int(ws_value)
    except Exception:
        pass
    return max(1, min(5, resolved))


def _parse_decision_action(raw: str) -> SupervisorAction | None:
    text = (raw or "").strip()
    if not text:
        return None
    import re

    m = re.search(
        r"^##\s*Action:\s*(RERUN_AIDER|DONE|ESCALATE_HOST)\s*$",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    if m is None:
        return None
    token = m.group(1).lower()
    if token == "rerun_aider":
        return "rerun_aider"
    if token == "done":
        return "done"
    if token == "escalate_host":
        return "escalate_host"
    return None


def _parse_decision_reason(raw: str) -> str:
    import re

    m = re.search(r"^##\s*Reason\s*$", raw or "", re.MULTILINE | re.IGNORECASE)
    if m is None:
        return ""
    body = (raw[m.end():]).strip()
    line = body.splitlines()[0].strip() if body else ""
    return line[:200]


class SupervisorAgent:
    """Stateful supervisor that owns the whole post-planning loop for a delegation."""

    def __init__(
        self,
        *,
        delegation_id: str | None,
        workspace_path: str | Any,
        executor_fn: ExecutorFn,
        reviewer_fn: ReviewerFn | None = None,
        decision_fn: DecisionFn | None = None,
        max_turns: int = 1,
        event_sink: EventSink | None = None,
        supervisor_model: str | None = None,
    ) -> None:
        self._delegation_id = delegation_id
        self._workspace_path = workspace_path
        self._executor_fn = executor_fn
        self._reviewer_fn = reviewer_fn
        self._decision_fn = decision_fn
        self._max_turns = max(1, int(max_turns))
        self._event_sink = event_sink
        self._supervisor_model = supervisor_model
        self._loop_id = f"{delegation_id}:supervisor:1" if delegation_id else "supervisor:1"
        self._loop_start_emitted = False
        self._loop_end_emitted = False
        # Host-driven (manual) mode state — see begin()/begin_turn()/complete_turn()/finish().
        self._cur_turn = 0
        self._turn_t0: float | None = None
        self._decisions: list[SupervisorTurnDecision] = []
        self._last_result: ExecutionResult | None = None

    @property
    def loop_id(self) -> str:
        return self._loop_id

    @property
    def max_turns(self) -> int:
        return self._max_turns

    # ── public API ─────────────────────────────────────────────────────────

    def run(self) -> SupervisorAgentResult:
        """Drive the supervisor loop to completion and return the final outcome."""
        decisions: list[SupervisorTurnDecision] = []
        last_result: ExecutionResult | None = None
        final_action = "done"
        end_reason = "completed"
        turns_completed = 0

        self._emit_loop_start()
        try:
            correction: str | None = None
            for turn_index in range(1, self._max_turns + 1):
                turns_completed = turn_index
                t0 = time.perf_counter()
                self._emit_turn_start(turn_index)

                try:
                    result = self._executor_fn(turn_index, correction)
                except Exception as exc:  # worker blew up — close loop cleanly
                    last_result = last_result
                    final_action = "escalate_host"
                    end_reason = f"executor_exception: {type(exc).__name__}"
                    self._emit_turn_end(
                        turn_index,
                        worker_outcome="error",
                        checks_result=None,
                        duration_ms=int((time.perf_counter() - t0) * 1000),
                    )
                    return self._finish(
                        outcome="error",
                        turns_completed=turns_completed,
                        final_action=final_action,
                        end_reason=end_reason,
                        executor_result=last_result,
                        decisions=decisions,
                    )

                last_result = result
                checks = None
                if self._reviewer_fn is not None:
                    try:
                        checks = self._reviewer_fn(turn_index, result)
                    except Exception:
                        checks = None

                self._emit_turn_end(
                    turn_index,
                    worker_outcome=self._worker_outcome(result),
                    checks_result=checks,
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                )

                turns_remaining = self._max_turns - turn_index
                decision = self._decide(
                    SupervisorTurnContext(
                        turn_index=turn_index,
                        max_turns=self._max_turns,
                        turns_remaining=turns_remaining,
                        result=result,
                        checks=checks,
                        prior_decisions=list(decisions),
                    )
                )
                decisions.append(decision)
                self._emit_decision(turn_index, decision)

                if decision.action == "done":
                    final_action = "done"
                    end_reason = self._success_end_reason(result)
                    break
                if decision.action == "escalate_host":
                    final_action = "escalate_host"
                    end_reason = "escalated"
                    break
                # rerun_aider
                if turns_remaining <= 0:
                    final_action = "escalate_host"
                    end_reason = "max_turns_reached"
                    break
                correction = self._correction_note(checks, result)

            outcome = self._resolve_outcome(final_action, last_result)
            return self._finish(
                outcome=outcome,
                turns_completed=turns_completed,
                final_action=final_action,
                end_reason=end_reason,
                executor_result=last_result,
                decisions=decisions,
            )
        finally:
            # Logging invariant: exactly one loop_end per delegation that started.
            if self._loop_start_emitted and not self._loop_end_emitted:
                self._emit_loop_end(
                    turns_completed=turns_completed,
                    final_action=final_action,
                    end_reason=end_reason or "aborted",
                )

    # ── host-driven (manual) API ─────────────────────────────────────────────
    #
    # When the MCP server already owns the heavy executor/reviewer plumbing it can
    # drive the loop turn-by-turn while letting the agent own event emission and the
    # inter-turn decision:
    #
    #   agent.begin()
    #   while True:
    #       turn = agent.begin_turn()
    #       result = <run worker>            # turn>1 uses agent.last_correction()
    #       checks = <run reviewer>
    #       decision = agent.complete_turn(result, checks)
    #       if decision.action != "rerun_aider" or not agent.can_rerun():
    #           break
    #   final = agent.finish()

    def begin(self) -> None:
        self._emit_loop_start()

    def begin_turn(self) -> int:
        self._cur_turn += 1
        self._turn_t0 = time.perf_counter()
        self._emit_turn_start(self._cur_turn)
        return self._cur_turn

    def can_rerun(self) -> bool:
        """True when at least one more turn is allowed after the current one."""
        return self._cur_turn < self._max_turns

    def complete_turn(
        self, result: ExecutionResult, checks: dict[str, Any] | None = None
    ) -> SupervisorTurnDecision:
        duration_ms = (
            int((time.perf_counter() - self._turn_t0) * 1000)
            if self._turn_t0 is not None
            else 0
        )
        self._emit_turn_end(
            self._cur_turn,
            worker_outcome=self._worker_outcome(result),
            checks_result=checks,
            duration_ms=duration_ms,
        )
        self._last_result = result
        decision = self._decide(
            SupervisorTurnContext(
                turn_index=self._cur_turn,
                max_turns=self._max_turns,
                turns_remaining=self._max_turns - self._cur_turn,
                result=result,
                checks=checks,
                prior_decisions=list(self._decisions),
            )
        )
        self._decisions.append(decision)
        self._emit_decision(self._cur_turn, decision)
        return decision

    def correction_note(self, checks: dict[str, Any] | None) -> str:
        return self._correction_note(checks, self._last_result or ExecutionResult(False, ""))

    def finish(self) -> SupervisorAgentResult:
        """Close a host-driven loop, deriving the final outcome from recorded turns."""
        last_decision = self._decisions[-1] if self._decisions else None
        result = self._last_result
        if last_decision is None:
            final_action, end_reason = "done", "no_turns"
        elif last_decision.action == "escalate_host":
            final_action, end_reason = "escalate_host", "escalated"
        elif last_decision.action == "rerun_aider":
            # Loop ended on a rerun request → turns exhausted.
            final_action, end_reason = "escalate_host", "max_turns_reached"
        else:
            final_action = "done"
            end_reason = self._success_end_reason(result) if result else "completed"
        outcome = self._resolve_outcome(final_action, result)
        return self._finish(
            outcome=outcome,
            turns_completed=self._cur_turn,
            final_action=final_action,
            end_reason=end_reason,
            executor_result=result,
            decisions=list(self._decisions),
        )

    # ── decision logic ──────────────────────────────────────────────────────

    def _decide(self, ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        if self._decision_fn is not None:
            return self._decision_fn(ctx)
        if self._max_turns == 1:
            return self._policy_decide(ctx)
        return self._llm_decide(ctx)

    def _policy_decide(self, ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        """Cheap, deterministic decision used for single-turn delegations."""
        result = ctx.result
        checks = ctx.checks or {}
        if (
            ctx.turns_remaining > 0
            and str(checks.get("outcome") or "") == "issues"
        ):
            return SupervisorTurnDecision(
                action="rerun_aider",
                reason=str(checks.get("note") or "reviewer found issues")[:200],
            )
        if result.success:
            return SupervisorTurnDecision(action="done", reason="quality sufficient")
        return SupervisorTurnDecision(
            action="done",
            reason=str(result.error or result.error_class or "executor finished")[:200],
        )

    def _llm_decide(self, ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
        """LLM-backed inter-turn decision. Falls back to policy on any failure."""
        try:
            from core.config.providers import apply_provider_env
            from core.config.models import provider_hint_for_model
            from core.config.role_models import ROLE_SUPERVISOR, resolve_role_model_name
            from core.engine.owned_helper_llm import run_owned_helper_completion

            apply_provider_env()
            model = self._supervisor_model or resolve_role_model_name(
                ROLE_SUPERVISOR, self._workspace_path
            )
            if provider_hint_for_model(model):
                return self._policy_decide(ctx)

            prompt = self._build_decision_prompt(ctx)
            t0 = time.perf_counter()
            completion = run_owned_helper_completion(
                [{"role": "user", "content": prompt}], model=model
            )
            duration_ms = completion.duration_ms or int((time.perf_counter() - t0) * 1000)
            if completion.error:
                fallback = self._policy_decide(ctx)
                fallback.model = model
                fallback.duration_ms = duration_ms
                return fallback
            action = _parse_decision_action(completion.text)
            if action is None:
                fallback = self._policy_decide(ctx)
                fallback.model = model
                fallback.duration_ms = duration_ms
                return fallback
            reason = _parse_decision_reason(completion.text) or f"supervisor {action}"
            return SupervisorTurnDecision(
                action=action,
                reason=reason,
                model=model,
                tokens=completion.tokens or {},
                duration_ms=duration_ms,
            )
        except Exception:
            return self._policy_decide(ctx)

    def _build_decision_prompt(self, ctx: SupervisorTurnContext) -> str:
        result = ctx.result
        checks = ctx.checks or {}
        prior = ctx.prior_decisions[-3:]
        prior_lines = (
            "\n".join(f"- [{d.action}] {d.reason}" for d in prior) if prior else "(none)"
        )
        files = ", ".join((result.files_changed or [])[:20]) or "(none)"
        tail = (result.output or "")[-800:]
        sections = [
            _DECISION_PREAMBLE,
            f"## Turn\n{ctx.turn_index} of {ctx.max_turns} (remaining: {ctx.turns_remaining})",
            f"## Worker outcome\n{self._worker_outcome(result)}",
            f"## Files changed\n{files}",
            f"## Checks\noutcome={checks.get('outcome') or 'none'}; note={str(checks.get('note') or '')[:300]}",
            f"## Prior decisions\n{prior_lines}",
            f"## Worker output tail\n{tail}",
        ]
        return "\n\n".join(sections)

    @staticmethod
    def _correction_note(checks: dict[str, Any] | None, result: ExecutionResult) -> str:
        c = checks or {}
        note = str(c.get("note") or "").strip()
        if note:
            return (
                "A previous attempt left issues that must be fixed:\n"
                f"{note}\n"
                "Address them precisely without expanding scope beyond the spec."
            )
        return (
            "A previous attempt did not fully satisfy the spec. "
            "Review your changes and complete the remaining work without expanding scope."
        )

    @staticmethod
    def _worker_outcome(result: ExecutionResult) -> str:
        if result.success:
            return "success"
        return str(result.error_class or "failure")

    @staticmethod
    def _success_end_reason(result: ExecutionResult) -> str:
        if result.success:
            return "completed"
        return str(result.error_class or "executor_error")

    @staticmethod
    def _resolve_outcome(
        final_action: str, result: ExecutionResult | None
    ) -> SupervisorOutcome:
        if final_action == "escalate_host":
            return "escalated"
        if result is not None and result.success:
            return "success"
        return "error"

    # ── event emission ───────────────────────────────────────────────────────

    def _finish(
        self,
        *,
        outcome: SupervisorOutcome,
        turns_completed: int,
        final_action: str,
        end_reason: str,
        executor_result: ExecutionResult | None,
        decisions: list[SupervisorTurnDecision],
    ) -> SupervisorAgentResult:
        self._emit_loop_end(
            turns_completed=turns_completed,
            final_action=final_action,
            end_reason=end_reason,
        )
        return SupervisorAgentResult(
            outcome=outcome,
            turns_completed=turns_completed,
            final_action=final_action,
            end_reason=end_reason,
            executor_result=executor_result,
            decisions=decisions,
            loop_id=self._loop_id,
        )

    def context_block(self, result: SupervisorAgentResult) -> dict[str, Any]:
        """Delegation-record block describing the agent loop (replaces supervisor_outer_loop)."""
        return {
            "loop_id": self._loop_id,
            "turns_completed": result.turns_completed,
            "final_action": result.final_action,
            "end_reason": result.end_reason,
        }

    def _emit_loop_start(self) -> None:
        self._loop_start_emitted = True
        self._emit(
            {
                "type": "supervisor_loop_start",
                "loop_id": self._loop_id,
                "max_turns": self._max_turns,
            }
        )

    def _emit_turn_start(self, turn_index: int) -> None:
        self._emit(
            {
                "type": "supervisor_turn_start",
                "loop_id": self._loop_id,
                "turn_index": turn_index,
            }
        )

    def _emit_turn_end(
        self,
        turn_index: int,
        *,
        worker_outcome: str,
        checks_result: dict[str, Any] | None,
        duration_ms: int,
    ) -> None:
        self._emit(
            {
                "type": "supervisor_turn_end",
                "loop_id": self._loop_id,
                "turn_index": turn_index,
                "worker_outcome": worker_outcome,
                "checks_result": checks_result,
                "duration_ms": duration_ms,
            }
        )

    def _emit_decision(self, turn_index: int, decision: SupervisorTurnDecision) -> None:
        self._emit(
            {
                "type": "supervisor_decision",
                "loop_id": self._loop_id,
                "turn_index": turn_index,
                "action": decision.action,
                "reason": decision.reason,
                "model": decision.model,
                "tokens": decision.tokens,
                "duration_ms": decision.duration_ms,
            }
        )

    def _emit_loop_end(
        self, *, turns_completed: int, final_action: str, end_reason: str
    ) -> None:
        if self._loop_end_emitted:
            return
        self._loop_end_emitted = True
        self._emit(
            {
                "type": "supervisor_loop_end",
                "loop_id": self._loop_id,
                "turns_completed": turns_completed,
                "final_action": final_action,
                "end_reason": end_reason,
            }
        )

    def _emit(self, record: dict[str, Any]) -> None:
        record.setdefault("delegation_id", self._delegation_id)
        try:
            from core.logging.server_log import utc_now_iso

            record.setdefault("timestamp", utc_now_iso())
        except Exception:
            pass
        if self._event_sink is not None:
            try:
                self._event_sink(record)
            except Exception:
                pass
            return
        try:
            from core.observability.context import (
                delegation_id_var,
                session_dir_var,
                workspace_var,
            )
            from core.observability.trace import append_trace_record

            delegation_id = self._delegation_id or delegation_id_var.get()
            session_dir = session_dir_var.get()
            workspace = workspace_var.get()
            if not delegation_id or not session_dir:
                return
            append_trace_record(
                record,
                delegation_id=delegation_id,
                session_dir=session_dir,
                workspace=workspace or "",
            )
        except Exception:
            pass  # observability must never break delegations
