"""Supervised Aider InputOutput (P11-002). Routes confirm_ask to DelegationSupervisor."""

from __future__ import annotations

import io
import re
from collections.abc import Callable
from typing import Any

from core.config.aider_runtime import STALL_OUTPUT_TAIL_CHARS, _executor_output_tail
from core.engine.supervisor import DelegationSupervisor, SupervisorDecision

_PATH_RE = re.compile(
    r"[`'\"]?((?:[\w./-]+/)?[\w./-]+\.[\w]+)[`'\"]?",
    re.IGNORECASE,
)

_SHELL_MARKERS = (
    "shell command",
    "run this command",
    "execute command",
    "terminal",
    "subprocess",
    "npm ",
    "pip ",
    "yarn ",
    "cargo ",
    "make ",
    "pytest ",
    "python -m",
    "bash ",
    "sh -c",
)

_DELETE_MARKERS = (
    "delete ",
    "remove ",
    "rm -",
    "rmdir",
    "unlink ",
)

_LOW_RISK_MARKERS = (
    "apply",
    "edit",
    "update",
    "modify",
    "write",
    "change",
    "patch",
)

# Aider's confirm_ask when loading a file into chat context (e.g. "Add file to the chat?",
# "Add `core/foo.py` to the chat?"). Generic without a path = always low-risk (just read
# context). With a specific path: only low-risk if the path is in the allowed set.
_FILE_TO_CHAT_RE = re.compile(r"\badd\b.*\bto\s+the\s+chat\b", re.IGNORECASE)


