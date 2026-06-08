"""MCP-owned updates to workspace delegation reports after delegation."""

from __future__ import annotations

import re
from pathlib import Path

from core.context.summary import redact_secrets
from core.specs.modes import DELEGATE_MODE_REVIEW
from core.specs.read import sha256_text
from core.specs.sections import (
    REPORT_STATUS_BLOCKED,
    REPORT_STATUS_DELEGATED_OK,
    REPORT_STATUS_REVIEWED,
    join_front_matter,
    parse_sections,
    replace_section_body,
    split_front_matter,
)

RUN_LOG_OUTPUT_PREVIEW_CHARS = 300
WORKER_FEEDBACK_PREVIEW_CHARS = 4000


def _status_value(*, success: bool, delegate_mode: str) -> str:
    if delegate_mode == DELEGATE_MODE_REVIEW:
        return REPORT_STATUS_REVIEWED if success else REPORT_STATUS_BLOCKED
    return REPORT_STATUS_DELEGATED_OK if success else REPORT_STATUS_BLOCKED


def _format_run_log_entry(
    *,
    timestamp: str,
    delegation_id: str,
    mcp_session_id: str,
    delegate_mode: str,
    success: bool,
    files_changed: list[str],
    output_preview: str,
    error: str | None,
    task_spec: str | None = None,
    usage_summary: str | None = None,
) -> str:
    files = ", ".join(files_changed) if files_changed else "(none)"
    lines = [
        f"### {timestamp} — `{delegation_id}` (session `{mcp_session_id[:8]}…`)",
        f"- **mode:** {delegate_mode}",
        f"- **success:** {str(success).lower()}",
        f"- **files_changed:** {files}",
        f"- **output:** {output_preview or '(empty)'}",
    ]
    if task_spec:
        lines.insert(2, f"- **task_spec:** `{task_spec}`")
    if error:
        lines.append(f"- **error:** {error[:RUN_LOG_OUTPUT_PREVIEW_CHARS]}")
    if usage_summary:
        lines.append(usage_summary)
    return "\n".join(lines)


def _format_worker_feedback_entry(
    *,
    timestamp: str,
    delegation_id: str,
    body: str,
) -> str:
    return f"### {timestamp} — `{delegation_id}`\n\n{body.strip()}"


def _failure_blockers(error: str | None, output: str) -> str:
    parts: list[str] = []
    if error:
        parts.append(error.strip())
    if output and output.strip() and output.strip() != (error or "").strip():
        tail = output.strip()[-RUN_LOG_OUTPUT_PREVIEW_CHARS:]
        parts.append(f"Last output:\n{tail}")
    return "\n\n".join(parts) if parts else "Delegation failed; see Run log and delegations.jsonl."


