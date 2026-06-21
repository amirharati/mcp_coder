<!--
  STEWARDSHIP — Phase 12 issues log. See docs/VISION_DOCS.md.

  - OK: log bugs found during implementation, add workaround notes, mark fixed.
  - NOT OK: replan milestones or change locked decisions here; do that in PHASE12_MVP.md.
  - Workers: file issues here when found; fix in task spec § Results.
-->

# Phase 12 issues

**Status:** **Active** — Phase 12 opened 2026-06-20.
**Open:** P12-ISS-001
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

| ID | Status | Severity | Summary | Milestone | Notes |
|----|--------|----------|---------|-----------|-------|
| **P12-ISS-001** | **open** | medium | `resume_token` should be internal; host should not need to pass it | P12-001 | See detail below |

---

### P12-ISS-001 — Implicit resume: token should be internal, not host-facing

**Filed:** 2026-06-21
**Milestone:** P12-001 (correction before P12-003 ships)
**Severity:** medium — correctness risk (host can forget token, causing unintended cold restart)

**Problem:**
P12-001 shipped `resume_token` as a host-facing param on `delegate_to_agent`. The host must store and pass it back on resume. This over-trusts the host orchestration layer: if the token is lost (host forgets, new Cursor session, etc.), the next call silently starts a fresh delegation instead of resuming — losing saved supervisor state.

**Why this is wrong architecturally:**
- mcp-coder is the stateful agent; the host is a junior PM. State handling belongs inside mcp-coder.
- There is at most one paused state per project_key at a time (system is sequential today).
- Per-spec scoping is preserved for the future parallel world: paused state lives under `projects/<project_key>/supervisor_states/` — one active slot per project_key.

**Desired behaviour:**
- `delegate_to_agent(spec_path=..., answer=...) ` — if a paused state exists for this project_key, auto-resume it with the answer. No token needed.
- `delegate_to_agent(spec_path=..., start_fresh=True)` — explicitly abandon paused state and restart.
- `delegate_to_agent(spec_path=...) ` with no answer and no `start_fresh` — if a paused state exists, return `outcome="needs_input"` with the original questions (don't restart, don't resume — remind host it is paused).
- `resume_token` stays as an **internal implementation detail** (filename of the state JSON). Never exposed in the response or required in the request.

**Scope of fix (small):**
- `server/mcp_server.py`: remove `resume_token` param; add `answer: str | None` and `start_fresh: bool = False`; auto-detect paused state by project_key; route accordingly.
- `_response_payload`: remove `resume_token` field from response (or keep as optional debug field only).
- `core/state/supervisor_state.py`: add `find_latest(project_key)` → returns most-recent non-expired state for that key (single-slot assumption).
- Tests: update `test_supervisor_state_p12_001.py` to cover auto-detect + start_fresh paths.

**Timing:** fix before P12-003 spec is handed to a worker. P12-003 (tool-calling loop) does not depend on the resume API shape, but having a clean API now avoids carrying technical debt into later milestones.

---

## Changelog

| Date | Event |
|------|-------|
| 2026-06-21 | P12-ISS-001 filed — implicit resume: token should be internal, not host-facing. Fix targeted before P12-003. |
| 2026-06-20 | Phase 12 issues log opened. |
