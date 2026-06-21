# Phase 11 issues

**Status:** **Active** — Phase 11 opened 2026-06-18.
**Open:** P11-ISS-002, P11-ISS-014, P11-ISS-017, P11-ISS-018, P11-ISS-019
**Promoted from backlog:** BL-351 (full), BL-521 (new), BL-354 (v0), BL-358 (v0), BL-512 (Stage 2), BL-522 (new) — see [PHASE11_MVP.md](./PHASE11_MVP.md)
**Related PM board:** [PHASE11_MVP.md](./PHASE11_MVP.md)

---

## Promoted from backlog → Phase 11 milestones

*(Planning session 2026-06-18. Full vision for BL-351 / BL-354 / BL-358 remains in [BACKLOG.md](./BACKLOG.md); only the scoped slices below are Phase 11 work.)*

| Backlog | Milestone | Scope in Phase 11 | Full vision deferred |
|---------|-----------|-------------------|----------------------|
| **BL-521** | **P11-001** ✅ | Clarity pass: cheap LLM pre-delegation Q&A, `clarification_needed` early return | Cross-session intent history → Phase 12 |
| **BL-351** | **P11-002** ✅ | Supervised IO: `SupervisedIO` + `DelegationSupervisor` + in-memory decision log + abort-on-escalate | Mid-run async resume, cheap-LLM step planner, outer-loop resume → Phase 12 |
| **BL-354** | **P11-003** ✅ | Executor-pull v0: system prefix `/read` hint only | Full sidecar HTTP tool server → Phase 12 |
| **BL-522** | **P11-004** ✅ | Mid-run human gate shipped: `answer_delegation_question` tool + Event bridge (experimental) | Protocol-level async mid-run gate + late-answer resume (BL-528) → Phase 12 |
| **BL-358** | **P11-005** ✅ | Tier-1 reviewer shipped: cheap model scan on `files_changed`, appended to spec report | Tier-2 epic-boundary review, critic/redo → Phase 12 |
| — | **P11-006** ✅ | Smart architect trigger shipped: heuristic skip for trivial tasks + spec front-matter override + skip-reason audit detail | — |
| **BL-512** | **P11-007** ✅ | Host model policy shipped: `model_policy` arg on `delegate_to_agent`, precedence over env with non-fatal validation warnings | BL-513 AI-suggested, BL-514 dynamic escalation → Phase 12 |
| — | **P11-008** ✅ | Naming refactor: `architect_pass` → `planner_pass` (canonical); legacy aliases retained with warnings; role constants `ROLE_PLANNER`, `ROLE_REVIEWER`, `ROLE_PLANNER_PASS` added | — |

---

## Shipped milestones

| Milestone | Date | Notes |
|-----------|------|-------|
| P11-001 | 2026-06-19 | `clarity_check` phase; 16 tests; code uncommitted pending review |
| P11-002 | 2026-06-19 | Supervised confirm handling shipped; structured `needs_input` escalation; code uncommitted pending review |
| P11-003 | 2026-06-19 | Executor-pull `/read` prompt hint shipped; merge-safe with existing system prefix; code uncommitted pending review |
| P11-004 | 2026-06-19 | Mid-run human gate shipped (`QuestionRegistry` + answer tool); timeout fallback clean; 30 tests passed |
| P11-005 | 2026-06-19 | Tier-1 reviewer shipped (`reviewer_pass` + report section append); non-fatal error path; 34 tests passed |
| P11-006 | 2026-06-19 | Smart architect trigger shipped (`should_run_architect_pass` + pipeline skip-reason wiring); 24 tests passed |
| P11-007 | 2026-06-19 | Host `model_policy` shipped (executor/helper wiring + audit/warnings); 36 tests passed (41 incl. helper-path regression run) |
|| P11-008 | 2026-06-19 | `architect_pass` → `planner_pass` rename refactor; legacy aliases + warnings; 21 files; 1126 passed full suite |

---

## Open implementation issues

