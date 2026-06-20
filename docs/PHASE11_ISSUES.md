# Phase 11 issues

**Status:** **Active** — Phase 11 opened 2026-06-18.
**Open:** P11-ISS-002 through P11-ISS-011 (6 new from timetracker dogfood 2026-06-19)
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
| P11-ISS-003 | open | medium | Supervisor LLM calls not emitted as `llm_call` trace events — supervisor `model_roles` entry has cost/model but no `role=supervisor` trace event; makes cost + latency invisible per turn | P11-002 logging | Fix: emit `llm_call(role=supervisor)` event in `DelegationSupervisor.evaluate()` |
| P11-ISS-004 | open | medium | Human gate events not emitted as typed trace events — `supervisor_human_gate_opened` / `supervisor_human_gate_timeout` stored in action detail string rather than dedicated events per P11-004 spec | P11-004 logging | Fix: emit proper typed events from `SupervisedIO` escalation path |
| P11-ISS-005 | **fixed** | high | Supervisor misclassifies "Add file to the chat?" as `unknown` risk → escalate; blocks every CLI delegation with SUPERVISED_EXEC=1 since no human is available to answer the gate | P11-002 classifier | Fixed: added `_FILE_TO_CHAT_RE` low-risk pattern in `supervised_io.py`; also aligned `confirm_ask()` kwargs with Aider API (`group`, `allow_never`); 15 tests pass |
| P11-ISS-006 | open | **high** | `delegation_pipeline: {}` is empty in every delegation row — phase-level breakdown (ran/skipped/duration per phase) is never populated in `delegations.jsonl`; trace has the data but the structured summary field is always `{}` | cross-cutting | Found: timetracker dogfood 2026-06-19, all 6 delegations; fix: serialize pipeline phase summary from pipeline runner into delegation row on completion |
| P11-ISS-007 | open | **high** | `success: false` despite executor writing files — if Aider makes a post-implementation comment after writing all files (e.g. "want me to run tests?"), the pipeline marks it as `clarification_requested` failure; 6 files were written but delegation shows error `"Aider requested clarification before implementing"` | P11-002 / engine | Found: delegation `54d12044`, 6 files written; fix: if `files_changed` is non-empty, treat post-work Aider questions as soft warning not hard failure |
| P11-ISS-008 | open | medium | `reviewer_pass` never runs despite `reviewer_pass: true` in config — no `llm_call(role=reviewer_pass)` seen in any trace; delegation has `spec_path` but `context_mode: fallback`; reviewer probably requires compiled spec context | P11-005 | Found: timetracker dogfood 2026-06-19; investigate whether reviewer skip condition is tied to context_mode rather than presence of `files_changed` |
| P11-ISS-009 | open | medium | `planner_pass` model resolution ignores env var at runtime — `MCP_CODER_PLANNER_PASS_MODEL=openrouter/anthropic/claude-sonnet-4` set in `.env` but planner ran gemini-2.5-flash; `policy_applied.sources.model = 'role_models'` confirms env lookup was bypassed; likely MCP server was started before env var was added (no hot-reload) | P11-008 / role_models | Found: delegation `54d12044`; fix: confirm env var name matches key in `_ROLE_MODEL_ENV`, add startup log for each resolved role model so mismatches are visible on launch |
| P11-ISS-010 | open | low | `clarity_check` `llm_call` trace event has no structured `needs_clarification` field — decision must be inferred by parsing raw `response_body` text; makes programmatic log analysis fragile | P11-001 logging | Found: all 5 clarity-blocked delegations; fix: add `needs_clarification: bool` + `questions: list[str]` to `llm_call` event when `role=clarity_check` |
| P11-ISS-011 | open | low | `context_mode: fallback` even when `spec_path` is explicitly provided — final timetracker delegation supplied `spec_path` yet context mode is `fallback`; spec wasn't compiled despite being passed | context compiler | Found: delegation `54d12044`; investigate spec compilation trigger condition when spec_path provided in `mcp_request` |

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

**Phase 12 theme:** *Context intelligence for all roles* — move from waterfall pipeline (each model gets a single compiled snapshot) to an agentic loop where every role can query, communicate, and iterate.
