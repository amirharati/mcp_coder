"""CLI: browse workspace_history.db checkpoints."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from core.workspace.history_query import build_delegation_diff, list_delegations
from core.workspace.revert import revert_to_before


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


def _cmd_list(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    rows = list_delegations(ws, limit=args.limit, spec_path=args.spec_path)
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
        print(f"{ts}  {did[:8]}…  {counts}  {spec}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    diff = build_delegation_diff(ws, args.delegation_id)
    if diff is None:
        print(f"error: delegation not found: {args.delegation_id}", file=sys.stderr)
        return 1

    if args.path:
        path = args.path
        if path not in diff.diffs:
            print(f"error: no diff for path {path!r}", file=sys.stderr)
            return 1
        print(diff.diffs[path], end="")
        return 0

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
    list_p.add_argument("--json", action="store_true", help="JSON lines output")

    diff_p = sub.add_parser("diff", help="Show unified diffs for a delegation")
    diff_p.add_argument("delegation_id", help="Delegation UUID")
    diff_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    diff_p.add_argument("--path", default=None, help="Single file path filter")
    diff_p.add_argument("--json", action="store_true", help="Full delegation_diff JSON")

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
    if args.command == "diff":
        return _cmd_diff(args)
    if args.command == "revert":
        return _cmd_revert(args)
    return 1
