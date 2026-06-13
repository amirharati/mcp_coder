"""CLI: unified search commands (P5-002)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from core.rag.retrieval import (
    CORPUS_DELEGATION,
    CORPUS_WORKSPACE_FILES,
    context_refs_to_dict,
    retrieve,
)
from core.rag.search import rag_search_for_mcp
from core.rag.workspace_search import workspace_search_for_mcp


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


def _format_plain_line(ref_dict: dict) -> str:
    meta = ref_dict.get("metadata") or {}
    spec = meta.get("spec_path") or "?"
    outcome = meta.get("outcome") or "?"
    snippet = (ref_dict.get("snippet") or "").strip()
    return f"Prior delegation {spec} ({outcome}): {snippet}"


def _cmd_search_delegations(args: argparse.Namespace) -> int:
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

    refs = retrieve(
        ws,
        args.query,
        corpus=CORPUS_DELEGATION,
        k=args.limit,
        spec_path_prefix=args.spec_path_prefix,
        outcome=args.outcome,
    )
    if not refs:
        print("No hits.", file=sys.stderr)
        return 1

    ref_dicts = context_refs_to_dict(refs)
    if args.format == "plain":
        lines = [_format_plain_line(d) for d in ref_dicts]
        print("\n\n".join(lines))
        return 0

    for ref, hit in zip(refs, ref_dicts):
        ts = (hit.get("metadata") or {}).get("timestamp_end") or "?"
        spec = (hit.get("metadata") or {}).get("spec_path") or "-"
        summary = hit.get("snippet") or ""
        score = ref.score if ref.score is not None else 0.0
        line = f"{score:.3f}  {ts}  {ref.id[:8]}…  {spec}"
        if summary:
            line = f"{line}  {summary}"
        print(line)
    return 0


def _format_workspace_plain_line(hit: dict) -> str:
    path = hit.get("id") or (hit.get("metadata") or {}).get("path") or "?"
    score = hit.get("score")
    score_text = f"{score:.2f}" if isinstance(score, (int, float)) else "?"
    snippet = (hit.get("snippet") or "").strip()
    return f"{path} (score {score_text}): {snippet}"


def _cmd_search_files(args: argparse.Namespace) -> int:
    ws = _resolve_workspace(args.workspace)
    if args.json:
        payload = workspace_search_for_mcp(ws, args.query, limit=args.limit)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if not payload.get("found"):
            return 1
        return 0

    refs = retrieve(ws, args.query, corpus=CORPUS_WORKSPACE_FILES, k=args.limit)
    if not refs:
        print("No hits.", file=sys.stderr)
        return 1

    hit_dicts = context_refs_to_dict(refs)
    if args.format == "plain":
        lines = [_format_workspace_plain_line(h) for h in hit_dicts]
        print("\n\n".join(lines))
        return 0

    for ref, hit in zip(refs, hit_dicts):
        score = ref.score if ref.score is not None else 0.0
        summary = hit.get("snippet") or ""
        line = f"{score:.3f}  {ref.id}"
        if summary:
            line = f"{line}  {summary}"
        print(line)
    return 0


def main_search(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search indexed project context.")
    sub = parser.add_subparsers(dest="command", required=True)

    deleg_p = sub.add_parser(
        "delegations",
        help="Keyword search indexed delegations (same backend as rag_search MCP)",
    )
    deleg_p.add_argument("query", help="Search query (min 2 chars)")
    deleg_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    deleg_p.add_argument("--limit", type=int, default=5, help="Max hits (default 5)")
    deleg_p.add_argument(
        "--spec-prefix",
        dest="spec_path_prefix",
        default=None,
        help="Filter spec_path prefix",
    )
    deleg_p.add_argument("--outcome", default=None, help="Filter by outcome")
    deleg_p.add_argument(
        "--format",
        choices=("table", "plain"),
        default="table",
        help="Output format (default: table)",
    )
    deleg_p.add_argument("--json", action="store_true", help="JSON output (MCP shape)")

    files_p = sub.add_parser(
        "files",
        help="Keyword search indexed workspace files (same backend as workspace_search MCP)",
    )
    files_p.add_argument("query", help="Search query (min 2 chars)")
    files_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    files_p.add_argument("--limit", type=int, default=5, help="Max hits (default 5)")
    files_p.add_argument(
        "--format",
        choices=("table", "plain"),
        default="table",
        help="Output format (default: table)",
    )
    files_p.add_argument("--json", action="store_true", help="JSON output (MCP shape)")

    args = parser.parse_args(argv)

    if args.command == "delegations":
        return _cmd_search_delegations(args)
    if args.command == "files":
        return _cmd_search_files(args)
    return 1
