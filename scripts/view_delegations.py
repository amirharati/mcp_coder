#!/usr/bin/env python3
"""Serve a small UI to review delegations.jsonl. Opens your browser."""

from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
VIEWER_HTML = ROOT / "tools" / "delegation_viewer.html"


def resolve_log_source(path: str | None, workspace: str | None) -> tuple[Path | None, str | None]:
    """Return (single log path, workspace) for the viewer API."""
    if path:
        return Path(path).expanduser().resolve(), None
    if workspace:
        return None, str(Path(workspace).expanduser().resolve())
    raise SystemExit("Provide LOG_FILE or --workspace")


class ViewerHandler(BaseHTTPRequestHandler):
    log_path: Path | None = None
    workspace: str | None = None

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # quiet server

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/delegations":
            from core.logging.read_delegations import (
                load_delegations,
                load_delegations_for_workspace,
            )

            try:
                if self.workspace:
                    records = load_delegations_for_workspace(self.workspace)
                    label = f"home store for {self.workspace}"
                else:
                    assert self.log_path is not None
                    records = load_delegations(self.log_path)
                    label = str(self.log_path)
                self._send_json(
                    {
                        "path": label,
                        "count": len(records),
                        "records": records,
                    }
                )
            except FileNotFoundError as exc:
                self._send_json({"error": str(exc)}, 404)
            except json.JSONDecodeError as exc:
                self._send_json({"error": f"Invalid JSONL: {exc}"}, 400)
            return

        if parsed.path in ("/", "/index.html"):
            if not VIEWER_HTML.is_file():
                self._send_json({"error": "Viewer HTML missing"}, 500)
                return
            body = VIEWER_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404)


def main() -> None:
    parser = argparse.ArgumentParser(description="Review mcp-coder delegations.jsonl")
    parser.add_argument(
        "log_file",
        nargs="?",
        help="Path to delegations.jsonl",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        help="Project root; loads all session logs from MCP_CODER_HOME (or legacy fallback)",
    )
    parser.add_argument("--port", "-p", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Do not open browser")
    args = parser.parse_args()

    log_path, workspace = resolve_log_source(args.log_file, args.workspace)
    ViewerHandler.log_path = log_path
    ViewerHandler.workspace = workspace

    server = ThreadingHTTPServer(("127.0.0.1", args.port), ViewerHandler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"[mcp-coder] Delegation viewer: {url}")
    if workspace:
        print(f"[mcp-coder] Workspace: {workspace} (home store, merged session logs)")
    else:
        print(f"[mcp-coder] Log file: {log_path}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mcp-coder] Stopped.")


if __name__ == "__main__":
    main()
