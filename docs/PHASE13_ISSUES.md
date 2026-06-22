<!--
  STEWARDSHIP — Phase 13 issues log. See docs/VISION_DOCS.md.

  - OK: log bugs found during implementation or dogfood, add workaround notes, mark fixed.
  - NOT OK: replan milestones or change locked decisions here; do that in PHASE13_MVP.md.
  - Workers: file issues here when found; fix in task spec § Results.
-->

# Phase 13 issues

**Status:** **Active** — Phase 13 opened 2026-06-21.
**Open:** P13-ISS-001, P13-ISS-002, P13-ISS-003, P13-ISS-006
**Related PM board:** [PHASE13_MVP.md](./PHASE13_MVP.md)

---

## Open implementation issues

| ID | Status | Severity | Summary | Milestone | Notes |
|----|--------|----------|---------|-----------|-------|
| **P13-ISS-001** | **open** | medium | `project_key` becomes `mcp-coder/specs` when internal `spec_path` is `.mcp-coder/specs/tasks/...` — breaks epic-based memory (D-P12-2) | P13-001 | CLI dogfood 2026-06-21; state at `projects/mcp-coder/specs/` not `tasks/p13-habit` |
| **P13-ISS-002** | **open** | low | `ProjectKeyResolver` maps `tasks/p13-habit-01-models.md` → `tasks/p13` (first `-` in stem), not `tasks/p13-habit` | P13-001 | Epic naming docs / resolver tweak; defer unless blocks real projects |
| **P13-ISS-003** | **open** | low | Reviewer promoted false critical: "Habit dataclass not present" when `habit_cli/models.py` has `Habit` | P13-001 | Del `f5fbc2bd`; poisoned planner with bogus open_risk; defer P13-004 |
| **P13-ISS-004** | **fixed-pending-verify** | medium | Supervisor visibility starts at execution loop; delegation pre/post phases are outside Supervisor lifecycle envelope, weakening single-agent semantics and pause/resume lifecycle coherence | P13-005 | Implemented in P13-005 (`delegation_lifecycle_*`, phase envelope, resume coherence); verify in renewed dogfood traces |
| **P13-ISS-005** | **fixed-pending-verify** | low | Reviewer pass can fail contract parsing ("missing LGTM or ISSUES heading") while delegation still succeeds, creating noisy `reviewer_pass_failed` warnings and inconsistent observability | P13-005 | Implemented non-fatal reviewer result propagation (`reviewer_pass_result=error`) in lifecycle context; verify runtime noise level in dogfood |
| **P13-ISS-006** | **open** | medium | Executor failure classifier can mislabel output as `config` (missing API key/model) even when LLM executed and produced patch attempt; outcome becomes misleading `needs_input` root cause | P13-001 | CLI dogfood del `db96b1ce`; output contains model thinking + patch markers, but `error_class=config` |
| **P13-ISS-007** | **fixed** | medium | P13-005 shipped lifecycle envelope *observability* but kept *control flow* in the server — agent doesn't own preloop/postloop, making the envelope retroactive rather than agent-driven (violates "only the Supervisor is stateful" design principle) | P13-006 | Fixed in P13-006: agent created early, emits `lifecycle_start` + `phase_start(preloop)` BEFORE preloop work, emits phase transitions at execution entry (non-retroactive). Dogfood `eea1e0c4` trace confirms. |
| **P13-ISS-008** | **fixed-pending-verify** | high | Early-close preloop gates (`clarity_check`, `invalid_spec`, `review_target_files_error`) emit `lifecycle_end` then fall through to the unconditional postloop block, producing a stray `phase_end(loop)` (loop never started), `phase_start(postloop)`/`phase_end(postloop)`, and a **second** `lifecycle_end` with outcome `error` — breaks single-envelope-per-delegation invariant and corrupts checkpoint `phases_completed` | P13-007 | Fixed in P13-008: agent-side idempotent `emit_lifecycle_end` (no-op + warn on 2nd call) + phase-event guards; server-side `_lifecycle_closed` flag in 3 early-close branches + gates on postloop block. Verify in next dogfood: each delegation shows exactly one `lifecycle_end`. |
| **P13-ISS-009** | **fixed-pending-verify** | low | Orphan delegation `e110fdbb` ran a complete lifecycle envelope + `agent_checkpoint_saved` (success, 04:15:14–04:15:46) but is missing from `delegations.jsonl` (7 envelopes vs 6 delegations rows) — likely the resume path between `0c59917d` escalation and `8af942aa` skipped the delegations-log append | P13-007 | Fixed in P13-008: `_delegation_record_appended` flag + minimal interrupted-record append in `delegate_to_agent` `finally` block (covers host-cancel / uncaught-exception paths). Root cause was a cancelled `delegate_to_agent` call (not a resume — `_handle_resume` reuses the same trace file). Verify: `delegations.jsonl` row count == trace envelope count. |
| **P13-ISS-010** | **fixed-pending-verify** | high | Delegation viewer (`core/cli/delegation_view_enrich.py::_build_view_events`) has no handlers for P13-005/006/007 event types (`delegation_lifecycle_start/end`, `delegation_phase_start/end`, `agent_checkpoint_saved`, `agent_rehydrated`, `project_state_loaded/saved`) — the `if/elif` chain silently drops them, so the agent boundary envelope and checkpoint events are invisible in the viewer despite being correctly emitted and persisted in the trace JSONL | P13-005/006/007 | Fixed in P13-008: 8 new `elif t == "…"` handlers in `_build_view_events()` (scope=`agent`). Verify in next dogfood: agent boundary rows (lifecycle start/end, phase dividers, checkpoint) appear in viewer. |

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

