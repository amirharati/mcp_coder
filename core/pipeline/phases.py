"""Pipeline phase recorder for implement delegations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

_STATUS_VALUES = {"ok", "skipped", "error", "blocked"}


@dataclass
class PipelinePhase:
    phase: str
    status: str
    duration_ms: int
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "phase": self.phase,
            "status": self.status,
            "duration_ms": self.duration_ms,
        }
        if self.detail:
            data["detail"] = self.detail
        return data


class PipelineRecorder:
    """Collect ordered pipeline phases with coarse timing."""

    def __init__(self) -> None:
        self._phases: list[PipelinePhase] = []
        self._started_at: dict[str, float] = {}

    def start(self, phase: str) -> None:
        self._started_at[phase] = time.perf_counter()

    def end(
        self,
        phase: str,
        *,
        status: str = "ok",
        detail: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        if status not in _STATUS_VALUES:
            raise ValueError(f"invalid phase status: {status}")
        if duration_ms is None:
            started = self._started_at.pop(phase, None)
            if started is None:
                duration_ms = 0
            else:
                duration_ms = int((time.perf_counter() - started) * 1000)
        else:
            self._started_at.pop(phase, None)
        self._phases.append(
            PipelinePhase(
                phase=phase,
                status=status,
                duration_ms=max(0, int(duration_ms)),
                detail=detail,
            )
        )

    def mark(
        self,
        phase: str,
        *,
        status: str,
        detail: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        self.end(phase, status=status, detail=detail, duration_ms=duration_ms)

    def to_list(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._phases]
