<!--
  STEWARDSHIP — Phase 6 issue tracker. See docs/VISION_DOCS.md.

  - Active during Phase 6 implementation.
  - Workers: do not edit. Found gaps → open new P6-ISS-* via master session.
  - On Phase 6 exit: freeze this file; open items → BACKLOG BL-*.
-->

# Phase 6 issue tracker

**Status:** **Active** — Phase 6 implementation started 2026-06-13
**Purpose:** Gaps found during Phase 6 implementation and dogfood.
**Milestone board:** [PHASE6_MVP.md](./PHASE6_MVP.md)

Status: `open` | `done` | `wontfix` | `carried`

---

## Issues

| ID | Status | Priority | Title | Resolution |
|----|--------|----------|-------|------------|
| P6-ISS-001 | **done** | low | **`NullObservability.merge_model_roles` returns `None` — wrong return type** | Fixed in `6e6b1cc` — returns `{}`; test added. |
| P6-ISS-002 | **open** | low | **V1 logging = LiteLLM callback; revisit unified `LlmGateway` proxy** | **Locked for P6-002–P6-004:** Route A (`litellm.success_callback` + `contextvars`) is v1 — good start, ships tokens + trace substrate without Aider patching. **Revisit:** end-of-Phase-6 planning session (design); real implementation likely **Phase 7+** after minimum exit. Target: single completion proxy for owned calls (helpers, `test-model`, future backends) — logging + related concerns (budget, redaction, rate limits); callback remains shim for Aider executor until BL-350 owns the loop. See Observations 2026-06-13. |
| P6-ISS-003 | **open** | medium | **BL-335 live dogfood not run in P6-002 worker session** | Code + unit tests shipped (`test_litellm_callback.py`, overlay merge). Master session: one live delegate on `mcp_coder_phase1_e2e` with helpers enabled; confirm `model_roles.*.tokens` non-null in JSONL. Close when replicate passes. |
| P6-ISS-004 | **done** | low | **`get_role_tokens` / `overlay_model_roles_tokens` not on `ObservabilityBackend` ABC** | Fixed in P6-003 — promoted to ABC + `NullObservability` stubs. |
| P6-ISS-005 | **done** | low | **`mcp_server` bypasses seam for token overlay** | Fixed in P6-003 — `mcp_server` uses `obs.overlay_model_roles_tokens()` only. |

---

## Observations

| Date | Finding |
|------|---------|
| 2026-06-13 | P6-003 deep-check: trace append via callback; lean/standard/full tiers; P6-ISS-004/005 closed. |
| 2026-06-13 | P6-002 deep-check: implementation matches D-P6-2. Minor seam nits (non-blocking): `get_role_tokens` / `overlay_model_roles_tokens` on `LocalObservability` only (not ABC/`NullObservability`); `mcp_server` imports `overlay_model_roles_from_callback` directly instead of `obs.overlay_*`. **Fixed P6-003.** |
| 2026-06-13 | **Logging v1 architecture (master session):** Prefer long-term **unified `LlmGateway` / completion proxy** so mcp-coder does not chase per-backend details — one boundary for everything sent/received. **Not this iteration:** P6-002 ships **LiteLLM `success_callback`** (D-P6-2) as v1; covers helper + executor paths without forking Aider. Callback is a **transitional tap** for the opaque executor loop; owned helper calls (~6 `core/engine/*_llm.py` modules) are natural first migrate targets when proxy lands. Proxy scope is **broader than logging** (tokens, trace bodies, reasoning, budget, redaction) but same seam — aligns with AGENTIC_LOOP_LOGGING extract and **BL-353**. Schedule: note at Phase 6 exit; implement when executor loop ownership (BL-350) or P6-003 trace needs make callback-only awkward. |
| 2026-06-13 | P6-001 deep-check: `NullObservability.merge_model_roles` returns `None` (matches `dict \| None` annotation) but `_build_model_roles_payload` in `mcp_server.py` expects a dict. No production impact (production uses `LocalObservability`), but will cause `TypeError` if any future test wires `NullObservability` through the full delegate path. |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | P6-ISS-004, P6-ISS-005 → done (P6-003 seam polish) |
| 2026-06-13 | P6-ISS-004, P6-ISS-005 opened — observability seam polish from P6-002 deep-check |
| 2026-06-13 | P6-ISS-003 opened — BL-335 live dogfood pending after P6-002 code ship |
| 2026-06-13 | P6-ISS-002 opened — v1 callback locked for P6-002; defer unified LlmGateway proxy revisit to Phase 6 exit / Phase 7+ |
| 2026-06-13 | P6-ISS-001 → done (commit `6e6b1cc`) |
| 2026-06-13 | P6-ISS-001 opened — `NullObservability.merge_model_roles` wrong return type found during P6-001 deep-check |
| 2026-06-13 | Created at Phase 6 planning session |
