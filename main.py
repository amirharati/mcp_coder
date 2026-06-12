"""mcp-coder entry point: MCP server over stdio (for Cursor mcp.json)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "inspect-context":
        from core.cli.inspect_context import main_inspect_context

        raise SystemExit(main_inspect_context(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "delegate":
        from core.cli.delegate import main_delegate

        raise SystemExit(main_delegate(sys.argv[2:]))

    parser = argparse.ArgumentParser(description="mcp-coder MCP server and CLI")
    sub = parser.add_subparsers(dest="command")

    setup_p = sub.add_parser(
        "setup",
        help="Print workspace info and the mcp.json block to paste into Cursor",
    )
    setup_target_group = setup_p.add_mutually_exclusive_group()
    setup_target_group.add_argument(
        "--global",
        dest="setup_global",
        action="store_true",
        help="Merge mcp-coder entry into the system-wide Cursor mcp.json",
    )
    setup_target_group.add_argument(
        "--local",
        dest="setup_local",
        action="store_true",
        help="Merge mcp-coder entry into .cursor/mcp.json in the current directory",
    )
    setup_p.add_argument(
        "--init-config",
        action="store_true",
        help="Create .mcp-coder/config.yaml from the bundled example if absent (never overwrites)",
    )

    test_p = sub.add_parser(
        "test-model",
        help="Ping configured AIDER_MODEL via Aider Model (same stack as delegations)",
    )
    test_model_group = test_p.add_mutually_exclusive_group()
    test_model_group.add_argument("--model", help="Override model id")
    test_model_group.add_argument(
        "--all",
        action="store_true",
        help="Test all configured role models (executor, context_builder, review) sequentially",
    )
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

    sub.add_parser(
        "inspect-context",
        help="Dry-run context compiler (assemble + adapter preview, no backend)",
    )
    sub.add_parser(
        "delegate",
        help="Run delegation pipeline (full or --stop-after context for prepare-only)",
    )

    view_p = sub.add_parser(
        "view",
        help="Open browser UIs for inspection (subcommands: delegations, …)",
    )
    view_sub = view_p.add_subparsers(dest="view_command", required=True)
    deleg_view_p = view_sub.add_parser(
        "delegations",
        help="Delegation log browser (delegations.jsonl)",
    )
    deleg_view_p.add_argument(
        "log_file",
        nargs="?",
        help="Path to delegations.jsonl (default: merged logs for cwd workspace)",
    )
    deleg_view_p.add_argument(
        "--workspace",
        "-w",
        help="Project root (default: cwd when log_file omitted)",
    )
    deleg_view_p.add_argument("--port", "-p", type=int, default=8765)
    deleg_view_p.add_argument("--no-open", action="store_true", help="Do not open browser")

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

    if args.command == "setup":
        from core.cli.setup import run_setup

        write_target = None
        if args.setup_global:
            write_target = "global"
        elif args.setup_local:
            write_target = "local"
        raise SystemExit(run_setup(init_config=args.init_config, write_target=write_target))

    if args.command == "test-model":
        from core.cli.test_model import (
            print_test_all_result,
            print_test_result,
            run_test_model,
            run_test_model_all,
        )

        if args.all:
            rows = run_test_model_all(
                prompt=args.prompt,
                max_tokens=args.max_tokens,
                via=args.via,
            )
            raise SystemExit(print_test_all_result(rows))

        result = run_test_model(
            model=args.model,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            via=args.via,
        )
        print_test_result(result)
        raise SystemExit(0 if result.ok else 1)

    if args.command == "view":
        if args.view_command == "delegations":
            from core.cli.view_delegations import run_view

            if args.log_file and args.workspace:
                parser.error("view delegations: provide log_file or --workspace, not both")
            run_view(
                log_file=args.log_file,
                workspace=args.workspace,
                port=args.port,
                no_open=args.no_open,
            )
            raise SystemExit(0)
        parser.error(f"unknown view subcommand: {args.view_command}")

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

    # Bare invocation from an interactive terminal: the stdio server would just
    # sit waiting for JSON-RPC on stdin (looks like a hang). Cursor runs us with
    # pipes, so a TTY means a human — show help instead. --mcp forces the server.
    if not args.mcp and sys.stdin.isatty():
        parser.print_help()
        print(
            "\nNo subcommand given. The MCP stdio server only starts when run by an"
            " MCP client (e.g. Cursor) or with --mcp.",
            file=sys.stderr,
        )
        raise SystemExit(2)

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
