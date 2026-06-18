"""CLI: mcp-coder view delegations — serve delegation log browser UI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.cli.delegation_view_enrich import enrich_delegation_record

_REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWER_HTML = _REPO_ROOT / "tools" / "delegation_viewer.html"


def _mcp_coder_home() -> Path:
    raw = os.environ.get("MCP_CODER_HOME", "~/.mcp-coder")
    return Path(os.path.expanduser(raw)).resolve()


def _project_key(workspace: str | Path) -> str:
    resolved = str(Path(workspace).resolve())
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()


def _sessions_root(workspace: str | Path) -> Path:
    return _mcp_coder_home() / "projects" / _project_key(workspace) / "sessions"


def _legacy_workspace_log_path(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / ".mcp-coder" / "logs" / "delegations.jsonl"


def _load_workspace_pointer(workspace: str | Path) -> dict[str, Any]:
    ws = Path(workspace).resolve()
    for rel in (".mcp-coder/session.json", ".mcp-coder/project.json"):
        path = ws / rel
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def _load_jsonl_file(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def _delegation_log_paths_for_workspace(ws: str) -> list[Path]:
    """Session log paths for a workspace (mirrors delegation_log; stdlib-only imports)."""
    resolved = str(Path(ws).resolve())
    root = _sessions_root(resolved)
    if root.is_dir():
        paths = [p for p in root.glob("*/delegations.jsonl") if p.is_file()]
        if paths:
            paths.sort(key=lambda p: p.stat().st_mtime)
            return paths

    data = _load_workspace_pointer(resolved)
    sessions_root_raw = data.get("sessions_root")
    if sessions_root_raw:
        try:
            sessions_root_path = Path(sessions_root_raw)
            if sessions_root_path.is_dir():
                paths = [
                    p for p in sessions_root_path.glob("*/delegations.jsonl") if p.is_file()
                ]
                if paths:
                    paths.sort(key=lambda p: p.stat().st_mtime)
                    return paths
        except (TypeError, OSError):
            pass

    legacy = _legacy_workspace_log_path(resolved)
    if legacy.is_file():
        return [legacy]
    return []


def _delegation_sort_key(record: dict[str, Any]) -> str:
    return str(record.get("timestamp_start") or record.get("timestamp_end") or "")


def _sort_delegations_chronological(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Oldest first (JSONL file order / timeline order)."""
    return sorted(records, key=_delegation_sort_key)


def _load_delegations(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    return _sort_delegations_chronological(_load_jsonl_file(p))


def _load_delegations_for_workspace(ws: str | Path) -> list[dict[str, Any]]:
    paths = _delegation_log_paths_for_workspace(str(ws))
    if not paths:
        raise FileNotFoundError(f"No delegation logs found for workspace: {ws}")
    records: list[dict[str, Any]] = []
    for path in paths:
        records.extend(_load_jsonl_file(path))
    return _sort_delegations_chronological(records)


def resolve_view_source(
    log_file: str | Path | None,
    workspace: str | Path | None,
    *,
    default_workspace: str | Path | None = None,
) -> tuple[Path | None, str | None]:
    """Return (single log path, workspace) for the viewer API."""
    if log_file:
        return Path(log_file).expanduser().resolve(), None
    if workspace:
        return None, str(Path(workspace).expanduser().resolve())
    if default_workspace is not None:
        return None, str(Path(default_workspace).expanduser().resolve())
    return None, str(Path.cwd().resolve())


class ViewerHandler(BaseHTTPRequestHandler):
    log_path: Path | None = None
    workspace: str | None = None

    def log_message(self, fmt: str, *args: object) -> None:
        pass

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/delegation/enrich":
            try:
                record = self._read_json_body()
                if not record:
                    self._send_json({"error": "empty body"}, 400)
                    return
                self._send_json(enrich_delegation_record(record))
            except (json.JSONDecodeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                self._send_json({"error": f"enrich failed: {exc}"}, 500)
            return
        self.send_error(404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/delegations":
            try:
                if self.workspace:
                    records = _load_delegations_for_workspace(self.workspace)
                    label = f"home store for {self.workspace}"
                else:
                    assert self.log_path is not None
                    records = _load_delegations(self.log_path)
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


def run_view(
    *,
    log_file: str | Path | None = None,
    workspace: str | Path | None = None,
    port: int = 8765,
    no_open: bool = False,
    default_workspace: str | Path | None = None,
) -> None:
    """Start the delegation viewer HTTP server (blocks until interrupted)."""
    resolved_log, resolved_ws = resolve_view_source(
        log_file,
        workspace,
        default_workspace=default_workspace,
    )
    ViewerHandler.log_path = resolved_log
    ViewerHandler.workspace = resolved_ws

    server = ThreadingHTTPServer(("127.0.0.1", port), ViewerHandler)
    url = f"http://127.0.0.1:{port}/"
    print(f"[mcp-coder] Delegation viewer: {url}")
    if resolved_ws:
        print(f"[mcp-coder] Workspace: {resolved_ws} (home store, merged session logs)")
    else:
        print(f"[mcp-coder] Log file: {resolved_log}")
    if not no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mcp-coder] Stopped.")
        server.shutdown()


def main_view(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve delegation log browser UI (merged workspace logs or one JSONL file)",
    )
    parser.add_argument(
        "log_file",
        nargs="?",
        help="Path to delegations.jsonl (optional; default loads cwd workspace from home store)",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        help="Project root (default: cwd when log_file omitted)",
    )
    parser.add_argument("--port", "-p", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Do not open browser")
    args = parser.parse_args(argv)

    if args.log_file and args.workspace:
        parser.error("provide log_file or --workspace, not both")

    run_view(
        log_file=args.log_file,
        workspace=args.workspace,
        port=args.port,
        no_open=args.no_open,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_view())
