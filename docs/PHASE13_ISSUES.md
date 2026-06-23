<!--
  STEWARDSHIP — Phase 13 issues log. See docs/VISION_DOCS.md.

  - OK: log bugs found during implementation or dogfood, add workaround notes, mark fixed.
  - NOT OK: replan milestones or change locked decisions here; do that in PHASE13_MVP.md.
  - Workers: file issues here when found; fix in task spec § Results.
-->

# Phase 13 issues

**Status:** **Active** — Phase 13 opened 2026-06-21.
**Open:** _(none — all P13 issues resolved or fixed-pending-verify)_
**Related PM board:** [PHASE13_MVP.md](./PHASE13_MVP.md)

---

## Open implementation issues

| ID | Status | Severity | Summary | Milestone | Notes |
|----|--------|----------|---------|-----------|-------|
| **P13-ISS-001** | **fixed** | medium | `project_key` becomes `mcp-coder/specs` when internal `spec_path` is `.mcp-coder/specs/tasks/...` — breaks epic-based memory (D-P12-2) | P13-001 | Fixed in P13-009: resolver strips `.mcp-coder/specs/` prefix before key extraction; acceptance tests for resolver path normalization added and passing. |
| **P13-ISS-002** | **fixed** | low | `ProjectKeyResolver` maps `tasks/p13-habit-01-models.md` → `tasks/p13` (first `-` in stem), not `tasks/p13-habit` | P13-001 | Fixed in P13-009: leaf normalization now strips trailing step suffixes (`-NN`/`-NN-*`) instead of truncating at first hyphen; dedicated resolver tests passing. |
| **P13-ISS-003** | **fixed** | low | Reviewer promoted false critical: "Habit dataclass not present" when `habit_cli/models.py` has `Habit` | P13-001 | Fixed in P13-011: contradiction guard prevents absence-claim findings from promotion when symbol exists in changed content; regression coverage added. |
| **P13-ISS-004** | **fixed** | medium | Supervisor visibility starts at execution loop; delegation pre/post phases are outside Supervisor lifecycle envelope, weakening single-agent semantics and pause/resume lifecycle coherence | P13-005 | Verified in e2e session `97b549b6`: lifecycle starts before preflight (`spec_validation`/`clarity_check`) and closes after postloop/indexing. |
| **P13-ISS-005** | **fixed** | low | Reviewer pass can fail contract parsing ("missing LGTM or ISSUES heading") while delegation still succeeds, creating noisy `reviewer_pass_failed` warnings and inconsistent observability | P13-005 | Fixed in P13-015: parser tolerates heading drift + fenced preamble. Verified via dogfood session `28fbe283` (4 reviewer runs: 3 lgtm + 1 issues, all parsed cleanly, zero `reviewer_pass_failed` noise). |
| **P13-ISS-006** | **fixed-pending-verify** | medium | Executor failure classifier can mislabel output as `config` (missing API key/model) even when LLM executed and produced patch attempt; outcome becomes misleading `needs_input` root cause | P13-001 | Tail hardening landed in P13-015: notfound+edit-flow evidence now maps to non-config (`edit_format`) unless explicit auth/model-config markers exist. Regression suites pass. **No error case in latest dogfood (`28fbe283`) to confirm live** — moved to backlog watch-for-evidence (BL-554). |
| **P13-ISS-007** | **fixed** | medium | P13-005 shipped lifecycle envelope *observability* but kept *control flow* in the server — agent doesn't own preloop/postloop, making the envelope retroactive rather than agent-driven (violates "only the Supervisor is stateful" design principle) | P13-006 | Fixed in P13-006: agent created early, emits `lifecycle_start` + `phase_start(preloop)` BEFORE preloop work, emits phase transitions at execution entry (non-retroactive). Dogfood `eea1e0c4` trace confirms. |
| **P13-ISS-008** | **fixed** | high | Early-close preloop gates (`clarity_check`, `invalid_spec`, `review_target_files_error`) emit `lifecycle_end` then fall through to the unconditional postloop block, producing a stray `phase_end(loop)` (loop never started), `phase_start(postloop)`/`phase_end(postloop)`, and a **second** `lifecycle_end` with outcome `error` — breaks single-envelope-per-delegation invariant and corrupts checkpoint `phases_completed` | P13-007 | Verified in e2e session `97b549b6`: no delegation produced duplicate `lifecycle_end` rows; max observed is one close event per trace. |
| **P13-ISS-009** | **fixed** | low | Orphan delegation `e110fdbb` ran a complete lifecycle envelope + `agent_checkpoint_saved` (success, 04:15:14–04:15:46) but is missing from `delegations.jsonl` (7 envelopes vs 6 delegations rows) — likely the resume path between `0c59917d` escalation and `8af942aa` skipped the delegations-log append | P13-007 | Verified in e2e session `97b549b6`: `traces/*.jsonl` count equals `delegations.jsonl` rows (`8 == 8`). |
| **P13-ISS-010** | **fixed** | high | Delegation viewer (`core/cli/delegation_view_enrich.py::_build_view_events`) has no handlers for P13-005/006/007 event types (`delegation_lifecycle_start/end`, `delegation_phase_start/end`, `agent_checkpoint_saved`, `agent_rehydrated`, `project_state_loaded/saved`) — the `if/elif` chain silently drops them, so the agent boundary envelope and checkpoint events are invisible in the viewer despite being correctly emitted and persisted in the trace JSONL | P13-005/006/007 | Verified in e2e viewer: lifecycle boundary and checkpoint events render (example `eac45425`: lifecycle start/end + checkpoint visible). |
| **P13-ISS-011** | **fixed** | high | Delegation can emit `delegation_lifecycle_start` but never emit `delegation_lifecycle_end` (open envelope) on some failed `needs_input` paths, leaving malformed traces and partial phase metadata | P13-004 | Fixed in P13-012: lifecycle close is guarded/idempotent across failed/blocked paths (including resume handler), with targeted + regression tests and subsequent CLI verification. |
| **P13-ISS-012** | **fixed** | medium | Lifecycle outcome/state can diverge across artifacts: `delegations.jsonl` reports `needs_input` while `delegation_lifecycle_end` reports `error` in trace, making triage and downstream tooling ambiguous | P13-004 | Fixed in P13-013: canonical final outcome parity enforced (including invalid-spec + clarity-block combination); dedicated regression test added and passing. |
| **P13-ISS-013** | **superseded** | medium | Clarity-block follow-up may run as a fresh delegation instead of an explicit resume lineage (`resumed=true` / `supervisor_resumed`), weakening pause/resume semantics and future context-policy separation | P13-004 | Superseded by P13-ISS-014, which captures the stricter product requirement: clarity-blocked pause must resume true lineage (not `fresh_by_policy`). |
| **P13-ISS-014** | **fixed** | high | Clarity-blocked delegations are not resumed; follow-up runs start fresh (`resumed=false`) and viewer shows loop failures instead of explicit pause→resume continuity | P13-004 | Fixed in P13-016: clarity-block pause now auto-resumes on next delegation (host return = resume signal); emits `lifecycle_start(resumed=true)` + `supervisor_resumed(resume_reason=clarity_block_reentry)`. Verified via 5-delegation dogfood (session `28fbe283`, delegation `6462b2c3`). Escalation pauses remain answer-gated by design. |
| **P13-ISS-015** | **fixed-pending-verify** | medium | Executor turn can fail with `supervisor_turn_end.worker_outcome=unknown` / `supervisor_loop_end.end_reason=unknown` while row-level error typing is missing, making root-cause triage opaque in viewer + JSONL | P13-004 | Fixed in P13-014: unknown loop outcomes now persist typed row/payload cause (`error_class=unknown` + machine reason) and viewer enrichment surfaces typed fields. Regression tests pass. **No unknown failure in latest dogfood (`28fbe283`) to confirm live** — moved to backlog watch-for-evidence (BL-555). |
| **P13-ISS-016** | **fixed** | medium | Specific unknown-failure trace for `3c10501d` needs explicit forensic check before next dogfood once ISS-014/015 are fixed | P13-004 | Forensic gate completed (2026-06-23): trace + row analysis confirms true failure cause was executor output-contract drift (whole-file markdown response), not provider/config outage. P13-014 now surfaces typed unknown cause in row/view fields; follow-up observability gap tracked separately in P13-ISS-017. |
| **P13-ISS-017** | **fixed** | medium | Clarity-blocked preloop delegations are represented as loop failures instead of explicit pause-to-host state, despite no executor turn | P13-004 | Fixed in P13-016: gated host-driven turn/loop closure with `not _lifecycle_closed` so blocked preloop no longer emits synthetic `supervisor_turn_end=failure` / `supervisor_loop_end=executor_error`. Path now renders cleanly as pause/back-to-host. Verified via dogfood (session `28fbe283`, delegation `1a077ce7`: zero loop events, clean `needs_input` close). |