| ID | Status | Severity | Summary | Milestone | Notes |
|----|--------|----------|---------|-----------|-------|
| P11-ISS-001 | **closed** | medium | Pre-dogfood log integrity review — ran 2026-06-19; delegation `d2f31679`; full pipeline + P11 fields confirmed; see issues below for gaps found | P11-008 / phase-exit | Gate passed with known gaps logged as P11-ISS-003/004/005 |
| P11-ISS-002 | open | low | `trace inspect <id>` fails for specless CLI runs — trace file exists but not indexed in workspace_history.db | CLI UX gap | Fix: fall back to trace file scan, or document the limitation |
| P11-ISS-003 | **fixed** | medium | Supervisor LLM calls not emitted as `llm_call` trace events — supervisor `model_roles` entry has cost/model but no `role=supervisor` trace event; makes cost + latency invisible per turn | P11-002 logging | Fixed: emit `llm_call(role=supervisor)` event in `DelegationSupervisor._emit_llm_call_event()` after each `evaluate()` call |
| P11-ISS-004 | **fixed** | medium | Human gate events not emitted as typed trace events — `supervisor_human_gate_opened` / `supervisor_human_gate_timeout` stored in action detail string rather than dedicated events per P11-004 spec | P11-004 logging | Fixed: `SupervisedIO._emit_gate_event()` emits `human_gate_opened`, `human_gate_answered`, `human_gate_timeout` typed trace events |
| P11-ISS-005 | **fixed** | high | Supervisor misclassifies "Add file to the chat?" as `unknown` risk → escalate; blocks every CLI delegation with SUPERVISED_EXEC=1 since no human is available to answer the gate | P11-002 classifier | Fixed: added `_FILE_TO_CHAT_RE` low-risk pattern in `supervised_io.py`; also aligned `confirm_ask()` kwargs with Aider API (`group`, `allow_never`); 15 tests pass |
| P11-ISS-006 | **fixed** | **high** | `delegation_pipeline: {}` is empty in every delegation row — phase-level breakdown (ran/skipped/duration per phase) is never populated in `delegations.jsonl`; trace has the data but the structured summary field is always `{}` | cross-cutting | Fixed: `pipeline_recorder` now created for all `IMPLEMENT` delegations (not just spec-backed ones); was gated on `spec_read is not None` |
| P11-ISS-007 | **fixed** | **high** | `success: false` despite executor writing files — if Aider makes a post-implementation comment after writing all files (e.g. "want me to run tests?"), the pipeline marks it as `clarification_requested` failure; 6 files were written but delegation shows error `"Aider requested clarification before implementing"` | P11-002 / engine | Fixed: root cause was P11-ISS-013; also updated error message to be less misleading |
| P11-ISS-008 | **fixed** | medium | `reviewer_pass` never runs despite `reviewer_pass: true` in config — no `llm_call(role=reviewer_pass)` seen in any trace; delegation has `spec_path` but `context_mode: fallback`; reviewer probably requires compiled spec context | P11-005 | Fixed: decoupled `reviewer_applicable` check from `spec_read is not None` and `delegation_policies is not None` — reviewer now runs whenever `success=True` and `files_changed` is non-empty |
| P11-ISS-009 | **fixed** | medium | `planner_pass` model resolution ignores env var at runtime — `MCP_CODER_PLANNER_PASS_MODEL=openrouter/anthropic/claude-sonnet-4` set in `.env` but planner ran gemini-2.5-flash; `policy_applied.sources.model = 'role_models'` confirms env lookup was bypassed; likely MCP server was started before env var was added (no hot-reload) | P11-008 / role_models | Fixed: confirmed env key `MCP_CODER_PLANNER_PASS_MODEL` matches `_ROLE_MODEL_ENV`; added `_log_role_model_startup()` called from `run_stdio()` that emits resolved models at server start — mismatch will now be visible in server log |
| P11-ISS-010 | **fixed** | low | `clarity_check` `llm_call` trace event has no structured `needs_clarification` field — decision must be inferred by parsing raw `response_body` text; makes programmatic log analysis fragile | P11-001 logging | Fixed: emit `clarity_result` typed trace event with `needs_clarification: bool`, `ran`, `passed`, `questions: list[str]`, `questions_count`, and `error` fields after every clarity check |
| P11-ISS-011 | **fixed** | low | `context_mode: fallback` even when `spec_path` is explicitly provided — final timetracker delegation supplied `spec_path` yet context mode is `fallback`; spec wasn't compiled despite being passed | context compiler | Fixed as part of P11-ISS-006/008: `pipeline_recorder` now always created for IMPLEMENT; `reviewer_applicable` no longer requires `spec_read` |
| P11-ISS-012 | **fixed** | low | Trace viewer still labels planner phase as "architect" — `compile_event` stage constants `STAGE_ARCHITECT_INPUT`/`STAGE_ARCHITECT_OUTPUT` in `trace.py` and display mapping in `delegation_view_enrich.py` were not renamed in P11-008; viewer shows "mcp.architect" instead of "mcp.planner" | P11-008 rename gap | Fixed: added `STAGE_PLANNER_INPUT`/`STAGE_PLANNER_OUTPUT` constants in `trace.py`; old constants aliased for backward compat; `_COMPILE_STAGE_MAP` in `delegation_view_enrich.py` maps both `planner_input` and `architect_input` to `"mcp.planner"` |
| P11-ISS-013 | **fixed** | **high** | `_looks_like_clarification()` too broad — fires on any `?` in output not matching a files-request; executor output (thinking text, README content, log strings) routinely contains `?`, triggering false `clarification_requested` failures even when all files were written; root cause of P11-ISS-007 | `aider_runtime.py` | Fixed: `_looks_like_clarification()` now only checks the **last 20 lines** of output for bare `?`; marker-based detection still checks full output |
| P11-ISS-014 | open | **high** | `llm_call` trace events missing role attribution (`role=None`) — model calls are visible but cannot be reliably mapped to planner/reviewer/clarity/spec-validation/executor in event stream | Observability / phase-exit | Add required fields on every `proxy_llm_call` / `backend_llm_call`: `role`, `model`, `provider`, `ok`, `duration_ms`, token summary; verify with one full delegation |
| P11-ISS-015 | **fixed** | medium | Supervisor outer-loop lifecycle is implicit — no explicit start/end envelope to group inner events and explain control flow | P11-009 | Fixed: `SupervisorAgent` emits canonical `supervisor_loop_start` / `supervisor_loop_end`; unified lifecycle removes the dual `supervisor_outer_loop_*` + inner split; 17 tests pass |
| P11-ISS-016 | **fixed** | medium | Supervisor turn-level decisions are not fully normalized — hard to reconstruct why loop continued, gated, retried, or aborted | P11-009 | Fixed: `SupervisorAgent` emits `supervisor_turn_start`, `supervisor_turn_end`, `supervisor_decision` per turn with `turn_index`, `action`, `reason`, `worker_outcome`, `checks_result`, `duration_ms` |
| P11-ISS-017 | open | medium | Reviewer pass outcome is visible but policy semantics are unclear (advisory vs blocking / continue vs retry) in delegation record and response payload | P11-005 UX/logging | Add explicit reviewer policy fields: `reviewer_mode`, `reviewer_outcome`, `reviewer_action`; include in `response_to_cursor` and `delegations.jsonl` context block |
| P11-ISS-018 | open | low | Planner pass visibility is uneven — pipeline phase exists, but planner audit block is not normalized alongside clarity/spec-validation/reviewer | P11-008 telemetry | Add `planner_pass` audit block (`ran`, `applied`, `error`, `duration_ms`, model role ref) to context block and viewer enrichment |
| P11-ISS-019 | open | low | Clarity loop guardrails now work (Q&A + cap) but telemetry is incomplete for explainability of block vs auto-pass transitions | P11-001 stabilization | Add clarity telemetry fields: `clarity_round_index`, `clarity_round_cap`, `clarity_auto_passed`, and surface them in trace + delegation record |

