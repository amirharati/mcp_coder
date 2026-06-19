"""CLI: tail delegation trace events in real time (P10-002)."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, TextIO

from core.cli.replay import _find_delegation_row, _session_dir_for_row
from core.logging.delegation_log import delegation_log_paths_for_workspace


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


def _trace_path_from_row(row: dict[str, Any], log_path: Path) -> tuple[str, Path] | None:
    delegation_id = row.get("delegation_id")
    if not isinstance(delegation_id, str) or not delegation_id.strip():
        return None
    session_dir = _session_dir_for_row(row, log_path)
    trace_ref = row.get("trace_ref")
    if isinstance(trace_ref, str) and trace_ref.strip():
        trace_path = Path(trace_ref)
        if not trace_path.is_absolute():
            trace_path = (session_dir / trace_path).resolve()
    else:
        trace_path = (session_dir / "traces" / f"{delegation_id}.jsonl").resolve()
    return delegation_id, trace_path


def _timestamp_key(row: dict[str, Any]) -> str:
    return str(row.get("timestamp_end") or row.get("timestamp_start") or "")


def resolve_latest_trace(workspace: Path) -> tuple[str | None, Path | None]:
    paths = delegation_log_paths_for_workspace(str(workspace))
    best: tuple[str, int, str, Path] | None = None
    seq = 0
    for log_path in paths:
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            text = raw.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            resolved = _trace_path_from_row(row, log_path)
            if resolved is None:
                continue
            delegation_id, trace_path = resolved
            seq += 1
            candidate = (_timestamp_key(row), seq, delegation_id, trace_path)
            if best is None or (candidate[0], candidate[1]) > (best[0], best[1]):
                best = candidate
    if best is None:
        return None, None
    return best[2], best[3]


def resolve_trace_for_delegation(workspace: Path, delegation_id: str) -> Path | None:
    row, log_path = _find_delegation_row(workspace, delegation_id)
    if row is None or log_path is None:
        return None
    resolved = _trace_path_from_row(row, log_path)
    if resolved is None:
        return None
    return resolved[1]


def _pick_target_trace(
    workspace: Path,
    *,
    latest: bool,
    delegation_id: str | None,
) -> tuple[str | None, Path | None]:
    if delegation_id:
        return delegation_id, resolve_trace_for_delegation(workspace, delegation_id)
    if latest:
        return resolve_latest_trace(workspace)
    return resolve_latest_trace(workspace)


def _format_human_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "unknown")
    ts = str(event.get("timestamp") or event.get("created_at") or "-")

    if event_type == "trace_header":
        return (
            f"{ts} trace_header delegation_id={event.get('delegation_id')} "
            f"model={event.get('model') or '-'}"
        )
    if event_type == "compile_event":
        return (
            f"{ts} compile_event stage={event.get('stage') or '-'} "
            f"status={event.get('status') or '-'}"
        )
    if event_type == "executor_step":
        return (
            f"{ts} executor_step step={event.get('step_index') or '-'} "
            f"status={event.get('status') or '-'}"
        )
    if event_type == "llm_call":
        return (
            f"{ts} llm_call role={event.get('role') or '-'} "
            f"model={event.get('model') or '-'}"
        )
    if event_type == "proxy_llm_call":
        return (
            f"{ts} proxy_llm_call call={event.get('call_index') or '-'} "
            f"status={event.get('status_code') or '-'}"
        )
    if event_type == "backend_llm_call":
        return (
            f"{ts} backend_llm_call call={event.get('call_index') or '-'} "
            f"model={event.get('model') or '-'}"
        )
    if event_type == "delegation_complete":
        return (
            f"{ts} delegation_complete success={event.get('success')} "
            f"outcome={event.get('outcome') or '-'}"
        )
    return f"{ts} {event_type}"


def read_appended_events(
    trace_path: Path,
    *,
    offset: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    if not trace_path.exists():
        return [], offset, False
    try:
        file_size = trace_path.stat().st_size
        if offset > file_size:
            offset = 0
        with trace_path.open("r", encoding="utf-8") as fh:
            fh.seek(offset)
            chunk = fh.read()
            new_offset = fh.tell()
    except OSError:
        return [], offset, False

    events: list[dict[str, Any]] = []
    for raw in chunk.splitlines():
        text = raw.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events, new_offset, True


def tail_trace_file(
    trace_path: Path,
    *,
    output_format: str = "human",
    follow: bool = True,
    poll_interval_s: float = 0.5,
    stdout: TextIO | None = None,
) -> int:
    out = stdout
    if out is None:
        import sys

        out = sys.stdout

    offset = 0
    missing_notice_printed = False
    try:
        while True:
            events, offset, exists = read_appended_events(trace_path, offset=offset)
            if not exists:
                if not missing_notice_printed:
                    print(f"waiting for trace file: {trace_path}", file=out)
                    missing_notice_printed = True
            else:
                missing_notice_printed = False
                for event in events:
                    if output_format == "json":
                        print(json.dumps(event, ensure_ascii=False), file=out)
                    else:
                        print(_format_human_event(event), file=out)
            if not follow:
                return 0
            time.sleep(poll_interval_s)
    except KeyboardInterrupt:
        return 0


def main_logs_tail(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tail delegation trace events")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--latest",
        action="store_true",
        help="Tail the most recent delegation trace in the workspace (default).",
    )
    group.add_argument("--delegation-id", default=None, help="Tail this delegation trace id.")
    parser.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument(
        "--poll-interval-s",
        type=float,
        default=0.5,
        help="File polling interval in seconds (default: 0.5)",
    )
    args = parser.parse_args(argv)

    workspace = _resolve_workspace(args.workspace)
    latest = bool(args.latest or not args.delegation_id)
    delegation_id, trace_path = _pick_target_trace(
        workspace,
        latest=latest,
        delegation_id=args.delegation_id,
    )
    if trace_path is None:
        if args.delegation_id:
            print(f"delegation not found: {args.delegation_id}")
        else:
            print(f"no delegation traces found in workspace: {workspace}")
        return 1

    selected = delegation_id or args.delegation_id or "(unknown)"
    print(f"tailing trace for delegation_id={selected}: {trace_path}")
    return tail_trace_file(
        trace_path,
        output_format=args.format,
        follow=True,
        poll_interval_s=max(0.1, float(args.poll_interval_s or 0.5)),
    )


if __name__ == "__main__":
    raise SystemExit(main_logs_tail())