---

### P13-ISS-001 — project_key from normalized spec_path

**Filed:** 2026-06-21 (P13-001 CLI dogfood)  
**Severity:** medium

Host passes `spec_path=tasks/p13-habit-01-models.md` but server stores/uses `.mcp-coder/specs/tasks/p13-habit-01-models.md`. `ProjectKeyResolver` then yields `mcp-coder/specs`, so all delegations in a workspace share one project_state bucket unrelated to epic name.

**Expected:** key derived from epic segment (e.g. `tasks/p13-habit`) regardless of `.mcp-coder/specs/` prefix.

**Disposition:** fixed in P13-009 (2026-06-22). Resolver now strips `.mcp-coder/specs/` before project-key extraction; acceptance coverage added in `tests/test_supervisor_state_p12_001.py` (`-k project_key`).

---

### P13-ISS-002 — epic filename stem truncation

**Filed:** 2026-06-21  
**Severity:** low

`tasks/p13-habit-01-models.md` → `tasks/p13` because `_leaf_key` splits on first `-`.

**Workaround:** use path-style specs `tasks/p13-habit/01-models.md` or `MCP_CODER_PROJECT_KEY` env.

**Disposition:** fixed in P13-009 (2026-06-22). Leaf-key normalization now removes trailing step suffixes (`-NN`, `-NN-*`) instead of splitting at first hyphen, preserving epic stems like `p13-habit`.

