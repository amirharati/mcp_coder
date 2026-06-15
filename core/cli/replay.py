"""CLI: replay one delegation from disk artifacts only (P9-004)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from core.logging.delegation_log import delegation_log_paths_for_workspace


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def _timestamp_key(row: dict[str, Any]) -> str:
    return str(row.get("timestamp_end") or row.get("timestamp_start") or "")


def _find_delegation_row(
    workspace: Path, delegation_id: str
) -> tuple[dict[str, Any] | None, Path | None]:
    paths = delegation_log_paths_for_workspace(str(workspace))
    matches: list[tuple[str, int, dict[str, Any], Path]] = []
    seq = 0
    for log_path in paths:
        try:
            rows = _load_jsonl_records(log_path)
        except (OSError, json.JSONDecodeError):
            continue
        for row in rows:
            seq += 1
            if row.get("delegation_id") == delegation_id:
                matches.append((_timestamp_key(row), seq, row, log_path))
    if not matches:
        return None, None
    _, _, row, path = max(matches, key=lambda item: (item[0], item[1]))
    return row, path


def _session_dir_for_row(row: dict[str, Any], log_path: Path) -> Path:
    raw = row.get("session_dir")
    if isinstance(raw, str) and raw.strip():
        return Path(raw).resolve()
    return log_path.resolve().parent


def _trace_candidate_paths(row: dict[str, Any], delegation_id: str, session_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    trace_ref = row.get("trace_ref")
    if isinstance(trace_ref, str) and trace_ref.strip():
        trace_path = Path(trace_ref)
        if not trace_path.is_absolute():
            trace_path = session_dir / trace_path
        candidates.append(trace_path.resolve())
    fallback = (session_dir / "traces" / f"{delegation_id}.jsonl").resolve()
    if fallback not in candidates:
        candidates.append(fallback)
    return candidates


def _load_trace(
    row: dict[str, Any], delegation_id: str, session_dir: Path
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    for path in _trace_candidate_paths(row, delegation_id, session_dir):
        if not path.is_file():
            continue
        events: list[dict[str, Any]] = []
        for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                warnings.append(f"trace malformed JSON skipped at line {idx}: {path}")
                continue
            if isinstance(payload, dict):
                events.append(payload)
            else:
                warnings.append(f"trace non-object event skipped at line {idx}: {path}")
        counts = Counter(str(event.get("type", "unknown")) for event in events)
        return (
            {
                "status": "found",
                "path": str(path),
                "events": events,
                "counts_by_type": dict(counts),
            },
            warnings,
        )
    warnings.append(f"trace missing for delegation {delegation_id}")
    return (
        {
            "status": "missing",
            "path": str(_trace_candidate_paths(row, delegation_id, session_dir)[-1]),
            "events": [],
            "counts_by_type": {},
        },
        warnings,
    )


def _load_context_blob(row: dict[str, Any], session_dir: Path) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    context = row.get("context") if isinstance(row.get("context"), dict) else {}
    pkg_hash = context.get("context_package_hash")
    if not isinstance(pkg_hash, str) or not pkg_hash.strip():
        return (
            {
                "hash": None,
                "status": "not_recorded",
                "path": None,
                "content": None,
            },
            warnings,
        )
    blob_path = (session_dir / "context_packages" / f"{pkg_hash}.json").resolve()
    if not blob_path.is_file():
        warnings.append(f"context blob missing: {blob_path}")
        return (
            {
                "hash": pkg_hash,
                "status": "missing",
                "path": str(blob_path),
                "content": None,
            },
            warnings,
        )
    try:
        content = json.loads(blob_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        warnings.append(f"context blob unreadable: {blob_path}")
        return (
            {
                "hash": pkg_hash,
                "status": "missing",
                "path": str(blob_path),
                "content": None,
            },
            warnings,
        )
    return (
        {
            "hash": pkg_hash,
            "status": "found",
            "path": str(blob_path),
            "content": content,
        },
        warnings,
    )


def _build_replay_payload(
    row: dict[str, Any], log_path: Path, workspace: Path
) -> dict[str, Any]:
    delegation_id = str(row.get("delegation_id", ""))
    session_dir = _session_dir_for_row(row, log_path)
    context_blob, context_warnings = _load_context_blob(row, session_dir)
    trace, trace_warnings = _load_trace(row, delegation_id, session_dir)
    warnings = [*context_warnings, *trace_warnings]
    return {
        "found": True,
        "delegation": row,
        "workspace": str(workspace),
        "session_dir": str(session_dir),
        "log_path": str(log_path),
        "context_blob": context_blob,
        "trace": trace,
        "warnings": warnings,
    }


def _print_human(payload: dict[str, Any]) -> None:
    delegation = payload["delegation"]
    context_blob = payload["context_blob"]
    trace = payload["trace"]
    warnings = payload["warnings"]
    mcp_request = delegation.get("mcp_request") if isinstance(delegation.get("mcp_request"), dict) else {}

    print("Replay")
    print(f"- delegation_id: {delegation.get('delegation_id')}")
    print(f"- workspace: {payload.get('workspace')}")
    print(f"- session_dir: {payload.get('session_dir')}")
    print(f"- success: {delegation.get('success')}")
    print(f"- start: {delegation.get('timestamp_start')}")
    print(f"- end: {delegation.get('timestamp_end')}")
    print(f"- duration_ms: {delegation.get('duration_ms')}")
    print()
    print("Request")
    print(f"- task: {mcp_request.get('task')}")
    print(f"- mode: {delegation.get('delegate_mode')}")
    print(f"- backend: {delegation.get('backend')}")
    print(f"- target_files: {mcp_request.get('target_files', [])}")
    print(f"- spec_path: {delegation.get('spec_path')}")
    print()
    print("Context Package")
    print(f"- hash: {context_blob.get('hash')}")
    print(f"- status: {context_blob.get('status')}")
    print(f"- path: {context_blob.get('path')}")
    content = context_blob.get("content")
    if isinstance(content, dict):
        entries = content.get("entries")
        metadata = content.get("metadata")
        policies = content.get("policies")
        print(f"- entry_count: {len(entries) if isinstance(entries, list) else 0}")
        print(f"- metadata_keys: {sorted(metadata.keys()) if isinstance(metadata, dict) else []}")
        print(f"- policies_keys: {sorted(policies.keys()) if isinstance(policies, dict) else []}")
    print()
    print("Trace")
    print(f"- status: {trace.get('status')}")
    print(f"- path: {trace.get('path')}")
    print(f"- counts_by_type: {trace.get('counts_by_type')}")
    events = trace.get("events") if isinstance(trace.get("events"), list) else []
    for event in events:
        if str(event.get("type")) not in {"backend_llm_call", "proxy_llm_call", "llm_call"}:
            continue
        duration = (
            event.get("duration_ms")
            if event.get("duration_ms") is not None
            else event.get("latency_ms")
        )
        print(
            "- call:"
            f" type={event.get('type')}"
            f" model={event.get('model')}"
            f" index={event.get('call_index') or event.get('step_index')}"
            f" duration_ms={duration}"
        )
    print()
    print("Outcome")
    print(f"- files_changed: {delegation.get('files_changed', [])}")
    print(f"- files_unexpected: {delegation.get('files_unexpected', [])}")
    if delegation.get("checkpoint") is not None:
        print(f"- checkpoint: {delegation.get('checkpoint')}")
    if delegation.get("outcome") is not None:
        print(f"- outcome: {delegation.get('outcome')}")
    if warnings:
        print()
        print("Warnings")
        for warning in warnings:
            print(f"- {warning}")


def main_replay(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay one delegation from disk artifacts (delegation row + context blob + trace)."
    )
    parser.add_argument("delegation_id", help="Delegation ID to replay")
    parser.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    parser.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human; json for machine-readable output)",
    )
    args = parser.parse_args(argv)

    workspace = _resolve_workspace(args.workspace)
    row, log_path = _find_delegation_row(workspace, args.delegation_id)
    if row is None or log_path is None:
        msg = f"delegation not found: {args.delegation_id}"
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "found": False,
                        "delegation": None,
                        "context_blob": None,
                        "trace": None,
                        "warnings": [msg],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 1

    payload = _build_replay_payload(row, log_path, workspace)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_replay())
