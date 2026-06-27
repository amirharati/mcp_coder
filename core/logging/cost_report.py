"""Minimal per-project cost report from delegation logs (P15-004).

Pure read-and-aggregate: reads ``model_roles`` from every delegation JSONL
record, folds across delegations, and returns a structured report grouped by
model, role, and task (spec_path).  Zero new storage, zero LLM calls.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from core.logging.read_delegations import load_delegations_for_workspace


def build_project_cost_report(
    workspace: str | Path,
    *,
    project_key: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Aggregate cost data from delegation logs for a project.

    Reads all delegation JSONL records for the workspace, folds the
    ``model_roles`` field across delegations (optionally filtered to
    ``project_key``), and returns a structured cost report.

    Args:
        workspace: Workspace root path.
        project_key: If given, filter to delegations whose ``project_key``
            field matches this value. If None, aggregate ALL delegations.
        limit: If given, read only the most recent ``limit`` delegations.

    Returns:
        A dict with keys: ``project_key``, ``delegation_count``,
        ``total_usd``, ``by_model``, ``by_role``, ``by_task``,
        ``uncaptured_roles``, ``note``.

    Raises:
        FileNotFoundError: If no delegation logs exist for the workspace.
    """
    # --- Load records --------------------------------------------------
    try:
        records = load_delegations_for_workspace(str(workspace))
    except FileNotFoundError:
        return _zeroed_report(project_key or "all")

    # --- Filter --------------------------------------------------------
    if project_key is not None:
        records = [r for r in records if r.get("project_key") == project_key]

    if not records:
        return _zeroed_report(project_key or "all")

    if limit is not None and limit > 0:
        records = records[-limit:]

    # --- Accumulate ----------------------------------------------------
    # by_model[model] = {"input_tokens": int, "output_tokens": int, "cost_usd": float}
    by_model: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    )

    # by_role[role] = {"model": str, "calls": int, "cost_usd": float}
    by_role: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"model": "unknown", "calls": 0, "cost_usd": 0.0}
    )
    # Track the last-seen model for each role (v1 simple heuristic)
    last_model_for_role: dict[str, str] = {}

    # by_task[spec_path] = {"runs": int, "cost_usd": float}
    by_task_accum: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"runs": 0, "cost_usd": 0.0}
    )

    uncaptured: set[str] = set()
    delegation_count = len(records)

    for record in records:
        roles_dict = record.get("model_roles") or {}
        spec_path = record.get("spec_path")  # may be None

        # Count this delegation once per task (spec_path), regardless of how many roles
        # have data. Cost is accumulated per-role below.
        by_task_accum[spec_path]["runs"] += 1

        for role_name, entry in roles_dict.items():
            if not isinstance(entry, dict):
                continue

            model = entry.get("model", "unknown")
            tokens = entry.get("tokens", {})

            input_t = tokens.get("input") or 0
            output_t = tokens.get("output") or 0
            source = tokens.get("source", "unavailable")

            cost_est = entry.get("cost_est_usd", {})
            cost_total: float = (
                cost_est.get("total", 0.0)
                if isinstance(cost_est, dict)
                else 0.0
            )

            # --- per-role tracking ---
            role_stats = by_role[role_name]
            role_stats["calls"] += 1
            last_model_for_role[role_name] = model

            if source == "unavailable":
                uncaptured.add(role_name)
            else:
                role_stats["cost_usd"] += cost_total
                # --- per-model ---
                model_stats = by_model[model]
                model_stats["input_tokens"] += input_t
                model_stats["output_tokens"] += output_t
                model_stats["cost_usd"] += cost_total

                # --- per-task ---
                by_task_accum[spec_path]["cost_usd"] += cost_total

    # --- Finalise by_role model field ---
    for role_name in list(by_role.keys()):
        by_role[role_name]["model"] = last_model_for_role.get(role_name, "unknown")

    # --- Build by_task sorted list ---
    by_task_list: list[dict[str, Any]] = sorted(
        [
            {"spec_path": sp, "runs": v["runs"], "cost_usd": v["cost_usd"]}
            for sp, v in by_task_accum.items()
        ],
        key=lambda x: -x["cost_usd"],
    )

    # --- Total ---
    total_usd = sum(m["cost_usd"] for m in by_model.values())

    return {
        "project_key": project_key or "all",
        "delegation_count": delegation_count,
        "total_usd": total_usd,
        "by_model": dict(by_model),
        "by_role": dict(by_role),
        "by_task": by_task_list,
        "uncaptured_roles": sorted(uncaptured),
        "note": (
            "Executor tokens sourced via litellm_callback "
            "(best-effort; some runs may be incomplete)."
        ),
    }


def _zeroed_report(project_key: str) -> dict[str, Any]:
    return {
        "project_key": project_key,
        "delegation_count": 0,
        "total_usd": 0.0,
        "by_model": {},
        "by_role": {},
        "by_task": [],
        "uncaptured_roles": [],
        "note": "No delegation records found.",
    }