### P13-ISS-004 — Supervisor envelope excludes pre/post lifecycle

**Filed:** 2026-06-21  
**Severity:** medium

Current behavior is a valid hybrid: Supervisor owns execution turn orchestration, while preflight (`spec_validation`, `clarity_check`, planner/builder prep) and post-delegate indexing run outside the Supervisor loop. In traces this looks like "agent loop inside larger server flow", not one persistent MCP agent lifecycle.

**Observed:** Cursor run delegation `b250d28e-d703-47f9-8701-db7f173c1075` shows `supervisor_loop_start` after preflight and `supervisor_loop_end` before post indexing.

**Expected:** One Supervisor-owned lifecycle envelope with explicit phases (`preloop`, `loop`, `postloop`) and shared state awareness across phases, while preserving deterministic gates.

**Disposition:** implement in P13-005 before continuing remaining Phase 13 milestones.

---

### P13-ISS-005 — reviewer pass strict heading contract is brittle

**Filed:** 2026-06-21  
**Severity:** low

Cursor dogfood delegation `b250d28e-d703-47f9-8701-db7f173c1075` completed successfully, but reviewer stage emitted error `missing LGTM or ISSUES heading` and server logged `reviewer_pass_failed`. This creates noisy warning telemetry and ambiguity in run health despite successful execution.

**Expected:** reviewer output parser should degrade gracefully (normalize/lenient fallback) and report structured outcome without warning spam for non-critical format drift.

**Disposition:** fold into P13-005 lifecycle coherence work (observability + reviewer stage robustness), or P13-004 if kept small.

---

### P13-ISS-006 — executor error misclassified as config

**Filed:** 2026-06-21  
**Severity:** medium

CLI dogfood delegation `db96b1ce-e5ed-490f-84aa-606282bfdf8d` returned `error_class=config` / "missing API key or unknown model id" even though trace/output show successful LLM call and partial patch attempt (including SEARCH/REPLACE markers) plus file writes.

**Expected:** classifier should report parse/patch/conflict-style error class (or explicit executor-format failure), not config/auth when provider calls succeeded.

**Disposition:** prioritize in P13-004 (or dedicated issue worker) because it directly impacts triage and host guidance quality.

---

### P13-ISS-007 — P13-005 envelope is retroactive, not agent-owned

**Filed:** 2026-06-21 (post-P13-001 re-verification)
**Severity:** medium

P13-005 shipped the lifecycle envelope events (`delegation_lifecycle_start/end`, `delegation_phase_start/end`) but the *control flow* remains in `server/mcp_server.py`. The server emits preloop phase events *after* preloop work completes (retroactive), and the agent only owns the loop phase. This contradicts the design principle in [notes/supervisor-orchestration-layer.md](../notes/supervisor-orchestration-layer.md): "Only the Supervisor is stateful. Every other component is a pure worker."

**Observed:** Delegation `d1b0bea1` trace shows `delegation_phase_start(preloop)` (event 8) emitted after `spec_validation` and `clarity_check` already ran. The envelope is a trace-level illusion of agent ownership.

**Expected:** `SupervisorAgent.delegate()` owns the full lifecycle — calls `run_preloop()` / `run_loop()` / `run_postloop()` and emits phase events *around* the work as it transitions. The server becomes a thin entry point.

**Disposition:** fixed in P13-006 (2026-06-21). Agent is now created early (before preloop) and owns the lifecycle envelope — emits `lifecycle_start` + `phase_start(preloop)` BEFORE preloop work, emits `phase_end(preloop)` + `phase_start(loop)` at execution entry (non-retroactive). Added `delegate()` / `resume_and_delegate()` API surface. Dogfood `eea1e0c4` trace confirms honest ordering (timestamps: lifecycle_start 07:32.160 → phase_start(preloop) 07:32.225 → spec_validation compile_event 07:32.225 → phase_end(preloop) 07:32.225 → phase_start(loop) 07:32.225 → supervisor_loop_start 07:32.228). Body migration of preloop/postloop work code into `agent.run_preloop()/run_postloop()` deferred to a future milestone — the `delegate()` entry point is the stable surface for that.

