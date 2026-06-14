<!--
  STEWARDSHIP — Phase 7 issue tracker. See docs/VISION_DOCS.md.

  - Workers: do not edit. Gaps found during implementation → open new P7-ISS-NNN rows here via master session.
  - New backlog items → BACKLOG BL-* via planning session.
-->

# Phase 7 issue tracker

**Status:** **Frozen** — closed 2026-06-13 at optional capstone exit
**Purpose:** Gaps found during Phase 7 implementation and dogfood.
**Milestone board:** [PHASE7_MVP.md](./PHASE7_MVP.md)
**Phase 6 issues (frozen):** [PHASE6_ISSUES.md](./PHASE6_ISSUES.md)

Status: `open` | `done` | `wontfix` | `carried`

---

## Issues

| ID | Status | Priority | Title | Resolution |
|----|--------|----------|-------|------------|
| P7-ISS-001 | done | high | Double-recording risk: LiteLLM callback fires for owned helper calls too | Fixed P7-001: `_gateway_call_active` guard in `litellm_success_handler`; `test_llm_gateway.py` verifies exactly one trace record per helper completion. |
| P7-ISS-002 | done | low | `owned_completion.py` is a confusing thin re-export | Deprecated with P7-001 comment; delete in Phase 8 cleanup. |
| P7-ISS-003 | done | medium | `stdio_isolation.py` is in `core/engine/` — gateway cannot import it | Resolved: `gateway.py` imports `core/engine/stdio_isolation` only (not `aider_engine.py`). Extractability constraint satisfied. Optional move to `core/utils/` deferred. |
| P7-ISS-004 | done | low | Config toggles for step budget (D-P7-2) have no config key names yet | Resolved in P7-002: `executor_max_steps`, `executor_hard_max`, `executor_step_timeout_s`, `executor_total_timeout_s` implemented with defaults and clamping in `core/config/aider_runtime.py`. |
| P7-ISS-005 | carried | low | CLI paths need ad-hoc gateway bootstrap | Carried to **BL-369**: lazy gateway bootstrap for CLI entry points. |
| P7-ISS-006 | carried | low | `validation_input` compile provenance lacks transcript byte ranges | Carried to **BL-370**: host transcript byte-range provenance for replay fidelity. |
| P7-ISS-007 | carried | medium | Backend-specific interception strategy needed before claiming full in/out capture | Carried to **BL-371**: backend-specific interception plan; full-complete logging milestone may shift to Phase 9 depending on Phase 8 design outcomes. |

---

## Observations

| Date | Finding |
|------|---------|
| 2026-06-13 | Master session: reviewed `litellm_callback.py` source — both `_extract_from_success` (callback path) and `record_owned_completion` (Route B path) independently call `_bump_call_index` and `_append_trace_for_completion`. A single helper call today triggers both, producing call_index 1 (callback) and call_index 2 (owned) in the trace. This is the root cause behind P7-ISS-001. Phase 6 tests likely don't catch it because they mock litellm and disable the callback. |
| 2026-06-13 | Master session: `core/observability/gateway.py` location confirmed (D-P7-1). Dependency direction is engine → observability → litellm. `gateway.py` may freely import `core/observability/context.py`, `trace.py`, `base.py`, `litellm_callback.py` — all same package. Must NOT import `server/`, `core/engine/aider_engine.py`. |
| 2026-06-13 | Master session: `NullLlmGateway` is the test swap point — tests that currently mock `litellm.completion` directly should migrate to `set_llm_gateway(NullLlmGateway())` for cleaner isolation. Worker can leave existing mocks in place; migration is optional during P7-001. |
| 2026-06-13 | P7-001 shipped: 735 pytest green; dedup guard verified; `reset_llm_gateway()` added for test teardown; `test_model.py` routed through gateway. |
| 2026-06-13 | P7-002 shipped: executor outer loop trace events (`llm_call` + `tool_call` + `action`) and `maintenance stats` executor_turns landed; dogfood `42321f57-315e-4275-a086-5d08c861f028` confirmed expected event types. |
| 2026-06-13 | P7-003 shipped: compile provenance `compile_event` stages landed in same trace file; dogfood `40b4f69d-8ab8-4b33-ade0-c2d521ab5123` confirmed all 8 stages at standard verbosity. |
| 2026-06-13 | Carry decision: backend-specific interception strategy deferred to Phase 8 planning; "full complete logging" may move to Phase 9 depending on Phase 8 design outcomes across multiple backends. |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | **Phase 7 issues frozen** — P7-ISS-005/006/007 carried to backlog (BL-369/370/371) |
| 2026-06-13 | P7 closeout carry added: P7-ISS-007 (backend-specific interception strategy, potential full-log milestone shift to Phase 9) |
| 2026-06-13 | P7 closeout: P7-ISS-004 done (step-budget config shipped in P7-002); P7-ISS-006 opened (validation_input byte ranges unavailable) |
| 2026-06-13 | P7-001 closeout: P7-ISS-001…003 done; P7-ISS-005 opened (lazy gateway bootstrap for CLI) |
| 2026-06-13 | Master session: P7-ISS-001…004 opened (double-recording risk, owned_completion dead code, stdio_isolation location, step-budget config keys); observations added |
| 2026-06-13 | Created at Phase 7 planning session — no issues yet |
