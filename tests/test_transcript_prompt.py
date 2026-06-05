import json

from core.context.summary import PROMPT_SEPARATOR, assemble_prompt, prompt_metadata
from core.host.cursor_transcript import (
    TRANSCRIPT_HEADER,
    load_cursor_transcript,
    transcript_log_context,
)


def test_assemble_prompt_prepends_transcript():
    transcript = f"{TRANSCRIPT_HEADER}\n\n[user]\nhello"
    prompt = assemble_prompt("summary bit", "do task", host_transcript=transcript)
    parts = prompt.split(PROMPT_SEPARATOR)
    assert len(parts) == 3
    assert parts[0].startswith(TRANSCRIPT_HEADER)
    assert parts[1] == "do task"
    assert parts[2] == "summary bit"


def test_assemble_prompt_without_transcript_unchanged():
    prompt = assemble_prompt("Use pytest.", "Add tests for foo.")
    assert "Use pytest." in prompt
    assert "Add tests for foo." in prompt
    assert prompt.index("Add tests") < prompt.index("Use pytest.")


def test_prompt_metadata_includes_transcript_fields(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        json.dumps(
            {
                "role": "user",
                "message": {"content": [{"type": "text", "text": "ctx"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    load_result = load_cursor_transcript(path)
    transcript_meta = transcript_log_context(
        policy="dump",
        load_result=load_result,
        file_bytes=load_result.file_bytes,
        context_mode="host_transcript",
    )
    prompt = assemble_prompt("sum", "task", host_transcript=load_result.text)
    meta = prompt_metadata(prompt, context_summary="sum", transcript_meta=transcript_meta)
    assert meta["host_transcript_policy"] == "dump"
    assert meta["host_transcript_injected_bytes"] == load_result.injected_bytes
    assert meta["host_transcript_bytes"] == load_result.injected_bytes
    assert meta["host_transcript_hash"]
    assert meta["truncated"] is False


def test_transcript_log_context_none_policy_zeros():
    ctx = transcript_log_context(
        policy="none",
        load_result=None,
        file_bytes=123,
        context_mode="fallback",
    )
    assert ctx["host_transcript_policy"] == "none"
    assert ctx["host_transcript_file_bytes"] == 123
    assert ctx["host_transcript_injected_bytes"] == 0
    assert ctx["host_transcript_bytes"] == 0
    assert ctx["host_transcript_hash"] is None
    assert ctx["truncated"] is False
