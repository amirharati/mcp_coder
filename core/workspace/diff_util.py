from __future__ import annotations

import difflib

from core.workspace.walk import is_binary_content


def unified_diff_text(path: str, before: bytes, after: bytes) -> str | None:
    """Return unified diff text for UTF-8 files; None for binary or decode errors."""
    if is_binary_content(before) or is_binary_content(after):
        return None
    try:
        before_lines = before.decode("utf-8").splitlines(keepends=True)
        after_lines = after.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None
    chunks = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=path,
        tofile=path,
    )
    text = "".join(chunks)
    return text if text else None
