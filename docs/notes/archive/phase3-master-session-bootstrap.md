# Phase 3 — master session bootstrap

**Purpose:** Hand off from Phase 2 exit to a **new planning/master chat** without loading full history. This session can run in **parallel** with the Phase 2 wrap-up chat until Phase 3 PM owns the board.

**Phase 2 status:** **Closed / frozen** (2026-06-08) — [phase2-exit-validation.md](./phase2-exit-validation.md), [PHASE2_MVP.md](../../PHASE2_MVP.md).
**Phase 3 PM:** [PHASE3_MVP.md](../../PHASE3_MVP.md) · [PHASE3_ISSUES.md](../../PHASE3_ISSUES.md).

---

## Copy-paste prompt (new master session)

```
You are the mcp-coder Phase 3 planning/master session (PM + task orchestration).

## Read first (in order — do NOT load prior chat history)

1. docs/notes/archive/phase3-master-session-bootstrap.md — this handoff
2. docs/VISION_DOCS.md — doc tiers + stewardship
3. docs/PHASES.md — phase arc table + § Phase 3–5 (skim Phase 1–2 as needed)
4. docs/PHASE3_MVP.md — waves, D-P3 decisions, milestone order, open questions
5. docs/PHASE3_ISSUES.md — P3-ISS-001–004 (carried from P2)
6. docs/PHASE2_MVP.md — frozen; exit reference only
7. docs/notes/archive/phase2-exit-validation.md — P2-499 dogfood sign-off
8. docs/OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md — BL-322 design (scan rules, schema)
9. docs/BACKLOG.md — BL-322, BL-320, BL-002, BL-151, BL-323
10. .cursor/rules/mcp-coder-vision.mdc — worker vs master boundaries

Skim docs/IDEA.md § Shipped vs next + Suggested evolution (tier 0 — do not rewrite).

## Deep context (search only — never read linearly)

Transcript: agent-transcripts/d44a5b15-2ed4-4834-bc91-91f776e5dd02/d44a5b15-2ed4-4834-bc91-91f776e5dd02.jsonl

Search keywords: P2-499, BL-322, WORKSPACE_HISTORY, tracker-primary, D-P3-2, BL-320, attempt archive, P2-ISS-002, P2-ISS-007, tip-calc, dogfood

## Locked decisions (do not re-debate without user)

| ID | Decision |
|----|----------|
| D-P3-1 | `workspace_history.db` lives in ~/.mcp-coder/projects/<key>/ — NOT under workspace .mcp-coder/ |
| D-P3-2 | **Tracker-primary:** files_changed from manifest before/after walk every delegate — git-agnostic |
| D-P3-3 | Main spec report stays current; failures → attempt archive (BL-320) |
| D-P3-5 | RAG v1 = keyword + recency before embeddings |

**Phase boundary:** Phase 3 = workspace truth + attempt archive + RAG lite + gates. Phase 4 = smart context builder / janitor / verify / BL-161. See PHASES.md phase arc.

**Milestone order:** P3-322a → (P3-320 ∥ P3-322b) → P3-322c → P3-322d → P3-002-lite → P3-151

## Your job

1. Confirm with user that milestone order + open questions (Q2–Q5 in PHASE3_MVP) are acceptable.
2. Verify docs/tasks/P3-322a-workspace-snapshot.md matches D-P3-2 (gitignored — exists locally, not in git).
3. Dispatch P3-322a worker: attach ONLY that spec; model composer-2.5 or claude-4.6-sonnet-medium-thinking.
4. After worker § Results: update PHASE3_MVP status rows + PHASE3_ISSUES if needed.
5. Optional parallel: draft P3-320 spec while 322a runs.

## Worker rules (enforce when dispatching)

- Single source of truth: attached docs/tasks/P3-*.md only
- Fill § Results in same spec; suggest PM changes as bullets only
- Do NOT edit IDEA, PHASES, PHASE*_MVP, BACKLOG, PHASE*_ISSUES, VISION_DOCS
- No Aider API leakage into core/context/ or core/specs/ (backend-neutral rule)
- New code: core/workspace/ + wire aider_engine.py + git_diff.py

## Confusion traps (read carefully)

1. **Tracker vs git:** files_changed is ALWAYS manifest delta when snapshot on — not git status. Git is optional metadata only.
2. **Skip .mcp-coder in walk:** entire .mcp-coder/ tree skipped (specs, config) — history DB is in MCP home.
3. **JSONL stays canonical:** workspace_history.db supplements; does not replace delegations.jsonl.
4. **P3-322a scope:** snapshot + DB + attribution only — NO revert (322b), NO gateway (322c), NO new MCP tools (322d).
5. **Worker specs are gitignored:** docs/tasks/P3-*.md not in remote; master creates/refines locally.
6. **E2E workspace:** mcp_coder_phase1_e2e — dogfood there; pytest in mcp_coder repo (348 passed at P2 exit).
7. **Phase 2 Wave 4 intelligence** (BL-001, BL-003, BL-008) → Phase 4, not Phase 3.

## Repo state at handoff (2026-06-08)

- main: Phase 2 closed (P2-499 commit 96c9077+); Phase 3 PM stack committed in doc-freeze commit
- Entry worker spec ready: docs/tasks/P3-322a-workspace-snapshot.md
- First dispatch: P3-322a

Start by summarizing Phase 3 scope in 5 bullets, then ask user to confirm Q2–Q5 before dispatching P3-322a.
```

