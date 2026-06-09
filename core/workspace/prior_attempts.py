"""Query prior failed delegations for host summary hints (P4-008)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.logging.read_delegations import load_delegations
from core.specs.outcome import (
    OUTCOME_FAILED,
    OUTCOME_INVALID_SPEC,
    OUTCOME_NEEDS_INPUT,
    OUTCOME_REVIEW,
    OUTCOME_SCOPE_VIOLATION,
    OUTCOME_SUCCESS,
)
from core.specs.paths import normalize_spec_path_arg
from core.storage.paths import session_delegations_path
from core.workspace.history_query import list_delegations

_FAILED_OUTCOMES = frozenset(
    {
        OUTCOME_FAILED,
        OUTCOME_INVALID_SPEC,
        OUTCOME_SCOPE_VIOLATION,
        OUTCOME_NEEDS_INPUT,
    }
)
_SUCCESS_OUTCOMES = frozenset({OUTCOME_SUCCESS, OUTCOME_REVIEW, "partial", "delegated_ok"})

PRIOR_FAILED_ATTEMPTS_REMINDER = (
    "Earlier attempts failed for this step/session — cite each delegation_id and error "
    "in your summary before claiming success."
)


def _error_from_jsonl_record(record: dict[str, Any]) -> str | None:
    error = record.get("error")
    if error:
        return str(error)
    error_detail = record.get("error_detail") or {}
    message = error_detail.get("error_message")
    if message:
        return str(message)
    error_class = error_detail.get("error_class")
    if error_class:
        return str(error_class)
    outcome = record.get("outcome")
    if outcome:
        return str(outcome)
    return None


def _attempt_item_from_jsonl(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "delegation_id": str(record["delegation_id"]),
        "spec_path": record.get("spec_path"),
        "success": bool(record.get("success")),
        "error": _error_from_jsonl_record(record),
        "outcome": record.get("outcome"),
        "timestamp_end": record.get("timestamp_end"),
    }


def _error_from_history_row(row: dict[str, Any]) -> str | None:
    error_class = row.get("error_class")
    if error_class:
        return str(error_class)
    outcome = row.get("outcome")
    if outcome in _FAILED_OUTCOMES:
        return str(outcome)
    summary = row.get("checkpoint_summary")
    if summary:
        return str(summary)
    return None


def _attempt_item_from_history(row: dict[str, Any]) -> dict[str, Any]:
    outcome = row.get("outcome")
    return {
        "delegation_id": str(row["delegation_id"]),
        "spec_path": row.get("spec_path"),
        "success": outcome in _SUCCESS_OUTCOMES if outcome else False,
        "error": _error_from_history_row(row),
        "outcome": outcome,
        "timestamp_end": row.get("timestamp_end"),
    }


def _is_failed_jsonl_record(record: dict[str, Any]) -> bool:
    success = record.get("success")
    outcome = record.get("outcome")
    error_detail = record.get("error_detail") or {}
    if success is True and outcome in (OUTCOME_SUCCESS, OUTCOME_REVIEW):
        return False
    if success is False:
        return True
    if error_detail.get("error_class"):
        return True
    return outcome in _FAILED_OUTCOMES


def _is_failed_history_row(row: dict[str, Any]) -> bool:
    if row.get("error_class"):
        return True
    return row.get("outcome") in _FAILED_OUTCOMES


def _normalize_spec_path(spec_path: str | None) -> str | None:
    if not spec_path:
        return None
    try:
        return normalize_spec_path_arg(spec_path)
    except ValueError:
        return spec_path.strip().replace("\\", "/").lstrip("/")


def _merge_attempts(
    items: list[dict[str, Any]],
    *,
    exclude_delegation_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in sorted(
        items,
        key=lambda row: row.get("timestamp_end") or "",
        reverse=True,
    ):
        delegation_id = str(item["delegation_id"])
        if delegation_id == exclude_delegation_id or delegation_id in seen:
            continue
        seen.add(delegation_id)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _session_jsonl_attempts(
    workspace: str | Path,
    *,
    mcp_session_id: str | None,
) -> list[dict[str, Any]]:
    if not mcp_session_id:
        return []
    path = session_delegations_path(workspace, mcp_session_id)
    if not path.is_file():
        return []
    return [
        _attempt_item_from_jsonl(record)
        for record in load_delegations(path)
        if _is_failed_jsonl_record(record)
    ]


def _history_attempts(
    workspace: str | Path,
    *,
    spec_path: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    normalized = _normalize_spec_path(spec_path)
    if not normalized:
        return []
    rows = list_delegations(workspace, limit=limit, spec_path=normalized)
    return [
        _attempt_item_from_history(row)
        for row in rows
        if _is_failed_history_row(row)
    ]


def find_prior_failed_attempts(
    workspace: str | Path,
    *,
    spec_path: str | None,
    mcp_session_id: str | None,
    exclude_delegation_id: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return recent failed attempts for the same session and/or spec_path."""
    limit = max(1, min(limit, 5))
    items: list[dict[str, Any]] = []
    items.extend(
        _session_jsonl_attempts(workspace, mcp_session_id=mcp_session_id)
    )
    items.extend(
        _history_attempts(workspace, spec_path=spec_path, limit=limit)
    )
    return _merge_attempts(
        items,
        exclude_delegation_id=exclude_delegation_id,
        limit=limit,
    )
