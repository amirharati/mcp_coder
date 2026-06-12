"""CLI delegation artifact envelopes (executor in/out, post steps, caller response)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.context.package import TIER_EDIT_FULL, TIER_READ_EXCERPT, TIER_READ_FULL

if TYPE_CHECKING:
    from core.context.package import ContextPackage
from core.context.summary import estimate_tokens


def delegation_envelope(
    *,
    ok: bool,
    stop_after: str,
    artifacts: dict[str, Any],
    caller_response: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "stop_after": stop_after,
        "artifacts": artifacts,
    }
    if caller_response is not None:
        payload["caller_response"] = caller_response
    if error:
        payload["error"] = error
    return payload


def executor_in_artifact(
    *,
    prompt: str,
    package: ContextPackage | None,
    capability_warnings: list[str] | None = None,
) -> dict[str, Any]:
    read_paths: list[str] = []
    fnames: list[str] = []
    if package is not None:
        read_paths = [
            e.path
            for e in package.entries
            if e.tier in (TIER_READ_FULL, TIER_READ_EXCERPT) and e.payload is not None
        ]
        fnames = sorted(e.path for e in package.entries if e.tier == TIER_EDIT_FULL)
    artifact: dict[str, Any] = {
        "prompt": prompt,
        "fnames": fnames,
        "read_paths_in_prompt": read_paths,
        "prompt_chars": len(prompt),
        "prompt_tokens_est": estimate_tokens(prompt),
    }
    if capability_warnings:
        artifact["capability_warnings"] = capability_warnings
    return artifact


def executor_out_artifact(
    *,
    output: str,
    files_changed: list[str],
    files_unexpected: list[str] | None = None,
    success: bool | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "output": output,
        "files_changed": files_changed,
        "files_unexpected": files_unexpected or [],
    }
    if success is not None:
        out["success"] = success
    return out


def post_delegate_artifact(caller_response: dict[str, Any]) -> dict[str, Any]:
    """Extract wrap-up fields from the MCP delegate response."""
    post: dict[str, Any] = {}
    for key in (
        "spec_report_path",
        "scope_violations",
        "reverted_paths",
        "revert_skipped",
        "outcome",
        "delegation_diff",
        "judgment_checklist",
        "verify_result",
        "delegation_pipeline",
    ):
        if key in caller_response and caller_response[key] is not None:
            post[key] = caller_response[key]
    return post


def prepare_artifacts(
    *,
    inspect_result: dict[str, Any],
    executor_prompt: str,
    capability_warnings: list[str] | None = None,
) -> dict[str, Any]:
    preview = inspect_result.get("adapter_preview") or {}
    executor_in: dict[str, Any] = {
        "prompt": executor_prompt,
        "fnames": list(preview.get("fnames") or []),
        "read_paths_in_prompt": list(preview.get("read_paths_in_prompt") or []),
        "prompt_chars": len(executor_prompt),
        "prompt_tokens_est": estimate_tokens(executor_prompt),
    }
    if capability_warnings:
        executor_in["capability_warnings"] = capability_warnings

    package_dict = inspect_result.get("context_package") or {}
    artifacts: dict[str, Any] = {
        "executor_in": executor_in,
        "helper_phases": inspect_result.get("helper_phases"),
        "context_package": package_dict,
    }
    if inspect_result.get("adapter_preview"):
        artifacts["adapter_preview"] = inspect_result["adapter_preview"]
    for key in (
        "auto_merged_read_paths",
        "contract_warnings",
        "spec_files_missing_from_target",
    ):
        if inspect_result.get(key):
            artifacts[key] = inspect_result[key]
    return artifacts


def full_run_artifacts(
    *,
    caller_response: dict[str, Any],
    executor_prompt: str,
    fnames: list[str] | None = None,
    read_paths_in_prompt: list[str] | None = None,
    capability_warnings: list[str] | None = None,
) -> dict[str, Any]:
    executor_in: dict[str, Any] = {
        "prompt": executor_prompt,
        "fnames": fnames or [],
        "read_paths_in_prompt": read_paths_in_prompt or [],
        "prompt_chars": len(executor_prompt),
        "prompt_tokens_est": estimate_tokens(executor_prompt),
    }
    if capability_warnings:
        executor_in["capability_warnings"] = capability_warnings

    return {
        "executor_in": executor_in,
        "executor_out": executor_out_artifact(
            output=str(caller_response.get("output") or ""),
            files_changed=list(caller_response.get("files_changed") or []),
            files_unexpected=list(caller_response.get("files_unexpected") or []),
            success=bool(caller_response.get("success")),
        ),
        "post_delegate": post_delegate_artifact(caller_response),
    }
