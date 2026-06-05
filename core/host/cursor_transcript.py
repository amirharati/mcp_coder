from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from core.context.summary import sha256_hex

TRANSCRIPT_HEADER = "## Cursor chat history"


@dataclass
class TranscriptLoadResult:
    text: str
    file_bytes: int | None
    injected_bytes: int
    lines_parsed: int
    lines_skipped: int
    truncated: bool
    truncation_reason: str | None
    bytes_dropped: int
    read_error: str | None


def empty_transcript_result(*, file_bytes: int | None = None) -> TranscriptLoadResult:
    return TranscriptLoadResult(
        text="",
        file_bytes=file_bytes,
        injected_bytes=0,
        lines_parsed=0,
        lines_skipped=0,
        truncated=False,
        truncation_reason=None,
        bytes_dropped=0,
        read_error=None,
    )


def _max_transcript_bytes_cap() -> int:
    raw = os.environ.get("MCP_CODER_MAX_TRANSCRIPT_BYTES", "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def apply_max_transcript_bytes(text: str, cap: int) -> tuple[str, bool, int]:
    """Keep tail of UTF-8 bytes when cap > 0."""
    if cap <= 0 or not text:
        return text, False, 0
    raw = text.encode("utf-8")
    if len(raw) <= cap:
        return text, False, 0
    tail = raw[-cap:]
    while tail:
        try:
            out = tail.decode("utf-8")
            break
        except UnicodeDecodeError:
            tail = tail[1:]
    else:
        out = ""
    bytes_dropped = len(raw) - len(out.encode("utf-8"))
    return out, True, bytes_dropped


def _extract_turn_text(obj: dict) -> tuple[str | None, str | None]:
    role = obj.get("role")
    if not isinstance(role, str) or not role.strip():
        return None, None
    message = obj.get("message")
    if not isinstance(message, dict):
        return role.strip(), ""
    content = message.get("content")
    if not isinstance(content, list):
        return role.strip(), ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return role.strip(), "\n".join(parts) if parts else ""


def _format_transcript_block(turns: list[str]) -> str:
    if not turns:
        return ""
    body = "\n\n".join(turns)
    return f"{TRANSCRIPT_HEADER}\n\n{body}"


def parse_cursor_transcript_jsonl(raw: str) -> tuple[str, int, int]:
    """Parse JSONL text into injectable transcript block."""
    turns: list[str] = []
    lines_parsed = 0
    lines_skipped = 0
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            lines_skipped += 1
            continue
        if not isinstance(obj, dict):
            lines_skipped += 1
            continue
        role, text = _extract_turn_text(obj)
        if role is None:
            lines_skipped += 1
            continue
        lines_parsed += 1
        if text:
            turns.append(f"[{role}]\n{text}")
        else:
            turns.append(f"[{role}]")
    return _format_transcript_block(turns), lines_parsed, lines_skipped


def load_cursor_transcript(path: str | Path) -> TranscriptLoadResult:
    transcript_path = Path(path)
    file_bytes: int | None = None
    try:
        file_bytes = transcript_path.stat().st_size
    except OSError as exc:
        return TranscriptLoadResult(
            text="",
            file_bytes=None,
            injected_bytes=0,
            lines_parsed=0,
            lines_skipped=0,
            truncated=False,
            truncation_reason=None,
            bytes_dropped=0,
            read_error=f"{type(exc).__name__}: {exc}",
        )

    try:
        raw = transcript_path.read_text(encoding="utf-8")
    except OSError as exc:
        return TranscriptLoadResult(
            text="",
            file_bytes=file_bytes,
            injected_bytes=0,
            lines_parsed=0,
            lines_skipped=0,
            truncated=False,
            truncation_reason=None,
            bytes_dropped=0,
            read_error=f"{type(exc).__name__}: {exc}",
        )

    text, lines_parsed, lines_skipped = parse_cursor_transcript_jsonl(raw)
    truncated = False
    truncation_reason: str | None = None
    bytes_dropped = 0
    cap = _max_transcript_bytes_cap()
    if text and cap > 0:
        text, truncated, bytes_dropped = apply_max_transcript_bytes(text, cap)
        if truncated:
            truncation_reason = "max_transcript_bytes"

    injected_bytes = len(text.encode("utf-8")) if text else 0
    return TranscriptLoadResult(
        text=text,
        file_bytes=file_bytes,
        injected_bytes=injected_bytes,
        lines_parsed=lines_parsed,
        lines_skipped=lines_skipped,
        truncated=truncated,
        truncation_reason=truncation_reason,
        bytes_dropped=bytes_dropped,
        read_error=None,
    )


def transcript_log_context(
    *,
    policy: str,
    load_result: TranscriptLoadResult | None,
    file_bytes: int | None,
    context_mode: str,
) -> dict[str, object]:
    """Build delegation context fields for transcript injection metrics."""
    injected = 0
    text_for_hash = ""
    lines_parsed = 0
    lines_skipped = 0
    truncated = False
    truncation_reason: str | None = None
    bytes_dropped = 0
    read_error: str | None = None

    if load_result is not None:
        lines_parsed = load_result.lines_parsed
        lines_skipped = load_result.lines_skipped
        truncated = load_result.truncated
        truncation_reason = load_result.truncation_reason
        bytes_dropped = load_result.bytes_dropped
        read_error = load_result.read_error
        if context_mode == "host_transcript" and load_result.text:
            injected = load_result.injected_bytes
            text_for_hash = load_result.text

    ctx: dict[str, object] = {
        "host_transcript_policy": policy,
        "host_transcript_file_bytes": file_bytes,
        "host_transcript_injected_bytes": injected,
        "host_transcript_bytes": injected,
        "host_transcript_hash": sha256_hex(text_for_hash) if text_for_hash else None,
        "host_transcript_lines_parsed": lines_parsed,
        "host_transcript_lines_skipped": lines_skipped,
        "truncated": truncated,
        "truncation_reason": truncation_reason,
        "bytes_dropped": bytes_dropped,
    }
    if read_error:
        ctx["host_transcript_read_error"] = read_error
    return ctx
