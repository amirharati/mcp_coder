"""CLI: observability maintenance and storage stats (P6-005)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from core.observability.stats import collect_observability_stats


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


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
    return 0


def main_maintenance(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observability maintenance and storage stats.")
    sub = parser.add_subparsers(dest="command", required=True)

    stats_p = sub.add_parser("stats", help="Report RAG rows, trace files, and JSONL disk usage")
    stats_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    stats_p.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args(argv)
    if args.command == "stats":
        return _cmd_stats(args)
    print(f"unknown maintenance subcommand: {args.command}", file=sys.stderr)
    return 1
