from __future__ import annotations

import re
from pathlib import Path


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _strip_markdown_bullet(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^[-*+]\s+", "", text)
    text = re.sub(r"^\d+\.\s+", "", text)
    return text.strip()


def _normalize_summary(line: str, *, max_chars: int) -> str:
    text = _strip_markdown_bullet(line)
    text = " ".join(text.split())
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


def resolve_checkpoint_summary(
    *,
    task: str,
    spec_path: str | None,
    workspace: str | Path,
    max_chars: int = 200,
) -> str:
    """
    Resolve a single-line checkpoint label for workspace_history.db.

    Priority: spec Goal first line → task first line → \"delegation\".
    """
    if spec_path:
        try:
            from core.specs.paths import resolve_spec_path
            from core.specs.read import read_task_spec

            abs_path = resolve_spec_path(workspace, spec_path)
            if abs_path.is_file():
                spec_read = read_task_spec(abs_path, workspace=workspace)
                goal = spec_read.sections.get("Goal", "")
                line = _first_line(goal)
                if line:
                    return _normalize_summary(line, max_chars=max_chars)
        except (OSError, ValueError):
            pass

    line = _first_line(task)
    if line:
        return _normalize_summary(line, max_chars=max_chars)

    return "delegation"
