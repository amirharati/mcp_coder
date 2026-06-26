"""P14-ISS-010: shared swallow-count counters for supervisor observability sites.

These module-level counters let a future health check surface
"N swallowed errors in the last delegation" without wiring up
contextvar-scoped state (v1 decision, see P14-ISS-FIX spec ambiguity table).

Two supervisors share the same dict (supervisor.py and supervisor_agent.py);
the keys disambiguate the site. Reset is the caller's responsibility — tests
call :func:`reset_supervisor_swallow_counts`; a future health-check should
snapshot + reset on delegation boundaries.
"""

from __future__ import annotations

_SUPERVISOR_SWALLOW_COUNTS: dict[str, int] = {}


def bump_supervisor_swallow_count(site: str) -> None:
    """Increment the swallow counter for a named site (e.g. ``_emit_llm_call_event``)."""
    _SUPERVISOR_SWALLOW_COUNTS[site] = _SUPERVISOR_SWALLOW_COUNTS.get(site, 0) + 1


def get_supervisor_swallow_counts() -> dict[str, int]:
    """Return a snapshot copy of the swallow counters (read-only for callers)."""
    return dict(_SUPERVISOR_SWALLOW_COUNTS)


def reset_supervisor_swallow_counts() -> None:
    """Clear all swallow counters (tests / future health-check delegation reset)."""
    _SUPERVISOR_SWALLOW_COUNTS.clear()
