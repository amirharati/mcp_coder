from pathlib import Path

from core.specs.read import compile_planner_sections, read_task_spec
from core.specs.sections import parse_sections


SAMPLE = """---
spec_id: demo
status: open
---

# Task spec

## Goal

Build the widget.

## Scope

In: widget. Out: mobile app.

## Files

- `src/widget.py`

## Constraints

- Python 3.10+

## Done when

- [ ] Widget renders

## Plan

1. Create file

## Status

`open`

## Run log

## Blockers / questions

## Suggested next (hints only)
"""


def test_compile_planner_sections_omits_mcp_sections():
    sections = parse_sections(SAMPLE.split("---", 2)[-1])
    block = compile_planner_sections(sections)
    assert "Build the widget" in block
    assert "src/widget.py" in block
    assert "## Run log" not in block
    assert "## Status" not in block


def test_read_task_spec(tmp_path: Path):
    ws = tmp_path / "proj"
    ws.mkdir()
    spec = ws / ".mcp-coder" / "specs" / "tasks" / "demo.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(SAMPLE, encoding="utf-8")
    result = read_task_spec(spec, workspace=ws)
    assert result.rel_path.endswith("tasks/demo.md")
    assert result.sha256
    assert result.file_bytes > 0
    assert "Build the widget" in result.prompt_block
