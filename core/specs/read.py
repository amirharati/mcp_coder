"""Read workspace task specs for delegate prompt compilation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from core.specs.sections import (
    EPIC_SECTION_TITLES,
    PLANNER_SECTION_TITLES,
    parse_sections,
    split_front_matter,
)

SPEC_PROMPT_HEADER = "## Task spec (from workspace)"
EPIC_PROMPT_HEADER = "## Epic context (linked)"


@dataclass
class SpecReadResult:
    path: Path
    rel_path: str
    raw_text: str
    front_matter: dict
    sections: dict[str, str]
    prompt_block: str
    sha256: str
    file_bytes: int
    mtime_iso: str | None
    epic_path: str | None = None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compile_planner_sections(sections: dict[str, str], *, header: str = SPEC_PROMPT_HEADER) -> str:
    parts: list[str] = [header]
    for title in PLANNER_SECTION_TITLES:
        content = sections.get(title, "").strip()
        if content:
            parts.append(f"## {title}\n\n{content}")
    if len(parts) == 1:
        return ""
    return "\n\n".join(parts)


def compile_epic_sections(sections: dict[str, str]) -> str:
    parts: list[str] = [EPIC_PROMPT_HEADER]
    for title in EPIC_SECTION_TITLES:
        content = sections.get(title, "").strip()
        if content:
            parts.append(f"## {title}\n\n{content}")
    if len(parts) == 1:
        return ""
    return "\n\n".join(parts)


def _mtime_iso(path: Path) -> str | None:
    try:
        from datetime import datetime, timezone

        st = path.stat()
        return (
            datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except OSError:
        return None


def read_task_spec(path: Path, *, workspace: str | Path) -> SpecReadResult:
    raw = path.read_text(encoding="utf-8")
    front_matter, body = split_front_matter(raw)
    sections = parse_sections(body)
    prompt_block = compile_planner_sections(sections)
    st = path.stat()
    ws = Path(workspace).resolve()
    try:
        rel = str(path.resolve().relative_to(ws))
    except ValueError:
        rel = str(path)

    epic_path: str | None = None
    epic_slug = (front_matter.get("epic") or "").strip()
    if epic_slug:
        from core.specs.paths import resolve_epic_path

        epic_file = resolve_epic_path(ws, epic_slug)
        if epic_file.is_file():
            epic_path = str(epic_file.resolve().relative_to(ws))
            _, epic_body = split_front_matter(epic_file.read_text(encoding="utf-8"))
            epic_block = compile_epic_sections(parse_sections(epic_body))
            if epic_block:
                prompt_block = (
                    f"{epic_block}\n\n{prompt_block}" if prompt_block else epic_block
                )

    return SpecReadResult(
        path=path,
        rel_path=rel,
        raw_text=raw,
        front_matter=front_matter,
        sections=sections,
        prompt_block=prompt_block,
        sha256=sha256_text(raw),
        file_bytes=st.st_size,
        mtime_iso=_mtime_iso(path),
        epic_path=epic_path,
    )
