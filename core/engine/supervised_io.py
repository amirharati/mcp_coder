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

    def confirm_ask(
        self,
        question: str,
        default: bool | None = None,
        subject: str | None = None,
    ) -> bool:
        del default, subject  # supervised path ignores defaults
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
        raise SupervisorAbort(
            reasoning=result.reasoning,
            decision=result.decision,
            question=question,
            decisions_count=self.supervisor_decisions_count,
            aborts_count=self.supervisor_aborts_count,
            decisions=self.supervisor_decisions,
        )
