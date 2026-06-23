<!--
  STEWARDSHIP — docs index. Vision map: docs/VISION_DOCS.md. Workers: docs/tasks/ only.
-->

# mcp-coder documentation

## Vision & design (do not lose the “why”)

**Start here:** [VISION_DOCS.md](./VISION_DOCS.md) — which file is canonical vs operational.

| Tier | Doc | Use when |
|------|-----|----------|
| 0 | [IDEA.md](./IDEA.md) | Why we exist, architecture, principles (edit only when user asks) |
| 1 | [PHASES.md](./PHASES.md) | Phase boundaries and delivery order |
| 2 | [PHASE1_MVP.md](./PHASE1_MVP.md), [BACKLOG.md](./BACKLOG.md), [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) | Current phase tasks, deferrals, gaps |

Each tier-0–2 file has an HTML **stewardship** comment at the top — agents must not rewrite vision casually.

---

## How we work (workflow)

```
┌─────────────────────────────────────────────────────────────┐
│  Planning chat (here)                                       │
│  • Decide next task (feature, bug, milestone)               │
│  • Agree scope in PHASE1_MVP → write docs/tasks/{id}.md     │
│    (local only; never committed)                            │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Worker session (new Cursor chat / agent)                     │
│  • Input: docs/tasks/{id}.md only (attach that file)        │
│  • Implement; do not expand scope                           │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Report back (planning chat)                                │
│  • What shipped, sample log, blockers                       │
│  • PM updates PHASE1_MVP task status + experiment notes     │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
                      Next task → repeat
```

**Tracked in git:** [VISION_DOCS.md](./VISION_DOCS.md) (map), [IDEA.md](./IDEA.md), [PHASES.md](./PHASES.md), [PHASE1_MVP.md](./PHASE1_MVP.md) (tasks/status), [BACKLOG.md](./BACKLOG.md), [TASK_SPEC_TEMPLATE.md](./TASK_SPEC_TEMPLATE.md) (blank template only).  
**Local dev only (never commit):** `docs/tasks/*.md` — one concrete spec file per worker session.

---

| Document | Purpose |
|----------|---------|
| [VISION_DOCS.md](./VISION_DOCS.md) | **Vision doc map & stewardship** — what agents may edit |
| [INSTALL.md](./INSTALL.md) | **Install & reproducible env** — Python version, locked deps, bootstrap scripts |
| [resources/spec-template.md](../resources/spec-template.md) | Task spec template (MCP copy: `.mcp-coder/spec-template.md`) |
| [IDEA.md](./IDEA.md) | Vision, architecture, design principles (why we're building this) |
| [PHASES.md](./PHASES.md) | Multi-phase delivery plan (Phase 1–13+, technical detail) |
| [PHASE1_MVP.md](./PHASE1_MVP.md) | **Phase 1 PM** — closed P1-199 |
| [PHASE4_MVP.md](./PHASE4_MVP.md) | **Phase 4 PM** — closed P4 exit; active → Phase 5 / BACKLOG |
| [PHASE4_ISSUES.md](./PHASE4_ISSUES.md) | **Phase 4 issues** — frozen; carried → BACKLOG |
| [PHASE9_MVP.md](./PHASE9_MVP.md) | **Phase 9 PM** — closed 2026-06-17 (write-always + proxy + replay) |
| [PHASE10_MVP.md](./PHASE10_MVP.md) | **Phase 10 PM** — closed 2026-06-18 (trustable real-project dogfood) |
| [PHASE11_MVP.md](./PHASE11_MVP.md) | **Phase 11 PM** — closed 2026-06-20 (supervised execution + smarter context) |
| [PHASE12_MVP.md](./PHASE12_MVP.md) | **Phase 12 PM** — closed 2026-06-21 (supervisor orchestration infrastructure) |
| [PHASE13_MVP.md](./PHASE13_MVP.md) | **Phase 13 PM** — active (stabilize + dogfood + document + test hardening + backlog review) |
| [notes/system-design-overview.md](./notes/system-design-overview.md) | **Refined design entry** — how the current notes fit together (vision stays in IDEA) |
| [notes/supervisor-agent-architecture.md](./notes/supervisor-agent-architecture.md) | **Supervisor agent architecture** — persistent project agent, state model, pause/resume, project memory, subagent/tool context control |
| [BACKLOG.md](./BACKLOG.md) | Project backlog (deferred / later / nice-to-have; includes Phase 13 watch-for-evidence items BL-549..BL-555) |
| [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) | **Phase 1 issue tracker** — gaps found during P1 (incl. server log) |
| [TASK_SPEC_TEMPLATE.md](./TASK_SPEC_TEMPLATE.md) | Blank template — **do not edit**; copy into `docs/tasks/` |

## `docs/tasks/` — local worker specs (never in git)

Each implementation session gets **one markdown file** in `docs/tasks/`. We keep these on disk for our own dev workflow; **git never tracks them** (see root `.gitignore`).

**When planning (this chat):**

```bash
mkdir -p docs/tasks
cp docs/TASK_SPEC_TEMPLATE.md docs/tasks/P1-1.0-barebones-mcp-aider.md
# fill scope from PHASE1_MVP § P1-100; refine until ready
```

**When implementing (new session):** attach `docs/tasks/P1-1.0-barebones-mcp-aider.md` — worker does not need repo PM docs unless blocked.

**When reporting back:** worker fills § Results in that same local file; we update [PHASE1_MVP.md](./PHASE1_MVP.md) task status in git.

## Consumer workflow (spec + delegate)

For repos using mcp-coder as planner ↔ worker (not building mcp-coder itself):

| Doc | Topic |
|-----|--------|
| [notes/spec-workflow.md](./notes/spec-workflow.md) | Current spec-driven workflow for master/worker and `review` / `implement` paths |
| [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) | E2E gaps (P1-ISS-013–016) and deferrals |
| Root [README.md](../README.md) | `delegate_to_agent`, `spec_path`, `test-model` |

E2E reference consumer: `mcp_coder_phase1_e2e` (expense-splitter epic).

---

## Notes (design)

| Note | Topic |
|------|--------|
| [notes/context-storage-and-observability.md](./notes/context-storage-and-observability.md) | Contract/compiler/adapter split, storage model, observability/capture layers |
| [notes/spec-workflow.md](./notes/spec-workflow.md) | Spec-as-contract workflow, review/implement loop, planner/worker split |
| [notes/retrieval-and-rag-strategy.md](./notes/retrieval-and-rag-strategy.md) | Retrieval/RAG boundaries, corpora, dependency order, FTS vs embeddings |
| [notes/viewer-and-trace-design.md](./notes/viewer-and-trace-design.md) | Delegation viewer mental model, trace mapping, event rendering rules |
| [notes/delegation-roles-and-lifecycle.md](./notes/delegation-roles-and-lifecycle.md) | Stable role vocabulary, delegation lifecycle, shipped modes vs future turns |
| [notes/model-routing-and-policy.md](./notes/model-routing-and-policy.md) | Current model-policy behavior plus future routing/escalation direction |
| [notes/archive/](./notes/archive/README.md) | **Archive** — frozen phase master-session bootstrap handoffs (Phases 3–11) |

## Quick start (planning)

1. Read [IDEA.md](./IDEA.md) for context.
2. Use the active phase PM board (currently [PHASE13_MVP.md](./PHASE13_MVP.md)) for what to build next.
3. Deep dive: [PHASES.md](./PHASES.md) § Phase 1 · [context-storage-and-observability.md](./notes/context-storage-and-observability.md).
