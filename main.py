"""mcp-coder entry point: MCP server over stdio (for Cursor mcp.json)."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path


def _bootstrap_cli_env() -> None:
    """Load repo .env and normalize provider env (shared by stdio server and delegate CLI)."""
    from core.config import apply_provider_env, load_env_files

    load_env_files()
    apply_provider_env()


def _is_client_disconnect(exc: Exception) -> bool:
    """Detect benign MCP client disconnects (Cursor closed the stdio pipe).

    B012/B011: when a long delegation times out on the client side, Cursor
    closes the connection. The MCP SDK raises BrokenResourceError wrapped in
    an ExceptionGroup. This is NOT a server bug — exit gracefully.
    """
    # Direct BrokenResourceError.
    try:
        import anyio  # type: ignore

        if isinstance(exc, anyio.BrokenResourceError):
            return True
    except Exception:
        pass
    # ExceptionGroup wrapping BrokenResourceError (the common case).
    if hasattr(exc, "exceptions"):
        for sub in exc.exceptions:  # type: ignore[attr-defined]
            if _is_client_disconnect(sub):
                return True
    # String fallback: match by class name in case anyio import is unavailable.
    exc_name = type(exc).__name__
    if exc_name == "BrokenResourceError":
        return True
    exc_str = str(exc)
    if "BrokenResourceError" in exc_str or "broken pipe" in exc_str.lower():
        return True
    return False


def _flush_inflight_delegation_state(workspace: str) -> None:
    """P15-ISS-012: write a crash marker so the next session can detect orphaned writes.

    When the server dies mid-delegation, the executor may have written partial
    files to disk with no completed delegation record. This writes a marker file
    that the next session can check to surface orphaned state.

    Failure-tolerant: never raises — if any step fails, we silently skip the
    marker so the exit handler itself cannot crash.
    """
    import json
    import time

    try:
        from core.storage.paths import mcp_coder_home, project_key

        pk = project_key(workspace)
        marker_dir = Path(mcp_coder_home()) / "projects" / pk
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker_path = marker_dir / "last_crash.json"

        marker = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid": os.getpid(),
            "workspace": workspace,
            "reason": "client_disconnect",
        }
        marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    except Exception:
        pass


def _reconcile_on_startup(workspace: str) -> None:
    """P15-019: backfill orphaned delegations (timestamp_end IS NULL) on startup.

    Gated by MCP_CODER_RECONCILE_ON_STARTUP (default on). Failure-tolerant: a
    crash here must never block server startup, so all errors are swallowed
    and logged via server_log_emit.
    """
    try:
        from core.workspace.snapshot import (
            is_reconcile_on_startup_enabled,
            reconcile_interrupted_delegations,
        )

        if not is_reconcile_on_startup_enabled():
            return
        summaries = reconcile_interrupted_delegations(workspace)
        if summaries:
            from core.logging.server_log import server_log_emit

            server_log_emit(
                "delegation_reconcile_pass",
                level="info",
                workspace_path=workspace,
                reconciled_count=len(summaries),
                delegations=[s["delegation_id"] for s in summaries],
            )
    except Exception as exc:
        try:
            from core.logging.server_log import server_log_emit

            server_log_emit(
                "delegation_reconcile_startup_failed",
                level="warn",
                workspace_path=workspace,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            pass


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "inspect-context":
        from core.cli.inspect_context import main_inspect_context

        raise SystemExit(main_inspect_context(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "delegate":
        _bootstrap_cli_env()
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
    replay_p = sub.add_parser(
        "replay",
        help="Replay one delegation from disk artifacts (JSONL + trace + context blob)",
    )
    replay_p.add_argument("delegation_id", help="Delegation ID to replay")
    replay_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    replay_p.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human)",
    )

    compare_p = sub.add_parser(
        "compare",
        help="Compare backend_llm_call vs proxy_llm_call events for one delegation",
    )
    compare_p.add_argument("delegation_id", help="Delegation ID to compare")
    compare_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    compare_p.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human)",
    )

    trace_p = sub.add_parser(
        "trace",
        help="Inspect delegation trace events",
    )
    trace_sub = trace_p.add_subparsers(dest="trace_command", required=True)
    inspect_p = trace_sub.add_parser(
        "inspect",
        help="Dump events from a delegation trace",
    )
    inspect_p.add_argument("delegation_id")
    inspect_p.add_argument("--workspace", default=None)
    inspect_p.add_argument(
        "--type",
        default=None,
        dest="event_type",
        help="Filter to events of this type",
    )
    inspect_p.add_argument(
        "--event",
        type=int,
        default=None,
        help="Select Nth matching event (1-based)",
    )
    inspect_p.add_argument(
        "--field",
        default=None,
        help="Print only this field from each event",
    )
    inspect_p.add_argument("--format", choices=("human", "json"), default="human")

    logs_p = sub.add_parser(
        "logs",
        help="Log utilities (subcommands: tail)",
    )
    logs_sub = logs_p.add_subparsers(dest="logs_command", required=True)
    logs_tail_p = logs_sub.add_parser(
        "tail",
        help="Tail delegation trace events in real time",
    )
    logs_tail_target = logs_tail_p.add_mutually_exclusive_group()
    logs_tail_target.add_argument(
        "--latest",
        action="store_true",
        help="Tail the most recent delegation trace (default).",
    )
    logs_tail_target.add_argument(
        "--delegation-id",
        default=None,
        help="Tail this specific delegation trace id.",
    )
    logs_tail_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    logs_tail_p.add_argument("--format", choices=("human", "json"), default="human")
    logs_tail_p.add_argument(
        "--poll-interval-s",
        type=float,
        default=0.5,
        help="File polling interval in seconds (default: 0.5)",
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

    search_p = sub.add_parser(
        "search",
        help="Search indexed project context",
    )
    search_p.add_argument(
        "search_args",
        nargs=argparse.REMAINDER,
        help="search subcommand: delegations | files",
    )

    index_ws_p = sub.add_parser(
        "index-workspace",
        help="Index workspace source files into workspace_rag.db (FTS5)",
    )
    index_ws_p.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    index_ws_p.add_argument(
        "--changed-only",
        action="store_true",
        help="Re-index only new/changed files",
    )
    index_ws_p.add_argument("--limit", type=int, default=None, help="Max files to index")
    index_ws_p.add_argument("--json", action="store_true", help="JSON summary output")

    maintenance_p = sub.add_parser(
        "maintenance",
        help="Observability storage stats and maintenance (subcommands: stats)",
    )
    maintenance_p.add_argument(
        "maintenance_args",
        nargs=argparse.REMAINDER,
        help="maintenance subcommand: stats",
    )

    cost_p = sub.add_parser(
        "cost",
        help="Show per-project cost report from delegation logs",
    )
    cost_p.add_argument("--workspace", "-w", default=None, help="Repo root (default: cwd)")
    cost_p.add_argument("--project", "-p", default=None, dest="project_key", help="Filter to project_key")
    cost_p.add_argument("--limit", "-n", type=int, default=None, help="Max delegations to read")
    cost_p.add_argument("--json", action="store_true", dest="json_output", help="Raw JSON output")

    sub.add_parser(
        "ps",
        help="List running mcp-coder stdio server processes",
    )
    sub.add_parser(
        "status",
        help="Check mcp-coder stdio freshness and multi-instance state",
    )
    kill_p = sub.add_parser(
        "kill",
        help="Kill mcp-coder stdio server(s); default scope is current workspace",
    )
    kill_p.add_argument(
        "--all",
        action="store_true",
        help="Kill all mcp-coder stdio server processes across workspaces",
    )
    kill_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace path scope for kill (default: current workspace)",
    )
    kill_p.add_argument(
        "--min-age-seconds",
        type=float,
        default=0.0,
        help="Only kill processes older than this many seconds",
    )

    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run MCP server on stdio (default when no subcommand)",
    )
    args = parser.parse_args()

    if args.command == "delegate":
        _bootstrap_cli_env()
        from core.cli.delegate import main_delegate

        delegate_argv = sys.argv[sys.argv.index("delegate") + 1 :]
        raise SystemExit(main_delegate(delegate_argv))

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

    if args.command == "search":
        from core.cli.search import main_search

        search_argv = args.search_args or []
        if search_argv and search_argv[0] == "--":
            search_argv = search_argv[1:]
        raise SystemExit(main_search(search_argv))

    if args.command == "index-workspace":
        from core.cli.index_workspace import main_index_workspace

        index_argv: list[str] = []
        if args.workspace:
            index_argv.extend(["--workspace", args.workspace])
        if args.changed_only:
            index_argv.append("--changed-only")
        if args.limit is not None:
            index_argv.extend(["--limit", str(args.limit)])
        if args.json:
            index_argv.append("--json")
        raise SystemExit(main_index_workspace(index_argv))

    if args.command == "maintenance":
        from core.cli.maintenance import main_maintenance

        maintenance_argv = args.maintenance_args or []
        if maintenance_argv and maintenance_argv[0] == "--":
            maintenance_argv = maintenance_argv[1:]
        raise SystemExit(main_maintenance(maintenance_argv))

    if args.command == "cost":
        _bootstrap_cli_env()
        from core.cli.cost import main_cost

        cost_argv: list[str] = []
        if args.workspace:
            cost_argv.extend(["--workspace", args.workspace])
        if args.project_key:
            cost_argv.extend(["--project", args.project_key])
        if args.limit is not None:
            cost_argv.extend(["--limit", str(args.limit)])
        if args.json_output:
            cost_argv.append("--json")
        raise SystemExit(main_cost(cost_argv))

    if args.command == "ps":
        from core.cli.mcp_process import cmd_ps

        raise SystemExit(cmd_ps())

    if args.command == "status":
        from core.cli.mcp_process import cmd_status

        raise SystemExit(cmd_status())

    if args.command == "kill":
        from core.cli.mcp_process import cmd_kill

        raise SystemExit(
            cmd_kill(
                all_processes=args.all,
                workspace=args.workspace,
                min_age_seconds=args.min_age_seconds,
            )
        )

    if args.command == "replay":
        from core.cli.replay import main_replay

        replay_argv: list[str] = [args.delegation_id]
        if args.workspace:
            replay_argv.extend(["--workspace", args.workspace])
        if args.format:
            replay_argv.extend(["--format", args.format])
        raise SystemExit(main_replay(replay_argv))

    if args.command == "compare":
        from core.cli.compare import main_compare

        compare_argv: list[str] = [args.delegation_id]
        if args.workspace:
            compare_argv.extend(["--workspace", args.workspace])
        if args.format:
            compare_argv.extend(["--format", args.format])
        raise SystemExit(main_compare(compare_argv))

    if args.command == "trace":
        from core.cli.trace_inspect import main_trace_inspect

        trace_argv = sys.argv[sys.argv.index("trace") :]
        raise SystemExit(main_trace_inspect(trace_argv))

    if args.command == "logs":
        if args.logs_command == "tail":
            from core.cli.logs_tail import main_logs_tail

            logs_argv = sys.argv[sys.argv.index("tail") + 1 :]
            raise SystemExit(main_logs_tail(logs_argv))
        parser.error(f"unknown logs subcommand: {args.logs_command}")

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
    from core.server.singleton import register_stdio_server
    from server.mcp_server import run_stdio

    from core.logging.delegation_log import log_brief, log_stderr, workspace_path
    from core.logging.server_log import resolve_config, server_log_emit
    from core.host.cursor_rules import sync_workspace_cursor_rules
    from core.specs.bootstrap import ensure_workspace_spec_layout
    from core.storage.paths import ensure_mcp_coder_home, mcp_coder_home, project_key

    ws: str | None = None
    try:
        _bootstrap_cli_env()
        ensure_mcp_coder_home()
        ws = workspace_path()
        spec_layout = ensure_workspace_spec_layout(ws)
        rule_sync = sync_workspace_cursor_rules(ws)
        register_stdio_server(ws)
        # P15-019: reconcile orphaned delegations (timestamp_end IS NULL) left
        # behind by a previous crash. Gated by MCP_CODER_RECONCILE_ON_STARTUP.
        _reconcile_on_startup(ws)
        log_cfg = resolve_config(ws)
        host_raw = os.environ.get("MCP_CODER_HOST", "auto").strip() or "auto"
        from core.session.policy import resolve_session_policy

        from core.version import repo_root, source_revision

        server_log_emit(
            "stdio_server_ready",
            level="info",
            workspace_path=ws,
            mcp_coder_home=str(mcp_coder_home()),
            source_root=str(repo_root()),
            source_revision=source_revision(),
            host_provider=host_raw,
            session_policy=resolve_session_policy(ws),
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
                f"[mcp-coder] stdio server ready pid={os.getpid()}; "
                f"source={repo_root()}@{source_revision()}; "
                f"home={mcp_coder_home()} project_key={project_key(ws)} ws={ws}"
            )
        run_stdio()
    except Exception as exc:
        tb = traceback.format_exc(limit=8)

        # B012/B011 fix: BrokenResourceError means the MCP client (Cursor)
        # closed the stdio pipe — usually because a long delegation timed out
        # on the client side. This is a benign disconnect, NOT a server bug.
        # Exit gracefully instead of crashing and leaving orphaned state.
        _is_disconnect = _is_client_disconnect(exc)
        try:
            server_log_emit(
                "stdio_server_start_failed",
                level="warn" if _is_disconnect else "error",
                workspace_path=ws,
                error=str(exc),
                traceback=tb,
                client_disconnect=_is_disconnect,
            )
            # P15-ISS-012: capture in-flight delegation state before exit so the
            # next session can detect orphaned partial writes.
            if _is_disconnect:
                _flush_inflight_delegation_state(ws)
        except Exception:
            pass
        if log_brief():
            if _is_disconnect:
                log_stderr(f"[mcp-coder] stdio client disconnected (benign): {exc}")
            else:
                log_stderr(f"[mcp-coder] stdio startup failed: {exc}\n{tb}")
        # Benign disconnect: exit 0 so the host restarts cleanly.
        # Real errors: re-raise so the exit code reflects failure.
        if _is_disconnect:
            raise SystemExit(0)
        raise


if __name__ == "__main__":
    main()
