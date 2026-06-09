"""CLI: delegation RAG search and backfill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from core.rag.index import backfill_from_history
from core.rag.search import rag_search, rag_search_for_mcp, rag_stats


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


def _cmd_search(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    if args.json:
        payload = rag_search_for_mcp(
            ws,
            args.query,
            limit=args.limit,
            spec_path_prefix=args.spec_path_prefix,
            outcome=args.outcome,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if not payload.get("found"):
            return 1
        return 0

    hits = rag_search(
        ws,
        args.query,
        limit=args.limit,
        spec_path_prefix=args.spec_path_prefix,
        outcome=args.outcome,
    )
    if not hits:
        print("No hits.", file=sys.stderr)
        return 1

    for hit in hits:
        ts = hit.timestamp_end or "?"
        spec = hit.spec_path or "-"
        summary = hit.checkpoint_summary or ""
        line = f"{hit.score:.3f}  {ts}  {hit.delegation_id[:8]}…  {spec}"
        if summary:
            line = f"{line}  {summary}"
        print(line)
    return 0


def _cmd_index(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    count = backfill_from_history(ws)
    if args.json:
        print(json.dumps({"indexed": count}, ensure_ascii=False))
    else:
        print(f"Indexed {count} delegation(s) from workspace_history.db")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    stats = rag_stats(ws)
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        if not stats.get("enabled"):
            print("RAG disabled for this workspace.")
            return 0
        print(f"rows:          {stats.get('row_count', 0)}")
        print(f"last_indexed:  {stats.get('last_indexed') or '-'}")
        print(f"db_path:       {stats.get('db_path') or '-'}")
    return 0


def main_rag(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delegation RAG (SQLite FTS5).")
    sub = parser.add_subparsers(dest="command", required=True)

    search_p = sub.add_parser("search", help="Keyword search indexed delegations")
    search_p.add_argument("query", help="Search query (min 2 chars)")
    search_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    search_p.add_argument("--limit", type=int, default=5, help="Max hits (default 5)")
    search_p.add_argument(
        "--spec-prefix",
        dest="spec_path_prefix",
        default=None,
        help="Filter spec_path prefix",
    )
    search_p.add_argument("--outcome", default=None, help="Filter by outcome")
    search_p.add_argument("--json", action="store_true", help="JSON output")

    index_p = sub.add_parser("index", help="Backfill from workspace_history.db")
    index_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    index_p.add_argument("--json", action="store_true", help="JSON output")

    stats_p = sub.add_parser("stats", help="Row count and last indexed timestamp")
    stats_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    stats_p.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args(argv)

    if args.command == "search":
        return _cmd_search(args)
    if args.command == "index":
        return _cmd_index(args)
    if args.command == "stats":
        return _cmd_stats(args)
    return 1
