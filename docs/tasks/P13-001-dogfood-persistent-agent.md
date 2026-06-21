# P13-001 — Dogfood persistent Supervisor architecture

**Task ID:** P13-001  
**PM doc:** [PHASE13_MVP.md](../PHASE13_MVP.md)  
**Owner:** **master session** (dogfood + analysis; no new repo code unless blocking bug)  
**Depends on:** Phase 12 closed (P12-001..005, issues, BL-545 v1)

> Use **existing CLI only** (`mcp-coder delegate`, `trace inspect`, `logs tail`, `pytest`).  
> Do not add dogfood scripts to the repo.  
> Fill **§ Results** when done. File bugs in [PHASE13_ISSUES.md](../PHASE13_ISSUES.md).

---

## Goal

Prove the Phase 12 **persistent Supervisor** works end-to-end:

1. **Part A** — `pytest` gate + 1–2 live CLI delegations on the same `project_key`
2. **Part B** — Cursor: 4-step habit-tracker epic; host runs `delegate_to_agent`; master analyzes traces
3. Agree behaviour vs design; file issues (fix-now vs defer)

Deferred by design (not failures): BL-543 B/C, BL-547 (`supervisor_intercept`).

---

## Part A — CLI (existing tools)

### A0 — Unit gate (no LLM)

From repo root:

```bash
python -m pytest -q \
  tests/test_supervisor_state_p12_001.py \
  tests/test_supervisor_agent_p12_001.py \
  tests/test_project_state_p12_002.py \
  tests/test_supervisor_tool_runner_p12_003.py \
  tests/test_reviewer_findings_p12_004.py \
  tests/test_planner_project_aware_p12_005.py \
  tests/test_supervisor_token_accounting_p12_iss_004.py \
  tests/test_supervisor_session_reset_bl545.py
```

**Pass:** all green (87 tests as of Phase 12 closeout).

**Master session (2026-06-21):** ✅ passed.

### A1 — Optional single smoke (LLM)

```bash
python scripts/smoke_delegation.py
```

Uses `tests/smoke_workspace` — one live delegation sanity check.

### A2 — Two delegations, same project_key (LLM)

Use **any workspace** as cwd (a fresh folder is fine). Create `.mcp-coder/specs/tasks/` and add the two specs below (or open the folder in Cursor once so MCP creates the layout).

Set isolated home (recommended):

```bash
export MCP_CODER_HOME="$PWD/.mcp-coder-home"
export MCP_CODER_PLANNER_PASS=1
export MCP_CODER_REVIEWER_PASS=1
```

**Delegation 1:**

```bash
mcp-coder delegate \
  --task "Implement habit_cli/models.py per spec." \
  --target-files habit_cli/models.py \
  --spec tasks/p13-habit-01-models.md \
  --pretty
```

**Delegation 2** (same workspace, same epic prefix → `project_key` = `tasks/p13-habit`):

```bash
mcp-coder delegate \
  --task "Implement habit_cli/storage.py per spec." \
  --target-files habit_cli/storage.py,habit_cli/models.py \
  --spec tasks/p13-habit-02-storage.md \
  --pretty
```

**Pass criteria:**

- Both return `"ok": true`
- `$MCP_CODER_HOME/projects/tasks/p13-habit/project_state.json` exists after #2
- Trace for #2: `project_state_loaded`; planner audit ideally includes `project_state`

**Analyze:**

```bash
mcp-coder trace inspect --delegation-id <ID> --summary
mcp-coder trace inspect --delegation-id <ID> --field type
```

### Spec copy-paste — `tasks/p13-habit-01-models.md`

```markdown
---
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
- `@dataclass` `Habit` with `name: str`, `created_at: str` (ISO date)

## Done when

- [ ] `Habit` dataclass exists
```

### Spec copy-paste — `tasks/p13-habit-02-storage.md`

```markdown
---
spec_id: p13-habit-02-storage
epic: p13-habit
revision: 1
status: draft
planner_pass: true
reviewer_pass: true
---

## Goal

JSON file storage for habits.

## Scope

Create `habit_cli/storage.py` only.

## Files

- `habit_cli/storage.py`
- `habit_cli/models.py`

## Constraints

- `load_habits(path) -> list[Habit]`, `save_habits(path, habits) -> None`
- JSON list in `habits.json` at workspace root

## Done when

- [ ] load/save round-trip works
```

