<!--
  STEWARDSHIP — meta index for vision / design docs (this file included).

  Do NOT edit this map or demote IDEA.md unless the user explicitly asks.
  Workers: implement per docs/tasks/*.md; report in § Results only.
-->

# Vision & design documents — map

Use this page so **main vision** ([IDEA.md](./IDEA.md)) is not lost when editing phase or backlog docs.

## Canonical stack (read order)

| Tier | Document | Role | Who may edit |
|------|----------|------|----------------|
| **0 — Why** | [IDEA.md](./IDEA.md) | Product vision, architecture, principles, data models. Roots: commit `074753b` (`README.md`) + Grok ideation. | **User only** (explicit ask to change vision) |
| **1 — How we ship** | [PHASES.md](./PHASES.md) | Multi-phase delivery, boundaries, validation. Must stay **consistent with IDEA**. | Planning / master session; not workers |
| **2 — Phase 1 PM** | [PHASE1_MVP.md](./PHASE1_MVP.md) | Tasks, status, acceptance, worker handoffs | Planning session updates status; scope changes need user agreement |
| **2 — Deferred** | [BACKLOG.md](./BACKLOG.md) | BL-* items, priorities, post–P1 focus | Add/defer with user or P1-199; do not delete rows silently |
| **2 — P1 gaps** | [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) | Issues found during P1 | Planning session; link to BL-* when deferring |
| **3 — Direction notes** | [notes/spec-based-development.md](./notes/spec-based-development.md) | Spec-as-contract — **shipped experiment** (P1-151) | Update when workflow changes; P1-199 locks decisions |
| **3 — Direction notes** | [notes/spec-review-loop.md](./notes/spec-review-loop.md) | Review vs implement modes | Same |
| **3 — Related ideas** | [OTEHR_RELATED_IDEAS/](./OTEHR_RELATED_IDEAS/) | Gatekeeper, experiments — **not** canonical vision | Optional; may inform backlog only |

## Operational (not vision — safe to update when implementing)

| Document | Role |
|----------|------|
| [INSTALL.md](./INSTALL.md) | Install, Python, locks |
| [notes/storage-and-linking.md](./notes/storage-and-linking.md) | `~/.mcp-coder` layout |
| [TASK_SPEC_TEMPLATE.md](./TASK_SPEC_TEMPLATE.md) | Copy-only template |
| `docs/tasks/P1-*.md` | **Gitignored** worker specs |
| [README.md](./README.md) (this folder) | Workflow index |

## Rules for agents

1. **Never** rewrite Tier 0–1 to “match implementation” without the user asking — adapt with **additions** and phase tables, not deletions of original intent.
2. **Workers** implement from `docs/tasks/*.md` only; they do **not** edit IDEA, PHASES, PHASE1_MVP, or BACKLOG.
3. **Status-only** updates in PHASE1_MVP (mark P1-* done) belong to the **planning / master** session after reviewing worker § Results.
4. When unsure whether a change is vision vs execution: **stop** and ask — default to [IDEA.md](./IDEA.md) § Core problem & why this exists.
5. **Root** [README.md](../README.md) is install/quick start; vision lives under `docs/`.

## Quick anchors (do not forget)

- **Problem:** Stateless coding agents → cross-session memory + task-level orchestration ([IDEA.md](./IDEA.md)).
- **Two tiers:** Task-level (`mcp-coder`) + turn-level (`context_optimizer_proxy`) — separate repos.
- **Phase 1:** Delegate + pass-through context + home storage + sessions + opt-in transcript — **no** owned RAG/router yet.
- **Phase 2:** Owned context (creation, window, skills, topic detection) — see [PHASES.md](./PHASES.md) and BACKLOG § Post–Phase 1 focus.
- **Executor:** Aider-first; OpenCode/other hosts very low priority.

## Changelog

| Date | Change |
|------|--------|
| 2026-06-05 | Initial vision-doc map + stewardship tiers (with IDEA audit) |