---

### P13-ISS-003 — reviewer false critical on existing dataclass

**Filed:** 2026-06-21  
**Severity:** low

Tier-1 reviewer classified missing `Habit` as critical; file contained correct dataclass. Risk propagated to `project_state` and planner pre-injection on delegation 2.

**Disposition:** fixed in P13-011 (2026-06-22). Reviewer contradiction guard now blocks promotion of absence claims when symbols are present in changed content; regression coverage added.

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

**Disposition:** fixed in P13-015 (2026-06-23). Parser now tolerates common heading drift (`#` depth, bold wrappers, punctuation separators) and fenced preamble content without false parse failure. Verified via dogfood session `28fbe283`: 4 reviewer runs (3 lgtm + 1 issues) all parsed cleanly with zero `reviewer_pass_failed` noise.

---

### P13-ISS-006 — executor error misclassified as config

**Filed:** 2026-06-21  
**Severity:** medium

CLI dogfood delegation `db96b1ce-e5ed-490f-84aa-606282bfdf8d` returned `error_class=config` / "missing API key or unknown model id" even though trace/output show successful LLM call and partial patch attempt (including SEARCH/REPLACE markers) plus file writes.

**Expected:** classifier should report parse/patch/conflict-style error class (or explicit executor-format failure), not config/auth when provider calls succeeded.

**Disposition:** fixed-pending-verify in P13-015 (2026-06-23). Classifier no longer treats synthetic config short-message echo as primary evidence and prefers non-config classification (`edit_format`) when edit-flow markers are present without explicit auth/model evidence. Regression tests pass. No error case in latest dogfood (`28fbe283`) to confirm live — watch for evidence in future runs (BL-554).

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

### P13-ISS-011 — lifecycle envelope can remain open on failed `needs_input` paths

**Filed:** 2026-06-22 (e2e dogfood session `97b549b6`)  
**Severity:** high

Some delegations emit `delegation_lifecycle_start` and then fail with `delegation_failed error="unknown"` without ever emitting `delegation_lifecycle_end` (and without any phase boundary events). This violates the single-envelope invariant and makes trace-level completion ambiguous.

**Observed:** session `97b549b6`, delegations `b03c9cda`, `d50bafae`, `bce1b972`:
- trace has `lifecycle_start` + `clarity_result` + `supervisor_decision` + `agent_checkpoint_saved`
- trace has **no** `lifecycle_end`
- `delegations.jsonl` marks outcome `needs_input`
- server emits `delegation_failed ... error="unknown"`

**Expected:** every emitted `lifecycle_start` must be closed by exactly one `lifecycle_end` regardless of success/failure/cancel.

**Disposition:** fixed in P13-012 (2026-06-22). Lifecycle closure is now guarded and idempotent across failed/blocked/resume paths, with targeted resume/paused/needs_input tests and lifecycle regression suite passing.