---

## Project in one page

**mcp-coder** — MCP server + context compiler that delegates real coding to an execution backend (Aider today). Cursor stays a **thin planner**; mcp-coder owns **delegation behavior**, spec contract, context assembly, audit.

**Repo layout:**

| Area | Role |
|------|------|
| `server/mcp_server.py` | MCP tools: `delegate_to_agent`, `inspect_context` |
| `core/context/` | L2 compiler: `assemble_context`, tiers, budget, excerpts |
| `core/engine/` | L3 adapter: Aider `run_context(ContextPackage)` |
| `core/specs/` | L1 contract: Files parser, policies, report write |
| `~/.mcp-coder/` | JSONL delegations, sessions (not in repo) |
| Consumer workspace | `.mcp-coder/specs/{epics,tasks,reports}/`, `config.yaml` |

**Three layers (Phase 2 hinge):**

```text
L1 CONTRACT   spec + MCP API + policies
L2 COMPILER   assemble_context() → ContextPackage
L3 ADAPTER    translate → Aider → ExecutionResult
```

Design reference: [phase2-owned-context.md](../phase2-owned-context.md)

---

## Phase 1 — done (frozen)

**Goal:** Prove MCP → Aider → home storage → sessions → spec workflow.

Shipped: `delegate_to_agent`, `mode=review|implement`, spec epics/tasks/reports, cursor rules sync, read-deps convention, `files_changed` / `files_unexpected`, JSONL audit.

PM: [PHASE1_MVP.md](../../PHASE1_MVP.md) (closed P1-199). Issues: [PHASE1_ISSUES.md](../../PHASE1_ISSUES.md) (historical).

---

## Phase 2 — done (2026-06-08)

**Goal:** Own context compiler + behavioral contract; predictable delegation without reading Aider internals.

**Waves shipped:**

| Wave | Highlights |
|------|------------|
| 1 | P2-110 read-dep warnings, P2-115 policies/strict, P2-120 usage, P2-125 hardening |
| 2 | P2-200 assembler, P2-205 excerpts, P2-210 adapter hinge, P2-212 capabilities, P2-215 inspect, P2-220 budget |
| 3 | P2-305 scope reports, P2-308 rich MCP result, P2-310 review model, P2-300a cache hash, P2-3.15 polish |

**Exit:** P2-499 structured dogfood 6/6 + wild tip-calc step 1. `348` pytest.

**Open issues (carried):** P2-ISS-004 (planner ignores warnings), P2-ISS-005 (upstream_5xx live), P2-ISS-009 (budget env vs yaml).

**Deferred to Phase 3:** P2-ISS-002 → BL-322; P2-ISS-007 → BL-320; P2-ISS-008 → BL-321.

PM: [PHASE2_MVP.md](../../PHASE2_MVP.md) · Issues: [PHASE2_ISSUES.md](../../PHASE2_ISSUES.md)

---

## Phase 3 — scope (locked at handoff 2026-06-08)

Two tracks that **overlap** and can ship incrementally:

### Track A — Workspace truth (audit + revert)

**BL-322** [WORKSPACE_HISTORY.md](../../OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md)

