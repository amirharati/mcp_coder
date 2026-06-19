"""Smart architect-pass trigger heuristic (P11-006)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ARCH_KEYWORDS = (
    "refactor",
    "redesign",
    "introduce",
    "migrate",
    "new module",
    "integrate",
)

REASON_RUN = "run"
REASON_SPEC_OVERRIDE_TRUE = "spec_override_true"
REASON_SPEC_OVERRIDE_FALSE = "spec_override_false"
REASON_ENV_DISABLED = "env_disabled"
REASON_HEURISTIC_TRIVIAL = "heuristic_trivial_task"


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    return None


def _spec_front_matter(spec_read: Any | None) -> dict[str, Any]:
    if spec_read is None:
        return {}
    meta = getattr(spec_read, "meta", None)
    if isinstance(meta, dict):
        return meta
    front_matter = getattr(spec_read, "front_matter", None)
    if isinstance(front_matter, dict):
        return front_matter
    return {}


def _spec_front_matter_bool(spec_read: Any | None, key: str) -> bool | None:
    return _parse_bool(_spec_front_matter(spec_read).get(key))


def _spec_epic_step(spec_read: Any | None) -> bool:
    return _spec_front_matter_bool(spec_read, "epic_step") is True


def _task_has_arch_keywords(task: str) -> bool:
    lower = (task or "").lower()
    return any(keyword in lower for keyword in ARCH_KEYWORDS)


def _env_architect_disabled() -> bool:
    """Check both canonical and legacy env vars for explicit disable."""
    canonical = os.environ.get("MCP_CODER_PLANNER_PASS", "").strip()
    if canonical:
        return _parse_bool(canonical) is False
    legacy = os.environ.get("MCP_CODER_ARCHITECT_PASS", "").strip()
    if legacy:
        return _parse_bool(legacy) is False
    return False


def _spec_override_planner(spec_read: Any | None) -> bool | None:
    """Check canonical planner_pass key, then fall back to legacy architect_pass key."""
    canonical = _spec_front_matter_bool(spec_read, "planner_pass")
    if canonical is not None:
        return canonical
    return _spec_front_matter_bool(spec_read, "architect_pass")


def should_run_architect_pass(
    *,
    workspace: str | Path,
    task: str,
    target_files: list[str],
    spec_read: Any | None,
) -> tuple[bool, str]:
    """Return (should_run, reason).

    reason is one of:
    run | spec_override_true | spec_override_false | env_disabled | heuristic_trivial_task

    Checks canonical spec key `planner_pass` first, then legacy `architect_pass`.
    """
    _ = workspace  # reserved for future workspace-level policy hooks

    spec_override = _spec_override_planner(spec_read)
    if spec_override is True:
        return True, REASON_SPEC_OVERRIDE_TRUE
    if spec_override is False:
        return False, REASON_SPEC_OVERRIDE_FALSE

    if _env_architect_disabled():
        return False, REASON_ENV_DISABLED

    if (
        len(target_files) < 2
        and not _spec_epic_step(spec_read)
        and not _task_has_arch_keywords(task)
    ):
        return False, REASON_HEURISTIC_TRIVIAL

    return True, REASON_RUN
