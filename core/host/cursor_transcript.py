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
    source_byte_start: int | None = None
    source_byte_end: int | None = None


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
    text, lines_parsed, lines_skipped, _, _ = _parse_cursor_transcript_jsonl(raw)
    return text, lines_parsed, lines_skipped


def _parse_cursor_transcript_jsonl(
    raw: str,
) -> tuple[str, int, int, list[tuple[int, int]], list[str]]:
    """Parse JSONL; return formatted text, counts, source byte ranges, and turns."""
    turns: list[str] = []
    lines_parsed = 0
    lines_skipped = 0
    line_ranges: list[tuple[int, int]] = []
    offset = 0
    for line in raw.splitlines(keepends=True):
        line_start = offset
        line_end = offset + len(line.encode("utf-8"))
        offset = line_end
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
        line_ranges.append((line_start, line_end))
        if text:
            turns.append(f"[{role}]\n{text}")
        else:
            turns.append(f"[{role}]")
    return _format_transcript_block(turns), lines_parsed, lines_skipped, line_ranges, turns


def _turn_byte_spans_in_formatted(turns: list[str]) -> list[tuple[int, int]]:
    """Byte spans of each turn inside the formatted transcript block (UTF-8)."""
    if not turns:
        return []
    header = f"{TRANSCRIPT_HEADER}\n\n"
    offset = len(header.encode("utf-8"))
    spans: list[tuple[int, int]] = []
    for index, turn in enumerate(turns):
        suffix = "" if index == len(turns) - 1 else "\n\n"
        block = f"{turn}{suffix}"
        block_len = len(block.encode("utf-8"))
        spans.append((offset, offset + block_len))
        offset += block_len
    return spans


def _compute_source_byte_provenance(
    *,
    formatted_text: str,
    line_ranges: list[tuple[int, int]],
    turns: list[str],
    truncated: bool,
) -> tuple[int | None, int | None]:
    """Map parsed host transcript lines to inclusive-start/exclusive-end file byte range."""
    if not line_ranges:
        return None, None

    if not truncated:
        return 0, line_ranges[-1][1]

    cap = _max_transcript_bytes_cap()
    if cap <= 0:
        return 0, line_ranges[-1][1]

    capped_text, was_truncated, _ = apply_max_transcript_bytes(formatted_text, cap)
    if not was_truncated or not capped_text:
        return 0, line_ranges[-1][1]

    full_bytes = formatted_text.encode("utf-8")
    capped_bytes = capped_text.encode("utf-8")
    if len(capped_bytes) >= len(full_bytes):
        return 0, line_ranges[-1][1]

    tail_start = len(full_bytes) - len(capped_bytes)
    if len(turns) != len(line_ranges):
        return None, None

    included: list[int] = []
    for index, (turn_start, turn_end) in enumerate(_turn_byte_spans_in_formatted(turns)):
        if turn_end > tail_start:
            included.append(index)

    if not included:
        return None, None

    first = included[0]
    last = included[-1]
    return line_ranges[first][0], line_ranges[last][1]


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

    text, lines_parsed, lines_skipped, line_ranges, turns = _parse_cursor_transcript_jsonl(raw)
    truncated = False
    truncation_reason: str | None = None
    bytes_dropped = 0
    formatted_before_cap = text
    cap = _max_transcript_bytes_cap()
    if text and cap > 0:
        text, truncated, bytes_dropped = apply_max_transcript_bytes(text, cap)
        if truncated:
            truncation_reason = "max_transcript_bytes"

    source_byte_start, source_byte_end = _compute_source_byte_provenance(
        formatted_text=formatted_before_cap,
        line_ranges=line_ranges,
        turns=turns,
        truncated=truncated,
    )

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
        source_byte_start=source_byte_start,
        source_byte_end=source_byte_end,
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