- Delegation-granularity snapshots (not user git)
- Honest `files_changed` in non-git workspaces (closes P2-ISS-002)
- SQLite delta store at `~/.mcp-coder/projects/<key>/workspace_history.db`
- Enables post-delegation gateway (BL-151), diff in MCP response, time-travel

Suggested order: BL-322a (manifest snapshot) → 322b (content for contract files) → 322c/d (gateway + diff in response).

### Track B — Spec/delegation history (planner-visible)

**BL-320** — failed-attempt archive (P2-ISS-007)

- Don't rely on overwriting report Blockers on success
- Side artifacts: `.mcp-coder/specs/attempts/<spec_id>/<delegation_id>.md`
- Optional `list_delegation_attempts` MCP tool
- Feeds future context builder (“last failure was timeout on Qwen”)

### Track C — Memory (PHASES.md § Phase 3 classic)

**BL-002** — RAG / cross-session memory

- SQLite + FTS, post-delegation summaries, pre-delegation retrieval
- Can start light (keyword + recency) before embeddings

### Track D — Gatekeeper (after A or in parallel design)

**BL-151** — pre-delegation gate; pairs with BL-322c post-gate.

---

## Parallel sessions (handoff model)

| Session | Owns | Winding down |
|---------|------|----------------|
| **Phase 2 exit chat** | P2-499 commit, push, loose ends | After this commit — archive |
| **Phase 3 master (new)** | PHASE3 scope, P3 task specs, backlog priority | Long-running |

Overlap is OK: e.g. Phase 3 master drafts BL-322a worker spec while Phase 2 chat pushes `main`.

---

## Transcript pointer (deep dive only)

**Session:** Phase 2 tail + P2-499 dogfood + workspace history design

**Path:** `agent-transcripts/d44a5b15-2ed4-4834-bc91-91f776e5dd02/d44a5b15-2ed4-4834-bc91-91f776e5dd02.jsonl`

**Search keywords (don't read whole file):**

| Topic | Keywords |
|-------|----------|
| Phase 2 exit | `P2-499`, `phase2-exit`, `dogfood` |
| Workspace history | `BL-322`, `WORKSPACE_HISTORY`, `workspace_history.db` |
| Report overwrite debate | `P2-ISS-007`, `BL-320`, `attempt archive`, `override` |
| Polish | `P2-3.15`, `ISS-001`, `ISS-006`, `ISS-010` |
| Wild test | `tip-calc`, `06418163` |

---

## First actions for Phase 3 master

1. ~~Wave 1 (P3-322a–f, P3-401)~~ — **complete** 2026-06-09.
2. ~~**P3-311** read-deps auto-merge~~ — **done** 2026-06-09; 412 pytest (+14).
3. ~~**P3-320** spec versioning rules~~ — **done** 2026-06-09.
4. ~~**P3-002-lite** delegation RAG~~ — **done** 2026-06-09; `core/rag/`; 431 pytest (+17); workspace-file RAG + usage → Phase 5 (Phase 4 = context builder first).
5. ~~**P3-499 exit**~~ — **done** 2026-06-09; Phase 3 closed; issues → BACKLOG BL-324–328.
6. **Phase 4** — context builder + manager; start from [PHASES.md](../../PHASES.md) § Phase 4.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-08 | Created at Phase 2 exit; bootstrap prompt + summary for parallel Phase 3 master |
| 2026-06-08 | PHASE3_MVP + PHASE3_ISSUES created; PHASE2 frozen; issue triage complete |
| 2026-06-08 | Full handoff prompt v2; D-P3-2 locked; P3-322a spec aligned to tracker-primary |
| 2026-06-08 | Q1–Q5 fully resolved; D-P3-6/7/8 locked; bootstrap first-actions updated |
| 2026-06-09 | Wave 1 closed; P3-311 active; RAG + attempt-archive design queued |
| 2026-06-09 | **P3-311 done**; P3-ISS-003 closed; design queue next |
| 2026-06-09 | **P3-002-lite spec ready**; Q3 locked; dispatch Wave 3 |
| 2026-06-09 | **P3-002-lite done**; RAG corpus decisions in BL-002; **active: P3-499 exit** |
| 2026-06-09 | **P3-499 exit** — Phase 3 closed; PHASE3_ISSUES frozen; Phase 4 active |
