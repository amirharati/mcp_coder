# Phase 4 — master session bootstrap

**Purpose:** Hand off from Phase 3 exit to a **new planning/master chat** for Phase 4. Read this first; do not load Phase 3 chat history.

**Phase 3 status:** **Closed** (P3-499, 2026-06-09) — [PHASE3_MVP.md](../PHASE3_MVP.md), [PHASE3_ISSUES.md](../PHASE3_ISSUES.md) (frozen).  
**Phase 4 PM:** [PHASE4_MVP.md](../PHASE4_MVP.md)

---

## Copy-paste prompt (new master session)

```
You are the mcp-coder Phase 4 planning/master session (PM + task orchestration).

## Read first (in order — do NOT load prior chat history)

1. docs/notes/phase4-master-session-bootstrap.md — this handoff
2. docs/VISION_DOCS.md — doc tiers + stewardship
3. docs/PHASES.md — § Phase 4 + Phase 5 (skim Phase 1–3 as needed)
4. docs/PHASE4_MVP.md — waves, decisions, open questions, success checklist
5. docs/PHASE3_ISSUES.md — frozen; skim carried issues (BL-324–328)
6. docs/BACKLOG.md — BL-001, BL-161, BL-003, BL-162, BL-324–328
7. .cursor/rules/mcp-coder-vision.mdc — worker vs master boundaries

Skim docs/IDEA.md § Shipped vs next (tier 0 — do not rewrite).

## Deep context (search only — never read linearly)

Prior master session transcript: agent-transcripts/a886fdfc-9176-41ca-a083-8b0bd1856852/a886fdfc-9176-41ca-a083-8b0bd1856852.jsonl

Search keywords: BL-001, BL-324, BL-325, context builder, planner UX, spec path, judgment loop, P3-499

## What Phase 4 is

Phase 4 = active context assembly + verify loop + planner UX fixes.

The compiler (Phase 2) + history (Phase 3) are done. Phase 4 adds:
  1. A cheap-LLM (or rules-based) file picker that picks relevant files before delegating — planner stops listing every file.
  2. Optional post-delegation pytest hook; partial outcome when tests fail.
  3. Fixes to planner UX gaps found in P3-499 dogfood (spec path errors, inspect tools, etc).

RAG is NOT Phase 4 — it is Phase 5 (after Phase 4 reveals what retrieval is actually needed).

## What shipped in Phase 3 (do not re-implement)

- `core/workspace/` — manifest walker, workspace_history.db, content blobs, diffs
- `core/rag/` — delegation FTS5 index, rag_search MCP, CLI (P3-002-lite; scope → Phase 5)
- `core/specs/read_deps_merge.py` — auto-merge spec Read paths (P3-311)
- `core/workspace/gateway.py` — strict post-delegation gateway (P3-322c)
- MCP tools: `list_delegations`, `get_checkpoint_detail`, `get_delegation_diff`, `get_file_history`, `rag_search`
- Cursor rules: `use-mcp-coder.mdc` v9, `workspace-history.mdc` v3
- 431 pytest passing at Phase 3 exit

## Locked decisions (do not re-debate without user)

| ID | Decision |
|----|----------|
| D-P3-2 | `files_changed` always from manifest walk — git-agnostic; stays |
| D-P3-5 | Delegation RAG = `core/rag/` FTS5; usage scope decided in Phase 5 |
| D-P4-1 | Context builder is a cheap-LLM pass inside `delegate_to_agent`; Cursor stays thin |
| D-P4-2 | Verify loop opt-in via config (`auto_verify: true`); not blocking by default |
| D-P4-3 | Spec path strictly `.mcp-coder/specs/tasks/`; error includes correct path hint |
| D-P4-4 | `delegation_diff` summary prominent in response; rules require cite before done |

## Your job

1. Read [PHASE4_MVP.md](../PHASE4_MVP.md) — confirm milestone order + open questions Q1–Q4 with user.
2. Start with **Wave 1** (planner UX fixes — BL-324–327) — rules-only, fast to ship.
3. Lock Q1 (builder opt-in?) and Q2 (cheap model?) before drafting P4-001.
4. Dispatch one worker at a time; update PHASE4_MVP status after each § Results.

## Worker rules (enforce when dispatching)

- Single source of truth: attached `docs/tasks/P4-*.md` only
- Fill § Results in same spec; suggest PM changes as bullets only
- Do NOT edit IDEA, PHASES, PHASE*_MVP, BACKLOG, PHASE*_ISSUES, VISION_DOCS
- No Aider API leakage into `core/context/` or `core/specs/` (backend-neutral rule)
- Worker specs: `docs/tasks/P4-<id>-<name>-v1.md` (**versioned from first attempt**)

## Confusion traps

1. **Builder vs compiler:** Phase 2 compiler (`assemble_context`) is still the output stage. Phase 4 builder adds an upstream step that *feeds* the compiler — do not replace the compiler.
2. **RAG is Phase 5:** `core/rag/` exists but is passive (indexes after each delegate). Phase 4 does not add new RAG queries — that happens after builder reveals what it needs.
3. **Spec path is `.mcp-coder/specs/tasks/`** — not `specs/tasks/` at repo root. This burned us in P3-499 dogfood (delegation `58bb9846` failed).
4. **Worker specs are gitignored:** `docs/tasks/P4-*.md` not in remote; master creates/refines locally.
5. **E2E workspace:** `mcp_coder_phase1_e2e` — reset to greenfield at P3-499; `workspace_history.db` + `delegation_rag.db` wiped.

## Repo state at handoff (2026-06-09)

- `main` — 15 commits ahead of origin (not pushed)
- pytest: 431 passed (ignoring `tests/test_cli_test_model.py` optional dep)
- E2E workspace: greenfield (tip_calc removed; specs empty; MCP home cleared for that project)
- Cursor rules synced: `use-mcp-coder.mdc` v9 + `workspace-history.mdc` v3
- `delegation_rag.db` active per-project in MCP home (Phase 3 shipped; Phase 5 scope)

---

## First actions for Phase 4 master

1. **Confirm Q1–Q4** in [PHASE4_MVP.md](../PHASE4_MVP.md) with user.
2. **Wave 1** — draft P4-005 (spec path fix) + P4-006 (judgment loop rules v10); dispatch as separate workers.
3. **P4-007** (read-deps `(none` fix) — tiny code change, attach to P4-006 or separate.
4. **P4-008** (surface failed delegation) — rules-only.
5. After Wave 1 green + Q1/Q2 locked: draft P4-001 (context builder).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-09 | Created at Phase 3 exit (P3-499); Phase 4 master bootstrap |
