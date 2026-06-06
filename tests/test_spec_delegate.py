import json
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from core.specs.outcome import (
    OUTCOME_INVALID_SPEC,
    OUTCOME_PARTIAL,
    OUTCOME_SCOPE_VIOLATION,
    OUTCOME_SUCCESS,
)
from core.specs.sections import REPORT_STATUS_DELEGATED_OK, parse_sections, split_front_matter
from server.mcp_server import delegate_to_agent

SPEC_BODY = """---
spec_id: scrape-test
epic: scrape-epic
status: open
---

# Step task spec

## Goal

Write scraped_content.txt.

## Scope

One file only.

## Files

- `scraped_content.txt`

## Constraints

- No shell

## Done when

- [ ] File exists
"""

EPIC_BODY = """---
epic_id: scrape-epic
status: open
---

# Epic spec

## Goal

Epic north star for scrape test.

## Steps

| Step | Task spec | Status |
| tasks/scrape-test.md | open |
"""


def _setup_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    specs = ws / ".mcp-coder" / "specs"
    task = specs / "tasks" / "scrape.md"
    task.parent.mkdir(parents=True)
    task.write_text(SPEC_BODY, encoding="utf-8")
    epic = specs / "epics" / "scrape-epic.md"
    epic.parent.mkdir(parents=True)
    epic.write_text(EPIC_BODY, encoding="utf-8")
    return ws


def test_delegate_without_spec_path_no_spec_writes(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    spec = ws / ".mcp-coder" / "specs" / "tasks" / "x.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(SPEC_BODY, encoding="utf-8")
    before = spec.read_text(encoding="utf-8")

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=["a.py"], model="m")
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="t",
            target_files=["a.py"],
            context_summary="c",
        )

    assert spec.read_text(encoding="utf-8") == before
    payload = json.loads(raw)
    assert "outcome" not in payload


def test_delegate_missing_spec_invalid_spec(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup_workspace(tmp_path)
    missing = ws / ".mcp-coder" / "specs" / "tasks" / "missing.md"
    if missing.exists():
        missing.unlink()

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    with patch("server.mcp_server.get_engine") as get_engine:
        raw = delegate_to_agent(
            task="t",
            target_files=["a.py"],
            context_summary="c",
            spec_path="tasks/missing.md",
        )
        get_engine.assert_not_called()

    payload = json.loads(raw)
    assert payload["success"] is False
    assert payload["outcome"] == OUTCOME_INVALID_SPEC
    assert "spec-template.md" in payload["output"]

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["outcome"] == OUTCOME_INVALID_SPEC
    assert record["spec_path"] == ".mcp-coder/specs/tasks/missing.md"


def test_delegate_with_spec_writes_report_not_task(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup_workspace(tmp_path)
    task = ws / ".mcp-coder" / "specs" / "tasks" / "scrape.md"
    report = ws / ".mcp-coder" / "specs" / "reports" / "scrape.md"
    goal_before = parse_sections(split_front_matter(SPEC_BODY)[1])["Goal"]
    task_before = task.read_text(encoding="utf-8")

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_LOG_FULL_PROMPT", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["scraped_content.txt"],
        model="m",
    )
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Create the file now.",
            target_files=["scraped_content.txt"],
            context_summary="",
            spec_path="tasks/scrape.md",
            mode="implement",
        )

    payload = json.loads(raw)
    assert payload["outcome"] == OUTCOME_SUCCESS
    assert payload["spec_path"] == ".mcp-coder/specs/tasks/scrape.md"
    assert payload["spec_report_path"] == ".mcp-coder/specs/reports/scrape.md"
    assert payload["spec_sha256"]
    assert payload["spec_bytes"] > 0

    assert task.read_text(encoding="utf-8") == task_before
    assert report.is_file()
    report_sections = parse_sections(split_front_matter(report.read_text(encoding="utf-8"))[1])
    assert REPORT_STATUS_DELEGATED_OK in report_sections["Status"]
    assert report_sections["Run log"].strip()

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    prompt_full = record["context"]["prompt_full"]
    assert "Write scraped_content.txt" in prompt_full
    assert "Epic north star" in prompt_full
    assert prompt_full.index("Epic north star") < prompt_full.index("Write scraped_content.txt")
    assert prompt_full.index("Write scraped_content.txt") < prompt_full.index("Create the file")


def test_delegate_spec_partial_when_no_files_changed(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = _setup_workspace(tmp_path)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="noop", files_changed=[], model="m")
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="t",
            target_files=["scraped_content.txt"],
            context_summary="",
            spec_path=".mcp-coder/specs/tasks/scrape.md",
        )

    assert json.loads(raw)["outcome"] == OUTCOME_PARTIAL


