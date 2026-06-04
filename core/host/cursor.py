from __future__ import annotations

import os
from pathlib import Path

from core.host.base import HostSessionHint
from core.host.scoring import pick_host_session_id
from core.session.activity import host_delegation_activity
from core.storage.paths import normalize_workspace, project_key


def cursor_root() -> Path:
    raw = os.environ.get("MCP_CODER_CURSOR_ROOT", "~/.cursor")
    return Path(os.path.expanduser(raw)).resolve()


def slug_candidates(resolved_workspace: str) -> list[str]:
    """Build Cursor project slug candidates from resolved absolute workspace path."""
    override = os.environ.get("MCP_CODER_CURSOR_PROJECT_SLUG", "").strip()
    if override:
        return [override]

    base = resolved_workspace.lstrip("/").replace("/", "-")
    candidates = [base]
    if "_" in base:
        candidates.append(base.replace("_", "-"))
    seen: set[str] = set()
    unique: list[str] = []
    for slug in candidates:
        if slug not in seen:
            seen.add(slug)
            unique.append(slug)
    return unique


def resolve_cursor_project_slug(resolved_workspace: str) -> tuple[str | None, str | None]:
    """Return (slug, resolve_error)."""
    root = cursor_root() / "projects"
    for slug in slug_candidates(resolved_workspace):
        transcripts = root / slug / "agent-transcripts"
        if transcripts.is_dir():
            return slug, None
    return None, "cursor_project_not_found"


def _list_transcript_candidates(transcripts_dir: Path) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    for path in transcripts_dir.glob("**/*.jsonl"):
        if path.is_file():
            candidates.append((path.stem, path))
    return candidates


class CursorHostProvider:
    def resolve_active_session(self, workspace_path: str | Path) -> HostSessionHint:
        ws = normalize_workspace(workspace_path)
        slug, resolve_error = resolve_cursor_project_slug(ws)
        if slug is None:
            return HostSessionHint(resolve_error=resolve_error)

        transcripts_dir = cursor_root() / "projects" / slug / "agent-transcripts"
        candidates = _list_transcript_candidates(transcripts_dir)
        if not candidates:
            return HostSessionHint(
                host_project_slug=slug,
                resolve_error="cursor_transcript_not_found",
            )

        pk = project_key(ws)
        activity = host_delegation_activity(pk)
        host_id, method = pick_host_session_id(candidates, activity)

        if host_id is None:
            return HostSessionHint(
                host_project_slug=slug,
                resolve_error="cursor_transcript_not_found",
            )

        transcript_path = next(p for hid, p in candidates if hid == host_id)
        return HostSessionHint(
            host_kind="cursor",
            host_session_id=host_id,
            host_transcript_path=str(transcript_path.resolve()),
            host_project_slug=slug,
            host_resolve_method=method,
        )
