from __future__ import annotations

import os
import time
from pathlib import Path


def host_tie_window_sec() -> float:
    raw = os.environ.get("MCP_CODER_HOST_TIE_WINDOW_SEC", "10").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 10.0


def pick_host_session_id(
    candidates: list[tuple[str, Path]],
    delegation_activity: dict[str, float],
    *,
    now: float | None = None,
    tie_window_sec: float | None = None,
) -> tuple[str | None, str]:
    """
    Choose host_session_id from transcript candidates.

    Returns (host_session_id, host_resolve_method).
    """
    if not candidates:
        return None, "none"

    now = now if now is not None else time.time()
    window = host_tie_window_sec() if tie_window_sec is None else tie_window_sec

    scored: list[tuple[str, Path, float, float, float]] = []
    for host_id, path in candidates:
        t_transcript = path.stat().st_mtime
        t_delegation = delegation_activity.get(host_id, 0.0)
        activity = max(t_transcript, t_delegation)
        scored.append((host_id, path, t_transcript, t_delegation, activity))

    recent = [row for row in scored if now - row[4] <= window]

    if len(recent) == 1:
        return recent[0][0], "score_window_single"

    if len(recent) > 1:
        recent.sort(key=lambda r: (r[3], r[2], r[4]), reverse=True)
        return recent[0][0], "score_window_multi"

    method = "mtime_only" if not delegation_activity else "score_global"
    best = max(scored, key=lambda r: (r[4], r[3], r[2]))
    return best[0], method
