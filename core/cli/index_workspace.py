"""CLI: index workspace files for RAG (P5-003)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from core.config.rag import workspace_file_rag_enabled
from core.rag.workspace_indexer import index_workspace
from core.rag.workspace_db import WorkspaceRagDB


def _resolve_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(os.environ.get("MCP_CODER_WORKSPACE", os.getcwd())).resolve()


def main_index_workspace(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Index workspace source files into workspace_rag.db (FTS5)."
    )
    parser.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Re-index only new/changed files (sha256 compare)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max files to index this run (tests/dogfood)",
    )
    parser.add_argument("--json", action="store_true", help="JSON summary output")
    args = parser.parse_args(argv)

    ws = _resolve_workspace(args.workspace)
    if not workspace_file_rag_enabled(ws):
        msg = "workspace file RAG disabled (set workspace_file_rag: true or MCP_CODER_WORKSPACE_FILE_RAG=1)"
        if args.json:
            print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
        else:
            print(msg, file=sys.stderr)
        return 1

    result = index_workspace(
        ws,
        changed_only=args.changed_only,
        limit=args.limit,
    )
    db = WorkspaceRagDB(ws)
    payload = {
        "ok": True,
        "indexed": result.indexed,
        "skipped_unchanged": result.skipped_unchanged,
        "deleted": result.deleted,
        "errors": result.errors,
        "row_count": db.row_count(),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"indexed={result.indexed} skipped_unchanged={result.skipped_unchanged} "
            f"deleted={result.deleted} row_count={db.row_count()}"
        )
        if result.errors:
            print("errors:", file=sys.stderr)
            for err in result.errors:
                print(f"  {err}", file=sys.stderr)
    return 0 if not result.errors else 1
