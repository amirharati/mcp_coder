"""CLI: run delegate pipeline (prepare-only or full pre + executor + post)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.delegation.prepare import prepare_delegation_context
from core.logging.delegation_log import workspace_path


def _parse_target_files(values: list[str]) -> list[str]:
    paths: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                paths.append(part)
    return paths


def main_delegate(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the delegation pipeline from the CLI. "
            "Default: full run (pre + executor + post) — same as delegate_to_agent MCP. "
            "Use --stop-after context for pre-executor artifacts only (no file edits)."
        ),
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Repo root (default: cwd or MCP_CODER workspace resolution)",
    )
    parser.add_argument("--task", required=True, help="Task text (same as delegate_to_agent)")
    parser.add_argument(
        "--target-files",
        action="append",
        default=[],
        metavar="PATH",
        help="Repo-relative path hint; repeatable or comma-separated",
    )
    parser.add_argument(
        "--context-summary",
        default="",
        help="Planner context summary (same as delegate_to_agent)",
    )
    parser.add_argument(
        "--spec",
        dest="spec_path",
        default=None,
        help="Step task spec under .mcp-coder/specs/ (e.g. tasks/foo.md)",
    )
    parser.add_argument(
        "--backend",
        default="aider",
        help="Execution backend (default: aider)",
    )
    parser.add_argument(
        "--mode",
        default="implement",
        choices=("implement", "review"),
        help="Delegate mode (default: implement)",
    )
    parser.add_argument(
        "--stop-after",
        choices=("context",),
        default=None,
        help="Stop after pre-executor compile (no Aider, no JSONL side effects beyond prepare)",
    )
    parser.add_argument(
        "--include-payloads",
        action="store_true",
        help="Include file payloads in context_package.entries (can be large)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON to stdout",
    )
    args = parser.parse_args(argv)

    target_files = _parse_target_files(args.target_files)
    if args.mode == "implement" and not target_files:
        print("error: at least one --target-files path is required for implement mode", file=sys.stderr)
        return 1

    ws = Path(args.workspace) if args.workspace else Path(workspace_path())

    if args.stop_after == "context":
        result = prepare_delegation_context(
            workspace=ws,
            task=args.task,
            target_files=target_files,
            context_summary=args.context_summary or None,
            spec_path=args.spec_path,
            backend=args.backend,
            include_payloads=args.include_payloads,
        )
    else:
        from server.mcp_server import delegate_to_agent

        raw = delegate_to_agent(
            task=args.task,
            target_files=target_files,
            context_summary=args.context_summary,
            backend=args.backend,
            spec_path=args.spec_path,
            mode=args.mode,
            cli_artifacts=True,
        )
        result = json.loads(raw)

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))

    if not result.get("ok"):
        return 1
    return 0
