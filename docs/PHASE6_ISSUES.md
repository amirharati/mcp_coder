<!--
  STEWARDSHIP — Phase 6 issue tracker. See docs/VISION_DOCS.md.

  - **Frozen** 2026-06-13 at recommended exit (+ P6-006…P6-008 post-dogfood fixes).
  - Workers: do not edit. New gaps → BACKLOG BL-* via planning session.
-->

# Phase 6 issue tracker

**Status:** **Frozen** (2026-06-13 — recommended exit met; P6-001…P6-008 done)
**Purpose:** Gaps found during Phase 6 implementation and dogfood.
**Milestone board:** [PHASE6_MVP.md](./PHASE6_MVP.md) (frozen)
**Carried to backlog:** [BACKLOG.md](./BACKLOG.md) § Phase 6 exit — BL-350, BL-333, BL-368, BL-367, BL-357, BL-321

Status: `open` | `done` | `wontfix` | `carried`

---

## Issues (final)

| ID | Status | Priority | Title | Resolution |
|----|--------|----------|-------|------------|
| P6-ISS-001 | **done** | low | **`NullObservability.merge_model_roles` returns `None` — wrong return type** | Fixed in `6e6b1cc` — returns `{}`; test added. |
| P6-ISS-002 | **carried** | low | **V1 logging = LiteLLM callback; revisit unified `LlmGateway` proxy** | Route A + Route B shipped (P6-002, P6-008). Callback remains shim for opaque executor. → **[BL-368](./BACKLOG.md#bl-368-unified-llmgateway-completion-proxy)** (Phase 7); composes with **BL-367** (Phase 8 full-capture). |
| P6-ISS-003 | **done** | medium | **BL-335 live dogfood not run in P6-002 worker session** | Dogfood v3 (`f9cb07fc`, session `4c2dac56`) after P6-008: all helper `model_roles.*.tokens` non-null (`source: owned_completion`); trace file with header + 3 `llm_call` lines; `maintenance stats` shows 2 trace files. |
| P6-ISS-004 | **done** | low | **`get_role_tokens` / `overlay_model_roles_tokens` not on `ObservabilityBackend` ABC** | Fixed in P6-003 — promoted to ABC + `NullObservability` stubs. |
| P6-ISS-005 | **done** | low | **`mcp_server` bypasses seam for token overlay** | Fixed in P6-003 — `mcp_server` uses `obs.overlay_model_roles_tokens()` only. |
| P6-ISS-006 | **carried** | high | **Executor inner loop is opaque — no tool calls, retries, or lint-loop visibility** | → **[BL-350](./BACKLOG.md#bl-350-supervised-executor-loop-mid-run-inspect--context-inject)** (Phase 7+) |
| P6-ISS-007 | **carried** | medium | **Reasoning capture is executor-only; builder + architect reasoning not accumulated** | → extend **[BL-333](./BACKLOG.md#bl-333-reasoning-trace-capture--cross-delegation-context-feed)** when dogfood shows value |
| P6-ISS-008 | **done** | medium | **No version tags on trace records (git SHA, model IDs, pipeline flags, config fingerprint)** | Fixed in P6-005 — `trace_header` + training tuple version tags. |
| P6-ISS-009 | **carried** | low | **No cross-session reasoning persistence** | Hot buffer session-scoped only. → **[BL-333](./BACKLOG.md#bl-333-reasoning-trace-capture--cross-delegation-context-feed)** + `workspace_history.db` persistence (Phase 7+) |
| P6-ISS-010 | **carried** | low | **No novelty scoring / curation pipeline** | Bootstrap sequence — log raw first. → **[AGENTIC_LOOP_LOGGING.md](./OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md)** product scope; pairs with **BL-357** |
| P6-ISS-011 | **carried** | low | **No confusion/escalation heuristic wired to reasoning capture** | → **[BL-321](./BACKLOG.md#bl-321-progressive--tiered-executor-model-selection)** (acts on Phase 6 capture) |
| P6-ISS-012 | **done** | high | **`contextvars` not propagated into `ThreadPoolExecutor` worker threads** | Fixed in P6-006. |
| P6-ISS-013 | **done** | high | **`response_to_cursor` body inlined in `delegations.jsonl`** | Fixed in P6-007 — digest only. |
| P6-ISS-014 | **done** | high | **`context_refs` full bodies inlined in `delegations.jsonl`** | Fixed in P6-007 — pointer-only. |
| P6-ISS-015 | **done** | medium | **`context.context_package` blob inlined in `delegations.jsonl`** | Fixed in P6-007 — `context_package_hash` only. |
| P6-ISS-016 | **done** | medium | **No `trace_ref` join key in `delegations.jsonl`** | Fixed in P6-007. |
| P6-ISS-017 | **done** | high | **Helper LLM tokens + trace files missing — Aider bypasses LiteLLM callback** | Fixed in P6-008 — Route B `owned_completion`. |

---

## Observations (archive)

| Date | Finding |
|------|---------|
| 2026-06-13 | **Phase 6 exit — full-capture architectural decision (master session):** Phase 6 verbosity tiers (`lean`/`standard`/`full`) currently control **what gets written to disk** — at `lean` or `standard`, prompt bodies and executor turns are permanently lost. Decision: the correct long-term design is **capture 100% at the boundary always**; verbosity tiers become display/export/RAG-promotion filters only. Requires: unified `LlmGateway` proxy (P6-ISS-002 grown up) + executor loop ownership (BL-350). Logged as **BL-367** (target Phase 8). Do not delay: this is the foundation for forensic replay, training data quality, and systematic gap-finding. |
| 2026-06-13 | **Dogfood v2 analysis (master session):** delegation `ffa0b17b` — P6-007 lean JSONL PASS (11.9 KB vs 24 KB); helper tokens FAIL (all `unavailable`); trace files FAIL (0 project-wide despite `trace_ref`). P6-006 necessary but insufficient — root cause is Aider Model path bypasses LiteLLM callback. Opened P6-ISS-017 → P6-008 owned helper completion. |
| 2026-06-13 | **Phase 6 exit gap analysis (master session):** compared shipped substrate against AGENTIC_LOOP_LOGGING vision. Four structural gaps carried to Phase 7+: (1) inner Aider loop opaque — P6-ISS-006, gated on BL-350; (2) reasoning capture executor-only — P6-ISS-007; (3) no version tags on trace records — P6-ISS-008; (4) no cross-session reasoning persistence — P6-ISS-009. Two pipeline gaps are intentionally deferred per bootstrap sequence: no novelty scoring — P6-ISS-010; no escalation heuristic — P6-ISS-011. Substrate is correct for "log everything raw first" stage. |
| 2026-06-13 | **JSONL storage analysis (master session):** live dogfood record breakdown — one `delegations.jsonl` per host session (not per project); 10 sessions × ~2–31 delegations for the e2e project. Single record ~24 KB: `response_to_cursor` 33%, `context` 24%, `context_refs` 19%. Three concrete bloat sources opened as P6-ISS-013/014/015. D-P6-3 pointer gap opened as P6-ISS-016. Root bug for null helper tokens opened as P6-ISS-012. Designed target: ~3 KB per record after P6-007 (lean refs + digest provenance). BL-356 remains the long-horizon RAG-backed lean-refs milestone. |
| 2026-06-13 | P6-004 deep-check: executor-only callback capture, JSONL `context.reasoning_summary` omit-when-absent, hot buffer + builder injection; recommended exit met (P6-ISS-003 live dogfood still open). |
| 2026-06-13 | P6-003 deep-check: trace append via callback; lean/standard/full tiers; P6-ISS-004/005 closed. |
| 2026-06-13 | P6-002 deep-check: implementation matches D-P6-2. Minor seam nits (non-blocking): `get_role_tokens` / `overlay_model_roles_tokens` on `LocalObservability` only (not ABC/`NullObservability`); `mcp_server` imports `overlay_model_roles_from_callback` directly instead of `obs.overlay_*`. **Fixed P6-003.** |
| 2026-06-13 | **Logging v1 architecture (master session):** Prefer long-term **unified `LlmGateway` / completion proxy** so mcp-coder does not chase per-backend details — one boundary for everything sent/received. **Not this iteration:** P6-002 ships **LiteLLM `success_callback`** (D-P6-2) as v1; covers helper + executor paths without forking Aider. Callback is a **transitional tap** for the opaque executor loop; owned helper calls (~6 `core/engine/*_llm.py` modules) are natural first migrate targets when proxy lands. Proxy scope is **broader than logging** (tokens, trace bodies, reasoning, budget, redaction) but same seam — aligns with AGENTIC_LOOP_LOGGING extract and **BL-353**. Schedule: note at Phase 6 exit; implement when executor loop ownership (BL-350) or P6-003 trace needs make callback-only awkward. |
| 2026-06-13 | P6-001 deep-check: `NullObservability.merge_model_roles` returns `None` (matches `dict \| None` annotation) but `_build_model_roles_payload` in `mcp_server.py` expects a dict. No production impact (production uses `LocalObservability`), but will cause `TypeError` if any future test wires `NullObservability` through the full delegate path. |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | **Frozen** — Phase 6 exit; recommended + post-dogfood fixes (P6-006…P6-008) done; P6-ISS-002 → carried (BL-368); P6-ISS-006…011 → carried (BL-350, BL-333, BL-321, BL-357, AGENTIC_LOOP_LOGGING) |
| 2026-06-13 | Observation added — full-capture architectural decision: verbosity as display-only filter; BL-367 opened; Phase 8 target |
| 2026-06-13 | P6-ISS-003 closed — dogfood v3 (`f9cb07fc`): helper tokens + trace files PASS after P6-008 |
| 2026-06-13 | P6-008 done — owned helper `litellm.completion` + `record_owned_completion`; P6-ISS-017 closed; P6-ISS-003 dogfood re-run pending |
| 2026-06-13 | P6-ISS-017 opened — dogfood v2: Aider Model bypasses LiteLLM callback; helper tokens + traces still missing; P6-008 tasked |
| 2026-06-13 | P6-007 done — JSONL lean record (response digest, lean context_refs, context_package_hash, trace_ref); P6-ISS-013…016 closed; ~24 KB → ~3 KB per record |
| 2026-06-13 | P6-006 done — `copy_context()` + `ctx.run` in 3 helper LLM modules; P6-ISS-012 closed; P6-ISS-003 dogfood unblocked |
| 2026-06-13 | P6-ISS-012…016 opened — storage analysis: contextvars bug + JSONL bloat (response_to_cursor, context_refs, context_package, trace_ref gap); P6-006 + P6-007 tasked |
| 2026-06-13 | P6-005 done — trace version tags, training capture foundation, `mcp-coder maintenance stats`; P6-ISS-008 closed |
| 2026-06-13 | P6-ISS-006–011 opened — gaps from exit gap analysis; all carried to Phase 7+ |
| 2026-06-13 | Phase 6 **recommended exit** met in code (P6-001–P6-004); P6-ISS-003 live BL-335 dogfood still open |
| 2026-06-13 | P6-ISS-004, P6-ISS-005 opened — observability seam polish from P6-002 deep-check |
| 2026-06-13 | P6-ISS-003 opened — BL-335 live dogfood pending after P6-002 code ship |
| 2026-06-13 | P6-ISS-002 opened — v1 callback locked for P6-002; defer unified LlmGateway proxy revisit to Phase 6 exit / Phase 7+ |
| 2026-06-13 | P6-ISS-001 → done (commit `6e6b1cc`) |
| 2026-06-13 | P6-ISS-001 opened — `NullObservability.merge_model_roles` wrong return type found during P6-001 deep-check |
| 2026-06-13 | Created at Phase 6 planning session |
