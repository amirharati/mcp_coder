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
| [IDEA.md](./IDEA.md) | Vision, architecture, design principles (why we’re building this) |
| [PHASES.md](./PHASES.md) | Multi-phase delivery plan (Phase 1–4, technical detail) |
| [PHASE1_MVP.md](./PHASE1_MVP.md) | **Phase 1 product manager doc** — tasks, status, worker handoffs |
| [BACKLOG.md](./BACKLOG.md) | Project backlog (deferred / later / nice-to-have) |
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
| [notes/spec-based-development.md](./notes/spec-based-development.md) | Epic + step specs, roles, layout v2 (**shipped** P1-151) |
| [notes/spec-review-loop.md](./notes/spec-review-loop.md) | `mode=review` → refine → `mode=implement` |
| [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) | E2E gaps (P1-ISS-013–016) and deferrals |
| Root [README.md](../README.md) | `delegate_to_agent`, `spec_path`, `test-model` |

E2E reference consumer: `mcp_coder_phase1_e2e` (expense-splitter epic).

---

## Notes (design)

| Note | Topic |
|------|--------|
| [notes/storage-and-linking.md](./notes/storage-and-linking.md) | `~/.mcp-coder` layout, IDs, session ↔ Cursor chat links, `specs/` |
| [notes/spec-based-development.md](./notes/spec-based-development.md) | Spec-as-contract hypothesis → **live experiment** |

## Quick start (planning)

1. Read [IDEA.md](./IDEA.md) for context.
2. Use [PHASE1_MVP.md](./PHASE1_MVP.md) for what to build next.
3. Deep dive: [PHASES.md](./PHASES.md) § Phase 1 · [storage-and-linking.md](./notes/storage-and-linking.md).
