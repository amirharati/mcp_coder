# Note: Spec-based development (meta → product)

**Status:** Deferred to **P1-199** (end of Phase 1 review). Not blocking P1-110–P1-140.  
**Related:** [PHASE1_MVP.md](../PHASE1_MVP.md), [PHASES.md](../PHASES.md), [BACKLOG.md](../BACKLOG.md) BL-150

---

## What we do today (building mcp-coder)

1. **Planning chat** agrees scope (high level in `PHASE1_MVP.md`).
2. **Local spec file** `docs/tasks/P1-{…}.md` — concrete handoff for one worker session (gitignored).
3. **Worker** implements from that spec only; reports back.
4. **PM doc** tracks status in git; spec § Results holds run notes locally.

This works well: bounded context, clear done-when, no need to paste entire chat history into the worker session.

---

## Hypothesis for the product (after Phase 1)

**Spec-based delegation** may reduce reliance on **full chat transcripts** (SpecStory / huge context):

| Approach | Planner carries | Executor receives |
|----------|-----------------|-------------------|
| **Full history** | Entire thread | SpecStory `.md` or massive prompt |
| **Summary only** | Compressed `context_summary` | Subset — nuance loss |
| **Spec-based** | Chat + evolving **task spec** | Structured spec doc (goal, constraints, files, done-when) + small delta from planner |

The executor (Aider) does not need every chat turn if the **spec is the contract** — same as our worker workflow.

---

## Possible adaptations (decide at P1-199 — implement Phase 2+)

Explore after P1-110–P1-140 experiments; gatekeeper out of scope until post-P1.

1. **MCP tool accepts a `task_spec` object** (or path to workspace spec under `.mcp-coder/specs/current.md`) instead of only `context_summary` blob.
2. **Planner (Cursor) updates spec** each delegation; mcp-coder appends to spec § Results / log (mirror our `delegations.jsonl`).
3. **Session boundary** = spec file version/hash changed materially (like SpecStory hash today).
4. **Optional:** generate spec from chat via cheap LLM once, then refine per delegation — less resummarizing every call.
5. **Coexist with host transcript:** spec = contract; Cursor `agent-transcripts` = audit trail when available.

**Open question:** Is a workspace-local `.mcp-coder/specs/` (gitignored or committed per team preference) better than only MCP JSON args?

---

## Why not during P1-110–P1-140

Phase 1 validates: MCP → Aider → **home storage** → host adapter → sessions → transcript context.  
Spec-based product features need that data: when does summary fail? when is transcript overload? would a structured spec have helped? **Decide at P1-199.**

---

## Success criteria for a future spike

- [ ] Same task completed with smaller `prompt_tokens_est` than full SpecStory inject.
- [ ] No critical nuance loss vs transcript (measure on 3–5 real tasks).
- [ ] Cursor reliably fills structured spec fields (or we generate spec server-side once).

---

## Changelog

| Date | Note |
|------|------|
| 2026-06-03 | Initial note from planning chat |
| 2026-06-04 | Deferred to P1-199; SpecStory removed from plan |
