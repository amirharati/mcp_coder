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

import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, cast

from core.engine.base import ExecutionResult
from core.state.supervisor_state import SupervisorState

logger = logging.getLogger(__name__)

SupervisorAction = Literal["rerun_aider", "done", "escalate_host"]
SupervisorOutcome = Literal["success", "escalated", "error"]

# Worker: given (turn_index, correction_note, reset_session) produce an ExecutionResult.
ExecutorFn = Callable[[int, "str | None", bool], ExecutionResult]
# Checks: given (turn_index, result) produce a compact check summary (or None).
ReviewerFn = Callable[[int, ExecutionResult], "dict[str, Any] | None"]
# Event sink: receives each canonical trace record (used by tests / custom routing).
EventSink = Callable[["dict[str, Any]"], None]


def _normalize_executor_fn(executor_fn: Callable[..., ExecutionResult]) -> ExecutorFn:
    """Accept legacy 2-arg executor callables and adapt to the 3-arg contract."""
    try:
        params = list(inspect.signature(executor_fn).parameters.values())
    except (TypeError, ValueError):
        return cast(ExecutorFn, executor_fn)
    has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
    positional = [
        p
        for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if has_varargs or len(positional) >= 3:
        return cast(ExecutorFn, executor_fn)
    if len(positional) == 2:
        legacy_fn = cast(Callable[[int, str | None], ExecutionResult], executor_fn)

        def _wrapped_executor(
            turn_index: int,
            correction_note: str | None,
            _reset_session: bool,
        ) -> ExecutionResult:
            return legacy_fn(turn_index, correction_note)

        return _wrapped_executor
    return cast(ExecutorFn, executor_fn)


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
    resume_token: str | None = None
    paused_questions: list[str] = field(default_factory=list)
    completed_turn_artifacts: list[dict] = field(default_factory=list)


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


def _resolve_session_reset_every() -> int:
    """Reset executor session every N turns. 0/unset = never. Env-only for v1."""
    import os

    raw = os.environ.get("MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY", "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


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
        spec_path: str | None = None,
        plan: str | None = None,
    ) -> None:
        self._delegation_id = delegation_id
        self._workspace_path = workspace_path
        self._spec_path = spec_path
        self._executor_fn = _normalize_executor_fn(executor_fn)
        self._reviewer_fn = reviewer_fn
        self._decision_fn = decision_fn
        self._max_turns = max(1, int(max_turns))
        self._event_sink = event_sink
        self._supervisor_model = supervisor_model
        self._plan = plan
        self._loop_id = f"{delegation_id}:supervisor:1" if delegation_id else "supervisor:1"
        self._loop_start_emitted = False
        self._loop_end_emitted = False
        # Host-driven (manual) mode state — see begin()/begin_turn()/complete_turn()/finish().
        self._cur_turn = 0
        self._turn_t0: float | None = None
        self._decisions: list[SupervisorTurnDecision] = []
        self._last_result: ExecutionResult | None = None
        self._completed_turn_artifacts: list[dict] = []
        self._pending_host_clarification: str | None = None
        self._project_state: Any | None = None
        self._project_state_trace_enabled = False
        self._resumed_from_pause: bool = False
        # P13-005: shared lifecycle context (persisted to SupervisorState on escalation)
        self._lifecycle_context: dict[str, Any] = {}
        self._lifecycle_phases: dict[str, str] = {}  # phase → status
        self._lifecycle_started: bool = False  # P13-006: envelope started by set_lifecycle_context/emit_lifecycle_start
        # P13-008: True once emit_lifecycle_end has fired for the current envelope.
        # Subsequent emit_lifecycle_end / emit_lifecycle_phase_* calls become no-ops
        # (with a warning) — the per-delegation envelope is single-shot. Reset to
        # False in begin_delegation() so the same agent instance (registry cache hit)
        # can open a fresh envelope on the next delegation.
        self._lifecycle_closed: bool = False
        # P13-007: True when this agent was rehydrated from an AgentCheckpoint
        # (post-restart / CLI mode). Identity + lifecycle context restored, but
        # _lifecycle_started stays False — the next delegation emits a fresh
        # lifecycle_start(resumed=False). The checkpoint is history, not an
        # open envelope.
        self._resumed_from_checkpoint: bool = False

    @property
    def loop_id(self) -> str:
        return self._loop_id

    @property
    def max_turns(self) -> int:
        return self._max_turns

    def set_plan(self, plan: str | None) -> None:
        self._plan = plan

    # P13-006: late-binding setters so the server can create the agent early
    # (before delegation_id / event_sink / spec_path are known) and wire them
    # in once the session is acquired. This lets the agent own the lifecycle
    # envelope from the very first event, before preloop work begins.
    def set_delegation_id(self, delegation_id: str | None) -> None:
        self._delegation_id = delegation_id
        self._loop_id = (
            f"{delegation_id}:supervisor:1" if delegation_id else "supervisor:1"
        )

    def set_lifecycle_event_sink(self, sink: EventSink | None) -> None:
        self._event_sink = sink

    def set_spec_path(self, spec_path: str | None) -> None:
        self._spec_path = spec_path

    # P13-007: rehydrate steady-state identity + lifecycle context from a
    # checkpoint saved at the end of the previous delegation. Called by
    # _get_or_create_supervisor() when the in-memory registry misses (fresh
    # process, post-restart, or CLI invocation). Restores identity + lifecycle
    # position but NOT _lifecycle_started — the next delegation must emit a
    # fresh lifecycle_start(resumed=False). The checkpoint is history, not an
    # open envelope.
    def rehydrate_from(self, checkpoint: "object") -> None:
        from core.state.agent_checkpoint import AgentCheckpoint

        if not isinstance(checkpoint, AgentCheckpoint):
            return
        self._lifecycle_context = dict(checkpoint.lifecycle_context)
        self._lifecycle_context.setdefault("project_key", checkpoint.project_key)
        # Deliberately do NOT set _lifecycle_started=True. A new delegation
        # emits a fresh envelope; the checkpoint is prior history.
        self._resumed_from_checkpoint = True
        # P13-007: emit a trace event so dogfood traces can confirm rehydration
        # happened (observability for the CLI ≡ server invariant). Best-effort:
        # the sink may not be wired yet at rehydrate time (server creates agent
        # before setting sink); in that case the event is silently dropped.
        self._emit(
            {
                "type": "agent_rehydrated",
                "project_key": checkpoint.project_key,
                "last_delegation_id": checkpoint.last_delegation_id,
                "last_outcome": checkpoint.last_outcome,
                "last_finished_at": checkpoint.last_finished_at,
            }
        )

    def begin_delegation(
        self,
        *,
        delegation_id: str | None,
        executor_fn: ExecutorFn,
        reviewer_fn: ReviewerFn | None = None,
        decision_fn: DecisionFn | None = None,
        max_turns: int = 1,
        event_sink: EventSink | None = None,
        supervisor_model: str | None = None,
        spec_path: str | None = None,
        plan: str | None = None,
    ) -> None:
        """Reset per-delegation state. Call before begin() for each new delegation.

        Keeps cross-delegation state intact: _project_state, _workspace_path.
        """
        self._delegation_id = delegation_id
        self._executor_fn = _normalize_executor_fn(executor_fn)
        self._reviewer_fn = reviewer_fn
        self._decision_fn = decision_fn
        self._max_turns = max(1, int(max_turns))
        self._event_sink = event_sink
        self._supervisor_model = supervisor_model
        self._plan = plan
        self._spec_path = spec_path
        self._loop_id = f"{delegation_id}:supervisor:1" if delegation_id else "supervisor:1"
        self._loop_start_emitted = False
        self._loop_end_emitted = False
        self._cur_turn = 0
        self._turn_t0 = None
        self._decisions = []
        self._last_result = None
        self._completed_turn_artifacts = []
        self._pending_host_clarification = None
        self._resumed_from_pause = False
        # Reset so begin() re-enables it when spec_path is not None.
        self._project_state_trace_enabled = False
        # _project_state and _workspace_path are intentionally preserved.
        # P13-005: reset lifecycle tracking per delegation.
        # P13-006: but preserve context that was set before preloop (lifecycle_start +
        # phase_start(preloop) already emitted by the server's early agent creation).
        # If the caller already started the envelope (via set_lifecycle_context /
        # emit_lifecycle_start), keep it; otherwise reset to a clean slate.
        if not self._lifecycle_started:
            self._lifecycle_context = {}
            self._lifecycle_phases = {}
        # P13-008: a fresh delegation opens a fresh envelope — clear the closed
        # flag even when the caller pre-populated lifecycle context (the prior
        # delegation's close must not poison this one).
        self._lifecycle_closed = False

    @classmethod
    def resume(
        cls,
        state: SupervisorState,
        host_answer: str,
        *,
        workspace_path: str,
        executor_fn: ExecutorFn,
        reviewer_fn: ReviewerFn | None = None,
        event_sink: EventSink | None = None,
    ) -> "SupervisorAgent":
        agent = cls(
            delegation_id=state.context_ref,
            workspace_path=workspace_path,
            executor_fn=executor_fn,
            reviewer_fn=reviewer_fn,
            max_turns=max(1, int(state.turn_index) + 1),
            event_sink=event_sink,
            spec_path=state.spec_path,
            plan=state.plan,
        )
        agent._cur_turn = int(state.turn_index)
        agent._decisions = [agent._decision_from_dict(item) for item in state.decision_log]
        agent._completed_turn_artifacts = list(state.completed_turn_artifacts or [])
        from core.state.project_state import ProjectState

        agent._project_state = ProjectState.load(state.project_key)
        agent._project_state_trace_enabled = True
        answer = (host_answer or "").strip()
        if answer:
            agent._pending_host_clarification = f"## Host clarification\n{answer}"
        agent._resumed_from_pause = True
        # P13-005: restore lifecycle context from persisted state
        agent._lifecycle_context = dict(state.lifecycle_context or {})
        agent._lifecycle_context.setdefault("project_key", state.project_key)
        # P13-005: emit coherent lifecycle envelope for resumed path (preloop already done)
        # Order: lifecycle_start → phase_start(loop) → supervisor_resumed → project_state_loaded
        agent.emit_lifecycle_start(resumed=True)
        agent.emit_lifecycle_phase_start("loop", resumed=True)
        agent._emit(
            {
                "type": "supervisor_resumed",
                "resume_token": state.resume_token,
                "resumed_at_turn": state.turn_index,
                "project_key": state.project_key,
                "host_answer_chars": len(host_answer or ""),
            }
        )
        agent._emit_project_state_loaded(state.project_key)
        return agent

    # ── public API ─────────────────────────────────────────────────────────

    # P13-006: delegate() and resume_and_delegate() are the canonical ownership
    # entry points. Today the server still wires workers (executor/reviewer) and
    # drives the loop turn-by-turn for implement mode, so these methods are thin
    # markers that emit the lifecycle envelope the agent owns. They exist so a
    # future refactor can move the orchestration body behind them without
    # changing the public surface. Callers may use begin_delegation()/run()
    # directly; these wrappers are for code that wants to signal "the agent
    # owns this delegation" explicitly.
    def delegate(
        self,
        *,
        delegation_id: str,
        executor_fn: ExecutorFn,
        reviewer_fn: ReviewerFn | None = None,
        max_turns: int = 1,
        event_sink: EventSink | None = None,
        spec_path: str | None = None,
        plan: str | None = None,
    ) -> None:
        """Agent-owned delegation entry point.

        Emits the lifecycle envelope (lifecycle_start + phase_start(preloop))
        the agent owns, then delegates to begin_delegation() for state setup.
        The server's delegate_to_agent() is the thin caller of this method.
        """
        if self._delegation_id is None or self._delegation_id != delegation_id:
            self.set_delegation_id(delegation_id)
        if event_sink is not None:
            self.set_lifecycle_event_sink(event_sink)
        if spec_path is not None:
            self.set_spec_path(spec_path)
        # Only emit if not already emitted by an earlier set_lifecycle_context path.
        if not self._lifecycle_phases:
            self.emit_lifecycle_start(resumed=False)
            self.emit_lifecycle_phase_start("preloop", resumed=False)
        self.begin_delegation(
            delegation_id=delegation_id,
            executor_fn=executor_fn,
            reviewer_fn=reviewer_fn,
            max_turns=max_turns,
            event_sink=event_sink,
            spec_path=spec_path,
            plan=plan,
        )

    @classmethod
    def resume_and_delegate(
        cls,
        state: SupervisorState,
        host_answer: str,
        *,
        workspace_path: str,
        executor_fn: ExecutorFn,
        reviewer_fn: ReviewerFn | None = None,
        event_sink: EventSink | None = None,
    ) -> "SupervisorAgent":
        """Agent-owned resume entry point (thin alias for resume()).

        resume() already emits lifecycle_start(resumed=True) + phase_start(loop,
        resumed=True). This alias exists so callers can signal "the agent owns
        the resumed delegation" without coupling to the internal resume() name.
        """
        return cls.resume(
            state,
            host_answer,
            workspace_path=workspace_path,
            executor_fn=executor_fn,
            reviewer_fn=reviewer_fn,
            event_sink=event_sink,
        )

    def run(self) -> SupervisorAgentResult:
        """Drive the supervisor loop to completion and return the final outcome."""
        decisions: list[SupervisorTurnDecision] = list(self._decisions)
        last_result: ExecutionResult | None = None
        final_action = "done"
        end_reason = "completed"
        turns_completed = int(self._cur_turn)

        self.begin()
        try:
            correction: str | None = self._consume_host_clarification()
            for turn_index in range(self._cur_turn + 1, self._max_turns + 1):
                turns_completed = turn_index
                t0 = time.perf_counter()
                self._emit_turn_start(turn_index)
                resumed_first_turn = bool(
                    self._resumed_from_pause and turn_index == self._cur_turn + 1
                )
                reset_session = self._should_reset_executor_session(turn_index)
                if reset_session:
                    self._emit(
                        {
                            "type": "supervisor_session_reset",
                            "turn_index": turn_index,
                            "reason": (
                                "resumed_first_turn" if resumed_first_turn else "interval"
                            ),
                        }
                    )

                try:
                    result = self._executor_fn(turn_index, correction, reset_session)
                except Exception as exc:  # worker blew up — close loop cleanly
                    if resumed_first_turn:
                        self._resumed_from_pause = False
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

                if resumed_first_turn:
                    self._resumed_from_pause = False
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
                self._record_turn_artifact(result)

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
                correction = self._merge_correction_with_clarification(
                    self._correction_note(checks, result)
                )

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
        from core.state.project_key import ProjectKeyResolver
        from core.state.project_state import ProjectState

        if self._project_state is None:
            project_key = ProjectKeyResolver.from_spec_path(self._spec_path)
            self._project_state = ProjectState.load(project_key)
            # Keep existing event-order assertions stable for callers that do not
            # provide spec_path, while still emitting the new trace for spec-driven flows.
            if self._spec_path is not None:
                self._project_state_trace_enabled = True
                self._emit_project_state_loaded(project_key)
        if not self._loop_start_emitted:
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
        self._record_turn_artifact(result)
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
        note = self._correction_note(checks, self._last_result or ExecutionResult(False, ""))
        return self._merge_correction_with_clarification(note)

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
            from core.engine.supervisor_tool_runner import build_phase12_tool_runner
            from core.state.project_key import ProjectKeyResolver

            apply_provider_env()
            model = self._supervisor_model or resolve_role_model_name(
                ROLE_SUPERVISOR, self._workspace_path
            )
            if provider_hint_for_model(model):
                return self._policy_decide(ctx)

            prompt = self._build_decision_prompt(ctx)
            t0 = time.perf_counter()
            runner = build_phase12_tool_runner(
                workspace_path=str(self._workspace_path),
                project_key=ProjectKeyResolver.from_spec_path(self._spec_path),
                project_state=self._project_state,
                event_sink=self._event_sink,
                model=model,
            )
            tool_result = runner.run_with_metrics(
                system_prompt=_DECISION_PREAMBLE,
                messages=[{"role": "user", "content": prompt}],
            )
            text = tool_result.text
            duration_ms = int((time.perf_counter() - t0) * 1000)
            action = _parse_decision_action(text)
            if action is None:
                fallback = self._policy_decide(ctx)
                fallback.model = model
                fallback.duration_ms = duration_ms
                return fallback
            reason = _parse_decision_reason(text) or f"supervisor {action}"
            return SupervisorTurnDecision(
                action=action,
                reason=reason,
                model=model,
                tokens=tool_result.tokens,
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
            f"## Planner plan\n{(self._plan or '(none)')[:1200]}",
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
        resume_token: str | None = None
        paused_questions: list[str] = []
        if outcome == "escalated":
            pause_reason = "max_turns_reached" if end_reason == "max_turns_reached" else "needs_input"
            paused_questions = self._paused_questions(executor_result, decisions)
            # P13-005: include lifecycle context so resume can restore lifecycle position
            _lc_for_state = dict(self._lifecycle_context)
            _lc_for_state["phases_completed"] = [
                phase for phase, status in self._lifecycle_phases.items()
                if status not in ("in_progress",)
            ]
            state = SupervisorState.create(
                spec_path=self._spec_path,
                context_ref=self._delegation_id or self._loop_id,
                plan=self._plan,
                decision_log=[asdict(item) for item in decisions],
                completed_turn_artifacts=list(self._completed_turn_artifacts),
                turn_index=turns_completed,
                questions=list(paused_questions),
                pause_reason=pause_reason,
                lifecycle_context=_lc_for_state,
            )
            state.save()
            resume_token = state.resume_token
            self._emit(
                {
                    "type": "supervisor_paused",
                    "resume_token": state.resume_token,
                    "turn_index": state.turn_index,
                    "pause_reason": state.pause_reason,
                    "questions": state.questions,
                    "expires_at": state.expires_at,
                }
            )
        self._emit_loop_end(
            turns_completed=turns_completed,
            final_action=final_action,
            end_reason=end_reason,
        )
        if self._project_state is not None:
            files_changed: list[str] = []
            if executor_result is not None and executor_result.files_changed:
                files_changed = list(executor_result.files_changed)
            self._project_state.update_hot_areas(files_changed)
            delegation_id = self._delegation_id or ""
            if delegation_id:
                self._project_state.last_delegation = delegation_id
            added_decisions = 0
            added_risks = 0
            saved_path = self._project_state.save()
            if self._project_state_trace_enabled:
                self._emit(
                    {
                        "type": "project_state_saved",
                        "project_key": self._project_state.project_key,
                        "hot_areas_updated": len(files_changed),
                        "decisions_added": added_decisions,
                        "risks_added": added_risks,
                        "file_path": str(saved_path),
                    }
                )
        # P13-007: checkpoint the agent's steady-state identity + lifecycle
        # position at the end of EVERY delegation (success / error / escalated).
        # This is what makes the agent genuinely stateful across restarts —
        # _get_or_create_supervisor() rehydrates from this file when the
        # in-memory registry misses. Distinct from SupervisorState (which is
        # escalation-only, expiring, intra-delegation resume).
        self._save_agent_checkpoint(outcome=outcome)
        return SupervisorAgentResult(
            outcome=outcome,
            turns_completed=turns_completed,
            final_action=final_action,
            end_reason=end_reason,
            executor_result=executor_result,
            decisions=decisions,
            loop_id=self._loop_id,
            resume_token=resume_token,
            paused_questions=paused_questions,
            completed_turn_artifacts=list(self._completed_turn_artifacts),
        )

    def _save_agent_checkpoint(self, *, outcome: str) -> None:
        """P13-007: write AgentCheckpoint (steady-state, non-expiring) to disk.

        Called from _finish() for every outcome (success / error / escalated).
        Best-effort: never raises — a checkpoint failure must not fail the
        delegation. Emits an additive `agent_checkpoint_saved` trace event.
        """
        try:
            from core.state.agent_checkpoint import AgentCheckpoint, utc_now_iso
            from core.state.project_key import ProjectKeyResolver

            project_key = self._lifecycle_context.get("project_key") or (
                ProjectKeyResolver.from_spec_path(self._spec_path)
                if self._spec_path
                else ""
            )
            if not project_key:
                # No project_key resolvable — skip checkpoint (can't namespace it).
                return
            # Build phases_completed summary (mirror P13-005 SupervisorState logic)
            lc_for_checkpoint = dict(self._lifecycle_context)
            lc_for_checkpoint["phases_completed"] = [
                phase
                for phase, status in self._lifecycle_phases.items()
                if status not in ("in_progress",)
            ]
            checkpoint = AgentCheckpoint(
                project_key=project_key,
                last_delegation_id=self._delegation_id,
                last_outcome=outcome,
                last_spec_path=self._spec_path,
                last_finished_at=utc_now_iso(),
                lifecycle_context=lc_for_checkpoint,
            )
            saved_path = checkpoint.save()
            self._emit(
                {
                    "type": "agent_checkpoint_saved",
                    "project_key": project_key,
                    "last_delegation_id": self._delegation_id,
                    "last_outcome": outcome,
                    "file_path": str(saved_path),
                }
            )
        except Exception as exc:
            # Best-effort: log + emit warning, never fail the delegation.
            logger.warning("Agent checkpoint save failed: %s", exc)
            self._emit(
                {
                    "type": "agent_checkpoint_save_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    def context_block(self, result: SupervisorAgentResult) -> dict[str, Any]:
        """Delegation-record block describing the agent loop (replaces supervisor_outer_loop)."""
        return {
            "loop_id": self._loop_id,
            "turns_completed": result.turns_completed,
            "final_action": result.final_action,
            "end_reason": result.end_reason,
        }

    # ── P13-005: lifecycle envelope public API ───────────────────────────────
    # Used by the server (regular path) and by resume() (resume path).
    # In the regular path the server calls set_lifecycle_context() +
    # update_reviewer_pass_result() so the context is persisted on escalation;
    # the emit_* methods are used by the resume path and by tests.

    def set_lifecycle_context(
        self,
        *,
        project_key: str = "",
        session_policy: str = "",
        session_action: str = "",
        mcp_session_id: str = "",
    ) -> None:
        """Store lifecycle metadata for traces and pause/resume persistence."""
        self._lifecycle_context.update(
            {
                "project_key": project_key,
                "session_policy": session_policy,
                "session_action": session_action,
                "mcp_session_id": mcp_session_id,
            }
        )
        self._lifecycle_started = True  # P13-006: caller started the envelope

    def update_reviewer_pass_result(self, result: str) -> None:
        """Record latest reviewer pass result in lifecycle context."""
        self._lifecycle_context["reviewer_pass_result"] = result

    def emit_lifecycle_start(self, *, resumed: bool = False) -> None:
        """Emit delegation_lifecycle_start event (additive envelope, P13-005)."""
        self._lifecycle_started = True  # P13-006: envelope started
        self._emit(
            {
                "type": "delegation_lifecycle_start",
                "project_key": self._lifecycle_context.get("project_key", ""),
                "spec_path": self._spec_path,
                "session_policy": self._lifecycle_context.get("session_policy", ""),
                "session_action": self._lifecycle_context.get("session_action", ""),
                "mcp_session_id": self._lifecycle_context.get("mcp_session_id", ""),
                "resumed": resumed,
            }
        )

    def emit_lifecycle_phase_start(self, phase: str, *, resumed: bool = False) -> None:
        """Emit delegation_phase_start event (additive envelope, P13-005)."""
        if self._lifecycle_closed:
            # P13-008: envelope already closed — a phase event here is a bug
            # (e.g. an early-close branch fell through to the postloop block).
            # No-op + warn rather than emit a stray event that breaks the
            # single-envelope-per-delegation invariant.
            logger.warning(
                "emit_lifecycle_phase_start(%s) called after lifecycle envelope "
                "already closed; ignoring.", phase,
            )
            return
        self._lifecycle_phases[phase] = "in_progress"
        self._emit(
            {
                "type": "delegation_phase_start",
                "project_key": self._lifecycle_context.get("project_key", ""),
                "phase": phase,
                "resumed": resumed,
            }
        )

    def emit_lifecycle_phase_end(
        self, phase: str, *, status: str = "ok", detail: str | None = None
    ) -> None:
        """Emit delegation_phase_end event (additive envelope, P13-005)."""
        if self._lifecycle_closed:
            # P13-008: see emit_lifecycle_phase_start.
            logger.warning(
                "emit_lifecycle_phase_end(%s) called after lifecycle envelope "
                "already closed; ignoring.", phase,
            )
            return
        self._lifecycle_phases[phase] = status
        rec: dict[str, Any] = {
            "type": "delegation_phase_end",
            "project_key": self._lifecycle_context.get("project_key", ""),
            "phase": phase,
            "status": status,
        }
        if detail is not None:
            rec["detail"] = detail
        self._emit(rec)

    def emit_lifecycle_end(self, outcome: str) -> None:
        """Emit delegation_lifecycle_end event (additive envelope, P13-005).

        P13-008: idempotent — the per-delegation envelope closes exactly once.
        A second call (e.g. from an early-close branch that fell through to the
        postloop block) is a no-op with a warning, rather than emitting a stray
        second ``delegation_lifecycle_end`` that would break the
        single-envelope-per-delegation invariant and corrupt checkpoint
        ``phases_completed``.
        """
        if self._lifecycle_closed:
            logger.warning(
                "emit_lifecycle_end(%s) called after lifecycle envelope already "
                "closed; ignoring (previous outcome was emitted).", outcome,
            )
            return
        self._lifecycle_closed = True
        self._emit(
            {
                "type": "delegation_lifecycle_end",
                "project_key": self._lifecycle_context.get("project_key", ""),
                "outcome": outcome,
                "phase_summary": dict(self._lifecycle_phases),
                "reviewer_pass_result": self._lifecycle_context.get(
                    "reviewer_pass_result"
                ),
            }
        )

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

    def _emit_project_state_loaded(self, project_key: str) -> None:
        from core.state.project_state import ProjectState

        state = self._project_state
        if state is None:
            return
        self._emit(
            {
                "type": "project_state_loaded",
                "project_key": project_key,
                "decisions_count": len(state.decisions),
                "open_risks_count": len(state.open_risks),
                "hot_areas_count": len(state.hot_areas),
                "file_path": str(ProjectState.state_path(project_key)),
            }
        )

    def _record_turn_artifact(self, result: ExecutionResult) -> None:
        self._completed_turn_artifacts.append(
            {
                "files_changed": list(result.files_changed or []),
                "output_tail": (result.output or "")[-500:],
            }
        )

    def _merge_correction_with_clarification(self, note: str) -> str:
        clarification = self._consume_host_clarification()
        if not clarification:
            return note
        if not note:
            return clarification
        return f"{clarification}\n\n{note}"

    def _consume_host_clarification(self) -> str | None:
        text = self._pending_host_clarification
        self._pending_host_clarification = None
        return text

    @staticmethod
    def _decision_from_dict(raw: dict[str, Any]) -> SupervisorTurnDecision:
        action_raw = str(raw.get("action") or "done")
        action: SupervisorAction
        if action_raw == "rerun_aider":
            action = "rerun_aider"
        elif action_raw == "escalate_host":
            action = "escalate_host"
        else:
            action = "done"
        return SupervisorTurnDecision(
            action=action,
            reason=str(raw.get("reason") or ""),
            model=str(raw.get("model") or ""),
            tokens=dict(raw.get("tokens") or {}),
            duration_ms=int(raw.get("duration_ms") or 0),
        )

    @staticmethod
    def _paused_questions(
        result: ExecutionResult | None, decisions: list[SupervisorTurnDecision]
    ) -> list[str]:
        if result is None:
            return [decisions[-1].reason] if decisions and decisions[-1].reason else []
        questions: list[str] = []
        lines = [line.strip() for line in (result.output or "").splitlines() if line.strip()]
        for line in lines:
            if line.endswith("?"):
                questions.append(line)
        if not questions and result.error and result.error.strip():
            questions.append(result.error.strip())
        if not questions and decisions and decisions[-1].reason.strip():
            questions.append(decisions[-1].reason.strip())
        return questions[:5]

    def _should_reset_executor_session(self, turn_index: int) -> bool:
        """Decide whether the executor session should be reset before this turn.

        Backend-neutral: returns a boolean intent. The caller's executor_fn decides
        how to honor it (e.g. drop a cached Aider Coder). Reasons:
        - First turn of a resumed delegation: the cached session predates the pause
          and is stale.
        - Every N turns when MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY is set (drift bound).
        Richer adaptation policy is deferred to a later phase (BL-546).
        """
        if self._resumed_from_pause and turn_index == self._cur_turn + 1:
            # _cur_turn is the resumed-at turn; the next turn is the first new one.
            return True
        every = _resolve_session_reset_every()
        if every > 0 and turn_index > 1 and (turn_index - 1) % every == 0:
            return True
        return False