---

## Part B — Cursor session (4-step epic)

Open a **dedicated dogfood folder** in Cursor (not required to live in this repo). Set `MCP_CODER_HOME=<workspace>/.mcp-coder-home`. Create all four specs under `.mcp-coder/specs/tasks/`.

| Step | spec_path | Delivers |
|------|-----------|----------|
| 1 | `tasks/p13-habit-01-models.md` | `habit_cli/models.py` |
| 2 | `tasks/p13-habit-02-storage.md` | `habit_cli/storage.py` |
| 3 | `tasks/p13-habit-03-cli.md` | `habit_cli/cli.py` |
| 4 | `tasks/p13-habit-04-tests.md` | `tests/test_habit_cli.py` |

### Copy-paste — Cursor host prompt

```
P13-001 dogfood: Phase 12 persistent Supervisor.

Use a dedicated workspace folder. MCP_CODER_HOME=<workspace>/.mcp-coder-home.

Run delegate_to_agent sequentially (same project_key tasks/p13-habit):

1. tasks/p13-habit-01-models.md
2. tasks/p13-habit-02-storage.md
3. tasks/p13-habit-03-cli.md
4. tasks/p13-habit-04-tests.md

After each call: save delegation_id. If needs_input: resume with answer= (no resume_token).
After step 2 and 4: check .mcp-coder-home/projects/tasks/p13-habit/project_state.json

Paste delegation IDs for master trace analysis.
```

Steps 3–4 spec bodies are in the previous version of this doc — keep in master notes or add when running Part B.

---

## Trace checklist

| Check | Event | Expected (delegation 2+) |
|-------|-------|--------------------------|
| State load | `project_state_loaded` | yes |
| State save | `project_state_saved` | yes |
| Planner | `planner_context_sources` → `project_state` | delegation 3+ when state non-empty |
| Reviewer | `reviewer_findings_classified` | if reviewer_pass on |
| Pause/resume | `supervisor_paused` / `supervisor_resumed` | if tested |
| **Not required** | `supervisor_intercept` | BL-547 deferred |

---

## Issue protocol

- **Fix-now:** data loss, resume re-runs pipeline, state corruption, crash
- **Defer:** missing intercept, full continuation brief, cosmetic gaps

---

## Acceptance

- [ ] A0 pytest passed
- [ ] A1 and/or A2 live delegations with IDs recorded
- [ ] Part B: ≥3 Cursor delegations with checklist
- [ ] Issues filed with disposition
- [ ] P13-003/P13-004 recommendations noted

---

## § Results

**Date:** 2026-06-21  
**Workspace:** `/tmp/mcp_p13_dogfood` (ephemeral; not in repo)  
**A0 pytest:** ✅ 87 passed (prior session)  
**A1 smoke:** skipped  
**CLI delegation IDs:**
- `f5fbc2bd-91fa-4258-b70a-31813a7edf77` — del 1 models — **success**
- `db96b1ce-e5ed-490f-84aa-606282bfdf8d` — del 2 storage — **needs_input** (executor stall; storage.py partially written)

**Part B Cursor:** not run yet

### Checklist

| delegation_id | project_state_loaded | project_state_saved | planner project_state | notes |
|---------------|---------------------|---------------------|----------------------|-------|
| f5fbc2bd | ✅ | ✅ | n/a | reviewer false critical on Habit |
| db96b1ce | ✅ (2 prior risks) | ✅ | ✅ in planner prompt | exec failed; memory worked |

### Issues

| ID | Severity | Summary | Disposition |
|----|----------|---------|-------------|
| P13-ISS-001 | medium | project_key `mcp-coder/specs` | fix P13-004 |
| P13-ISS-002 | low | epic stem `tasks/p13` | defer + docs |
| P13-ISS-003 | low | reviewer false critical | defer |

### Follow-ups (P13-003 / P13-004)

- Fix ISS-001 or use `MCP_CODER_PROJECT_KEY` before Cursor epic
- Integration test for cross-delegation project_state
- Cursor Part B after workaround
