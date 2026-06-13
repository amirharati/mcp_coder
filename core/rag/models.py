from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WorkspaceFileIndexRow:
    path: str
    sha256: str
    llm_summary: str | None
    symbol_list: str | None
    searchable_text: str
    indexed_at: str


@dataclass
class WorkspaceFileHit:
    path: str
    score: float
    sha256: str | None
    llm_summary: str | None
    symbol_list: str | None
    indexed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "score": round(self.score, 4),
            "sha256": self.sha256,
            "llm_summary": self.llm_summary,
            "symbol_list": self.symbol_list,
            "indexed_at": self.indexed_at,
        }


@dataclass
class DelegationIndexRow:
    delegation_id: str
    workspace_path: str
    timestamp_end: str | None
    spec_path: str | None
    spec_report_path: str | None
    checkpoint_summary: str | None
    task_preview: str | None
    delegate_mode: str | None
    outcome: str | None
    files_changed: str | None
    searchable_text: str


@dataclass
class SearchHit:
    delegation_id: str
    score: float
    checkpoint_summary: str | None
    spec_path: str | None
    outcome: str | None
    timestamp_end: str | None
    files_changed: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "score": round(self.score, 4),
            "checkpoint_summary": self.checkpoint_summary,
            "spec_path": self.spec_path,
            "outcome": self.outcome,
            "timestamp_end": self.timestamp_end,
            "files_changed": self.files_changed,
        }