---

### P13-ISS-012 — outcome mismatch between `delegations.jsonl` and lifecycle-end trace

**Filed:** 2026-06-22 (e2e dogfood session `97b549b6`)  
**Severity:** medium

A delegation can report different terminal outcomes across artifacts:
- `delegations.jsonl`: `outcome=needs_input`
- trace: `delegation_lifecycle_end outcome=error`

This breaks observability invariants and confuses issue triage/automation.

**Observed:** session `97b549b6`, delegation `9f0c8821` (`success=False`):
- row outcome = `needs_input`
- lifecycle_end outcome = `error`
- trace still emits postloop closure events before lifecycle end

**Expected:** one canonical terminal outcome shared by lifecycle-end trace event, delegations row, and host response payload.

**Disposition:** fixed in P13-013 (2026-06-22). Canonical terminal outcome parity enforced across lifecycle trace + `delegations.jsonl` + response payload, including invalid-spec + clarity-block overlap.

---

### P13-ISS-013 — clarity follow-up not modeled as explicit resume lineage

**Filed:** 2026-06-22 (manual dogfood session `e3b31581`)  
**Severity:** medium

Architecture intent: a clarity-blocked delegation should pause and the next host answer should continue as a **resume lineage** (resume semantics/context), distinct from a fresh delegation rebuild path.

Observed behavior in manual dogfood:
- `2ab56c80` blocks on clarity questions (pause-like behavior).
- follow-up `bb38894d` starts as a fresh delegation with `delegation_lifecycle_start(resumed=false)`.
- no explicit `supervisor_resumed`/`resumed=true` lineage signal appears.

This blurs control-path semantics that we want to keep separate:
- **resume path**: continue prior context/turn lineage
- **fresh path**: recompile/rebuild context from scratch

Why it matters: we plan to manage context differently for resume vs fresh delegations. Without explicit lineage, observability and policy branching are ambiguous.

**Expected:** when host is answering prior clarity questions, routing should either:
1) use explicit resume path (with resume events/flags), or  
2) explicitly record why a fresh path was chosen (policy-level signal), so traces remain unambiguous.

**Disposition:** superseded by P13-ISS-014 (2026-06-22). This issue captured ambiguity about fresh-vs-resume signaling; ISS-014 now tracks the stricter product requirement that clarity follow-ups must resume true lineage.

---

### P13-ISS-014 — pause-on-clarity should resume, not fresh-start

**Filed:** 2026-06-22 (manual + e2e follow-up review, session `0f5d8db1`)  
**Severity:** high

Current behavior after a clarity block is still a fresh delegation (`resumed=false`, `clarity_followup_lineage.mode=fresh_by_policy`) instead of a true resume path.

**Observed sequence (session `0f5d8db1`):**
- `ec40fece` blocks in preloop (`clarity_result questions_count=2`) and ends `needs_input`.
- next delegation `3c10501d` starts with `delegation_lifecycle_start(resumed=false)`.
- no `supervisor_resumed` / resume rehydration event appears.

This causes viewer/operator confusion because the flow appears as a fresh run that failed in loop, not a continuation of the paused delegation.

**Expected:** host clarification follow-up should resume paused delegation lineage (resume event + `resumed=true`) unless explicitly overridden by policy.

**Disposition:** fixed in P13-016 (2026-06-23). Clarity-block pause now auto-resumes on next delegation (host return = resume signal); emits `lifecycle_start(resumed=true)` + `supervisor_resumed(resume_reason=clarity_block_reentry)`. Verified via 5-delegation dogfood (session `28fbe283`). Escalation pauses remain answer-gated by design.

---

### P13-ISS-015 — unknown loop failure lacks explicit typed cause in row/view

**Filed:** 2026-06-22 (e2e session `0f5d8db1`)  
**Severity:** medium

A delegation can fail inside loop with supervisor outcome metadata marked `unknown`, but row-level error typing is missing, so operators cannot distinguish parser/classifier fallback from provider/config/edit-format failures using `delegations.jsonl` + viewer alone.

**Observed (`3c10501d`):**
- trace: `supervisor_turn_end.worker_outcome=unknown`
- trace: `supervisor_loop_end.end_reason=unknown`
- trace: lifecycle ends `needs_input`
- row: `success=false`, `outcome=needs_input`, but no `error_class`
- row `response_to_cursor` digest omits outcome/error fields by design (preview-only digest), further reducing diagnosability in viewer.