EDIT_READ_SPEC_BODY = """---
spec_id: cli-step
epic: expense
status: open
---

# Step 2 CLI

## Goal

Add CLI.

## Scope

CLI only.

## Files

### Edit

- `expense_splitter/cli.py`

### Read (include in target_files)

- `expense_splitter/splitter.py` — public API from step 1

## Constraints

- none

## Done when

- [ ] CLI works
"""


def test_delegate_warns_when_read_path_missing_from_target_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    task = ws / ".mcp-coder" / "specs" / "tasks" / "step-02-cli.md"
    task.parent.mkdir(parents=True)
    task.write_text(EDIT_READ_SPEC_BODY, encoding="utf-8")

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["expense_splitter/cli.py"],
        model="m",
    )
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=["expense_splitter/cli.py"],
            context_summary="step 1 done",
            spec_path="tasks/step-02-cli.md",
            mode="implement",
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["spec_files_missing_from_target"] == ["expense_splitter/splitter.py"]
    assert payload["contract_warnings"] == [
        "Spec Files lists paths not in target_files: expense_splitter/splitter.py"
    ]

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["spec_files_missing_from_target"] == ["expense_splitter/splitter.py"]
    assert record["contract_warnings"] == payload["contract_warnings"]
    assert record["mcp_request"]["spec_files_missing_from_target"] == [
        "expense_splitter/splitter.py"
    ]


def test_delegate_no_contract_warn_when_all_paths_in_target(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    task = ws / ".mcp-coder" / "specs" / "tasks" / "step-02-cli.md"
    task.parent.mkdir(parents=True)
    task.write_text(EDIT_READ_SPEC_BODY, encoding="utf-8")

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(success=True, output="ok", files_changed=[], model="m")
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=[
                "expense_splitter/cli.py",
                "expense_splitter/splitter.py",
            ],
            context_summary="",
            spec_path="tasks/step-02-cli.md",
        )

    payload = json.loads(raw)
    assert "spec_files_missing_from_target" not in payload
    assert "contract_warnings" not in payload


STRICT_YAML_SPEC = """---
spec_id: cli-step
files_edit:
  - expense_splitter/cli.py
files_read:
  - expense_splitter/splitter.py
edit_scope: strict
---

# Step 2 CLI

## Goal

Add CLI.

## Files

### Edit

- `ignored/when/yaml/set.py`

### Read

- `also/ignored.py`

## Constraints

- none

## Done when

- [ ] CLI works
"""


def test_delegate_strict_scope_violation(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    task = ws / ".mcp-coder" / "specs" / "tasks" / "strict-cli.md"
    task.parent.mkdir(parents=True)
    task.write_text(STRICT_YAML_SPEC, encoding="utf-8")

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["expense_splitter/cli.py", "expense_splitter/splitter.py"],
        model="m",
    )
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=[
                "expense_splitter/cli.py",
                "expense_splitter/splitter.py",
            ],
            context_summary="",
            spec_path="tasks/strict-cli.md",
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["outcome"] == OUTCOME_SCOPE_VIOLATION
    assert payload["scope_violations"] == ["expense_splitter/splitter.py"]
    assert payload["delegation_policies"]["edit_scope"] == "strict"
    assert payload["delegation_policies"]["files_edit"] == ["expense_splitter/cli.py"]

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["outcome"] == OUTCOME_SCOPE_VIOLATION
    assert record["scope_violations"] == ["expense_splitter/splitter.py"]
    assert record["delegation_policies"]["edit_scope"] == "strict"


def test_delegate_invalid_edit_scope_invalid_spec(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    task = ws / ".mcp-coder" / "specs" / "tasks" / "bad-policy.md"
    task.parent.mkdir(parents=True)
    task.write_text(
        "---\nspec_id: bad\nedit_scope: tight\n---\n\n## Goal\n\nt\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    with patch("server.mcp_server.get_engine") as get_engine:
        raw = delegate_to_agent(
            task="t",
            target_files=["a.py"],
            context_summary="",
            spec_path="tasks/bad-policy.md",
        )
        get_engine.assert_not_called()

    payload = json.loads(raw)
    assert payload["success"] is False
    assert payload["outcome"] == OUTCOME_INVALID_SPEC
    assert "edit_scope" in payload["output"]


def test_delegate_discover_no_scope_violation_outcome(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    task = ws / ".mcp-coder" / "specs" / "tasks" / "discover.md"
    task.parent.mkdir(parents=True)
    task.write_text(EDIT_READ_SPEC_BODY, encoding="utf-8")

    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["expense_splitter/cli.py", "expense_splitter/splitter.py"],
        model="m",
    )
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Implement CLI",
            target_files=[
                "expense_splitter/cli.py",
                "expense_splitter/splitter.py",
            ],
            context_summary="",
            spec_path="tasks/discover.md",
        )

    payload = json.loads(raw)
    assert payload["outcome"] == OUTCOME_SUCCESS
    assert "scope_violations" not in payload
