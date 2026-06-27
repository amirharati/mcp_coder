"""Tests for per-project cost report aggregation (P15-004)."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from core.logging.cost_report import build_project_cost_report


def _make_delegation(
    project_key="proj-A",
    spec_path="tasks/T1.md",
    model_roles=None,
):
    return {
        "delegation_id": "test-id",
        "project_key": project_key,
        "spec_path": spec_path,
        "model_roles": model_roles or {},
    }


def _make_role(role, model, input_t, output_t, source="litellm_callback"):
    cost = input_t * 0.0000001 + output_t * 0.0000002  # synthetic rate
    return {
        "role": role,
        "model": model,
        "tokens": {
            "input": input_t,
            "output": output_t,
            "total": input_t + output_t,
            "source": source,
        },
        "cost_est_usd": {
            "input": input_t * 0.0000001,
            "output": output_t * 0.0000002,
            "total": cost,
        },
    }


# ---------------------------------------------------------------------------
# 1. Single delegation, two roles
# ---------------------------------------------------------------------------
def test_single_delegation_two_roles():
    exec_role = _make_role("executor", "openrouter/exec-model", 4200, 980)
    planner_role = _make_role("planner_pass", "openrouter/planner-model", 3100, 720)
    delegations = [
        _make_delegation(
            model_roles={"executor": exec_role, "planner_pass": planner_role}
        )
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=delegations,
    ):
        report = build_project_cost_report("/fake/ws")

    exec_cost = exec_role["cost_est_usd"]["total"]
    planner_cost = planner_role["cost_est_usd"]["total"]

    assert report["total_usd"] == pytest.approx(exec_cost + planner_cost)
    assert set(report["by_model"].keys()) == {
        "openrouter/exec-model",
        "openrouter/planner-model",
    }
    assert report["by_role"]["executor"]["calls"] == 1
    assert report["by_role"]["executor"]["cost_usd"] == pytest.approx(exec_cost)
    assert report["by_role"]["planner_pass"]["calls"] == 1
    assert report["by_role"]["planner_pass"]["cost_usd"] == pytest.approx(planner_cost)
    assert report["delegation_count"] == 1


# ---------------------------------------------------------------------------
# 2. Multi-delegation accumulates
# ---------------------------------------------------------------------------
def test_multi_delegation_accumulates():
    exec_role = _make_role("executor", "openrouter/exec-model", 1000, 500)
    three = [
        _make_delegation(
            spec_path="tasks/T1.md",
            model_roles={"executor": exec_role},
        )
        for _ in range(3)
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=three,
    ):
        report = build_project_cost_report("/fake/ws")

    single_cost = exec_role["cost_est_usd"]["total"]
    assert report["total_usd"] == pytest.approx(single_cost * 3)
    assert report["by_role"]["executor"]["calls"] == 3
    assert report["by_task"][0]["runs"] == 3
    assert report["by_task"][0]["cost_usd"] == pytest.approx(single_cost * 3)
    assert report["delegation_count"] == 3


# ---------------------------------------------------------------------------
# 3. unavailable source → zero cost, role in uncaptured_roles
# ---------------------------------------------------------------------------
def test_unavailable_source_zero_cost():
    exec_role = _make_role("executor", "openrouter/exec-model", 1000, 500, source="unavailable")
    delegations = [
        _make_delegation(model_roles={"executor": exec_role})
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=delegations,
    ):
        report = build_project_cost_report("/fake/ws")

    assert report["total_usd"] == 0.0
    assert "executor" in report["uncaptured_roles"]
    assert report["by_role"]["executor"]["calls"] == 1
    assert report["by_role"]["executor"]["cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# 4. Multi-model per delegation
# ---------------------------------------------------------------------------
def test_multi_model_per_delegation():
    exec_a = _make_role("executor", "openrouter/model-A", 100, 50)
    exec_b = _make_role("executor", "openrouter/model-B", 200, 80)
    delegations = [
        _make_delegation(model_roles={"executor": exec_a}),
        _make_delegation(model_roles={"executor": exec_b}),
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=delegations,
    ):
        report = build_project_cost_report("/fake/ws")

    assert set(report["by_model"].keys()) == {"openrouter/model-A", "openrouter/model-B"}
    assert report["total_usd"] == pytest.approx(
        exec_a["cost_est_usd"]["total"] + exec_b["cost_est_usd"]["total"]
    )
    assert report["by_role"]["executor"]["calls"] == 2


# ---------------------------------------------------------------------------
# 5. project_key filter
# ---------------------------------------------------------------------------
def test_project_key_filter():
    role = _make_role("executor", "openrouter/m", 100, 50)
    rec_a1 = _make_delegation(project_key="A", model_roles={"executor": role})
    rec_a2 = _make_delegation(project_key="A", model_roles={"executor": role})
    rec_b = _make_delegation(project_key="B", model_roles={"executor": role})
    all_recs = [rec_a1, rec_a2, rec_b]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=all_recs,
    ):
        report_a = build_project_cost_report("/fake/ws", project_key="A")
        report_b = build_project_cost_report("/fake/ws", project_key="B")

    assert report_a["delegation_count"] == 2
    assert report_b["delegation_count"] == 1


# ---------------------------------------------------------------------------
# 6. No filter includes all
# ---------------------------------------------------------------------------
def test_no_filter_includes_all():
    role = _make_role("executor", "openrouter/m", 100, 50)
    all_recs = [
        _make_delegation(project_key="A", model_roles={"executor": role}),
        _make_delegation(project_key="B", model_roles={"executor": role}),
        _make_delegation(project_key="C", model_roles={"executor": role}),
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=all_recs,
    ):
        report = build_project_cost_report("/fake/ws", project_key=None)

    assert report["delegation_count"] == 3
    assert report["project_key"] == "all"


# ---------------------------------------------------------------------------
# 7. limit most recent
# ---------------------------------------------------------------------------
def test_limit_most_recent():
    role = _make_role("executor", "openrouter/m", 100, 50)
    five = [
        _make_delegation(
            project_key="A", spec_path=f"tasks/T{i}.md", model_roles={"executor": role}
        )
        for i in range(1, 6)
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=five,
    ):
        report = build_project_cost_report("/fake/ws", limit=2)

    assert report["delegation_count"] == 2
    # Cost should match the last 2 records
    single = role["cost_est_usd"]["total"]
    assert report["total_usd"] == pytest.approx(single * 2)


# ---------------------------------------------------------------------------
# 8. Empty workspace returns zeroed report
# ---------------------------------------------------------------------------
def test_empty_workspace_returns_zeroed_report():
    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        side_effect=FileNotFoundError,
    ):
        report = build_project_cost_report("/nonexistent/ws")

    assert report["delegation_count"] == 0
    assert report["total_usd"] == 0.0
    assert report["by_model"] == {}
    assert report["by_role"] == {}
    assert report["by_task"] == []
    assert report["uncaptured_roles"] == []
    assert "No delegation records" in report["note"]


# ---------------------------------------------------------------------------
# 9. Records without model_roles gracefully skipped
# ---------------------------------------------------------------------------
def test_records_without_model_roles_gracefully_skipped():
    delegations = [
        _make_delegation(model_roles=None),
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=delegations,
    ):
        report = build_project_cost_report("/fake/ws")

    assert report["delegation_count"] == 1
    assert report["by_model"] == {}
    assert report["total_usd"] == 0.0


# ---------------------------------------------------------------------------
# 10. spec_path=None grouped under None key
# ---------------------------------------------------------------------------
def test_spec_path_none_grouped_under_none_key():
    role = _make_role("executor", "openrouter/m", 100, 50)
    delegations = [
        _make_delegation(spec_path=None, model_roles={"executor": role}),
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=delegations,
    ):
        report = build_project_cost_report("/fake/ws")

    assert len(report["by_task"]) == 1
    assert report["by_task"][0]["spec_path"] is None
    assert report["by_task"][0]["runs"] == 1


# ---------------------------------------------------------------------------
# 11. by_task sorted descending by cost
# ---------------------------------------------------------------------------
def test_by_task_sorted_descending():
    role = _make_role("executor", "openrouter/m", 100, 50)
    single_cost = role["cost_est_usd"]["total"]
    delegations = [
        _make_delegation(spec_path="tasks/low.md", model_roles={"executor": role}),
        _make_delegation(spec_path="tasks/high.md", model_roles={"executor": role}),
        _make_delegation(spec_path="tasks/high.md", model_roles={"executor": role}),
        _make_delegation(spec_path="tasks/mid.md", model_roles={"executor": role}),
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=delegations,
    ):
        report = build_project_cost_report("/fake/ws")

    tasks = report["by_task"]
    assert tasks[0]["cost_usd"] == pytest.approx(single_cost * 2)  # high.md
    assert tasks[0]["spec_path"] == "tasks/high.md"
    assert tasks[0]["runs"] == 2
    # Verify descending
    costs = [t["cost_usd"] for t in tasks]
    assert costs == sorted(costs, reverse=True)


# ---------------------------------------------------------------------------
# 12. Report dict has required keys
# ---------------------------------------------------------------------------
def test_report_dict_has_required_keys():
    role = _make_role("executor", "openrouter/m", 100, 50)
    delegations = [
        _make_delegation(model_roles={"executor": role}),
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=delegations,
    ):
        report = build_project_cost_report("/fake/ws")

    required = {
        "project_key",
        "delegation_count",
        "total_usd",
        "by_model",
        "by_role",
        "by_task",
        "uncaptured_roles",
        "note",
    }
    for key in required:
        assert key in report, f"Missing required key: {key}"


# ---------------------------------------------------------------------------
# 13. Multi-role delegation: by_task runs = number of delegations, not roles
# ---------------------------------------------------------------------------
def test_by_task_runs_counts_delegations_not_roles():
    """A delegation with 3 roles should count as 1 run, not 3."""
    exec_role = _make_role("executor", "openrouter/exec", 1000, 400)
    planner_role = _make_role("planner_pass", "openrouter/planner", 800, 300)
    supervisor_role = _make_role("supervisor", "openrouter/sup", 600, 200)

    two_delegations = [
        _make_delegation(
            spec_path="tasks/T1.md",
            model_roles={
                "executor": exec_role,
                "planner_pass": planner_role,
                "supervisor": supervisor_role,
            },
        ),
        _make_delegation(
            spec_path="tasks/T1.md",
            model_roles={
                "executor": exec_role,
                "planner_pass": planner_role,
                "supervisor": supervisor_role,
            },
        ),
    ]

    with patch(
        "core.logging.cost_report.load_delegations_for_workspace",
        return_value=two_delegations,
    ):
        report = build_project_cost_report("/fake/ws")

    assert report["by_task"][0]["runs"] == 2, (
        "runs should count delegations (2), not role entries (6)"
    )