**Expected:** when loop ends with unknown classification, persist explicit typed error metadata in row/view-friendly fields (at least `error_class=unknown` + short reason), so triage does not require deep trace spelunking every time.

**Disposition:** fixed-pending-verify in P13-014 (2026-06-23). Unknown loop failure now persists typed row/payload cause (`error_class=unknown` with machine reason), and viewer enrichment exposes `outcome`/`error_class`/`error_message`. Regression tests pass. No unknown failure in latest dogfood (`28fbe283`) to confirm live — watch for evidence in future runs (BL-555).

---

### P13-ISS-016 — pre-dogfood forensic gate for delegation `3c10501d`

**Filed:** 2026-06-22 (post-ISS-014/015 prioritization)  
**Severity:** medium

Before the next broad dogfood run, we need a focused forensic verification on the previously opaque failure (`session=0f5d8db1`, `delegation=3c10501d`) after ISS-014 and ISS-015 code fixes land.

**Scope of this check:**
- verify pause→resume continuity appears explicitly (resume lineage, not fresh restart);
- verify unknown-failure path carries typed row-level metadata (`error_class`, short reason) aligned with trace outcomes;
- verify viewer surface is no longer misleading for this trace (row/loop/lifecycle fields coherent).

**Why this is a separate issue:** this is a targeted acceptance gate, not just implementation work. It ensures we close the exact observed ambiguity before spending time on another full manual/CLI dogfood cycle.

**Forensic findings (2026-06-23):**
- Exact trace inspected from canonical store:
  - session: `0f5d8db1-b443-4164-bd45-4c289fa236ac`
  - delegation: `3c10501d-770b-41e7-be28-838b78f1c58f`
- `backend_llm_call` is present and successful (`ok=true`) but response body is a whole-file markdown answer (`habit_cli/storage.py` listing) instead of adapter-expected edit contract.
- No `executor_error_classified` event was emitted in that historical trace; supervisor ends with:
  - `supervisor_turn_end.worker_outcome=unknown`
  - `supervisor_loop_end.end_reason=unknown`
  - `delegation_lifecycle_end.outcome=needs_input`
- Delegation row already carried `error_detail.error_class=unknown`, but historical viewer signal was weak because:
  - `response_to_cursor` digest omitted outcome/error fields, and
  - prior enrich path did not reliably surface row-level typed failure fields.
- P13-014 addresses the typed-cause surfacing side (payload/row/view enrichment).

**Disposition:** fixed. Gate completed with trace-level evidence; no additional code change required under this issue.

---

### P13-ISS-017 — preloop clarity block emits synthetic loop-failure events

**Filed:** 2026-06-23 (post-ISS-016 forensic verification)  
**Severity:** medium

After a clarity block in preloop, traces still include loop-failure events even though no executor turn ran. This makes the viewer show a failure-like loop path for what should be an explicit pause/back-to-host handoff.

**Evidence:**
- Historical e2e traces in session `0f5d8db1`:
  - `ec40fece-41a6-4f84-a1e2-15f3977b7aca`
  - `932203d0-8a43-4e01-bd4d-cc5f97479b26`
- Both show:
  - `clarity_result` with questions (`passed=false`),
  - `delegation_phase_end(preloop, status=blocked, detail=clarity_check)`,
  - `delegation_lifecycle_end(outcome=needs_input)`,
  - **plus** `supervisor_turn_end(worker_outcome=failure)` and `supervisor_loop_end(end_reason=executor_error)`,
  - and `backend_llm_call` count is zero.
- Deterministic local repro on current code (2026-06-23) reproduced the same event pattern.

**Expected:** if delegation is blocked in preloop before executor loop starts, represent it as pause/needs-input handoff (not failure):
- emit/retain explicit pause marker for host handoff (`supervisor_paused` semantics),
- keep terminal lifecycle outcome as `needs_input`,
- do not emit synthetic loop-failure markers (`supervisor_turn_end=failure`, `supervisor_loop_end=executor_error`) when loop never ran.

**Disposition:** fixed in P13-016 (2026-06-23). Gated host-driven turn/loop closure block with `not _lifecycle_closed` so clarity-blocked preloop no longer emits synthetic loop-failure markers. Path now renders as pause/back-to-host (`needs_input`). Verified via dogfood (session `28fbe283`, delegation `1a077ce7`).

