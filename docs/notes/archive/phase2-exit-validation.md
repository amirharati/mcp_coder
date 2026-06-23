# Phase 2 exit validation

**Milestone:** P2-499 — Phase 2 sign-off  
**Workspace:** `mcp_coder_phase1_e2e`  
**Code repo:** `mcp_coder` (`main` @ P2-3.15+)  
**Issues:** [PHASE2_ISSUES.md](../../PHASE2_ISSUES.md)

Structured phases first (specific tasks), then **wild test** (natural multi-step epic).

---

## 0. Prerequisites (once per session)

### mcp_coder repo

```bash
cd ~/Dropbox/CodingProjects/personal_tools/mcp_coder
pytest -q   # record count
```

### Server env (`mcp_coder/.env`)

| Variable | Phase 2 exit default | Notes |
|----------|----------------------|-------|
| `AIDER_MODEL` | `openrouter/openai/gpt-4o-mini` | Raise tier if timeouts |
| `MCP_CODER_DELEGATION_TIMEOUT_S` | `180` | **Phase 2 only:** temporarily `30` |
| `MCP_CODER_USE_CONTEXT_PACKAGE` | `1` (default) | Leave on for Phases 4–6 |
| `MCP_CODER_REVIEW_MODEL` | optional | e.g. Sonnet if different from executor |

### CLI shim (Phase 3)

```bash
export PATH="$HOME/Dropbox/CodingProjects/personal_tools/mcp_coder/scripts:$PATH"
```

### MCP

1. E2E workspace open in Cursor: `mcp_coder_phase1_e2e`
2. **Restart MCP** after any `.env` change (`envFile` in `.cursor/mcp.json`)
3. **New Composer chat** per phase block (or per wild epic)

---

## Phase 1 — Placeholder filter (P2-ISS-001)

**Spec:** `.mcp-coder/specs/tasks/phase2-exit-01-placeholder.md` (pre-created)

**Cursor prompt:**

> Run `inspect_context` (or `delegate_to_agent` mode=implement) for spec `.mcp-coder/specs/tasks/phase2-exit-01-placeholder.md` with `target_files: ["expense_splitter/splitter.py"]`. Summarize `contract_warnings` and `spec_files_missing_from_target` if present.

**Pass:**

- [ ] No `contract_warnings` mentioning `(none)`
- [ ] No `spec_files_missing_from_target: ["(none)"]`
- [ ] Delegation / inspect completes without treating `(none)` as a path

**Record:** `delegation_id` or inspect response snippet.

---

## Phase 2 — Fast timeout return (P2-ISS-006)

**Setup (master):**

1. Set `MCP_CODER_DELEGATION_TIMEOUT_S=30` in `mcp_coder/.env`
2. Optionally switch to `AIDER_MODEL=openrouter/qwen/qwen-2.5-coder-32b-instruct` to provoke timeout
3. Restart MCP

**Spec:** `.mcp-coder/specs/tasks/phase2-exit-02-timeout.md`

**Cursor prompt:**

> Implement `.mcp-coder/specs/tasks/phase2-exit-02-timeout.md` via `delegate_to_agent` mode=implement. Include all read-deps in `target_files`. Report `error_class`, wall-clock time you waited, and `duration_ms` from the tool response.

**Pass:**

- [ ] `error_class: timeout` (or success if model finishes under 30s — then lower timeout or use harder task)
- [ ] Cursor unblocked within **~35s** of starting delegate (not 2× timeout)
- [ ] JSONL `duration_ms` ≈ timeout + small overhead (not +90s hang)

**After:** Restore `MCP_CODER_DELEGATION_TIMEOUT_S=180` and preferred model; restart MCP.

---

## Phase 3 — CLI shim (P2-ISS-010)

**From e2e workspace** (no venv activate):

```bash
cd ~/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e
mcp-coder inspect-context \
  --task "Phase 2 exit smoke" \
  --spec .mcp-coder/specs/tasks/phase2-exit-01-placeholder.md \
  --workspace . \
  --target-files expense_splitter/splitter.py
```

**Pass:**

- [ ] Exit 0; JSON shows `context_package` / tier entries
- [ ] No `command not found`
- [ ] Uses mcp_coder `.venv` (not system python)

---

## Phase 4 — Context inspect (P2-215 / P2-308)

**Spec:** existing `.mcp-coder/specs/tasks/expense-splitter-05b-models-comment.md`

```bash
mcp-coder inspect-context \
  --task "Add comment to models" \
  --spec .mcp-coder/specs/tasks/expense-splitter-05b-models-comment.md \
  --workspace . \
  --target-files expense_splitter/models.py \
  --target-files expense_splitter/loader.py
# Or: --target-files expense_splitter/models.py,expense_splitter/loader.py
```

