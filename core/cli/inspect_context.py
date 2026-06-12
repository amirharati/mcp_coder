"""CLI: dry-run context compiler inspection (no backend execution)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.context.inspect import inspect_context_package
from core.logging.delegation_log import workspace_path


def _parse_target_files(values: list[str]) -> list[str]:
    paths: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                paths.append(part)
    return paths


def main_inspect_context(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run context compiler: assemble ContextPackage and adapter preview "
            "without calling the execution backend. Optional helper LLM phases "
            "(builder, architect, spec validation) call configured model roles and "
            "may incur API cost."
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
        "--include-payloads",
        action="store_true",
        help="Include file payloads in context_package.entries (can be large)",
    )
    parser.add_argument(
        "--no-adapter-preview",
        action="store_true",
        help="Omit adapter_preview (fnames + prompt stats)",
    )
    parser.add_argument(
        "--run-builder-llm",
        action="store_true",
        help="Run context-builder LLM (opt-in; may incur API cost)",
    )
    parser.add_argument(
        "--run-architect",
        action="store_true",
        help="Run architect pass LLM (opt-in; may incur API cost)",
    )
    parser.add_argument(
        "--run-spec-validation",
        action="store_true",
        help="Run pre-delegate spec validation LLM (opt-in; may incur API cost)",
    )
    parser.add_argument(
        "--run-all-helpers",
        action="store_true",
        help="Shorthand for --run-builder-llm, --run-architect, and --run-spec-validation",
    )
    parser.add_argument(
        "--host-transcript-file",
        metavar="PATH",
        default=None,
        help="Read host transcript from file (for validation/architect)",
    )
    parser.add_argument(
        "--force-helpers",
        action="store_true",
        help="Run requested helpers even when disabled in workspace config.yaml",
    )
    parser.add_argument(
        "--fail-on-validation-block",
        action="store_true",
        help="Exit code 2 when spec validation would block a real delegate (default: 0)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON to stdout",
    )
    args = parser.parse_args(argv)

    target_files = _parse_target_files(args.target_files)
    if not target_files:
        print("error: at least one --target-files path is required", file=sys.stderr)
        return 1

    ws = Path(args.workspace) if args.workspace else Path(workspace_path())

    host_transcript: str | None = None
    if args.host_transcript_file:
        host_transcript = Path(args.host_transcript_file).read_text(encoding="utf-8")

    run_builder = args.run_builder_llm or args.run_all_helpers
    run_architect = args.run_architect or args.run_all_helpers
    run_spec_validation = args.run_spec_validation or args.run_all_helpers

    result = inspect_context_package(
        workspace=ws,
        task=args.task,
        target_files=target_files,
        context_summary=args.context_summary or None,
        spec_path=args.spec_path,
        include_payloads=args.include_payloads,
        include_adapter_preview=not args.no_adapter_preview,
        host_transcript=host_transcript,
        run_builder_llm=run_builder,
        run_architect=run_architect,
        run_spec_validation=run_spec_validation,
        force_helpers=args.force_helpers,
    )

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))

    if not result.get("ok"):
        return 1

    if args.fail_on_validation_block:
        sv = (result.get("helper_phases") or {}).get("spec_validation") or {}
        if sv.get("would_block_delegate"):
            return 2

    return 0
