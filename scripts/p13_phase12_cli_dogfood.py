#!/usr/bin/env python3
"""P13-001 targeted CLI dogfood for Phase 12 persistent Supervisor architecture."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "tests" / "p13_dogfood_workspace"
HOME = WORKSPACE / ".mcp-coder-home"
SPECS_DIR = WORKSPACE / ".mcp-coder" / "specs" / "tasks"
PROJECT_KEY = "tasks/p13-habit"
STATE_PATH = HOME / "projects" / PROJECT_KEY / "project_state.json"

SPEC_01 = """---
spec_id: p13-habit-01-models
epic: p13-habit
revision: 1
status: draft
planner_pass: true
reviewer_pass: true
---

## Goal

Add core data models for the habit tracker.

## Scope

Create `habit_cli/models.py` only.

## Files

- `habit_cli/models.py`

## Constraints

- Python 3.10+; stdlib only
- Use `@dataclass` for `Habit` (name: str, created_at: ISO date string)
- No CLI yet

## Done when

- [ ] `Habit` dataclass exists with `name` and `created_at`
"""

SPEC_02 = """---
spec_id: p13-habit-02-storage
epic: p13-habit
revision: 1
status: draft
planner_pass: true
reviewer_pass: true
---

## Goal

Add JSON file storage for habits.

## Scope

Create `habit_cli/storage.py` only.

## Files

- `habit_cli/storage.py`
- `habit_cli/models.py`

## Constraints

- Load/save list of `Habit` to `habits.json` in workspace root
- Functions: `load_habits(path) -> list[Habit]`, `save_habits(path, habits) -> None`

## Done when

- [ ] storage module reads/writes JSON list of habits
"""


def _run_pytest() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_supervisor_state_p12_001.py",
        "tests/test_project_state_p12_002.py",
        "tests/test_supervisor_tool_runner_p12_003.py",
        "tests/test_reviewer_findings_p12_004.py",
        "tests/test_planner_project_aware_p12_005.py",
        "tests/test_supervisor_session_reset_bl545.py",
    ]
    print("== Phase 12 unit tests ==")
    return subprocess.call(cmd, cwd=ROOT)


def _bootstrap_specs() -> None:
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    (SPECS_DIR / "p13-habit-01-models.md").write_text(SPEC_01, encoding="utf-8")
    (SPECS_DIR / "p13-habit-02-storage.md").write_text(SPEC_02, encoding="utf-8")


def _delegate(spec_name: str, task: str, target_files: list[str]) -> dict:
    from server.mcp_server import delegate_to_agent

    raw = delegate_to_agent(
        task=task,
        target_files=target_files,
        context_summary="P13 dogfood: habit_cli incremental build.",
        spec_path=f"tasks/{spec_name}",
        backend="aider",
        cli_artifacts=True,
    )
    return json.loads(raw)


def _trace_types(delegation_id: str) -> list[str]:
    from core.cli.trace_inspect import _find_trace_path, _load_trace_events

    trace_path = _find_trace_path(WORKSPACE, delegation_id)
    if trace_path is None:
        return []
    return [str(e.get("type") or "?") for e in _load_trace_events(trace_path)]


def _quick_checks() -> int:
    print("== Quick checks (no LLM) ==")
    if not WORKSPACE.is_dir():
        print("FAIL: workspace missing", WORKSPACE)
        return 1
    _bootstrap_specs()
    for name in ("p13-habit-01-models.md", "p13-habit-02-storage.md"):
        path = SPECS_DIR / name
        if not path.is_file():
            print("FAIL: spec missing", path)
            return 1
    print("OK: workspace + specs bootstrapped")
    print("OK: project_key will be", PROJECT_KEY)
    print("OK: state path will be", STATE_PATH)
    return 0


def _live_run() -> int:
    os.environ["MCP_CODER_HOME"] = str(HOME)
    os.environ.setdefault("MCP_CODER_PLANNER_PASS", "1")
    os.environ.setdefault("MCP_CODER_REVIEWER_PASS", "1")

    from core.config import apply_provider_env, load_env_files, resolve_model_name
    from core.config.models import provider_hint_for_model

    load_env_files()
    apply_provider_env()
    hint = provider_hint_for_model(resolve_model_name())
    if hint:
        print("FAIL: model config:", hint)
        return 1

    _bootstrap_specs()
    HOME.mkdir(parents=True, exist_ok=True)
    os.chdir(WORKSPACE)

    results: list[dict] = []
    for spec, task, targets in (
        (
            "p13-habit-01-models.md",
            "Implement habit_cli/models.py per spec. Minimal diff.",
            ["habit_cli/models.py"],
        ),
        (
            "p13-habit-02-storage.md",
            "Implement habit_cli/storage.py per spec. Reuse Habit from models.",
            ["habit_cli/storage.py", "habit_cli/models.py"],
        ),
    ):
        print(f"\n== Live delegation: {spec} ==")
        payload = _delegate(spec, task, targets)
        results.append(payload)
        print(json.dumps({k: payload.get(k) for k in ("ok", "success", "outcome", "delegation_id", "error")}, indent=2))
        if not payload.get("ok"):
            return 2

    if not STATE_PATH.is_file():
        print("FAIL: project_state.json not created at", STATE_PATH)
        return 3
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    print("\n== project_state.json ==")
    print(json.dumps({k: state.get(k) for k in ("version", "project_key", "last_delegation", "decisions", "open_risks", "hot_areas")}, indent=2)[:2000])

    for payload in results:
        did = str(payload.get("delegation_id") or "")
        if not did:
            continue
        types = _trace_types(did)
        p12_events = [
            t
            for t in types
            if t.startswith("project_state")
            or t.startswith("supervisor")
            or t in ("planner_pass", "reviewer_findings_classified")
        ]
        print(f"\n== trace highlights ({did}) ==")
        print(", ".join(p12_events) or "(none)")

    print("\n== Analyze ==")
    for payload in results:
        did = payload.get("delegation_id")
        if did:
            print(f"  mcp-coder trace inspect --delegation-id {did} --workspace {WORKSPACE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Layout + pytest only (no LLM)")
    parser.add_argument("--live", action="store_true", help="Run 2 live delegations (LLM cost)")
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    if not args.skip_pytest:
        if _run_pytest() != 0:
            return 1
    if _quick_checks() != 0:
        return 1
    if args.live:
        return _live_run()
    if not args.quick and not args.live:
        parser.print_help()
        print("\nPass --quick or --live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
