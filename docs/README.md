# mcp-coder documentation

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

**Tracked in git:** [PHASE1_MVP.md](./PHASE1_MVP.md) (tasks/status), [PHASES.md](./PHASES.md), [IDEA.md](./IDEA.md), [BACKLOG.md](./BACKLOG.md), [TASK_SPEC_TEMPLATE.md](./TASK_SPEC_TEMPLATE.md) (blank template only).  
**Local dev only (never commit):** `docs/tasks/*.md` — one concrete spec file per worker session.

---

| Document | Purpose |
|----------|---------|
| [INSTALL.md](./INSTALL.md) | **Install & reproducible env** — Python version, locked deps, bootstrap scripts |
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

## Notes (ideas — post Phase 1)

| Note | Topic |
|------|--------|
| [notes/storage-and-linking.md](./notes/storage-and-linking.md) | `~/.mcp-coder` layout, IDs, session ↔ Cursor chat links |
| [notes/spec-based-development.md](./notes/spec-based-development.md) | Spec-as-contract — **P1-199 review** (not blocking infra milestones) |

## Quick start (planning)

1. Read [IDEA.md](./IDEA.md) for context.
2. Use [PHASE1_MVP.md](./PHASE1_MVP.md) for what to build next.
3. Deep dive: [PHASES.md](./PHASES.md) § Phase 1 · [storage-and-linking.md](./notes/storage-and-linking.md).
