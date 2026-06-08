# Phase 3 — master session bootstrap

**Purpose:** Hand off from Phase 2 exit to a **new planning/master chat** without loading full history. This session can run in **parallel** with the Phase 2 wrap-up chat until Phase 3 PM owns the board.

**Phase 2 status:** **Closed** (2026-06-08) — [phase2-exit-validation.md](./phase2-exit-validation.md), [PHASE2_MVP.md](../PHASE2_MVP.md) P2-499.

---

## Copy-paste prompt (new master session)

```
You are the mcp-coder planning/master session for Phase 3.

Read first (do NOT load full chat history):
1. docs/notes/phase3-master-session-bootstrap.md (this file)
2. docs/VISION_DOCS.md — doc tiers
3. docs/IDEA.md — tier 0 vision (skim Core problem + architecture)
4. docs/PHASES.md — § Phase 3 (RAG) + read Phase 2 summary for what shipped
5. docs/PHASE2_MVP.md — exit status + Phase 3 anchor section
6. docs/BACKLOG.md — BL-322, BL-320, BL-002, BL-151

Deep context (search only — do NOT read linearly):
- Prior master transcript: agent-transcripts/d44a5b15-2ed4-4834-bc91-91f776e5dd02/d44a5b15-2ed4-4834-bc91-91f776e5dd02.jsonl
  Search for: P2-499, workspace history, BL-322, attempt archive, BL-320, context compiler, dogfood

Your job:
- Draft Phase 3 PM scope (PHASE3_MVP or extend PHASES — user decides)
- Prioritize entry milestones; workers use docs/tasks/P3-*.md only
- Overlap OK: Phase 2 chat may still commit/push; you own Phase 3 planning

Rules: .cursor/rules/mcp-coder-vision.mdc — workers do not edit tier 0–2 vision/PM without explicit ask.
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

Design reference: [phase2-owned-context.md](./phase2-owned-context.md)

---

## Phase 1 — done (frozen)

**Goal:** Prove MCP → Aider → home storage → sessions → spec workflow.

Shipped: `delegate_to_agent`, `mode=review|implement`, spec epics/tasks/reports, cursor rules sync, read-deps convention, `files_changed` / `files_unexpected`, JSONL audit.

PM: [PHASE1_MVP.md](../PHASE1_MVP.md) (closed P1-199). Issues: [PHASE1_ISSUES.md](../PHASE1_ISSUES.md) (historical).

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

PM: [PHASE2_MVP.md](../PHASE2_MVP.md) · Issues: [PHASE2_ISSUES.md](../PHASE2_ISSUES.md)

---

## Phase 3 — initial scope (planning; not locked)

Two tracks that **overlap** and can ship incrementally:

### Track A — Workspace truth (audit + revert)

**BL-322** [WORKSPACE_HISTORY.md](../OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md)

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

1. User agrees Phase 3 entry milestone order (322a vs 320 vs 002).
2. Create `docs/PHASE3_MVP.md` or extend [PHASES.md](../PHASES.md) § Phase 3 with milestone table (planning session).
3. Draft first worker spec: e.g. `docs/tasks/P3-322a-workspace-snapshot.md` from [TASK_SPEC_TEMPLATE.md](../TASK_SPEC_TEMPLATE.md).
4. Optional: tip-calc step 2 wild finish in e2e (not blocking).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-08 | Created at Phase 2 exit; bootstrap prompt + summary for parallel Phase 3 master |
