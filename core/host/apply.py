from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.host.base import HostSessionHint


def host_context_from_hint(hint: HostSessionHint) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "host_transcript_path": hint.host_transcript_path,
        "host_transcript_mtime": None,
        "host_transcript_file_bytes": None,
        "host_project_slug": hint.host_project_slug,
        "host_resolve_method": hint.host_resolve_method,
    }
    if hint.host_transcript_path:
        try:
            st = Path(hint.host_transcript_path).stat()
            ctx["host_transcript_mtime"] = (
                datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            ctx["host_transcript_file_bytes"] = st.st_size
        except OSError:
            pass
    return ctx


def apply_host_hint(session_dir: Path, hint: HostSessionHint) -> dict[str, Any]:
    """Update session.json with host fields; return context block for delegation record."""
    session_json_path = session_dir / "session.json"
    if session_json_path.is_file():
        data = json.loads(session_json_path.read_text(encoding="utf-8"))
    else:
        data = {}
    data["host_kind"] = hint.host_kind
    data["host_session_id"] = hint.host_session_id
    data["host_transcript_path"] = hint.host_transcript_path
    session_json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return host_context_from_hint(hint)
