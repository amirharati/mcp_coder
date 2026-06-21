from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.storage.paths import mcp_coder_home

logger = logging.getLogger(__name__)

_RISK_SEVERITIES = {"advisory", "notable", "critical"}
_FINDINGS_SUMMARY_MAX = 50


class ProjectStateCorrupt(Exception):
    pass


@dataclass
class ProjectState:
    version: int = 1
    project_key: str = ""
    decisions: list[dict] = field(default_factory=list)
    open_risks: list[dict] = field(default_factory=list)
    hot_areas: list[str] = field(default_factory=list)
    reviewer_findings_summary: list[dict] = field(default_factory=list)
    last_delegation: str | None = None
    last_updated: str | None = None

    @classmethod
    def load(cls, project_key: str) -> "ProjectState":
        path = cls.state_path(project_key)
        if not path.is_file():
            return cls(project_key=project_key)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ProjectStateCorrupt("Top-level JSON must be an object")
            return cls(
                version=int(raw.get("version", 1)),
                project_key=str(raw.get("project_key") or project_key),
                decisions=list(raw.get("decisions") or []),
                open_risks=list(raw.get("open_risks") or []),
                hot_areas=list(raw.get("hot_areas") or []),
                reviewer_findings_summary=list(raw.get("reviewer_findings_summary") or []),
                last_delegation=(
                    str(raw.get("last_delegation"))
                    if raw.get("last_delegation") is not None
                    else None
                ),
                last_updated=(
                    str(raw.get("last_updated"))
                    if raw.get("last_updated") is not None
                    else None
                ),
            )
        except json.JSONDecodeError as exc:
            corrupt = ProjectStateCorrupt(f"Invalid JSON in {path}: {exc}")
            logger.warning("ProjectStateCorrupt: %s", corrupt)
            return cls(project_key=project_key)
        except (TypeError, ValueError, ProjectStateCorrupt) as exc:
            corrupt = exc if isinstance(exc, ProjectStateCorrupt) else ProjectStateCorrupt(str(exc))
            logger.warning("ProjectStateCorrupt: %s", corrupt)
            return cls(project_key=project_key)

    def save(self) -> Path:
        path = self.state_path(self.project_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.last_updated = _utc_now_iso()
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
        return path

    def add_decision(self, text: str, delegation_id: str) -> None:
        self.decisions.append(
            {
                "text": text,
                "delegation_id": delegation_id,
                "timestamp": _utc_now_iso(),
            }
        )

    def add_risk(
        self,
        text: str,
        severity: str,
        source_delegation_id: str,
    ) -> None:
        level = (severity or "").strip().lower()
        if level not in _RISK_SEVERITIES:
            level = "advisory"
        self.open_risks.append(
            {
                "text": text,
                "severity": level,
                "source_delegation_id": source_delegation_id,
                "timestamp": _utc_now_iso(),
            }
        )

    def add_reviewer_finding(
        self,
        text: str,
        severity: str,
        delegation_id: str,
        spec_path: str | None = None,
        files: list[str] | None = None,
    ) -> None:
        """Append to reviewer_findings_summary (bounded to _FINDINGS_SUMMARY_MAX)."""
        entry = {
            "text": text,
            "severity": severity,
            "delegation_id": delegation_id,
            "spec_path": spec_path or "",
            "files": list(files or [])[:10],
            "timestamp": _utc_now_iso(),
        }
        self.reviewer_findings_summary.append(entry)
        if len(self.reviewer_findings_summary) > _FINDINGS_SUMMARY_MAX:
            self.reviewer_findings_summary = self.reviewer_findings_summary[-_FINDINGS_SUMMARY_MAX:]

    def update_hot_areas(self, files_changed: list[str]) -> None:
        max_items = _resolve_hot_areas_max()
        merged: list[str] = []
        seen: set[str] = set()
        for path in list(files_changed or []) + list(self.hot_areas or []):
            cleaned = str(path or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            merged.append(cleaned)
            if len(merged) >= max_items:
                break
        self.hot_areas = merged

    @staticmethod
    def state_path(project_key: str) -> Path:
        return mcp_coder_home() / "projects" / project_key / "project_state.json"


def _resolve_hot_areas_max() -> int:
    raw = os.environ.get("MCP_CODER_HOT_AREAS_MAX", "").strip()
    if not raw:
        return 50
    try:
        value = int(raw)
    except ValueError:
        return 50
    return value if value > 0 else 50


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
