from __future__ import annotations

from pathlib import Path

FORBIDDEN = ("agent-transcripts", ".cursor/projects")
CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
ALLOWED = CORE_ROOT / "host" / "cursor.py"


def test_no_cursor_paths_outside_cursor_module():
    hits: list[str] = []
    for path in CORE_ROOT.rglob("*.py"):
        if path == ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN:
            if needle in text:
                hits.append(f"{path.relative_to(CORE_ROOT)}: {needle}")
    assert hits == []
