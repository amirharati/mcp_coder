from __future__ import annotations

from core.engine.supervisor import build_supervisor_prompt, _MAX_PROMPT_CHARS


def _base_kwargs(**overrides):
    defaults = {
        "question": "Approve edit to foo.py?",
        "risk_tier": "unknown",
        "spec_contract": "### Allowed paths\n- `foo.py`",
        "architect_plan": None,
        "prior_decisions": [],
        "output_tail": "tail output",
    }
    defaults.update(overrides)
    return defaults


def test_project_state_section_included_when_summary_present():
    """When project_state_summary is a non-empty string, the prompt contains ## Project state."""
    kwargs = _base_kwargs(project_state_summary="### Recent decisions\n- Decision A (abc12345)")
    prompt = build_supervisor_prompt(**kwargs)
    assert "## Project state" in prompt
    assert "Decision A" in prompt


def test_project_state_section_omitted_when_summary_none():
    """When project_state_summary=None, the prompt does not contain ## Project state."""
    kwargs = _base_kwargs(project_state_summary=None)
    prompt = build_supervisor_prompt(**kwargs)
    assert "## Project state" not in prompt


def test_project_state_section_omitted_when_summary_empty():
    """When project_state_summary is empty after strip, section omitted."""
    kwargs = _base_kwargs(project_state_summary="   ")
    prompt = build_supervisor_prompt(**kwargs)
    assert "## Project state" not in prompt


def test_target_files_section_renders_edit_and_read():
    """target_files with both edit and read lists renders both subsections."""
    kwargs = _base_kwargs(target_files={"files_edit": ["a.py"], "files_read": ["b.md"]})
    prompt = build_supervisor_prompt(**kwargs)
    assert "## Target files" in prompt
    assert "**files_edit:**" in prompt
    assert "- `a.py`" in prompt
    assert "**files_read:**" in prompt
    assert "- `b.md`" in prompt


def test_target_files_section_omitted_when_none():
    """target_files=None omits the section."""
    kwargs = _base_kwargs(target_files=None)
    prompt = build_supervisor_prompt(**kwargs)
    assert "## Target files" not in prompt


def test_target_files_section_omitted_when_both_lists_empty():
    """target_files with both lists empty omits the section."""
    kwargs = _base_kwargs(target_files={"files_edit": [], "files_read": []})
    prompt = build_supervisor_prompt(**kwargs)
    assert "## Target files" not in prompt


def test_target_files_renders_only_nonempty_subsection():
    """When files_read is empty, only files_edit subsection renders."""
    kwargs = _base_kwargs(target_files={"files_edit": ["a.py"], "files_read": []})
    prompt = build_supervisor_prompt(**kwargs)
    assert "## Target files" in prompt
    assert "**files_edit:**" in prompt
    assert "**files_read:**" not in prompt


def test_target_files_normalizes_paths():
    """Paths with ./ prefix and backslashes are normalized."""
    kwargs = _base_kwargs(target_files={
        "files_edit": ["./src\\a.py", "b.py"],
        "files_read": ["./docs/c.md"],
    })
    prompt = build_supervisor_prompt(**kwargs)
    assert "- `src/a.py`" in prompt
    assert "- `b.py`" in prompt
    assert "- `docs/c.md`" in prompt
    # Original un-normalized paths should not appear
    assert "./src\\a.py" not in prompt


def test_new_sections_appear_before_prior_decisions():
    """Project state and Target files sections appear before Prior decisions."""
    kwargs = _base_kwargs(
        project_state_summary="### Recent decisions\n- A (abc12345)",
        target_files={"files_edit": ["x.py"], "files_read": ["y.md"]},
    )
    prompt = build_supervisor_prompt(**kwargs)
    ps_idx = prompt.index("## Project state")
    tf_idx = prompt.index("## Target files")
    pd_idx = prompt.index("## Prior decisions")
    assert ps_idx < pd_idx
    assert tf_idx < pd_idx


def test_prompt_respects_max_chars_cap():
    """When inputs would exceed _MAX_PROMPT_CHARS, the prompt is capped."""
    # Per-section caps make hitting the global cap rare, but the cap is a backstop.
    # Use a huge question (unbounded) + maxed-out section caps to trigger truncation.
    huge = "x" * (_MAX_PROMPT_CHARS + 1000)
    kwargs = _base_kwargs(
        spec_contract="### Allowed paths\n" + "x" * _MAX_PROMPT_CHARS,
        architect_plan="## Plan\n" + "x" * _MAX_PROMPT_CHARS,
        project_state_summary="### Decisions\n" + "x" * _MAX_PROMPT_CHARS,
        target_files={"files_edit": ["x" * 500, "y" * 500], "files_read": ["z" * 500]},
        question=huge,
        prior_decisions=[],
        output_tail="",
    )
    prompt = build_supervisor_prompt(**kwargs)
    assert len(prompt) <= _MAX_PROMPT_CHARS


def test_target_files_section_omitted_when_not_dict():
    """If target_files is passed as a list (not a dict), treat as None and omit section."""
    kwargs = _base_kwargs(target_files=["a.py", "b.py"])  # not a dict
    prompt = build_supervisor_prompt(**kwargs)
    assert "## Target files" not in prompt


def test_empty_string_paths_filtered_out():
    """Empty strings in file lists are filtered out."""
    kwargs = _base_kwargs(target_files={"files_edit": ["a.py", "", "  "], "files_read": [""]})
    prompt = build_supervisor_prompt(**kwargs)
    # Only a.py should appear
    assert prompt.count("- `a.py`") == 1
    # The section should still be present since there's one valid path
    assert "## Target files" in prompt
    assert "**files_read:**" not in prompt  # empty after filtering
