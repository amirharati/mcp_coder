"""mcp-coder entry point: MCP server over stdio (for Cursor mcp.json)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="mcp-coder MCP server and CLI")
    sub = parser.add_subparsers(dest="command")

    test_p = sub.add_parser(
        "test-model",
        help="Ping configured AIDER_MODEL via Aider Model (same stack as delegations)",
    )
    test_p.add_argument("--model", help="Override model id")
    test_p.add_argument(
        "--prompt",
        default="Reply with exactly: ok",
        help="User message for the ping",
    )
    test_p.add_argument("--max-tokens", type=int, default=16, help="litellm pass only")
    test_p.add_argument(
        "--via",
        choices=("aider", "litellm", "both"),
        default="aider",
        help="aider (default) = Model.send_completion; litellm = raw completion; both = compare",
    )

    inspect_p = sub.add_parser(
        "inspect-context",
        help="Dry-run context compiler (assemble + adapter preview, no backend)",
    )
    inspect_p.add_argument(
        "--workspace",
        default=None,
        help="Repo root (default: cwd or MCP_CODER workspace resolution)",
    )
    inspect_p.add_argument("--task", required=True, help="Task text")
    inspect_p.add_argument(
        "--target-files",
        action="append",
        default=[],
        metavar="PATH",
        help="Repo-relative path hint; repeatable or comma-separated",
    )
    inspect_p.add_argument("--context-summary", default="", help="Planner context summary")
    inspect_p.add_argument(
        "--spec",
        dest="spec_path",
        default=None,
        help="Step task spec under .mcp-coder/specs/",
    )
    inspect_p.add_argument(
        "--include-payloads",
        action="store_true",
        help="Include file payloads in entries",
    )
    inspect_p.add_argument(
        "--no-adapter-preview",
        action="store_true",
        help="Omit adapter_preview",
    )
    inspect_p.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    history_p = sub.add_parser(
        "history",
        help="Browse workspace_history.db (list, diff, revert)",
    )
    history_p.add_argument(
        "history_args",
        nargs=argparse.REMAINDER,
        help="history subcommand: list | diff | revert",
    )

    rag_p = sub.add_parser(
        "rag",
        help="Delegation RAG search and index (SQLite FTS5)",
    )
    rag_p.add_argument(
        "rag_args",
        nargs=argparse.REMAINDER,
        help="rag subcommand: search | index | stats",
    )

    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run MCP server on stdio (default when no subcommand)",
    )
    args = parser.parse_args()

    if args.command == "test-model":
        from core.cli.test_model import print_test_result, run_test_model

        result = run_test_model(
            model=args.model,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            via=args.via,
        )
        print_test_result(result)
        raise SystemExit(0 if result.ok else 1)

    if args.command == "inspect-context":
        from core.cli.inspect_context import main_inspect_context

        raise SystemExit(main_inspect_context(sys.argv[2:]))

    if args.command == "history":
        from core.cli.history import main_history

        history_argv = args.history_args or []
        if history_argv and history_argv[0] == "--":
            history_argv = history_argv[1:]
        raise SystemExit(main_history(history_argv))

    if args.command == "rag":
        from core.cli.rag import main_rag

        rag_argv = args.rag_args or []
        if rag_argv and rag_argv[0] == "--":
            rag_argv = rag_argv[1:]
        raise SystemExit(main_rag(rag_argv))

    from core.config import apply_provider_env, load_env_files
    from core.server.singleton import enforce_single_stdio_server
    from server.mcp_server import run_stdio

    from core.logging.delegation_log import log_brief, log_stderr, workspace_path
    from core.logging.server_log import resolve_config, server_log_emit
    from core.host.cursor_rules import sync_workspace_cursor_rules
    from core.specs.bootstrap import ensure_workspace_spec_layout
    from core.storage.paths import ensure_mcp_coder_home, mcp_coder_home, project_key

    load_env_files()
    apply_provider_env()
    ensure_mcp_coder_home()
    ws = workspace_path()
    spec_layout = ensure_workspace_spec_layout(ws)
    rule_sync = sync_workspace_cursor_rules(ws)
    enforce_single_stdio_server(ws, main_script=str(Path(__file__).resolve()))
    log_cfg = resolve_config(ws)
    host_raw = os.environ.get("MCP_CODER_HOST", "auto").strip() or "auto"
    from core.session.policy import resolve_session_policy

    server_log_emit(
        "stdio_server_ready",
        level="info",
        workspace_path=ws,
        mcp_coder_home=str(mcp_coder_home()),
        host_provider=host_raw,
        session_policy=resolve_session_policy(ws),
        singleton_enabled=os.environ.get("MCP_CODER_SINGLETON", "1").strip().lower()
        not in ("0", "false", "no", "off"),
        server_log_scope=log_cfg.scope,
        server_log_level=log_cfg.level,
        spec_template_path=spec_layout.get("spec_template_path"),
        spec_template_created=spec_layout.get("spec_template_created"),
        cursor_rules_skipped=rule_sync.get("skipped"),
        cursor_rules_skip_reason=rule_sync.get("reason"),
        cursor_rules_policy=rule_sync.get("policy"),
        cursor_rules_created=rule_sync.get("created_count"),
        cursor_rules_updated=rule_sync.get("updated_count"),
        cursor_rules_removed=rule_sync.get("removed"),
        cursor_rules=rule_sync.get("rules"),
    )
    if log_brief():
        log_stderr(
            f"[mcp-coder] stdio server ready pid={os.getpid()}; home={mcp_coder_home()} "
            f"project_key={project_key(ws)} ws={ws}"
        )
    run_stdio()


if __name__ == "__main__":
    main()