**Pass:**

- [ ] `read_paths_in_prompt` includes read-deps (e.g. `loader.py`)
- [ ] `fnames` / edit tier lists only edit paths
- [ ] `context_package` entries show tiers (`edit-full`, `read-excerpt`, etc.)

---

## Phase 5 — Small implement + rich result (P2-210 / P2-308 / P2-120)

**Spec:** `.mcp-coder/specs/tasks/phase2-exit-03-docstring.md`

**Cursor prompt:**

> Plan is done. Delegate implement for `.mcp-coder/specs/tasks/phase2-exit-03-docstring.md` with correct read-deps. After: run `pytest` in this workspace and summarize `usage`, `context_package_summary`, `capability_warnings`, `files_changed`.

**Pass:**

- [ ] `success: true`
- [ ] `context_package_summary` present in MCP response
- [ ] `usage.preflight_tokens_est` and (ideally) `usage.actual` populated
- [ ] `pytest` in e2e still passes

---

## Phase 6 — Review model (P2-310)

**Spec:** `.mcp-coder/specs/tasks/phase2-exit-04-review.md`

**Cursor prompt:**

> Run `delegate_to_agent` with `mode=review`, `target_files=[]`, spec `.mcp-coder/specs/tasks/phase2-exit-04-review.md`. Task: "Review this spec — any gaps before implement?"

**Pass:**

- [ ] `delegate_mode: review`; no file edits
- [ ] Worker feedback appended to report
- [ ] JSONL shows review model (if `MCP_CODER_REVIEW_MODEL` or yaml `review_model` set, differs from executor)

---

## Phase 7 — Wild test

**New Composer chat.** Do **not** mention Phase 2, dogfood, or P2-xxx.

**Epic:** 2-step **tip calculator** CLI (new — not expense-splitter).

**Opening prompt:**

> I want a small Python **tip calculator** in this repo.
>
> - `calculate_tip(bill, percent) -> float` with sensible rounding.
> - Then a tiny CLI: `python -m tip_calc "25.00" 18` prints tip and total.
> - Use our workflow: epic + step specs under `.mcp-coder/specs/`, delegate implementation to mcp-coder — don't write code yourself.
> - **Step 1 only** (package + core function). We'll continue after I verify.

After step 1:

> Step 1 looks good. Plan and implement **step 2** (CLI).

**Watch:** planner spec discipline, `contract_warnings`, JSONL trail, timeouts, `files_changed` without git (P2-ISS-002 still open).

**Realistic pass bar:**

- [ ] Planner uses epic + step specs + delegate (mostly)
- [ ] At least one step completes with working code **or** classified failure (no browser storm)
- [ ] JSONL sufficient to post-mortem each step

---

## Audit commands

```bash
# Latest delegation (adjust path)
tail -1 ~/.mcp-coder/projects/*/sessions/*/delegations.jsonl | python3 -m json.tool

# E2E pytest
cd ~/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e && pytest -q
```

---

## Sign-off

| Field | Value |
|-------|-------|
| Date | 2026-06-07 (in progress) |
| mcp_coder pytest | 348 passed, 1 skipped |
| e2e pytest | |
| Structured Phases 1–6 | **6/6 pass** |
| Wild test | **pass** (step 1/2) — `06418163`; 3 pytest |
| e2e pytest | 3 passed (tip_calc) |
| P2-ISS-001/006/010 closed | ✓ at P2-499 |
| Phase 3 goals locked | BL-322, BL-002, BL-151 |

### Phase log

| Phase | Pass? | Notes |
|-------|-------|-------|
| 1 placeholder | ✓ | MCP `inspect_context` + CLI shim; no `contract_warnings`; `(none)` only in Goal prose |
| 2 timeout | ✓ | ~33s wall clock @ 30s timeout; `error_class: timeout`; no browser; partial `util_stats.py` |
| 3 CLI shim | ✓ | (covered in Phase 1 terminal run) |
| 4 inspect tiers | ✓ | `fnames` edit-only; `loader.py` read-full in prompt |
| 5 implement | ✓ | `6d862236` + fix `09fe1622`; rich MCP + usage; 9 pytest pass; fix-only `contract_warnings` expected |
| 6 review | ✓ | `737a9932`; review model 4o-mini ≠ executor Qwen; Worker feedback on report |
| 7 wild | ✓ | `06418163` — epic + spec + delegate; tip_calc core; 3 pytest; step 2 CLI optional |
