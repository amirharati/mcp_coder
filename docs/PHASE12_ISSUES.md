<!--
  STEWARDSHIP — Phase 12 issues log. See docs/VISION_DOCS.md.

  - OK: log bugs found during implementation, add workaround notes, mark fixed.
  - NOT OK: replan milestones or change locked decisions here; do that in PHASE12_MVP.md.
  - Workers: file issues here when found; fix in task spec § Results.
-->

# Phase 12 issues

**Status:** **Active** — Phase 12 opened 2026-06-20.
**Open:** none yet
**Promoted from backlog:** BL-540 (project state), BL-529 (supervisor context), BL-543 (context lifecycle), BL-544 (pause/resume), BL-541 (reviewer feedback loop), BL-525 v1 / BL-542 (planner project-aware)
**Related PM board:** [PHASE12_MVP.md](./PHASE12_MVP.md)

---

## Promoted from backlog → Phase 12 milestones

*(Planning session 2026-06-20. Full vision for each BL item remains in [BACKLOG.md](./BACKLOG.md); only the scoped slices below are Phase 12 work.)*

| Backlog | Milestone | Scope in Phase 12 | Full vision deferred |
|---------|-----------|-------------------|----------------------|
| **BL-540** | **P12-001** | Project state store: schema, load/save, Supervisor reads/writes per delegation | Full multi-session corpus, RAG index → Phase 13 |
| **BL-529** | **P12-002** | Supervisor context window: task + spec + output tail + project state summary | Full HelperToolRunner sidecar (BL-530) → Phase 13 |
| **BL-543** | **P12-003** | Continuation brief (turn handoff) + confirm_ask enrichment from project state | Full context router with RAG pull (BL-542 full) → Phase 13 |
| **BL-544** | **P12-004** | Pause/resume: resume_token, session state serialization, skip-completed-stages on resume | Late-answer resume (BL-528 built on BL-544) → Phase 13 |
| **BL-541** | **P12-005** | Reviewer findings classified + promoted to project state; Planner sees findings | Tier-2 epic-boundary review → Phase 13 |
| **BL-525** / **BL-542** | **P12-006** | Planner reads project state + reviewer findings; decisions written back after planning | Full Planner-as-real-agent (multi-turn planner, mutable plan) → Phase 13 |

---

## Open implementation issues

*(None yet — Phase 12 not yet in implementation.)*

| ID | Status | Severity | Summary | Milestone | Notes |
|----|--------|----------|---------|-----------|-------|

---

## Changelog

| Date | Event |
|------|-------|
| 2026-06-20 | Phase 12 issues log opened. No issues yet. |
