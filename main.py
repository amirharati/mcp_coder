"""mcp-coder entry point: MCP server over stdio (for Cursor mcp.json)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="mcp-coder MCP server")
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run MCP server on stdio (default)",
    )
    parser.parse_args()
    from core.config import apply_provider_env, load_env_files
    from core.server.singleton import enforce_single_stdio_server
    from server.mcp_server import run_stdio

    from core.logging.delegation_log import log_brief, log_stderr, workspace_path
    from core.logging.server_log import resolve_config, server_log_emit
    from core.storage.paths import ensure_mcp_coder_home, mcp_coder_home, project_key

    load_env_files()
    apply_provider_env()
    ensure_mcp_coder_home()
    ws = workspace_path()
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
    )
    if log_brief():
        log_stderr(
            f"[mcp-coder] stdio server ready pid={os.getpid()}; home={mcp_coder_home()} "
            f"project_key={project_key(ws)} ws={ws}"
        )
    run_stdio()


if __name__ == "__main__":
    main()