def _remove_section_if_present(body: str, title: str) -> str:
    """Remove a ## section (header + body) entirely if present; leave body unchanged if absent."""
    pattern = re.compile(
        rf"^## {re.escape(title)}\s*\n.*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    result = pattern.sub("", body)
    return re.sub(r"\n{3,}", "\n\n", result)


def _format_scope_expansion_discover(files_unexpected: list[str]) -> str:
    paths = "\n".join(f"- `{p}`" for p in files_unexpected)
    return (
        "Executor touched paths outside the spec contract (edit_scope: discover).\n"
        "Consider updating the spec Files section if these changes were intentional.\n\n"
        f"**Unexpected paths:**\n{paths}"
    )


def _format_scope_expansion_strict(scope_violations: list[str]) -> str:
    paths = "\n".join(f"- `{p}`" for p in scope_violations)
    return (
        "**scope_violation** — executor edited paths outside `files_edit` (edit_scope: strict).\n"
        "Update the spec Files section and re-delegate; do not patch in the worker session.\n\n"
        f"**Violation paths (outside files_edit):**\n{paths}"
    )


def _scope_violation_blockers(scope_violations: list[str]) -> str:
    paths_inline = ", ".join(scope_violations)
    return (
        "scope_violation: executor touched paths outside files_edit.\n"
        "Update spec Files → Edit to include all intended paths, then re-delegate.\n"
        f"Violation paths: {paths_inline}"
    )


def _scope_violation_suggestions() -> str:
    return (
        "- Update spec Files section (add violation paths to Edit list or narrow task scope).\n"
        "- Re-delegate with the same spec_path after updating."
    )


def _failure_suggestions(error: str | None, delegate_mode: str) -> str:
    hints: list[str] = []
    lower = (error or "").lower()
    if "mode=review" in lower or "clarification" in lower:
        hints.append(
            "Run `delegate_to_agent` with `mode=review` and `target_files=[]` before implement."
        )
    if delegate_mode == DELEGATE_MODE_REVIEW:
        hints.append("Update the task spec (bump revision), then implement with mode=implement.")
    if "edit format" in lower or "search/replace" in lower:
        hints.append("Narrow scope or split into smaller delegate calls with fewer target_files.")
    if "token" in lower or "context" in lower:
        hints.append("Reduce prompt size (shorter spec, host_transcript: none, or smaller task).")
    if "credit" in lower or "openrouter" in lower:
        hints.append("Check OpenRouter credits or use a model with lower max_tokens.")
    if not hints:
        hints.append("Review Blockers and retry with a smaller task or stronger executor model.")
    return "\n".join(f"- {h}" for h in hints)


def apply_post_delegation_report_updates(
    path: Path,
    *,
    timestamp: str,
    delegation_id: str,
    mcp_session_id: str,
    delegate_mode: str,
    success: bool,
    files_changed: list[str],
    output: str,
    error: str | None,
    task_spec: str | None = None,
    usage_summary: str | None = None,
    scope_violations: list[str] | None = None,
    files_unexpected: list[str] | None = None,
    edit_scope: str | None = None,
) -> tuple[str, str]:
    """Append Run log on report file; update Status, Blockers, Worker feedback; sync YAML status."""
    raw = path.read_text(encoding="utf-8")
    front_matter, body = split_front_matter(raw)

    strict_violation = bool(scope_violations) and edit_scope == "strict"
    if strict_violation:
        status = REPORT_STATUS_BLOCKED
    else:
        status = _status_value(success=success, delegate_mode=delegate_mode)

    run_entry = _format_run_log_entry(
        timestamp=timestamp,
        delegation_id=delegation_id,
        mcp_session_id=mcp_session_id,
        delegate_mode=delegate_mode,
        success=success,
        files_changed=files_changed,
        output_preview=redact_secrets(output[:RUN_LOG_OUTPUT_PREVIEW_CHARS]),
        error=redact_secrets(error[:RUN_LOG_OUTPUT_PREVIEW_CHARS]) if error else None,
        task_spec=task_spec,
        usage_summary=usage_summary,
    )

    existing_run = parse_sections(body).get("Run log", "").strip()
    new_run = f"{existing_run}\n\n{run_entry}".strip() if existing_run else run_entry
    body = replace_section_body(body, "Run log", new_run)
    body = replace_section_body(body, "Status", f"`{status}`")

    # Scope expansion section: write when unexpected paths exist; remove when clean.
    discover_expansion = bool(files_unexpected) and edit_scope != "strict"
    if strict_violation:
        body = replace_section_body(
            body, "Scope expansion", _format_scope_expansion_strict(scope_violations or [])
        )
    elif discover_expansion:
        body = replace_section_body(
            body, "Scope expansion", _format_scope_expansion_discover(files_unexpected or [])
        )
    else:
        body = _remove_section_if_present(body, "Scope expansion")

    if strict_violation:
        body = replace_section_body(
            body, "Blockers / questions", _scope_violation_blockers(scope_violations or [])
        )
        body = replace_section_body(
            body, "Suggested next (hints only)", _scope_violation_suggestions()
        )
    elif delegate_mode == DELEGATE_MODE_REVIEW and success and output.strip():
        feedback_body = redact_secrets(output[:WORKER_FEEDBACK_PREVIEW_CHARS])
        feedback_entry = _format_worker_feedback_entry(
            timestamp=timestamp,
            delegation_id=delegation_id,
            body=feedback_body,
        )
        existing_feedback = parse_sections(body).get("Worker feedback", "").strip()
        new_feedback = (
            f"{existing_feedback}\n\n{feedback_entry}".strip()
            if existing_feedback
            else feedback_entry
        )
        body = replace_section_body(body, "Worker feedback", new_feedback)
        body = replace_section_body(body, "Blockers / questions", "")
        body = replace_section_body(
            body,
            "Suggested next (hints only)",
            "- Update task spec from worker feedback (bump `revision`); set `status: ready`; then implement.",
        )
    elif success and delegate_mode != DELEGATE_MODE_REVIEW:
        body = replace_section_body(body, "Blockers / questions", "")
        body = replace_section_body(body, "Suggested next (hints only)", "")
    else:
        body = replace_section_body(
            body,
            "Blockers / questions",
            _failure_blockers(error, output),
        )
        body = replace_section_body(
            body,
            "Suggested next (hints only)",
            _failure_suggestions(error, delegate_mode),
        )

    front_matter["status"] = status
    if task_spec:
        front_matter["task_spec"] = task_spec
    new_text = join_front_matter(front_matter, body)
    path.write_text(new_text, encoding="utf-8")
    return sha256_text(new_text), status


def apply_post_delegation_spec_updates(
    path: Path,
    *,
    timestamp: str,
    delegation_id: str,
    mcp_session_id: str,
    success: bool,
    files_changed: list[str],
    output: str,
    error: str | None,
    delegate_mode: str = "implement",
) -> tuple[str, str]:
    """Backward-compatible alias — prefer report file via apply_post_delegation_report_updates."""
    return apply_post_delegation_report_updates(
        path,
        timestamp=timestamp,
        delegation_id=delegation_id,
        mcp_session_id=mcp_session_id,
        delegate_mode=delegate_mode,
        success=success,
        files_changed=files_changed,
        output=output,
        error=error,
    )
