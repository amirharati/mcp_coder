# Phase 2 direction: owned context (design note)

**Status:** Direction note — **not** canonical vision. See [IDEA.md](../IDEA.md) for product WHY.  
**Locked at:** Phase 1 exit (P1-199, 2026-06-06).  
**Backlog:** [BL-001](../BACKLOG.md#deferred-from-phase-1-by-design--later-phases), [BL-154](../BACKLOG.md#postphase-1-focus-priority-after-p1-199), [BL-311](../BACKLOG.md#bl-311-read-deps-from-spec-files-section), [BL-316](../BACKLOG.md#bl-316-context-builder-file-materialization-tiers).

---

## Problem (Phase 1 reality)

Today, `delegate_to_agent(target_files=[…])` passes paths straight to **Aider `fnames`**. That means:

- Every listed path is loaded as **full file text** into the executor chat.
- Behavior is **backend-coupled** — what Cursor or the planner puts in `target_files` is what Aider sees.
- Blind full-file inclusion from spec or chat is **risky**: token blow-up, wrong cross-step deps, and no per-path policy (edit vs read vs excerpt).

Phase 1 mitigated this with **conventions** (read-deps in `target_files`, cursor rules v7) and **honest reporting** (`files_changed`, `files_unexpected` — P1-152). That is a bridge, not the end state.

---

## Principle

**mcp-coder owns a context builder** that decides, per repo path, how content enters the executor prompt:

| Tier | Meaning |
|------|---------|
| `edit-full` | Full file; worker may edit (today’s default for edit targets) |
| `read-full` | Full file; context only |
| `read-excerpt` | Snippet (function, class, ripgrep hit) |
| `pointer` | Path + one-line summary (“see `foo.py`”) |
| `map-only` | Tree / symbol map, no bodies |
| `hide` | Omit from prompt |

The builder applies tiers **regardless of source**: spec **Files**, API args, prior delegation history, or host transcript slices.

---

## Spec alignment (Phase 2)

When `spec_path` is set, **spec Files is the contract** (planner-owned sections):

- Phase 2 front matter: `files_edit` / `files_read` ([BL-315](../BACKLOG.md#bl-315-edit_scope--spec-files-yaml)) — today: markdown `### Edit` / `### Read` only (P1-152).
- `target_files` becomes a **planner hint / edit scope**, not “always full file in chat.”
- MCP builder **materializes** context (excerpts under `.mcp-coder/context/` when needed) before calling the engine adapter.

`edit_scope: discover | strict` ([D-SPEC-8](../PHASE1_MVP.md#p1-199--end-of-phase-1-review)) — whether Aider may touch paths outside declared edit set; reporting expands via [BL-314](../BACKLOG.md#bl-314-honest-delegation-file-reporting).

---

## Engine adapter boundary

```
assemble_context(workspace, spec, mcp_request)
  → ContextPackage(paths_with_tiers, prompt_blocks, excerpts)

AiderEngine.run(..., context: ContextPackage)
  → map to AiderContext(edit_fnames, read_only_fnames, prompt_prefix, ...)
```

Other backends (if ever) map the same package differently — **OpenCode / other hosts remain deferred** ([BL-004](../BACKLOG.md#very-low-priority--other-execution-engines)).

Phase 1 adapter stays thin: `target_files` → `fnames` until BL-316 lands.

---

## Phase 1 bridge (until builder ships)

| Mechanism | What it does |
|-----------|----------------|
| Read-deps convention | Planner lists edit + read paths in spec and `target_files` |
| `files_unexpected` | Surfaces edits outside `target_files` (git snapshot delta) |
| Cursor rules v7 | Enforces read-deps checklist for implement |
| `mode=review` | Spec Q&A only — does **not** load step N code |

Wave 1 Phase 2 ([BACKLOG](../BACKLOG.md) § Post–Phase 1 focus): start **BL-316 / BL-001** (tiers + assembly), **BL-311a** (warn when spec Files ⊄ `target_files`), then **BL-315** (`edit_scope`).

---

## Non-goals (still deferred)

- RAG / cross-session memory → Phase 3 ([BL-002](../BACKLOG.md#deferred-from-phase-1-by-design--later-phases))
- Gatekeeper MCP for protected specs → [BL-151](../BACKLOG.md#after-phase-1--adapt-our-dev-workflow-to-the-product)
- OpenCode / multi-host → [BL-004](../BACKLOG.md#very-low-priority--other-execution-engines)
- Default full transcript dump → stays opt-in ([D-SPEC-7](../PHASE1_MVP.md#p1-199--end-of-phase-1-review))

---

## Related decisions

| ID | Locked at P1-199 |
|----|------------------|
| D-SPEC-4 | Read-deps convention; MCP enforce → Phase 2 ([BL-311](../BACKLOG.md#bl-311-read-deps-from-spec-files-section)) |
| D-SPEC-7 | Lean context; `host_transcript: none` default |
| D-SPEC-8 | Log scope expansion; `edit_scope` → Phase 2 ([BL-315](../BACKLOG.md#bl-315-edit_scope--spec-files-yaml)) |

---

## Changelog

| Date | Note |
|------|------|
| 2026-06-06 | Created at P1-199 exit; thesis from planning session |
