# Wave 1 wild test — realistic multi-step (post-dogfood)

**Workspace:** `mcp_coder_phase1_e2e` (cleaned 2026-06-07)  
**Goal:** Exercise mcp-coder **without** telling Cursor about phases, expectations, or test harness language. Observe failures, tune params, confirm Wave 1 features in the wild.

**Wave 1 code status:** P2-110/115/120/125 shipped (`bef7cd2`+). Structured dogfood Phases 1–4 passed; this run is **integration realism**, not a replacement for pytest.

---

## Setup (once per session)

1. **E2E folder** — empty repo except `.mcp-coder/`, `.cursor/`, templates.
2. **`mcp_coder/.env`** — model ladder (restart MCP after each swap):
   ```bash
   MCP_CODER_DELEGATION_TIMEOUT_S=180   # 240 if still timing out
   # Ladder (cheapest → strongest):
   # AIDER_MODEL=openrouter/qwen/qwen-2.5-coder-32b-instruct
   AIDER_MODEL=openrouter/openai/gpt-4o-mini              # ← active mid tier
   # AIDER_MODEL=openrouter/deepseek/deepseek-chat-v3.1   # value + coding
   # AIDER_MODEL=openrouter/google/gemini-2.5-flash
   # AIDER_MODEL=openrouter/anthropic/claude-3.5-haiku
   # AIDER_MODEL=openrouter/anthropic/claude-sonnet-4       # control only
   ```
   Preflight: `mcp-coder test-model --model <id>` from `mcp_coder` repo.
3. **Restart MCP** after `.env` changes (`envFile` in `.cursor/mcp.json`).
4. **New Composer chat** in E2E workspace (fresh planner context).

---

## Epic: expense-splitter (lite)

Mid complexity — similar spirit to Phase 1 E2E, **3 steps** so each delegate stays smaller.

| Step | Delivers | Typical `target_files` size |
|------|----------|-----------------------------|
| **1** | Package + `split_total(amount, n) -> list[float]` (cent-safe) | 2–3 |
| **2** | `models.py` + JSON load helpers | 2–3 (+ read step 1) |
| **3** | `cli.py` + `sample_expenses.json`, `python -m expense_splitter.cli` | 3–4 (+ read 1–2) |

Planner (Cursor) writes epic + step specs per strict rules — **you do not pre-create specs**.

---

## Opening prompt (natural — paste in new chat)

> I want a small Python **expense splitter** CLI in this repo.
>
> - Split a total amount evenly across N people (handle cents fairly).
> - Read amounts from a JSON file eventually; start with core logic, then models/JSON, then CLI.
> - Use our usual workflow: epic + step specs under `.mcp-coder/specs/`, delegate implementation to mcp-coder — don't implement code yourself.
> - Do **step 1 first** only (core split logic + package layout). We'll do later steps after I verify.

After step 1 verifies:

> Step 1 looks good. Plan and implement **step 2** (models + JSON parsing).

Then step 3 similarly.

**Do not mention:** Wave 1, dogfood, P2-xxx, read-dep tests, or intentional omissions.

---

## What to watch (master review via logs)

| Signal | Where |
|--------|--------|
| `contract_warnings` | Tool response — planner should include read-deps in `target_files` |
| `usage` / cost | Tool response + JSONL |
| `error_class` / `outcome` | On failure |
| `duration_ms` vs `MCP_CODER_DELEGATION_TIMEOUT_S` | JSONL — see P2-ISS-006 if MCP returns long after timeout log |
| `files_changed` vs disk | Especially without git — P2-ISS-002 |
| Browser tabs | On provider errors |
| Planner bypassing delegate | Hand edits despite strict rules |

**Audit commands:**

```bash
tail -1 ~/.mcp-coder/projects/*/sessions/*/delegations.jsonl | python3 -m json.tool
grep delegation ~/.mcp-coder/server.jsonl | tail -5
```

---

## Tuning playbook

| Symptom | Try |
|---------|-----|
| `error_class: timeout` @ 120s | `MCP_CODER_DELEGATION_TIMEOUT_S=180` or 240; restart MCP |
| Qwen timeout / flake | Step up: `gpt-4o-mini` → `deepseek-chat-v3.1` → `gemini-2.5-flash` → `haiku` → Sonnet |
| `contract_warnings` | Planner should re-delegate with expanded `target_files` before accepting |
| Empty stub files | Delete stubs; re-delegate; track BL-309d |
| `needs_input` / conversational | `mode=review` or expand context |

---

## Success criteria (wild run)

Not “all steps green on Qwen” — realistic bar:

- [ ] Planner uses epic + step specs + delegate (mostly)
- [ ] At least one step completes with working code **or** a **classified** failure (not browser storm / megabyte traceback)
- [ ] JSONL audit trail sufficient to post-mortem each step
- [ ] You can articulate: keep Qwen + timeout X **or** need Sonnet for multi-file steps

---

## Issues already tracked

[PHASE2_ISSUES.md](../../PHASE2_ISSUES.md) P2-ISS-001–006 from structured dogfood.
