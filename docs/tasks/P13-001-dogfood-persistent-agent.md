# Worker spec: P13-001 — Dogfood persistent Supervisor architecture

**Task ID:** P13-001  
**PM doc:** [PHASE13_MVP.md](../PHASE13_MVP.md)  
**Depends on:** Phase 12 closed (P12-001..005, issues, BL-545 v1)

> **Worker / master session**: this milestone is **dogfood + analysis**, not feature code unless a blocking bug is found.  
> Fill **§ Results** with delegation IDs, checklist outcomes, and filed issues.  
> File new bugs in [PHASE13_ISSUES.md](../PHASE13_ISSUES.md). Do not edit sibling task specs.

---

## Goal

Fully exercise the Phase 12 **persistent Supervisor** architecture under real use:

1. **Part A (CLI)** — targeted automated smoke, then 2 live delegations on the same `project_key`.
2. **Part B (Cursor)** — multi-step habit-tracker app build across 4+ delegations; you (host) run delegations and use the trace viewer; master session analyzes logs via CLI.
3. **Agree** on whether behaviour matches design; file issues with fix-now vs defer decision.

Infrastructure-only gaps already deferred (BL-543 B/C, BL-547) — do **not** treat as P13-001 failures unless dogfood shows a regression in what **did** ship.

---

## Files policy

### May use / create
- `scripts/p13_phase12_cli_dogfood.py` — CLI harness (exists; extend if needed)
- `tests/p13_dogfood_workspace/` — isolated dogfood workspace
- `docs/PHASE13_ISSUES.md` — file issues found during dogfood
- This file § Results

### Must not touch
- Production code unless a **blocking** dogfood bug requires a minimal fix (separate commit; note in § Results)
- `PHASE12_*`, `IDEA.md`, `PHASES.md` (master session only)

---

## Part A — CLI targeted tests

### A0 — Automated gate (no LLM)

From repo root:

```bash
python scripts/p13_phase12_cli_dogfood.py --quick
```

**Pass criteria:**
- Phase 12 unit subset: **67+ passed** (supervisor state, project state, tool runner, reviewer, planner, BL-545)
- Workspace `tests/p13_dogfood_workspace/` bootstrapped
- Specs `tasks/p13-habit-01-models.md` and `tasks/p13-habit-02-storage.md` present
- Expected `project_key`: `tasks/p13-habit`

**Master session status (2026-06-21):** ✅ `--quick` passed.

### A1 — Live CLI multi-delegation (LLM)

```bash
export MCP_CODER_HOME="$(pwd)/tests/p13_dogfood_workspace/.mcp-coder-home"
export MCP_CODER_PLANNER_PASS=1
export MCP_CODER_REVIEWER_PASS=1
python scripts/p13_phase12_cli_dogfood.py --live
```

**Pass criteria:**
- Both delegations return `"ok": true`
- `tests/p13_dogfood_workspace/.mcp-coder-home/projects/tasks/p13-habit/project_state.json` exists after run 2
- Delegation 2 trace shows `project_state_loaded` and ideally `planner_context_sources` containing `project_state`
- `decisions[]` or `hot_areas[]` non-empty after run 2 (best effort)

**Analyze each delegation:**

```bash
mcp-coder trace inspect --delegation-id <ID> --workspace tests/p13_dogfood_workspace
mcp-coder trace inspect --delegation-id <ID> --workspace tests/p13_dogfood_workspace --summary
```

Record delegation IDs in § Results.

### A2 — Optional CLI pause/resume smoke

If A1 passes, optional third call simulating resume (requires a paused state from a prior `needs_input` escalation — may be **manual** in Part B instead):

```python
# From repo root, after a paused delegation exists for project_key tasks/p13-habit:
from server.mcp_server import delegate_to_agent
import json, os
os.chdir("tests/p13_dogfood_workspace")
os.environ["MCP_CODER_HOME"] = ".mcp-coder-home"
print(json.loads(delegate_to_agent(
    task="Continue",
    target_files=["habit_cli/models.py"],
    context_summary="",
    answer="Use JSON file storage in workspace root.",
)))
```

**Pass criteria:** `supervisor_resumed` in trace; planner/clarity **not** re-run (grep trace types).

---

## Part B — Cursor manual session (complex app)

### Setup

1. Open **`tests/p13_dogfood_workspace`** as the Cursor workspace (or a copy).
2. Set MCP env for isolated home:
   - `MCP_CODER_HOME=<workspace>/.mcp-coder-home`
3. Enable planner + reviewer passes (env or spec front matter).
4. Ensure mcp-coder MCP server connected with `cwd` = dogfood workspace.

### Epic: Habit Tracker CLI (`tasks/p13-habit`)

Build incrementally — **same project_key** (`tasks/p13-habit`) across all steps.

| Step | spec_path | Delivers |
|------|-----------|----------|
| 1 | `tasks/p13-habit-01-models.md` | `habit_cli/models.py` |
| 2 | `tasks/p13-habit-02-storage.md` | `habit_cli/storage.py` |
| 3 | `tasks/p13-habit-03-cli.md` | `habit_cli/cli.py` — `add`, `list`, `check` subcommands |
| 4 | `tasks/p13-habit-04-tests.md` | `tests/test_habit_cli.py` — basic tests |

Specs 01–02 are pre-created by the CLI harness. Create 03–04 in `.mcp-coder/specs/tasks/` before delegating (copy templates from `resources/` or duplicate 01 format).

### Copy-paste — Cursor host prompt (start session)