---

### P13-ISS-008 — early-close preloop gates emit a second, malformed lifecycle envelope

**Filed:** 2026-06-22 (P13-007 server dogfood `d8842b66`)  
**Severity:** high

Early-close preloop branches (`clarity_check_blocked`, `invalid_spec`, `review_target_files_error`) emit `phase_end(preloop, status="blocked")` + `lifecycle_end(<needs_input|error>)` and then fall through to the unconditional postloop closure block, which emits:
- `phase_end("loop", …)` — even though the loop phase was never started
- `phase_start("postloop")` + `phase_end("postloop")` — postloop was not run
- a **second** `lifecycle_end(_lifecycle_final_outcome)` computed as `"error"` (because `success=False`)

**Observed:** Server dogfood `d8842b66` (session `d8842b66-57fc-4712-94e9-b7ce1ded5968`), delegations `07df2634` and `0c59917d` (both `needs_input`):
```
04:14:13.845  delegation_lifecycle_end  outcome=needs_input   ← correct close
04:14:13.848  agent_checkpoint_saved
04:14:13.848  delegation_phase_end     phase=loop             ← stray (loop never started)
04:14:13.849  delegation_phase_start  phase=postloop         ← stray
04:14:13.855  delegation_phase_end     phase=postloop         ← stray
04:14:13.855  delegation_lifecycle_end outcome=error        ← STRAY second close
```
Aggregate effect across the session: `lifecycle_end` count (9) > `lifecycle_start` count (7). The persisted `~/.mcp-coder/projects/mcp-coder/specs/agent_state.json` confirms the corrupted `phases_completed=["preloop","postloop"]` — `loop` missing because never started, `postloop` included because started post-close. Future tooling that relies on a single coherent envelope per delegation will misparse these.

**Expected:** One `lifecycle_start` and at most one `lifecycle_end` per delegation. No phase events after the envelope closes.

**Disposition:** defer to a follow-up task spec. Two complementary fixes:
1. **Agent-side (idempotent guard):** `SupervisorAgent.emit_lifecycle_end` becomes idempotent — second and later calls log a warning and no-op. `emit_lifecycle_phase_*` no-ops when the envelope is closed. This is the durable fix that protects all callers.
2. **Server-side (control flow):** Set `_lifecycle_closed = True` in the three early-close branches (`clarity_check`, `invalid_spec`, `review_target_files_error`); gate the postloop closure block (lines 3055–3356) on `not _lifecycle_closed`. This prevents the stray emissions at the source.

---

### P13-ISS-009 — orphan delegation `e110fdbb` missing from delegations.jsonl

**Filed:** 2026-06-22 (P13-007 server dogfood `d8842b66`)  
**Severity:** low

Delegation `e110fdbb-cf2f-427f-b5ce-b13183a1ac7a` ran a complete lifecycle envelope (`lifecycle_start` + `preloop`/`loop`/`postloop` phases + `lifecycle_end outcome=success`) and emitted `agent_checkpoint_saved` at 04:15:46 with `last_delegation_id=e110fdbb`, but **no** corresponding row was appended to `delegations.jsonl` (the file lists 6 delegations; traces contain 7 envelopes). The delegation ran between `0c59917d`'s escalation (04:15:55) and `8af942aa` (04:16:00), suggesting it was triggered via the resume / answer path which may bypass the delegations-log writer used by the regular `delegate_to_agent` path.

**Observed:** `~/.mcp-coder/projects/948faf…/sessions/d8842b66…/delegations.jsonl` has 6 lines; `traces/` has 7 trace files with full envelopes.

**Expected:** Every delegation that opens a lifecycle envelope also appends a row to `delegations.jsonl` (same fields, same writer), so the delegations log and the trace tree agree 1:1.

**Disposition:** defer to a follow-up task spec. Audit `_handle_resume` (and any alternate entry paths) in `server/mcp_server.py` to ensure they go through the same `delegations.jsonl` append as the regular path.

---

### P13-ISS-010 — delegation viewer silently drops P13-005/006/007 events

**Filed:** 2026-06-22 (P13-007 server dogfood `d8842b66`)  
**Severity:** high

`core/cli/delegation_view_enrich.py::_build_view_events()` maps raw trace event types to ViewEvents via an `if/elif` chain (lines 592–1235). The chain has handlers for legacy types (`compile_event`, `llm_call`, `proxy_llm_call`, `backend_llm_call`, `action`, `tool_call`, `supervisor_loop_start/end`, `supervisor_turn_*`, `supervisor_decision`, `supervisor_outer_loop_*`, `clarity_result`) but **no handlers** for the P13-005/006/007 event types, and no `else` clause — so unrecognized types are silently dropped:

