# Phase 3 Wave 1 exit validation (checkpointing dogfood)

**Milestone:** P3-401 — Wave 1 sign-off  
**Workspace:** `~/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e`  
**Code repo:** `mcp_coder` (`main` @ P3-322f+)  
**Issues:** [PHASE3_ISSUES.md](../PHASE3_ISSUES.md)

Validates **workspace history** shipped in P3-322a–f: manifest attribution, diffs, checkpoint metadata, MCP/CLI inspect.

**Note:** Step 1 (`06418163`) ran before 322a — **no row in `workspace_history.db`**. This dogfood creates **fresh checkpoints** via new delegations (step 2+).

---

## 0. Prerequisites (once)

### Code repo

```bash
cd ~/Dropbox/CodingProjects/personal_tools/mcp_coder
pytest -q --ignore=tests/test_cli_test_model.py   # expect 397+ passed
```

### E2E workspace

```bash
cd ~/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e
pip install -e .    # once per venv; enables tip_calc import
pytest -q           # expect 3 passed (step 1 core)
```

Workspace state (2026-06-08):

- **No git** — manifest attribution (P3-ISS-001 / D-P3-2)
- **tip_calc** step 1 code present; **planner writes** epic + step specs (master does not pre-create task specs in e2e)
- MCP: `.cursor/mcp.json` → `mcp_coder` venv + `.env`

### Server env (`mcp_coder/.env`)

| Variable | Suggested |
|----------|-----------|
| `AIDER_MODEL` | `openrouter/openai/gpt-4o-mini` (or your usual mid tier) |
| `MCP_CODER_DELEGATION_TIMEOUT_S` | `180` |
| `MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT` | **unset** (snapshot must be on) |

### CLI shim

```bash
export PATH="$HOME/Dropbox/CodingProjects/personal_tools/mcp_coder/scripts:$PATH"
```

### MCP

1. Open **`mcp_coder_phase1_e2e`** in Cursor (not the `mcp_coder` repo).
2. **Restart MCP** after any `.env` change or mcp-coder upgrade (syncs Cursor rules).
3. Confirm **two** managed rules in `.cursor/rules/`: `use-mcp-coder.mdc` + `workspace-history.mdc`.
4. **New Composer chat** for Phase 1 delegate below.

---

## Phase 1 — Delegate step 2 (creates checkpoint)

**Spec:** planner-authored `.mcp-coder/specs/tasks/tip-calc-02-cli.md` (or equivalent step 2 task)

**Cursor prompt** (natural — do not mention P3 or dogfood):

> Step 1 of the tip calculator is done (`calculate_tip` + tests pass). Plan and implement **step 2** (CLI) — epic + step spec under `.mcp-coder/specs/`, delegate to mcp-coder, don't write code yourself. Include read-deps in `target_files`. After delegate, run `pytest` and confirm `python -m tip_calc 25.00 18` works.

**Pass:**

- [ ] `delegate_to_agent` **implement** succeeds
- [ ] Response includes **`delegation_diff`** (created/modified paths + diffs map)
- [ ] Response or JSONL has **`checkpoint`** with `summary` + `outcome`
- [ ] `checkpoint_summary` mentions CLI or Goal line (not empty)
- [ ] `pytest` passes in e2e workspace (3+ tests)
- [ ] `python -m tip_calc 25.00 18` shows tip `4.50` and total `29.50`

**Record:** `delegation_id` from MCP response → `STEP2_ID=...`

---

## Phase 2 — CLI history inspect

From **any** terminal (`mcp_coder` repo or e2e):

```bash
WS=~/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e
MC=~/Dropbox/CodingProjects/personal_tools/mcp_coder

$MC/.venv/bin/python $MC/main.py history list --workspace "$WS"
$MC/.venv/bin/python $MC/main.py history show --latest --workspace "$WS"
$MC/.venv/bin/python $MC/main.py history diff --latest --workspace "$WS" --path tip_calc/core.py
```

If step 2 touched `tip_calc/__main__.py`:

```bash
$MC/.venv/bin/python $MC/main.py history file tip_calc/__main__.py --workspace "$WS"
```

**Pass:**

- [ ] `history list` shows row with **checkpoint summary** and delta counts
- [ ] `history show --latest` shows `spec_path`, `spec_report_path`, file lists
- [ ] `history diff --latest --path …` prints a unified diff hunk (or “no diff” if file only created)
- [ ] `delegation_id` matches Phase 1 `STEP2_ID`

---

## Phase 3 — MCP inspect tools (in Cursor)

In the **same or new chat** (e2e workspace), ask the agent to call MCP tools:

