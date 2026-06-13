"""In-memory session hot buffer for executor reasoning summaries (P6-004)."""

from __future__ import annotations

from dataclasses import dataclass

_SESSION_BUFFER: dict[str, list["ReasoningBufferEntry"]] = {}


@dataclass(frozen=True)
class ReasoningBufferEntry:
    delegation_id: str
    reasoning_summary: str


def record_session_reasoning(
    mcp_session_id: str,
    delegation_id: str,
    reasoning_summary: str,
    *,
    max_entries: int,
) -> None:
    """Append summary; trim to last max_entries for the session."""
    if not mcp_session_id or not reasoning_summary.strip():
        return
    entries = _SESSION_BUFFER.setdefault(mcp_session_id, [])
    entries.append(
        ReasoningBufferEntry(
            delegation_id=delegation_id,
            reasoning_summary=reasoning_summary,
        )
    )
    if max_entries > 0 and len(entries) > max_entries:
        del entries[: len(entries) - max_entries]


def get_prior_reasoning(
    mcp_session_id: str,
    *,
    exclude_delegation_id: str | None = None,
) -> list[ReasoningBufferEntry]:
    """Entries for builder injection (exclude current delegate)."""
    entries = list(_SESSION_BUFFER.get(mcp_session_id, []))
    if exclude_delegation_id:
        entries = [e for e in entries if e.delegation_id != exclude_delegation_id]
    return entries


def clear_session_reasoning(mcp_session_id: str) -> None:
    """Clear hot buffer for one session (tests)."""
    _SESSION_BUFFER.pop(mcp_session_id, None)


def clear_all_session_reasoning() -> None:
    """Clear all session buffers (tests)."""
    _SESSION_BUFFER.clear()
