"""CLI: inspect delegation trace events (P9-010)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.cli.replay import _find_delegation_row, _load_trace, _resolve_workspace, _session_dir_for_row


def _find_trace_path(workspace: str | Path, delegation_id: str) -> Path | None:
    ws = Path(workspace).resolve()
    row, log_path = _find_delegation_row(ws, delegation_id)
    if row is None or log_path is None:
        return None
    session_dir = _session_dir_for_row(row, log_path)
    trace, _warnings = _load_trace(row, str(row.get("delegation_id") or delegation_id), session_dir)
    path = trace.get("path")
    if trace.get("status") == "found" and isinstance(path, str):
        return Path(path)
    return None


def _load_trace_events(trace_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in trace_path.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if not text:
            continue
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            events.append(loaded)
    return events


def _format_value_human(value: Any, *, max_chars: int = 2000) -> str:
    if value is None:
        text = "(null)"
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        text = str(value)

    if len(text) <= max_chars:
        return text
    truncated = len(text) - max_chars
    return (
        f"{text[:max_chars]}\n"
        f"... [TRUNCATED {truncated} chars — use --format json for full content]"
    )


def _event_summary(event: dict[str, Any]) -> str:
    etype = str(event.get("type") or "?")
    ts = str(event.get("timestamp") or event.get("created_at") or "-")

    if etype == "proxy_llm_call":
        return (
            f"{etype:<18} {ts}  "
            f"call_index={event.get('call_index')}  "
            f"step_index={event.get('step_index')}  "
            f"status={event.get('status_code')}  "
            f"wire_ms={event.get('wire_latency_ms')}"
        )
    if etype == "backend_llm_call":
        usage = event.get("usage")
        usage_text = ""
        if isinstance(usage, dict):
            usage_text = (
                f"usage={{input:{usage.get('input')},output:{usage.get('output')}}}"
            )
        return (
            f"{etype:<18} {ts}  "
            f"call_index={event.get('call_index')}  "
            f"step_index={event.get('step_index')}  "
            f"model={event.get('model')}  "
            f"{usage_text}".rstrip()
        )
    if etype == "llm_call":
        return (
            f"{etype:<18} {ts}  "
            f"role={event.get('role')}  model={event.get('model')}"
        )
    if etype == "compile_event":
        return (
            f"{etype:<18} {ts}  "
            f"kind={event.get('kind') or event.get('compile_type')}  "
            f"files={event.get('file_count') or event.get('files_count') or '-'}"
        )
    if etype == "tool_call":
        return f"{etype:<18} {ts}  tool={event.get('tool') or event.get('name')}"
    if etype == "action":
        return f"{etype:<18} {ts}  kind={event.get('kind')}"

    return f"{etype:<18} {ts}"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    incoming = list(argv or [])
    if incoming[:2] == ["trace", "inspect"]:
        incoming = incoming[2:]
    elif incoming[:1] == ["inspect"]:
        incoming = incoming[1:]

    parser = argparse.ArgumentParser(description="Dump events from a delegation trace")
    parser.add_argument("delegation_id")
    parser.add_argument("--workspace", default=None)
    parser.add_argument(
        "--type",
        default=None,
        dest="event_type",
        help="Filter to events of this type",
    )
    parser.add_argument(
        "--event",
        type=int,
        default=None,
        help="Select Nth matching event (1-based)",
    )
    parser.add_argument("--field", default=None, help="Print only this field from each event")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    return parser.parse_args(incoming)


def main_trace_inspect(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    workspace = _resolve_workspace(args.workspace)
    trace_path = _find_trace_path(workspace, args.delegation_id)
    if trace_path is None:
        print(f"delegation not found: {args.delegation_id}")
        return 1

    events = _load_trace_events(trace_path)
    matching = events
    if args.event_type:
        matching = [event for event in matching if event.get("type") == args.event_type]

    if args.event is not None:
        if args.event <= 0:
            print("--event must be >= 1")
            return 0
        if args.event > len(matching):
            print(
                f"event {args.event} out of range for {len(matching)} matching events"
            )
            return 0
        matching = [matching[args.event - 1]]

    if args.format == "json":
        if args.field:
            values = [event.get(args.field) for event in matching]
            payload: Any = values[0] if len(values) == 1 else values
        else:
            payload = matching[0] if len(matching) == 1 else matching
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.field:
        label = args.event_type or "event"
        total = len(matching)
        for idx, event in enumerate(matching, start=1):
            print(f"{label} [{idx}/{total}]")
            print(f"--- {args.field} ---")
            print(_format_value_human(event.get(args.field)))
        if not matching:
            print(f"{label} [0/0]")
            print(f"--- {args.field} ---")
            print("(null)")
        return 0

    print(f"Trace: {args.delegation_id}")
    for idx, event in enumerate(matching, start=1):
        print(f"  [{idx}] {_event_summary(event)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_trace_inspect())