---

## Changelog

| Date | Event |
|------|-------|
| 2026-06-23 | Dogfood evidence review (session `28fbe283`): closed P13-ISS-005 to **fixed** (4 clean reviewer runs, zero noise). ISS-006 and ISS-015 remain fixed-pending-verify (no error/unknown failure in this run to confirm live) — moved to backlog watch-for-evidence (BL-554, BL-555) for future log analysis. |
| 2026-06-23 | P13-016 implemented (Bundle C): fixed P13-ISS-014 (clarity-block auto-resume with true lineage) and P13-ISS-017 (blocked preloop = pause/handoff, not failure). 5-delegation dogfood (session `28fbe283`) confirms both fixes end-to-end. Both issues marked **fixed**. Also fixed 2 viewer rendering bugs found during dogfood (`_executor_ran` helper-call miscount + missing pause/resume/abandoned handlers). All P13 issues now resolved or fixed-pending-verify. |
| 2026-06-23 | Clarified P13-ISS-017 contract: clarity-blocked preloop path must be represented as pause/back-to-host (`needs_input`) rather than synthetic loop failure, so viewer semantics match actual control flow. |
| 2026-06-23 | Reopened P13-ISS-014 from live dogfood session `a9f90b63`: clarity-blocked delegation `9c33ecca` is followed by `797717b9` with `resumed=false` and `clarity_followup_lineage.mode=fresh_by_override` (`reason=start_fresh_true`), not true pause→resume continuity. |
| 2026-06-23 | P13-015 worker implemented (Bundle B tail hardening): moved P13-ISS-005 and P13-ISS-006 to **fixed-pending-verify** based on passing parser/classifier regressions (`16 + 38 + combined 85` tests). Remaining open issue: P13-ISS-017. |
| 2026-06-23 | Completed P13-ISS-016 forensic gate on exact trace (`0f5d8db1` / `3c10501d`): root cause confirmed as executor output-contract drift (whole-file markdown response), with unknown fallback path now better surfaced by P13-014. Added P13-ISS-017 for still-reproducible synthetic loop-failure events on clarity-blocked preloop exits (`ec40fece`, `932203d0`, plus deterministic current-code repro). |
| 2026-06-23 | P13-014 worker implemented (Bundle A): moved P13-ISS-014 and P13-ISS-015 to **fixed-pending-verify** based on passing regressions (resume-lineage + unknown-typed-cause + viewer surfacing). Kept P13-ISS-016 open as the live-trace/dogfood gate for `0f5d8db1` / `3c10501d`. |
| 2026-06-23 | Status reconciliation (conservative): marked P13-ISS-001/002/003/011/012 as **fixed** based on completed worker fixes + passing targeted regressions; marked P13-ISS-013 as **superseded** by P13-ISS-014; kept P13-ISS-005/006 open pending stronger verification evidence. |
| 2026-06-22 | Added P13-ISS-016 as a pre-dogfood gate: after fixing ISS-014/015, perform focused forensic verification on session `0f5d8db1` delegation `3c10501d` (resume continuity + typed unknown-cause parity across row/trace/viewer) before the next broad dogfood run. |
| 2026-06-22 | Added P13-ISS-015 from e2e session `0f5d8db1`: delegation `3c10501d` failed in-loop with `worker_outcome=end_reason=unknown` but row lacks explicit `error_class`, making viewer/JSONL root-cause triage opaque without deep trace inspection. |
| 2026-06-22 | Added P13-ISS-014 from e2e session `0f5d8db1`: clarity-blocked delegation (`ec40fece`) followed by non-resumed fresh run (`3c10501d`, `resumed=false`, `fresh_by_policy`), conflicting with required pause→resume behavior and viewer continuity. |
| 2026-06-22 | Added P13-ISS-013 from manual dogfood (`e3b31581`): clarity-block follow-up (`2ab56c80` -> `bb38894d`) executed as fresh delegation (`resumed=false`) rather than explicit resume lineage, conflicting with desired pause/resume architecture semantics. |
| 2026-06-22 | Re-verified with e2e session `97b549b6`: marked P13-ISS-004/008/009/010 as **fixed**; re-opened P13-ISS-005 (still emits `reviewer_pass_failed` on success); added P13-ISS-011 (open envelope on `delegation_failed` unknown path) and P13-ISS-012 (outcome mismatch between `delegations.jsonl` and `lifecycle_end`). |
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