| Event type | In trace JSONL? | Rendered by viewer? |
|---|---|---|
| `delegation_lifecycle_start` | ✓ | ✗ dropped |
| `delegation_phase_start` | ✓ | ✗ dropped |
| `delegation_phase_end` | ✓ | ✗ dropped |
| `delegation_lifecycle_end` | ✓ | ✗ dropped |
| `agent_checkpoint_saved` | ✓ | ✗ dropped |
| `agent_rehydrated` | ✓ | ✗ dropped |
| `project_state_loaded` | ✓ | ✗ dropped |
| `project_state_saved` | ✓ | ✗ dropped |

**Observed:** Server dogfood `d8842b66`, delegation `8af942aa` — the trace JSONL contains all 8 envelope+checkpoint events in correct order (lifecycle_start 04:16:00.999 → phase_start(preloop) 04:16:01.083 → phase_end(preloop) → phase_start(loop) → supervisor_loop_start → … → supervisor_loop_end → agent_checkpoint_saved → phase_end(loop) → phase_start(postloop) → phase_end(postloop) → lifecycle_end 04:17:37.738), but the viewer renders only legacy rows with no visible agent boundary. User cannot see the preloop/loop/postloop phase boundaries or the checkpoint save in the UI.

**Expected:** Viewer renders a row per `delegation_lifecycle_*` and `delegation_phase_*` event (as scope=`agent`, `is_boundary=True` for lifecycle start/end, `is_divider=True` for phase boundaries), plus rows for `agent_checkpoint_saved`, `agent_rehydrated`, `project_state_loaded/saved`. This is what makes the "agent owns the full lifecycle" (P13-006) and "agent is stateful" (P13-007) designs visible to the user.

**Disposition:** defer to a follow-up task spec. Additive — ~8 new `elif t == "…"` handlers in `_build_view_events()` following the existing `supervisor_*` pattern. No changes to the viewer JS or to log format. This is the issue that makes ISS-008 visible to the user, so it should be fixed before (or alongside) ISS-008.

---

## Changelog

| Date | Event |
|------|-------|
| 2026-06-22 | Marked P13-ISS-008, P13-ISS-009, P13-ISS-010 as fixed-pending-verify after P13-008 implementation: agent-side idempotent lifecycle close guard (ISS-008), `finally`-block interrupted-record append (ISS-009), 8 new viewer handlers for agent-envelope events (ISS-010). 65 tests passing (20 new + 45 regression). Live re-dogfood suggested for master session. |
| 2026-06-22 | Added P13-ISS-010 from server dogfood `d8842b66`: delegation viewer (`delegation_view_enrich.py`) silently drops P13-005/006/007 events (lifecycle envelope, phase boundaries, checkpoint, rehydration, project_state) — agent boundary invisible in UI despite correct logs. Fix: add ViewEvent handlers for the 8 new types. |
| 2026-06-22 | Added P13-ISS-009 from server dogfood `d8842b66`: orphan delegation `e110fdbb` (7 envelopes vs 6 delegations.jsonl rows) — resume path likely bypasses delegations-log append. |
| 2026-06-22 | Added P13-ISS-008 from server dogfood `d8842b66`: early-close preloop gates fall through to unconditional postloop block, emitting a stray `phase_end(loop)` + `phase_start/end(postloop)` + a **second** `lifecycle_end`. Affects delegations `07df2634`, `0c59917d`. Breaks single-envelope invariant and corrupts checkpoint `phases_completed`. |
| 2026-06-21 | Marked P13-ISS-007 as fixed after P13-006 implementation: agent now owns lifecycle envelope (non-retroactive phase events). Dogfood `eea1e0c4` confirms honest ordering. |
| 2026-06-21 | Added P13-ISS-007: P13-005 envelope is retroactive, not agent-owned. Spec P13-006 scoped. |
| 2026-06-21 | Marked P13-ISS-004 and P13-ISS-005 as fixed-pending-verify after P13-005 implementation; keep verification in resumed dogfood. |
| 2026-06-21 | Added P13-ISS-005 from Cursor dogfood: reviewer pass heading-contract brittleness (`reviewer_pass_failed` despite success). |
| 2026-06-21 | Added P13-ISS-006 from CLI dogfood: executor failure misclassified as `config`. |
| 2026-06-21 | Added P13-ISS-004 from Cursor dogfood: Supervisor loop does not yet own full delegation lifecycle envelope. |
| 2026-06-21 | P13-ISS-001..003 filed from CLI dogfood (delegations f5fbc2bd, db96b1ce). |
| 2026-06-21 | Phase 13 issues log opened. |