```
We are dogfooding Phase 12 persistent Supervisor architecture (P13-001).

Workspace: tests/p13_dogfood_workspace (habit_cli package).
MCP_CODER_HOME must point to <workspace>/.mcp-coder-home so project state is isolated.

Run delegations **sequentially** via delegate_to_agent — one spec per step, same epic prefix tasks/p13-habit:

1. tasks/p13-habit-01-models.md — implement habit_cli/models.py
2. tasks/p13-habit-02-storage.md — implement habit_cli/storage.py  
3. tasks/p13-habit-03-cli.md — implement habit_cli/cli.py (add/list/check)
4. tasks/p13-habit-04-tests.md — add tests/test_habit_cli.py

After **each** delegation:
- Note delegation_id from the response
- Do NOT call start_fresh unless we intentionally abandon paused state
- If outcome is needs_input / paused: answer via delegate_to_agent with answer= (no resume_token)

After step 2 and step 4, verify project_state.json exists under .mcp-coder-home/projects/tasks/p13-habit/

Optional pause/resume test (step 3 or 4): if supervisor escalates, stop and resume with answer= on the next delegate_to_agent call.

When all steps done, paste delegation IDs here for log analysis.
```

### Copy-paste — Step 3 spec (`tasks/p13-habit-03-cli.md`)

```markdown
---
spec_id: p13-habit-03-cli
epic: p13-habit
revision: 1
status: draft
planner_pass: true
reviewer_pass: true
---

## Goal

CLI entrypoint for habit tracker.

## Scope

Create `habit_cli/cli.py` only; wire to storage.

## Files

- `habit_cli/cli.py`
- `habit_cli/storage.py`
- `habit_cli/models.py`

## Constraints

- argparse: `habit add <name>`, `habit list`, `habit check <name>` (marks done today)
- Default habits file: `habits.json` in workspace root
- `python -m habit_cli.cli --help` works

## Done when

- [ ] all three subcommands work
```

### Copy-paste — Step 4 spec (`tasks/p13-habit-04-tests.md`)

```markdown
---
spec_id: p13-habit-04-tests
epic: p13-habit
revision: 1
status: draft
planner_pass: true
reviewer_pass: true
---

## Goal

Basic tests for habit CLI.

## Scope

Create `tests/test_habit_cli.py` only.

## Files

- `tests/test_habit_cli.py`
- `habit_cli/cli.py`

## Constraints

- pytest; use tmp_path for habits.json
- At least: add + list smoke test

## Done when

- [ ] pytest tests/test_habit_cli.py passes
```

---

## Trace / log analysis checklist

For **each** delegation ID, master session (CLI) and host (viewer) verify:

| Check | Event / artifact | Expected |
|-------|------------------|----------|
| Project state load | `project_state_loaded` | Present from delegation 2+ on same project_key |
| Project state save | `project_state_saved` | End of delegations that touch files |
| Planner memory | `planner_context_sources` includes `project_state` | Delegation 3+ (when state non-empty) |
| Reviewer loop | `reviewer_findings_classified` | When reviewer_pass runs |
| Risks promoted | `project_state_risks_updated` | If reviewer finding notable+ |
| Singleton | `project_state_loaded` once per process | Second delegation same MCP process — counts should not duplicate cold-load noise (best effort) |
| Tool runner | `supervisor_tool_call` | May appear on inter-turn / confirm_ask paths |
| Session reset | `supervisor_session_reset` | On resume path only (if pause/resume tested) |
| Pause | `supervisor_paused` | If escalated to host |
| Resume | `supervisor_resumed` | After `answer=` delegate |
| **Not required** | `supervisor_intercept` | Deferred BL-547 |
| **Not required** | `supervisor_context_refresh` | Deferred BL-543 C |

**CLI commands:**

```bash
mcp-coder trace inspect --delegation-id <ID> --workspace tests/p13_dogfood_workspace
mcp-coder trace inspect --delegation-id <ID> --field type --workspace tests/p13_dogfood_workspace
mcp-coder logs tail --delegation-id <ID> --workspace tests/p13_dogfood_workspace
```

**Disk checks:**

```bash
cat tests/p13_dogfood_workspace/.mcp-coder-home/projects/tasks/p13-habit/project_state.json
ls tests/p13_dogfood_workspace/.mcp-coder-home/projects/tasks/p13-habit/supervisor_states/  # if paused
```

---

## Issue filing protocol

When behaviour diverges from **shipped** Phase 12 scope:

1. Add row to `PHASE13_ISSUES.md` with: ID, severity, summary, delegation_id, fix-now vs defer.
2. In § Results, list issue IDs and decision.
3. **Fix-now** only if: data loss, wrong resume (re-runs pipeline), project_state corruption, or crash.
4. **Defer** if: missing BL-547 intercept, missing full continuation brief, cosmetic trace gaps.

---

## Acceptance

- [ ] A0 `--quick` passed (record date)
- [ ] A1 `--live` passed OR documented blocker with issue filed
- [ ] Part B: ≥3 delegations completed in Cursor with delegation IDs recorded
- [ ] Checklist table in § Results filled per delegation
- [ ] Master + host agree: shipped architecture works / or issues filed with disposition
- [ ] P13-003/P13-004 recommendations listed (tests to add, backlog picks)

---

## § Results

*(Fill during dogfood.)*

**Date:**  
**A0 quick:**  
**A1 live delegation IDs:**  
**Part B delegation IDs:**  

### Checklist (per ID)

| delegation_id | project_state_loaded | project_state_saved | planner project_state | reviewer classified | notes |
|---------------|---------------------|---------------------|----------------------|---------------------|-------|

### Issues filed

| ID | Severity | Summary | Disposition |
|----|----------|---------|-------------|

### Recommended follow-ups (P13-003 / P13-004)

- 
