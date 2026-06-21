<!--
  STEWARDSHIP — Phase 12 issues log. See docs/VISION_DOCS.md.

  - OK: log bugs found during implementation, add workaround notes, mark fixed.
  - NOT OK: replan milestones or change locked decisions here; do that in PHASE12_MVP.md.
  - Workers: file issues here when found; fix in task spec § Results.
-->

# Phase 12 issues

**Status:** **Active** — Phase 12 opened 2026-06-20.
**Open:** P12-ISS-003, P12-ISS-004
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
| **P12-ISS-001** | **closed** | medium | `resume_token` should be internal; host should not need to pass it | P12-001 | Fixed in commit 16dfe7b |
| **P12-ISS-002** | **closed** | high | `SupervisorAgent` recreated per delegation — should be a long-lived singleton per `project_key` | pre-P12-003 | Fixed in commit d8ff46c |
| **P12-ISS-003** | **open** | low | Resume early-return path passes `mcp_session_id=None` to `_handle_resume`; storage not yet created at that code point | post-P12-003 | See note below |
| **P12-ISS-004** | **open** | low | `SupervisorToolRunner` multi-round LLM calls not rolled into supervisor decision token totals | Phase 13 | See note below |

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

---

### P12-ISS-002 — SupervisorAgent singleton per project_key

**Filed:** 2026-06-21  
**Milestone:** pre-P12-003 (must fix before P12-003 is handed to a worker)  
**Severity:** high — architectural correctness; current design defeats the "stateful agent" vision

**Problem:**
`SupervisorAgent` is constructed fresh on every `delegate_to_agent` call and destroyed
when the delegation completes. Between delegations the agent doesn't exist. `project_state`
is reloaded from disk on every call. This contradicts the core vision:

> *"mcp-coder provides tactical execution AND institutional memory — the Supervisor is the
> mind that coordinates workers across the full lifecycle of a real project."*

An agent that dies and is recreated per call is not a persistent mind; it's a stateless
function with disk I/O.

**Desired behaviour:**
- One `SupervisorAgent` per `project_key` lives in a module-level registry for the entire
  MCP server process lifetime.
- First call: created + loads `project_state` from disk (cold start / after restart).
- Subsequent calls: same agent object, `project_state` already warm in memory.
- `project_state` is written to disk at the end of each delegation (crash recovery, already
  implemented by P12-002).
- Per-delegation state (`delegation_id`, `executor_fn`, `plan`, `decisions`, turn state)
  is reset by a new `begin_delegation()` call at the start of each delegation.
- `_handle_resume` stores the resumed agent in the registry.

**Why this matters beyond performance:**
- `project_state_loaded` fires once (cold start) not once per delegation.
- In-memory decisions and hot_areas accumulate without disk round-trips.
- Natural foundation for P12-003 (`SupervisorToolRunner`): the tool-calling loop queries
  the agent's own in-memory state, not disk on every call.
- Conceptually correct: the agent is the identity; delegations are tasks handed to it.

**Scope of fix:**
- `core/engine/supervisor_agent.py`: add `begin_delegation()` instance method that resets
  all per-delegation fields (`delegation_id`, `executor_fn`, `plan`, `decisions`,
  `_cur_turn`, `_completed_turn_artifacts`, `_pending_host_clarification`, `_loop_id`,
  `_loop_start_emitted`, `_loop_end_emitted`) while preserving `_project_state` and
  `_workspace_path`.
- `server/mcp_server.py`: add `_SUPERVISOR_REGISTRY: dict[str, SupervisorAgent]` and
  `_get_or_create_supervisor(project_key, workspace_path, spec_path)` factory; wire into
  `delegate_to_agent` normal path and `_handle_resume`.
- Tests: 5 new tests covering singleton identity, `begin_delegation` reset, project_state
  preservation, and no disk reload on warm agent.

**Spec:** [P12-ISS-002](./tasks/P12-ISS-002-supervisor-singleton.md)

---

---

### P12-ISS-003 — Resume early-return passes `mcp_session_id=None` to `_handle_resume`

**Filed:** 2026-06-21  
**Milestone:** post-P12-003 (low priority; does not block correctness)  
**Severity:** low — resume is correct; only the `align_host` cache-warmth benefit is lost on the first resume call

**Problem:**
In `delegate_to_agent`, the paused-state detection and early-return to `_handle_resume` happens *before* `SessionStore.acquire()` is called. So `storage.mcp_session_id` is unavailable at that point, and `_handle_resume` is called with `mcp_session_id=None` (the default). This means the resume turn always starts with a cold Aider Coder even when `align_host` is active and the Cursor session is still live.

**Fix:** Move the paused-state detection block to *after* `storage = SessionStore().acquire(ws, policy, host_hint)`, then pass `storage.mcp_session_id` to `_handle_resume`.

**Note:** Correctness is not affected. The resumed turn reads files from disk correctly. Only the repo-map warmth benefit of `align_host` is missed on that one call.

**Spec:** [P12-ISS-003](./tasks/P12-ISS-003-resume-session-id-after-storage.md)

---

### P12-ISS-004 — SupervisorToolRunner token accounting not in decision records

**Filed:** 2026-06-21  
**Milestone:** Phase 13 (observability cleanup; does not block P12-004/P12-005)  
**Severity:** low — reporting gap only; gateway still records each `gw.complete()` call independently

**Problem:**
P12-003 wired `SupervisorAgent._llm_decide()` and `DelegationSupervisor.evaluate()` through
`SupervisorToolRunner.run()`, which may invoke `gw.complete()` up to `max_tool_rounds + 1`
times per decision. The runner returns **text only**; callers now pass `tokens={}` into
`SupervisorTurnDecision` / `SupervisorDecision`. Per-delegation supervisor usage reports
therefore under-count supervisor LLM cost when tools are used.

**What still works:**
- Each `gw.complete()` call is recorded by `LlmGateway` / observability backend as a
  separate LLM call (trace + token events).
- Decision logic and tool-calling behaviour are unaffected.

**Desired fix (Phase 13):**
- `SupervisorToolRunner.run()` returns a small result object: `{text, tokens, duration_ms}`
  aggregating all rounds in the loop.
- `_llm_decide()` and `DelegationSupervisor.evaluate()` populate decision records from
  that aggregate.
- Optional: single `supervisor_tool_loop` trace summary with total tokens across rounds.

**Timing:** defer until after Phase 12 milestones ship; natural fit with D-ARCH-10
(multi-model Supervisor observability).

---

## Changelog

| Date | Event |
|------|-------|
| 2026-06-21 | P12-ISS-004 filed — SupervisorToolRunner multi-round token totals not in supervisor decision records; Phase 13 observability cleanup. |
| 2026-06-21 | P12-ISS-003 filed — resume early-return passes mcp_session_id=None; low-priority follow-up after P12-003. |
| 2026-06-21 | P12-ISS-002 closed — singleton agent + Aider session fix (commit d8ff46c). |
| 2026-06-21 | P12-ISS-002 filed — SupervisorAgent singleton: agent must live across delegations, not be recreated per call. Fix targeted before P12-003. |
| 2026-06-21 | P12-ISS-001 closed — implicit resume implemented and dogfooded (commit 16dfe7b). |
| 2026-06-21 | P12-ISS-001 filed — implicit resume: token should be internal, not host-facing. Fix targeted before P12-003. |
| 2026-06-20 | Phase 12 issues log opened. |