> Use mcp-coder tools only: `list_delegations` (limit 5), then `get_checkpoint_detail` with `latest=true`, then `get_delegation_diff` with `latest=true` and `file_path=tip_calc/core.py`. Summarize what changed in the last delegation.

Optional if multiple files changed:

> Call `get_file_history` for `tip_calc/__main__.py`.

**Pass:**

- [ ] `list_delegations` returns `found: true` and ≥1 row with `checkpoint_summary`
- [ ] `get_checkpoint_detail(latest=true)` matches CLI `history show`
- [ ] `get_delegation_diff(latest=true)` matches Phase 1 `delegation_diff`
- [ ] Tools return `{found: false, error}` — never crash — when given a bogus `delegation_id`

---

## Phase 4 — JSONL audit (canonical record)

```bash
# Find latest JSONL line for this workspace (path varies by project_key)
tail -1 ~/.mcp-coder/projects/*/sessions/*/delegations.jsonl | python3 -m json.tool | head -80
```

**Pass:**

- [ ] `workspace_snapshot` block with `delta` (created/modified/deleted)
- [ ] `checkpoint: {summary, outcome}`
- [ ] `spec_path` + `spec_report_path` pointers present
- [ ] `files_changed` lists paths (manifest-primary; no git required)

---

## Phase 5 — Optional second delegate (file timeline)

For **`history file`** / `get_file_history` with **2+ entries** on the same path, run a tiny follow-up (planner writes spec or use prompt):

> Add a one-line module docstring to `tip_calc/core.py` only. New task spec `tip-calc-03-docstring.md`, delegate implement, run pytest.

Then:

```bash
$MC/.venv/bin/python $MC/main.py history file tip_calc/core.py --workspace "$WS"
```

**Pass:**

- [ ] Two delegations listed for `tip_calc/core.py` (step 2 may not have modified core — step 3 should)

Skip if step 2 already gives enough signal.

---

## Phase 6 — Optional strict gateway spot-check

Only if you want to exercise **P3-322c** auto-revert:

1. Duplicate a task spec with `edit_scope: strict` and `files_edit` listing **only** one file.
2. Delegate a task that might tempt the executor to touch another file.
3. Check `post_gateway.reverted` in JSONL and disk state.

Skip by default — flaky with live models.

---

## Audit shortcuts

```bash
WS=~/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e
MC=~/Dropbox/CodingProjects/personal_tools/mcp_coder

# DB path
$MC/.venv/bin/python -c "
from pathlib import Path
from core.storage.paths import workspace_history_db_path
print(workspace_history_db_path(Path('$WS').expanduser()))
"

# Revert smoke (destructive — only on a throwaway path or backup first)
# $MC/.venv/bin/python $MC/main.py history revert <delegation_id> --workspace "$WS" --paths tip_calc/__main__.py
```

---

## Sign-off

| Field | Value |
|-------|-------|
| Date | 2026-06-09 |
| mcp_coder pytest | 397+ passed |
| e2e pytest | 4 passed |
| Final delegate `delegation_id` | `594b627e-a3c3-48f7-a7d6-455c38ab4b13` |
| Attempts on step 2 | 6 (all MCP `success: true`; planner retried) |
| Phases 1–4 pass | Phase 1 ✓; 2–4 verify below |
| Phase 5–6 | skipped |
| P3-ISS-001 | manifest attribution in live run (no git) |
| Pull 322g/h? | defer; **pull P3-320** stronger after 6-attempt step |
| Cursor rules history tools | `workspace-history.mdc` v1 (composed with policy rule) |

### Phase log

| Phase | Pass? | Notes |
|-------|-------|-------|
| 1 delegate step 2 | ✓ | 6 delegations; final `594b627e`; CLI + 4 pytest |
| 2 CLI history | ✓ | 6 rows in `history list`; `show --latest` has summary + report path |
| 3 MCP inspect | user | `list_delegations`, `get_checkpoint_detail`, `get_file_history` |
| 4 JSONL audit | ✓ | All 6 runs in report Run log; `checkpoint` + `workspace_snapshot` from run 2+ |
| 5 file timeline | partial | `history file tip_calc/__main__.py` shows 1 modify; nested paths separate |
| 6 strict gateway | skip | |

---

## After sign-off

- Master: mark P3-401 done in [PHASE3_MVP.md](../PHASE3_MVP.md); fill task spec § Results if created.
- If bisect/restore hurt: prioritize **P3-322g** / BL-322g.
- Next wave: **P3-002-lite** RAG or **P3-311** read-deps auto-merge per board.
