"""Supervised Aider InputOutput (P11-002). Routes confirm_ask to DelegationSupervisor."""

from __future__ import annotations

import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

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


_ADD_CREATE_MARKERS = ("add", "create", "new file", "include")


@dataclass(frozen=True)
class InterceptClassification:
    """Result of structural confirm_ask classification (P14-002, BL-547 v1)."""

    classification: Literal["in_spec_approve", "out_of_scope_deny", "ambiguous_escalate"]
    decision: Literal["approve", "deny", "escalate"]
    reasoning: str
    mentioned_paths: list[str]
    llm_used: bool
    risk_tier: str  # original classify_confirm_risk tier (low/high/unknown)
    question_preview: str = ""  # question[:120]


def classify_for_interception(
    question: str,
    *,
    target_files: dict[str, list[str]],
    contract_paths: set[str],
) -> InterceptClassification:
    """Classify a confirm_ask question for structural interception.

    Composes the existing classify_confirm_risk (which needs a flat set) then
    maps to the three-category taxonomy with a conservative out-of-scope deny
    heuristic.
    """
    # Flatten target_files into a set for classify_confirm_risk compatibility.
    fe = set(target_files.get("files_edit") or [])
    fr = set(target_files.get("files_read") or [])
    tf_flat: set[str] = fe | fr

    q_preview = question[:120]
    risk_tier = classify_confirm_risk(
        question,
        target_files=tf_flat,
        contract_paths=contract_paths,
    )
    mentioned = _extract_paths(question)

    # --- in_spec_approve ---
    if risk_tier == "low":
        return InterceptClassification(
            classification="in_spec_approve",
            decision="approve",
            reasoning="auto_approve_low_risk",
            mentioned_paths=mentioned,
            llm_used=False,
            risk_tier=risk_tier,
            question_preview=q_preview,
        )

    # --- out_of_scope_deny heuristic (item 3) ---
    # Conditions:
    # 1. Spec is present.
    # 2. A specific file path is mentioned.
    # 3. Every mentioned path is out of spec.
    # 4. An add/create marker is present.
    # 5. No unsafe marker (delete/shell) is present.
    if risk_tier == "high" and mentioned:
        lower = question.lower()
        # Condition 5: no delete or shell markers.
        has_unsafe = any(m in lower for m in _DELETE_MARKERS) or any(
            m in lower for m in _SHELL_MARKERS
        )
        if not has_unsafe:
            # Condition 1: spec present.
            has_spec = bool(tf_flat) or bool(contract_paths)
            if has_spec:
                # Condition 3: every path out of spec.
                allowed = tf_flat | contract_paths
                all_out = all(
                    p.replace("\\", "/").lstrip("./") not in allowed for p in mentioned
                )
                if all_out:
                    # Condition 4: add/create marker.
                    has_add = any(tok in lower for tok in _ADD_CREATE_MARKERS)
                    if has_add:
                        return InterceptClassification(
                            classification="out_of_scope_deny",
                            decision="deny",
                            reasoning="file_not_in_spec",
                            mentioned_paths=mentioned,
                            llm_used=False,
                            risk_tier=risk_tier,
                            question_preview=q_preview,
                        )

    # --- ambiguous_escalate ---
    # Everything else: high-risk without structural deny match, or unknown.
    return InterceptClassification(
        classification="ambiguous_escalate",
        decision="escalate",
        reasoning=(
            "high_risk_marker_no_structural_deny"
            if risk_tier == "high"
            else "unclassified"
        ),
        mentioned_paths=mentioned,
        llm_used=True,
        risk_tier=risk_tier,
        question_preview=q_preview,
    )


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
        target_files_dict: dict[str, list[str]] | None = None,
        project_state_summary: str | None = None,
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
        self._target_files_dict = target_files_dict or {}
        self._project_state_summary = project_state_summary
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
        # P14-ISS-011: per-loop dedupe set for supervisor_turn_decision trace events.
        # The supervisor_decisions list + count above are the source of truth for
        # "how many turns happened"; only the trace event stream is deduped.
        self._emitted_decision_hashes: set[str] = set()
        self._suppressed_duplicate_decisions: int = 0

    @property
    def suppressed_duplicate_decisions(self) -> int:
        """Number of duplicate supervisor_turn_decision trace events suppressed (P14-ISS-011)."""
        return self._suppressed_duplicate_decisions

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

    def _build_context_ref(self) -> dict[str, Any]:
        """Build compact context_ref for supervisor_intercept trace records."""
        from core.context.summary import sha256_hex

        tf = self._target_files_dict
        fe = sorted(tf.get("files_edit") or [])
        fr = sorted(tf.get("files_read") or [])
        all_tf = sorted(fe + fr)
        tf_hash = sha256_hex("\n".join(all_tf)) if all_tf else None
        pss = self._project_state_summary or ""
        pss_hash = sha256_hex(pss) if pss else sha256_hex("")
        return {
            "target_files_edit_count": len(fe),
            "target_files_read_count": len(fr),
            "contract_paths_count": len(self._contract_paths),
            "target_files_hash": tf_hash,
            "project_state_summary_hash": pss_hash,
        }

    def _emit_supervisor_intercept(
        self,
        ic: InterceptClassification,
        *,
        llm_decision: str | None = None,
        llm_reasoning: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        """Emit supervisor_intercept trace event (P14-002, BL-547 v1)."""
        try:
            from core.observability.context import (
                delegation_id_var,
                session_dir_var,
                workspace_var,
            )
            from core.observability.trace import (
                build_supervisor_intercept_record,
                append_trace_record,
            )

            delegation_id = delegation_id_var.get()
            session_dir = session_dir_var.get()
            workspace = workspace_var.get()
            if not delegation_id or not session_dir:
                return
            decision = ic.decision
            reasoning = ic.reasoning
            if ic.classification == "ambiguous_escalate":
                decision = llm_decision or decision
                reasoning = (llm_reasoning or reasoning)[:200]
            record = build_supervisor_intercept_record(
                delegation_id=delegation_id,
                loop_id=self._loop_id,
                turn_index=self.supervisor_decisions_count + 1,
                classification=ic.classification,
                decision=decision,
                reasoning=reasoning,
                question_preview=ic.question_preview[:120] if hasattr(ic, "question_preview") else "",
                mentioned_paths=ic.mentioned_paths,
                context_ref=self._build_context_ref(),
                llm_used=ic.llm_used,
                duration_ms=duration_ms,
            )
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
        # P14-ISS-011: dedupe identical trace events within a loop. The
        # supervisor_decisions list + count above are the source of truth for
        # "how many turns happened" — only the trace event stream is deduped.
        try:
            from core.context.summary import sha256_hex
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
                dedupe_key = sha256_hex(
                    f"{decision_name}|{reasoning[:200]}|{risk_tier}|{bool(question.strip())}"
                )
                if dedupe_key in self._emitted_decision_hashes:
                    self._suppressed_duplicate_decisions += 1
                else:
                    self._emitted_decision_hashes.add(dedupe_key)
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

        ic = classify_for_interception(
            question,
            target_files=self._target_files_dict,
            contract_paths=self._contract_paths,
        )

        # --- in_spec_approve (no LLM) ---
        if ic.decision == "approve":
            self._emit_supervisor_intercept(ic, duration_ms=0)
            self._record_decision(
                question=question,
                decision=None,
                decision_name="approve",
                reasoning=ic.reasoning,
                risk_tier=ic.risk_tier,
                duration_ms=0,
            )
            return True

        # --- out_of_scope_deny (no LLM) ---
        if ic.decision == "deny":
            self._emit_supervisor_intercept(ic, duration_ms=0)
            self._record_decision(
                question=question,
                decision=None,
                decision_name="deny",
                reasoning=ic.reasoning,
                risk_tier=ic.risk_tier,
                duration_ms=0,
            )
            return False

        # --- ambiguous_escalate: route to LLM ---
        result = self._supervisor.evaluate(question=question, risk_tier=ic.risk_tier)

        # Emit intercept event with LLM's decision copied in.
        self._emit_supervisor_intercept(
            ic,
            llm_decision=result.decision,
            llm_reasoning=result.reasoning,
            duration_ms=result.duration_ms,
        )

        self._record_decision(
            question=question,
            decision=result,
            decision_name=result.decision,
            reasoning=result.reasoning,
            risk_tier=ic.risk_tier,
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
                        "risk_tier": ic.risk_tier,
                        "duration_ms": result.duration_ms,
                    }
                )
            self._emit_gate_event("human_gate_opened", question=question, risk_tier=ic.risk_tier)

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
                    risk_tier=ic.risk_tier,
                    duration_ms=result.duration_ms,
                )
                self._emit_gate_event(
                    "human_gate_answered",
                    question=question,
                    risk_tier=ic.risk_tier,
                    answer=str(pq.answer)[:80],
                )
                return human_bool

            self._record_decision(
                question=question,
                decision=None,
                decision_name="human_gate_timeout",
                reasoning="human_gate_timeout_120s",
                risk_tier=ic.risk_tier,
                duration_ms=result.duration_ms,
            )
            self._emit_gate_event(
                "human_gate_timeout",
                question=question,
                risk_tier=ic.risk_tier,
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
