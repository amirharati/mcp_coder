"""CLI: browse workspace_history.db checkpoints."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from core.engine.git_diff import normalize_repo_path
from core.workspace.history_query import (
    build_checkpoint_detail,
    build_delegation_diff,
    build_file_history,
    list_delegations,
    resolve_delegation_id,
)
from core.workspace.revert import revert_to_before


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


def _resolve_id(ws: Path, args: argparse.Namespace) -> str | None:
    return resolve_delegation_id(
        ws,
        delegation_id=getattr(args, "delegation_id", None),
        latest=getattr(args, "latest", False),
    )


def _format_show_text(detail) -> str:
    lines = [
        f"delegation_id: {detail.delegation_id}",
        f"summary:       {detail.checkpoint_summary or '-'}",
        f"spec:          {detail.spec_path or '-'}",
        f"report:        {detail.spec_report_path or '-'}",
    ]
    duration_s = (
        f"{detail.duration_ms // 1000}s"
        if detail.duration_ms is not None
        else "?"
    )
    lines.append(
        f"outcome:       {detail.outcome or '-'}  "
        f"model={detail.model or '-'}  duration={duration_s}"
    )
    lines.append(
        f"changed:       +{len(detail.created)} "
        f"~{len(detail.modified)} -{len(detail.deleted)}"
    )
    lines.append(f"created:       {', '.join(detail.created) or '(none)'}")
    lines.append(f"modified:      {', '.join(detail.modified) or '(none)'}")
    lines.append(f"deleted:       {', '.join(detail.deleted) or '(none)'}")
    return "\n".join(lines)


def _cmd_list(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    rows = list_delegations(
        ws,
        limit=args.limit,
        spec_path=args.spec_path,
        file_path=args.file_path,
    )
    if args.json:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
        return 0

    if not rows:
        print("No delegations found.", file=sys.stderr)
        return 0

    for row in rows:
        did = row["delegation_id"]
        ts = row.get("timestamp_end") or row.get("timestamp_start") or "?"
        spec = row.get("spec_path") or "-"
        counts = (
            f"+{row['created_count']}"
            f" ~{row['modified_count']}"
            f" -{row['deleted_count']}"
        )
        summary = row.get("checkpoint_summary") or ""
        line = f"{ts}  {did[:8]}…  {counts}  {spec}"
        if summary:
            line = f"{line}  {summary}"
        print(line)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    did = _resolve_id(ws, args)
    if not did:
        print(
            "error: delegation_id required or use --latest",
            file=sys.stderr,
        )
        return 1

    detail = build_checkpoint_detail(ws, did)
    if detail is None:
        print(f"error: delegation not found: {did}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(detail.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print(_format_show_text(detail))
    return 0


def _cmd_latest(args: argparse.Namespace) -> int:
    args.latest = True
    args.delegation_id = None
    return _cmd_show(args)


def _cmd_diff(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    did = _resolve_id(ws, args)
    if not did:
        print(
            "error: delegation_id required or use --latest",
            file=sys.stderr,
        )
        return 1

    diff = build_delegation_diff(ws, did)
    if diff is None:
        print(f"error: delegation not found: {did}", file=sys.stderr)
        return 1

    if args.path:
        path = normalize_repo_path(args.path)
        if path in diff.diffs:
            print(diff.diffs[path], end="")
            return 0
        if path in diff.created or path in diff.deleted:
            print(f"({path}: {('created' if path in diff.created else 'deleted')}, no diff body)")
            return 0
        print(f"error: path {path!r} not changed in this delegation", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(diff.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if not diff.diffs:
        print("(no unified diffs stored for this delegation)")
        print(f"created: {', '.join(diff.created) or '(none)'}")
        print(f"modified: {', '.join(diff.modified) or '(none)'}")
        print(f"deleted: {', '.join(diff.deleted) or '(none)'}")
        return 0

    for path, text in sorted(diff.diffs.items()):
        print(f"=== {path} ===")
        print(text, end="")
        if not text.endswith("\n"):
            print()
    return 0


def _cmd_file(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    rel = normalize_repo_path(args.file_path)
    changes = build_file_history(ws, rel, limit=args.limit)

    if args.json:
        print(
            json.dumps(
                {"file_path": rel, "changes": changes},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not changes:
        print(f"No history for {rel}.", file=sys.stderr)
        return 0

    for row in changes:
        did = str(row["delegation_id"])
        ts = row.get("timestamp_end") or "?"
        summary = row.get("checkpoint_summary") or "-"
        ctype = row.get("change_type") or "?"
        print(f"{ts}  {did[:8]}…  {ctype}  {summary}")
        if row.get("diff"):
            print(row["diff"], end="")
            if not str(row["diff"]).endswith("\n"):
                print()
    return 0


def _cmd_revert(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    diff = build_delegation_diff(ws, args.delegation_id)
    if diff is None:
        print(f"error: delegation not found: {args.delegation_id}", file=sys.stderr)
        return 1

    target_paths = list(args.paths) if args.paths else diff.all_paths
    if not target_paths:
        print("error: no paths to revert for this delegation", file=sys.stderr)
        return 1

    reverted = revert_to_before(ws, args.delegation_id, target_paths)
    skipped = sorted(set(target_paths) - set(reverted))

    if reverted:
        print("reverted:", ", ".join(reverted))
    if skipped:
        print("skipped:", ", ".join(skipped), file=sys.stderr)

    if not reverted:
        return 1
    return 0


def main_history(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Browse workspace delegation history (SQLite).")
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List recent delegations")
    list_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    list_p.add_argument("--limit", type=int, default=20, help="Max rows (default 20)")
    list_p.add_argument("--spec", dest="spec_path", default=None, help="Filter by spec_path")
    list_p.add_argument("--file", dest="file_path", default=None, help="Filter by file path")
    list_p.add_argument("--json", action="store_true", help="JSON lines output")

    show_p = sub.add_parser("show", help="Checkpoint metadata + file lists (no diffs)")
    show_p.add_argument(
        "delegation_id",
        nargs="?",
        default=None,
        help="Delegation UUID (optional with --latest)",
    )
    show_p.add_argument("--latest", action="store_true", help="Most recent checkpoint")
    show_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    show_p.add_argument("--json", action="store_true", help="JSON output")

    latest_p = sub.add_parser("latest", help="Show most recent checkpoint (shorthand)")
    latest_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    latest_p.add_argument("--json", action="store_true", help="JSON output")

    diff_p = sub.add_parser("diff", help="Show unified diffs for a delegation")
    diff_p.add_argument(
        "delegation_id",
        nargs="?",
        default=None,
        help="Delegation UUID (optional with --latest)",
    )
    diff_p.add_argument("--latest", action="store_true", help="Most recent checkpoint")
    diff_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    diff_p.add_argument("--path", default=None, help="Single file path filter")
    diff_p.add_argument("--json", action="store_true", help="Full delegation_diff JSON")

    file_p = sub.add_parser("file", help="Per-file change timeline across delegations")
    file_p.add_argument("file_path", help="Workspace-relative file path")
    file_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    file_p.add_argument("--limit", type=int, default=20, help="Max rows (default 20)")
    file_p.add_argument("--json", action="store_true", help="JSON output")

    revert_p = sub.add_parser("revert", help="Revert paths to pre-delegation state")
    revert_p.add_argument("delegation_id", help="Delegation UUID")
    revert_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    revert_p.add_argument(
        "--paths",
        nargs="*",
        default=[],
        metavar="PATH",
        help="Paths to revert (default: all changed in delegation)",
    )

    args = parser.parse_args(argv)

    if args.command == "list":
        return _cmd_list(args)
    if args.command == "show":
        return _cmd_show(args)
    if args.command == "latest":
        return _cmd_latest(args)
    if args.command == "diff":
        return _cmd_diff(args)
    if args.command == "file":
        return _cmd_file(args)
    if args.command == "revert":
        return _cmd_revert(args)
    return 1