class SupervisorAbort(Exception):
    """Raised when supervisor decides abort or escalate."""

    def __init__(
        self,
        *,
        reasoning: str,
        decision: str,
        question: str,
        decisions_count: int,
        aborts_count: int,
        decisions: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(reasoning)
        self.reasoning = reasoning
        self.decision = decision
        self.question = question
        self.decisions_count = decisions_count
        self.aborts_count = aborts_count
        self.decisions = list(decisions or [])


def classify_confirm_risk(
    question: str,
    *,
    target_files: set[str],
    contract_paths: set[str],
) -> str:
    """Deterministic v1 risk tier: low | high | unknown."""
    q = (question or "").strip()
    lower = q.lower()
    allowed = target_files | contract_paths

    if any(marker in lower for marker in _DELETE_MARKERS):
        return "high"
    if any(marker in lower for marker in _SHELL_MARKERS):
        return "high"

    mentioned = _extract_paths(q)
    if mentioned:
        for path in mentioned:
            normalized = path.replace("\\", "/").lstrip("./")
            if allowed and normalized not in allowed:
                if any(tok in lower for tok in ("add", "create", "new file", "include")):
                    return "high"

    # "Add file to the chat?" / "Add `core/foo.py` to the chat?" — Aider loads read context.
    # If no specific path is mentioned, it's unconditionally low-risk. If a specific path is
    # mentioned and it's in the allowed set, also low-risk. Out-of-spec file already caught
    # by the high-risk branch above.
    if _FILE_TO_CHAT_RE.search(q):
        if not mentioned or all(
            p.replace("\\", "/").lstrip("./") in allowed for p in mentioned
        ):
            return "low"

    if any(marker in lower for marker in _LOW_RISK_MARKERS):
        if mentioned and all(p.replace("\\", "/").lstrip("./") in allowed for p in mentioned):
            return "low"
        if not mentioned and allowed:
            return "low"

    return "unknown"


def _extract_paths(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _PATH_RE.finditer(text):
        path = match.group(1).replace("\\", "/").lstrip("./")
        if path and path not in seen:
            seen.add(path)
            found.append(path)
    return found


class SupervisedIO:
    """Aider InputOutput subclass with supervisor-backed confirm_ask."""

    def __init__(
        self,
        *,
        output: io.StringIO,
        supervisor: DelegationSupervisor,
        target_files: set[str],
        contract_paths: set[str],
        on_decision: Callable[[dict[str, Any]], None] | None = None,
        question_registry: "QuestionRegistry | None" = None,
        delegation_id: str | None = None,
        emit_loop_events: bool = True,
    ) -> None:
        from aider.io import InputOutput

        self._inner = InputOutput(
            pretty=False,
            yes=False,
            fancy_input=False,
            output=output,
        )
        self._supervisor = supervisor
        self._target_files = target_files
        self._contract_paths = contract_paths
        self._on_decision = on_decision
        self._question_registry = question_registry
        self._delegation_id = delegation_id
        # P12-001: the unified SupervisorAgent now owns the supervisor_loop_* lifecycle.
        # When driven by SupervisorAgent (real flow), aider_engine sets this False so the
        # loop envelope is emitted exactly once (by the agent). Kept True by default so
        # SupervisedIO remains self-contained for direct/unit use.
        self._emit_loop_events = emit_loop_events
        self._loop_started = False
        self._loop_id = f"{delegation_id}:supervisor:1" if delegation_id else None
        self._loop_start_emitted = False
        self._loop_end_emitted = False
        self._loop_end_reason: str | None = None
        self.supervisor_decisions: list[dict[str, Any]] = []
        self.supervisor_decisions_count = 0
        self.supervisor_aborts_count = 0
        self.num_error_outputs = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _output_tail(self) -> str:
        buf = getattr(self._inner, "output", None)
        if buf is None:
            return ""
        try:
            text = buf.getvalue() if hasattr(buf, "getvalue") else str(buf)
        except Exception:
            text = ""
        return _executor_output_tail(text, max_chars=STALL_OUTPUT_TAIL_CHARS)

    def _human_gate_enabled(self) -> bool:
        return self._question_registry is not None and bool(self._delegation_id)

    def _emit_gate_event(
        self,
        event_type: str,
        *,
        question: str,
        risk_tier: str,
        answer: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        """Emit typed human gate trace events (P11-ISS-004)."""
        try:
            from core.observability.context import (
                delegation_id_var,
                session_dir_var,
                workspace_var,
            )
            from core.observability.trace import append_trace_record
            from core.logging.server_log import utc_now_iso

            delegation_id = delegation_id_var.get()
            session_dir = session_dir_var.get()
            workspace = workspace_var.get()
            if not delegation_id or not session_dir:
                return
            record: dict[str, Any] = {
                "type": event_type,
                "delegation_id": delegation_id,
                "risk_tier": risk_tier,
                "question_preview": question[:120],
                "timestamp": utc_now_iso(),
            }
            if answer is not None:
                record["answer_preview"] = answer
            if timeout_s is not None:
                record["timeout_s"] = timeout_s
            append_trace_record(
                record,
                delegation_id=delegation_id,
                session_dir=session_dir,
                workspace=workspace or "",
            )
        except Exception:
            pass  # observability must never break completions

    def _emit_supervisor_loop_event(
        self,
        event_type: str,
        *,
        end_reason: str | None = None,
        final_decision: str | None = None,
    ) -> None:
        """Emit explicit supervisor loop lifecycle envelope events."""
        if not self._emit_loop_events:
            return  # SupervisorAgent owns the loop lifecycle in the real flow (P12-001).
        try:
            from core.observability.context import (
                delegation_id_var,
                session_dir_var,
                workspace_var,
            )
            from core.observability.trace import append_trace_record
            from core.logging.server_log import utc_now_iso

            delegation_id = delegation_id_var.get()
            session_dir = session_dir_var.get()
            workspace = workspace_var.get()
            if not delegation_id or not session_dir:
                return
            record: dict[str, Any] = {
                "type": event_type,
                "delegation_id": delegation_id,
                "loop_id": self._loop_id,
                "turn_count": self.supervisor_decisions_count,
                "aborts_count": self.supervisor_aborts_count,
                "timestamp": utc_now_iso(),
            }
            if end_reason:
                record["end_reason"] = end_reason
            if final_decision:
                record["final_decision"] = final_decision
            append_trace_record(
                record,
                delegation_id=delegation_id,
                session_dir=session_dir,
                workspace=workspace or "",
            )
        except Exception:
            pass

    def _ensure_supervisor_loop_started(self) -> None:
        if self._loop_started:
            return
        self._loop_started = True
        if self._emit_loop_events:
            self._loop_start_emitted = True
        self._emit_supervisor_loop_event("supervisor_loop_start")

    def begin_supervisor_loop(self) -> None:
        """Public wrapper so caller can emit loop start before first prompt."""
        self._ensure_supervisor_loop_started()

    def finalize_supervisor_loop(self, *, end_reason: str, final_decision: str | None = None) -> None:
        """Best-effort loop closure emission (safe to call multiple times)."""
        if not self._loop_started:
            return
        if self._emit_loop_events:
            self._loop_end_emitted = True
        self._loop_end_reason = end_reason
        self._emit_supervisor_loop_event(
            "supervisor_loop_end",
            end_reason=end_reason,
            final_decision=final_decision,
        )
        self._loop_started = False

    @staticmethod
    def _human_answer_to_bool(answer: str | None) -> bool:
        """Treat 'yes'/'y'/'true'/'1' (case-insensitive) as True, everything else as False."""
        if answer is None:
            return False
        return answer.strip().lower() in ("yes", "y", "true", "1")

    def _record_decision(
        self,
        *,
        question: str,
        decision: SupervisorDecision | None,
        decision_name: str,
        reasoning: str,
        risk_tier: str,
        duration_ms: int,
    ) -> None:
        row = {
            "question": question[:500],
            "decision": decision_name,
            "reasoning": reasoning[:400],
            "risk_tier": risk_tier,
            "duration_ms": duration_ms,
        }
        self.supervisor_decisions.append(row)
        self.supervisor_decisions_count += 1
        if decision_name in ("abort", "escalate"):
            self.supervisor_aborts_count += 1
        if self._on_decision is not None:
            self._on_decision(row)
        # P11-ISS-016: structured turn-level decision event.
        try:
            from core.observability.context import (
                delegation_id_var,
                session_dir_var,
                workspace_var,
            )
            from core.observability.trace import append_trace_record
            from core.logging.server_log import utc_now_iso

            delegation_id = delegation_id_var.get()
            session_dir = session_dir_var.get()
            workspace = workspace_var.get()
            if delegation_id and session_dir:
                turn_rec = {
                    "type": "supervisor_turn_decision",
                    "delegation_id": delegation_id,
                    "loop_id": self._loop_id,
                    "turn_index": self.supervisor_decisions_count,
                    "action": decision_name,
                    "reason": reasoning[:200],
                    "risk_level": risk_tier,
                    "question_present": bool(question.strip()),
                    "llm_used": decision_name not in ("approve",),
                    "duration_ms": duration_ms,
                    "timestamp": utc_now_iso(),
                }
                append_trace_record(
                    turn_rec,
                    delegation_id=delegation_id,
                    session_dir=session_dir,
                    workspace=workspace or "",
                )
        except Exception:
            pass

    def confirm_ask(
        self,
        question: str,
        default: bool | None = None,
        subject: str | None = None,
        explicit_yes_required: bool = False,
        group: object = None,
        allow_never: bool = False,
    ) -> bool:
        del default, subject, explicit_yes_required, group, allow_never  # supervised path ignores these
        self._ensure_supervisor_loop_started()
        risk_tier = classify_confirm_risk(
            question,
            target_files=self._target_files,
            contract_paths=self._contract_paths,
        )

        if risk_tier == "low":
            self._record_decision(
                question=question,
                decision=None,
                decision_name="approve",
                reasoning="auto_approve_low_risk",
                risk_tier=risk_tier,
                duration_ms=0,
            )
            return True

        result = self._supervisor.evaluate(question=question, risk_tier=risk_tier)
        self._record_decision(
            question=question,
            decision=result,
            decision_name=result.decision,
            reasoning=result.reasoning,
            risk_tier=risk_tier,
            duration_ms=result.duration_ms,
        )

        if result.decision == "approve":
            return True
        if result.decision == "deny":
            return False
        if result.decision == "escalate" and self._human_gate_enabled():
            assert self._question_registry is not None
            assert self._delegation_id is not None
            pq = self._question_registry.post(self._delegation_id, question)

            if self._on_decision is not None:
                self._on_decision(
                    {
                        "question": question[:500],
                        "decision": "human_gate_opened",
                        "reasoning": "awaiting_human_answer",
                        "risk_tier": risk_tier,
                        "duration_ms": result.duration_ms,
                    }
                )
            self._emit_gate_event("human_gate_opened", question=question, risk_tier=risk_tier)

            from core.engine.question_registry import _GATE_TIMEOUT_S

            answered = pq.event.wait(timeout=_GATE_TIMEOUT_S)
            self._question_registry.pop(self._delegation_id)

            if answered:
                human_bool = self._human_answer_to_bool(pq.answer)
                self._record_decision(
                    question=question,
                    decision=None,
                    decision_name="human_gate_answered",
                    reasoning=f"human_answered: {str(pq.answer)[:80]}",
                    risk_tier=risk_tier,
                    duration_ms=result.duration_ms,
                )
                self._emit_gate_event(
                    "human_gate_answered",
                    question=question,
                    risk_tier=risk_tier,
                    answer=str(pq.answer)[:80],
                )
                return human_bool

            self._record_decision(
                question=question,
                decision=None,
                decision_name="human_gate_timeout",
                reasoning="human_gate_timeout_120s",
                risk_tier=risk_tier,
                duration_ms=result.duration_ms,
            )
            self._emit_gate_event(
                "human_gate_timeout",
                question=question,
                risk_tier=risk_tier,
                timeout_s=_GATE_TIMEOUT_S,
            )
            self.finalize_supervisor_loop(end_reason="human_gate_timeout", final_decision="abort")
            raise SupervisorAbort(
                reasoning="human_gate_timeout",
                decision="abort",
                question=question,
                decisions_count=self.supervisor_decisions_count,
                aborts_count=self.supervisor_aborts_count,
                decisions=self.supervisor_decisions,
            )

        self.finalize_supervisor_loop(
            end_reason=result.decision,
            final_decision=result.decision,
        )
        raise SupervisorAbort(
            reasoning=result.reasoning,
            decision=result.decision,
            question=question,
            decisions_count=self.supervisor_decisions_count,
            aborts_count=self.supervisor_aborts_count,
            decisions=self.supervisor_decisions,
        )
