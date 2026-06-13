"""Opt-in training tuple export (P6-005, D-P6-6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config.observability import capture_for_training_enabled
from core.observability.version_tags import CAPTURE_SCHEMA_VERSION, build_trace_version_tags


def build_training_record(
    *,
    workspace: str | Path,
    delegation_id: str,
    timestamp_end: str,
    task: str,
    context_package_hash: str | None,
    trace_ref: str,
    reasoning_summary: str | None,
    outcome: str | None,
    verify_result: dict[str, Any] | None,
    success: bool,
    model_roles: dict[str, Any] | None,
    pipeline_flags_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "capture_schema_version": CAPTURE_SCHEMA_VERSION,
        "delegation_id": delegation_id,
        "timestamp_end": timestamp_end,
        "version_tags": build_trace_version_tags(
            workspace,
            model_roles=model_roles,
            pipeline_flags_runtime=pipeline_flags_runtime,
        ),
        "task": task,
        "context_package_hash": context_package_hash,
        "trace_ref": trace_ref,
        "outcome": outcome,
        "success": success,
        "verify_result": verify_result,
    }
    if reasoning_summary:
        record["reasoning_summary"] = reasoning_summary
    return record


def training_capture_path(session_dir: str | Path, delegation_id: str) -> Path:
    return Path(session_dir) / "traces" / f"{delegation_id}-training.json"


def write_training_capture_if_enabled(
    *,
    workspace: str | Path,
    session_dir: str | Path,
    delegation_id: str,
    timestamp_end: str,
    task: str,
    context_package_hash: str | None,
    reasoning_summary: str | None,
    outcome: str | None,
    verify_result: dict[str, Any] | None,
    success: bool,
    model_roles: dict[str, Any] | None,
    pipeline_flags_runtime: dict[str, Any] | None = None,
) -> Path | None:
    """Write training tuple when capture_for_training is enabled; else no-op."""
    if not capture_for_training_enabled(workspace):
        return None

    trace_ref = f"traces/{delegation_id}.jsonl"
    record = build_training_record(
        workspace=workspace,
        delegation_id=delegation_id,
        timestamp_end=timestamp_end,
        task=task,
        context_package_hash=context_package_hash,
        trace_ref=trace_ref,
        reasoning_summary=reasoning_summary,
        outcome=outcome,
        verify_result=verify_result,
        success=success,
        model_roles=model_roles,
        pipeline_flags_runtime=pipeline_flags_runtime,
    )
    path = training_capture_path(session_dir, delegation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
