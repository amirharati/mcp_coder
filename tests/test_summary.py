from core.context.summary import assemble_prompt, prompt_metadata


def test_assemble_prompt_joins_task_and_summary():
    prompt = assemble_prompt("Use pytest.", "Add tests for foo.")
    assert "Use pytest." in prompt
    assert "Add tests for foo." in prompt
    assert "---" in prompt
    assert prompt.index("Add tests") < prompt.index("Use pytest.")


def test_prompt_metadata_hashes():
    prompt = assemble_prompt("ctx", "task")
    meta = prompt_metadata(prompt, context_summary="ctx")
    assert meta["prompt_chars"] == len(prompt)
    assert len(meta["prompt_hash"]) == 64
    assert len(meta["fallback_summary_hash"]) == 64
