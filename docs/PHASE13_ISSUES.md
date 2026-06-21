<!--
  STEWARDSHIP — Phase 13 issues log. See docs/VISION_DOCS.md.

  - OK: log bugs found during implementation or dogfood, add workaround notes, mark fixed.
  - NOT OK: replan milestones or change locked decisions here; do that in PHASE13_MVP.md.
  - Workers: file issues here when found; fix in task spec § Results.
-->

# Phase 13 issues

**Status:** **Active** — Phase 13 opened 2026-06-21.
**Open:** P13-ISS-001, P13-ISS-002, P13-ISS-003
**Related PM board:** [PHASE13_MVP.md](./PHASE13_MVP.md)

---

## Open implementation issues

| ID | Status | Severity | Summary | Milestone | Notes |
|----|--------|----------|---------|-----------|-------|
| **P13-ISS-001** | **open** | medium | `project_key` becomes `mcp-coder/specs` when internal `spec_path` is `.mcp-coder/specs/tasks/...` — breaks epic-based memory (D-P12-2) | P13-001 | CLI dogfood 2026-06-21; state at `projects/mcp-coder/specs/` not `tasks/p13-habit` |
| **P13-ISS-002** | **open** | low | `ProjectKeyResolver` maps `tasks/p13-habit-01-models.md` → `tasks/p13` (first `-` in stem), not `tasks/p13-habit` | P13-001 | Epic naming docs / resolver tweak; defer unless blocks real projects |
| **P13-ISS-003** | **open** | low | Reviewer promoted false critical: "Habit dataclass not present" when `habit_cli/models.py` has `Habit` | P13-001 | Del `f5fbc2bd`; poisoned planner with bogus open_risk; defer P13-004 |

---

### P13-ISS-001 — project_key from normalized spec_path

**Filed:** 2026-06-21 (P13-001 CLI dogfood)  
**Severity:** medium

Host passes `spec_path=tasks/p13-habit-01-models.md` but server stores/uses `.mcp-coder/specs/tasks/p13-habit-01-models.md`. `ProjectKeyResolver` then yields `mcp-coder/specs`, so all delegations in a workspace share one project_state bucket unrelated to epic name.

**Expected:** key derived from epic segment (e.g. `tasks/p13-habit`) regardless of `.mcp-coder/specs/` prefix.

**Disposition:** fix in P13-004 or dedicated issue worker — strip `.mcp-coder/specs/` prefix before key resolution.

---

### P13-ISS-002 — epic filename stem truncation

**Filed:** 2026-06-21  
**Severity:** low

`tasks/p13-habit-01-models.md` → `tasks/p13` because `_leaf_key` splits on first `-`.

**Workaround:** use path-style specs `tasks/p13-habit/01-models.md` or `MCP_CODER_PROJECT_KEY` env.

**Disposition:** defer — document epic naming convention in P13-002 docs; optional resolver fix later.

---

### P13-ISS-003 — reviewer false critical on existing dataclass

**Filed:** 2026-06-21  
**Severity:** low

Tier-1 reviewer classified missing `Habit` as critical; file contained correct dataclass. Risk propagated to `project_state` and planner pre-injection on delegation 2.

**Disposition:** defer to P13-004 / reviewer tuning.

---

## Changelog

| Date | Event |
|------|-------|
| 2026-06-21 | P13-ISS-001..003 filed from CLI dogfood (delegations f5fbc2bd, db96b1ce). |
| 2026-06-21 | Phase 13 issues log opened. |
