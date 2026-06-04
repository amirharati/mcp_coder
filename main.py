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
    from core.storage.paths import ensure_mcp_coder_home, mcp_coder_home, project_key

    load_env_files()
    apply_provider_env()
    ensure_mcp_coder_home()
    ws = workspace_path()
    enforce_single_stdio_server(ws, main_script=str(Path(__file__).resolve()))
    if log_brief():
        log_stderr(
            f"[mcp-coder] stdio server ready pid={os.getpid()}; home={mcp_coder_home()} "
            f"project_key={project_key(ws)} ws={ws}"
        )
    run_stdio()


if __name__ == "__main__":
    main()
