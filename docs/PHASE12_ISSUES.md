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
| **BL-544** | **P12-001** | Stateful SupervisorAgent + pause/resume: `SupervisorState`, session serialization, `resume_token` on `delegate_to_agent`, skip-completed-stages on resume. Gateway not changed here. | Late-answer resume (BL-528 built on BL-544) → Phase 13 |
| **BL-540** | **P12-002** | Persistent project state store: schema, load/save, Supervisor reads/writes per delegation; `ProjectState` built on `ProjectKeyResolver` from P12-001 | Full multi-session corpus, RAG index → Phase 13 |
| **BL-530/542** | **P12-003** | `SupervisorToolRunner`: two-tier context model, tool-calling loop (extends `gw.complete()` with `tools=`), Phase 12 tool set: `get_project_state`, `get_delegation_history` (via history_db), `read_file`. Tier-1 continuation brief assembly from `completed_turn_artifacts`. | `get_diff`, `search_past_decisions` (RAG), full HelperToolRunner for other roles → Phase 13 |
| **BL-541** | **P12-004** | Reviewer findings classified + promoted to project state; `get_reviewer_findings` tool available to SupervisorToolRunner | Tier-2 epic-boundary review → Phase 13 |
| **BL-525** | **P12-005** | Planner reads project state via pre-injection (D-P12-6); decisions extracted and written back | Full tool-calling Planner (BL-525 complete) → Phase 13 |

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