---

## Phase 12 candidates (surfaced during Phase 11 dogfood prep)

*These are design gaps identified while building and testing Phase 11. Not blocking dogfood — record here so Phase 12 planning starts with a concrete list.*

| ID | Backlog | Theme | One-line summary |
|----|---------|-------|-----------------|
| — | **BL-529** | Supervisor context | Supervisor sees only `question + target_files`; needs task, spec contract, and Aider output tail for informed risk decisions |
| — | **BL-530** | On-demand context retrieval | All helper models (clarity, planner, supervisor, reviewer) are context-frozen at call time; need a minimal tool interface (`read_file`, `rag_search`) to pull dynamic context |
| — | **BL-531** | Multi-turn helper loops | All helpers are single-shot today; planner/supervisor/reviewer should run an internal loop (up to N turns) to refine before producing final output |
| — | **BL-532** | Inter-model communication | No structured signals between models today (Aider → supervisor/planner, reviewer → next delegation, planner → executor mid-run); need a lightweight message bus |
| — | **BL-526** | Architect role | True epic-boundary CTO role (high-level context only, no inner task details); distinct from planner which is task-scoped |
| — | **BL-513** | AI-suggested model policy | Pre-delegation analysis step suggests `model_policy` overrides based on task complexity |
| — | **BL-514** | Dynamic escalation | Outer-loop controller modifies active model policy mid-delegation in response to runtime signals |
| — | **BL-533** | Supervisor as real agent loop | ~~Dual-loop namespace (supervisor_loop / supervisor_outer_loop) was a layering artifact.~~ **Resolved in Phase 11 (P11-009):** `SupervisorAgent` owns unified post-planning loop; single `supervisor_loop_*` lifecycle; `max_turns` config enables autonomous reruns. Live multi-turn rerun wiring in `mcp_server` deferred as follow-up (P11-009 § Results). |

**Phase 12 theme:** *Context intelligence for all roles + supervisor as agent* — move from waterfall pipeline (each model gets a single compiled snapshot) to an agentic loop where the supervisor owns post-planning control flow and every role can query, communicate, and iterate.
