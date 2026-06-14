import json

from core.host.cursor_transcript import (
    TRANSCRIPT_HEADER,
    apply_max_transcript_bytes,
    load_cursor_transcript,
    parse_cursor_transcript_jsonl,
)


def _line(role: str, text: str, *, tool: bool = False) -> str:
    content = [{"type": "text", "text": text}]
    if tool:
        content.append({"type": "tool_use", "name": "Read", "input": {"path": "x"}})
    return json.dumps({"role": role, "message": {"content": content}})


def test_parse_extracts_text_skips_tool_use():
    raw = "\n".join(
        [
            _line("user", "Hello"),
            _line("assistant", "Hi there", tool=True),
        ]
    )
    text, parsed, skipped = parse_cursor_transcript_jsonl(raw)
    assert parsed == 2
    assert skipped == 0
    assert text.startswith(TRANSCRIPT_HEADER)
    assert "[user]\nHello" in text
    assert "[assistant]\nHi there" in text
    assert "tool_use" not in text
    assert "Read" not in text


def test_parse_skips_invalid_json_lines():
    raw = "\n".join(
        [
            _line("user", "ok"),
            "not json",
            '{"role":"assistant"}',
        ]
    )
    text, parsed, skipped = parse_cursor_transcript_jsonl(raw)
    assert parsed == 2
    assert skipped == 1
    assert "[user]\nok" in text
    assert "[assistant]" in text


def test_load_from_file(tmp_path):
    path = tmp_path / "chat.jsonl"
    path.write_text(_line("user", "from disk") + "\n", encoding="utf-8")
    result = load_cursor_transcript(path)
    assert result.read_error is None
    assert result.file_bytes == path.stat().st_size
    assert result.injected_bytes > 0
    assert "from disk" in result.text
    assert result.lines_parsed == 1


def test_load_missing_file(tmp_path):
    result = load_cursor_transcript(tmp_path / "missing.jsonl")
    assert result.text == ""
    assert result.read_error is not None


def test_apply_max_transcript_bytes_tail_keep():
    text = "α" * 100
    capped, truncated, dropped = apply_max_transcript_bytes(text, 20)
    assert truncated is True
    assert dropped > 0
    assert len(capped.encode("utf-8")) <= 20


def test_load_applies_byte_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_MAX_TRANSCRIPT_BYTES", "64")
    path = tmp_path / "big.jsonl"
    lines = [_line("user", "x" * 200) for _ in range(5)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = load_cursor_transcript(path)
    assert result.truncated is True
    assert result.truncation_reason == "max_transcript_bytes"
    assert result.bytes_dropped > 0
    assert result.injected_bytes <= 64
    assert result.source_byte_start is not None
    assert result.source_byte_end is not None
    assert result.source_byte_start > 0
    assert 0 <= result.source_byte_start < result.source_byte_end <= result.file_bytes


def test_load_source_byte_range_full_file(tmp_path):
    path = tmp_path / "chat.jsonl"
    raw = _line("user", "from disk") + "\n" + _line("assistant", "reply") + "\n"
    path.write_text(raw, encoding="utf-8")
    result = load_cursor_transcript(path)
    assert result.source_byte_start == 0
    assert result.source_byte_end is not None
    assert result.source_byte_end <= result.file_bytes
    sliced = path.read_bytes()[result.source_byte_start : result.source_byte_end]
    sliced.decode("utf-8")
    assert "from disk" in sliced.decode("utf-8")
    assert "reply" in sliced.decode("utf-8")


def test_load_source_byte_range_empty_transcript(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    result = load_cursor_transcript(path)
    assert result.lines_parsed == 0
    assert result.source_byte_start is None
    assert result.source_byte_end is None
