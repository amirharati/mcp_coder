"""In-process question registry for the mid-run human gate (P11-004)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

_GATE_TIMEOUT_S: float = 120.0


@dataclass
class PendingQuestion:
    delegation_id: str
    question: str
    event: threading.Event = field(default_factory=threading.Event)
    answer: str | None = None


class QuestionRegistry:
    """Thread-safe store of pending human-gate questions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingQuestion] = {}

    def post(self, delegation_id: str, question: str) -> PendingQuestion:
        """Register a new pending question and return the PendingQuestion handle."""
        pq = PendingQuestion(delegation_id=delegation_id, question=question)
        with self._lock:
            self._pending[delegation_id] = pq
        return pq

    def answer(self, delegation_id: str, answer: str) -> bool:
        """Set the answer and fire the event. Returns True if delegation was found."""
        with self._lock:
            pq = self._pending.get(delegation_id)
        if pq is None:
            return False
        pq.answer = answer
        pq.event.set()
        return True

    def pop(self, delegation_id: str) -> None:
        """Remove the entry (call after delegation ends)."""
        with self._lock:
            self._pending.pop(delegation_id, None)

    def get(self, delegation_id: str) -> PendingQuestion | None:
        with self._lock:
            return self._pending.get(delegation_id)


# Module-level singleton — imported by both supervised_io.py and mcp_server.py.
_REGISTRY = QuestionRegistry()
