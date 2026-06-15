"""CLI: observability maintenance and storage stats (P6-005)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from core.config.observability import resolve_observability_retention
from core.observability.stats import collect_observability_stats


def _print_interception_profiles() -> None:
    from core.engine import get_engine, list_backends

    for backend_id in list_backends():
        engine = get_engine(backend_id)
        profile = engine.interception_profile
        print(f"Backend: {backend_id}")
        print(f"  interception.strategy:      {profile.strategy}")
        print(f"  interception.thinking:      {str(profile.thinking_captured).lower()}")
        verified = ", ".join(profile.verified_call_sites) or "(none)"
        print(f"  interception.verified:      {verified}")
        gaps = "; ".join(profile.known_gaps) or "(none)"
        print(f"  interception.known_gaps:      {gaps}")
        print()


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


def _parse_iso_datetime(raw: Any) -> dt.datetime | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _parse_ttl_days(policy: str) -> int | None:
    match = re.match(r"^(\d+)_days$", policy.strip().lower())
    if not match:
        return None
    return int(match.group(1))


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    loaded = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(loaded, dict):
                    rows.append(loaded)
    except OSError:
        return rows
    return rows


def _trace_header_created_at(trace_path: Path) -> dt.datetime | None:
    if not trace_path.is_file():
        return None
    try:
        with trace_path.open(encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    loaded = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(loaded, dict):
                    continue
                if loaded.get("type") != "trace_header":
                    continue
                return _parse_iso_datetime(loaded.get("created_at")) or _parse_iso_datetime(
                    loaded.get("timestamp")
                )
    except OSError:
        return None
    return None


def _fmt_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _print_gc_human(report: dict[str, Any]) -> None:
    layers = report["layers"]
    traces = layers["traces"]
    blobs = layers["blobs"]
    rows = layers["rows"]
    print("GC report")
    print(f"- policy:         {report['policy']} (cutoff: {report['cutoff'][:10]})")
    print(f"- dry_run:        {report['dry_run']}")
    print()
    print("Traces")
    print(
        f"  total:          {traces['file_count']} files, {_fmt_bytes(traces['total_bytes'])}"
    )
    print(
        f"  prunable:       {traces['prunable_count']} files, {_fmt_bytes(traces['prunable_bytes'])}"
    )
    print(
        f"  blocked:        {traces['blocked_count']} files  (training export present — not pruned)"
    )
    print()
    print("Blobs (context_packages)")
    print(
        f"  total:          {blobs['file_count']} files, {_fmt_bytes(blobs['total_bytes'])}"
    )
    print(
        f"  prunable:       {blobs['prunable_count']} files, {_fmt_bytes(blobs['prunable_bytes'])}"
    )
    print()
    print("Rows (delegations.jsonl)")
    print(
        f"  total:          {rows['file_count']} files, {_fmt_bytes(rows['total_bytes'])}"
    )
    print("  prunable:       0  (rows never pruned without --include-rows flag)")
    print()
    if report["dry_run"]:
        print(f"Would free: {_fmt_bytes(report['would_free_bytes'])}  (dry-run — nothing deleted)")
    else:
        print(
            f"Freed: {_fmt_bytes(report['pruned_bytes'])}  ({report['pruned_count']} files deleted)"
        )


def _cmd_gc(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    policy = resolve_observability_retention(ws)
    ttl_days = _parse_ttl_days(policy)
    if ttl_days is None:
        message = f"retention policy '{policy}' is not a TTL — nothing to prune"
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "policy": policy,
                        "dry_run": bool(args.dry_run),
                        "warning": message,
                        "layers": {
                            "traces": {
                                "file_count": 0,
                                "total_bytes": 0,
                                "prunable_count": 0,
                                "prunable_bytes": 0,
                                "blocked_count": 0,
                            },
                            "blobs": {
                                "file_count": 0,
                                "total_bytes": 0,
                                "prunable_count": 0,
                                "prunable_bytes": 0,
                            },
                            "rows": {
                                "file_count": 0,
                                "total_bytes": 0,
                                "prunable_count": 0,
                                "note": "rows never pruned without --include-rows",
                            },
                        },
                        "pruned_count": 0,
                        "pruned_bytes": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(message)
        return 0

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=ttl_days)

    from core.storage.paths import sessions_root

    rows_file_count = 0
    rows_total_bytes = 0

    trace_file_count = 0
    trace_total_bytes = 0
    trace_prunable_paths: list[Path] = []
    trace_prunable_bytes = 0
    trace_blocked_count = 0

    blob_file_count = 0
    blob_total_bytes = 0
    blob_prunable_paths: list[Path] = []
    blob_prunable_bytes = 0

    sessions = sessions_root(ws)
    if sessions.is_dir():
        for session_dir in sorted(sessions.iterdir()):
            if not session_dir.is_dir():
                continue

            delegation_created_at: dict[str, dt.datetime] = {}
            delegation_hashes: dict[str, set[str]] = {}

            deleg_log = session_dir / "delegations.jsonl"
            if deleg_log.is_file():
                rows_file_count += 1
                rows_total_bytes += deleg_log.stat().st_size
                for row in _read_jsonl_objects(deleg_log):
                    delegation_id = str(row.get("delegation_id") or "").strip()
                    if not delegation_id:
                        continue
                    created_at = _parse_iso_datetime(row.get("created_at"))
                    if created_at is not None:
                        delegation_created_at[delegation_id] = created_at
                    context = row.get("context")
                    if isinstance(context, dict):
                        pkg_hash = context.get("context_package_hash")
                        if isinstance(pkg_hash, str) and pkg_hash.strip():
                            delegation_hashes.setdefault(delegation_id, set()).add(pkg_hash)

            trace_prunable_by_delegation: dict[str, bool] = {}
            traces_dir = session_dir / "traces"
            if traces_dir.is_dir():
                for trace in traces_dir.iterdir():
                    if not trace.is_file() or trace.suffix != ".jsonl":
                        continue
                    trace_file_count += 1
                    trace_size = trace.stat().st_size
                    trace_total_bytes += trace_size

                    delegation_id = trace.stem
                    trace_created = (
                        _trace_header_created_at(trace)
                        or delegation_created_at.get(delegation_id)
                        or dt.datetime.fromtimestamp(
                            trace.stat().st_mtime, tz=dt.timezone.utc
                        )
                    )
                    is_old = trace_created < cutoff
                    has_training_sidecar = (
                        traces_dir / f"{delegation_id}-training.json"
                    ).is_file()
                    if is_old and has_training_sidecar:
                        trace_blocked_count += 1
                        trace_prunable_by_delegation[delegation_id] = False
                    elif is_old:
                        trace_prunable_paths.append(trace)
                        trace_prunable_bytes += trace_size
                        trace_prunable_by_delegation[delegation_id] = True
                    else:
                        trace_prunable_by_delegation[delegation_id] = False

            live_hashes: set[str] = set()
            for delegation_id, hashes in delegation_hashes.items():
                if not trace_prunable_by_delegation.get(delegation_id, False):
                    live_hashes.update(hashes)

            blobs_dir = session_dir / "context_packages"
            if blobs_dir.is_dir():
                for blob in blobs_dir.iterdir():
                    if not blob.is_file() or blob.suffix != ".json":
                        continue
                    blob_file_count += 1
                    blob_size = blob.stat().st_size
                    blob_total_bytes += blob_size
                    if blob.stem not in live_hashes:
                        blob_prunable_paths.append(blob)
                        blob_prunable_bytes += blob_size

    report: dict[str, Any] = {
        "policy": policy,
        "cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "dry_run": bool(args.dry_run),
        "layers": {
            "traces": {
                "file_count": trace_file_count,
                "total_bytes": trace_total_bytes,
                "prunable_count": len(trace_prunable_paths),
                "prunable_bytes": trace_prunable_bytes,
                "blocked_count": trace_blocked_count,
            },
            "blobs": {
                "file_count": blob_file_count,
                "total_bytes": blob_total_bytes,
                "prunable_count": len(blob_prunable_paths),
                "prunable_bytes": blob_prunable_bytes,
            },
            "rows": {
                "file_count": rows_file_count,
                "total_bytes": rows_total_bytes,
                "prunable_count": 0,
                "note": "rows never pruned without --include-rows",
            },
        },
        "pruned_count": 0,
        "pruned_bytes": 0,
        "would_free_bytes": trace_prunable_bytes + blob_prunable_bytes,
    }

    if not args.dry_run:
        # Delete traces first, then blobs.
        for path in trace_prunable_paths:
            try:
                size = path.stat().st_size
                path.unlink()
                report["pruned_count"] += 1
                report["pruned_bytes"] += size
            except OSError:
                continue
        for path in blob_prunable_paths:
            try:
                size = path.stat().st_size
                path.unlink()
                report["pruned_count"] += 1
                report["pruned_bytes"] += size
            except OSError:
                continue

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_gc_human(report)
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    stats = collect_observability_stats(ws)
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    obs = stats["observability"]
    delegation_rag = stats["delegation_rag"]
    workspace_rag = stats["workspace_rag"]
    sessions = stats["sessions"]
    traces = stats["traces"]
    blobs = stats["context_packages"]

    print(f"workspace:              {stats['workspace']}")
    print(f"project_dir:              {stats['project_dir']}")
    print(f"capture_for_training:     {obs['capture_for_training']}")
    print(f"observability_retention:  {obs['retention_policy']}")
    print()
    print(f"delegation_rag rows:      {delegation_rag['row_count']}")
    print(f"delegation_rag path:      {delegation_rag['db_path']}")
    print(f"workspace_rag rows:       {workspace_rag['row_count']}")
    print(f"workspace_rag path:       {workspace_rag['db_path']}")
    print()
    print(f"sessions:                 {sessions['count']}")
    print(f"delegations.jsonl bytes:  {sessions['delegations_jsonl_bytes']}")
    print(f"delegations.jsonl lines:  {sessions['delegations_jsonl_lines']}")
    if sessions["legacy_delegations_jsonl_bytes"]:
        print(f"legacy log bytes:         {sessions['legacy_delegations_jsonl_bytes']}")
    print()
    print(f"trace files:              {traces['file_count']}")
    print(f"trace bytes:              {traces['total_bytes']}")
    print(f"training files:           {traces['training_file_count']}")
    print(f"training bytes:           {traces['training_total_bytes']}")
    print(f"executor turns:           {traces.get('executor_turns', 0)}")
    print(f"blob files:               {blobs['file_count']}")
    print(f"blob bytes:               {blobs['total_bytes']}")
    if args.verbose:
        print()
        _print_interception_profiles()
    return 0


def main_maintenance(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observability maintenance and storage stats.")
    sub = parser.add_subparsers(dest="command", required=True)

    stats_p = sub.add_parser("stats", help="Report RAG rows, trace files, and JSONL disk usage")
    stats_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    stats_p.add_argument("--json", action="store_true", help="JSON output")
    stats_p.add_argument(
        "--verbose",
        action="store_true",
        help="Include backend interception profiles",
    )
    gc_p = sub.add_parser("gc", help="Prune expired trace files and context-package blobs")
    gc_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    gc_p.add_argument("--dry-run", action="store_true", help="Report without deleting")
    gc_p.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format",
    )

    args = parser.parse_args(argv)
    if args.command == "stats":
        return _cmd_stats(args)
    if args.command == "gc":
        return _cmd_gc(args)
    print(f"unknown maintenance subcommand: {args.command}", file=sys.stderr)
    return 1
