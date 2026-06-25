<!--
  STEWARDSHIP — Phase 14 issues log. See docs/VISION_DOCS.md.

  - OK: log bugs found during implementation or audit, add workaround notes, mark fixed.
  - NOT OK: replan milestones or change locked decisions here; do that in PHASE14_MVP.md.
  - Workers: file issues here when found; fix in task spec § Results.
-->

# Phase 14 issues

**Status:** **Active** — Phase 14 opened 2026-06-23.
**Open:** P14-ISS-001, P14-ISS-002, P14-ISS-003, P14-ISS-005, P14-ISS-006, P14-ISS-007
**Closed:** P14-ISS-004, P14-ISS-008
**Related PM board:** [PHASE14_MVP.md](./PHASE14_MVP.md)

---

## Open implementation issues

| ID | Status | Severity | Summary | Milestone | BL | Notes |
|----|--------|----------|---------|-----------|-----|-------|
| P14-ISS-001 | open | structural | Executor `llm_call` summary event omits `reasoning_tokens` (different code path from helper) | P14-003 | BL-534 | `core/observability/trace.py::build_executor_llm_trace_record()` (lines 488-493) only copies `input/output/total` from `tokens`, never `reasoning_tokens`/`cached_tokens` — even though underlying `backend_llm_call` captured them (e.g. 4908 + 344 in dogfood run). Silent omission for executor role. Fix is structural: the executor summary is built from a different code path that doesn't receive the reasoning count. Filed by P14-003 worker. |
| P14-ISS-002 | open | structural | Helper `llm_call` events silently omit `reasoning_tokens` when provider returns none (no `reasoning_unavailable` reason emitted) | P14-003 | BL-534 | `core/observability/trace.py::build_trace_record()` (lines 247-250) only adds `reasoning_tokens` when `not None`. When a reasoning-capable model chooses not to think on a trivial prompt, the field is silently absent. Spec 3c acceptance allows `reasoning_unavailable: "<reason>"` as escape hatch, but code never emits it. Should either always emit `reasoning_tokens: null` or add `reasoning_unavailable` when model is reasoning-capable family but returned none. Filed by P14-003 worker. |
| P14-ISS-003 | open | footgun | `AIDER_MODEL` silently overrides `MCP_CODER_MODEL` for executor | P14-003 | BL-536 | `resolve_role_model_name()` prefers `AIDER_MODEL` over `MCP_CODER_MODEL`. Documented in `docs/guide/env-vars.md` line 48 but a footgun for dogfood runs that set only `MCP_CODER_MODEL`. Worker's 3c run used DeepSeek-v4-pro instead of intended Gemini-flash because of this. Suggest: one-line `server_log_warn` when both set and differ (non-breaking). Not blocking 3c. Filed by P14-003 worker. |
| P14-ISS-005 | open | actionable | Executor path silently ignores `temperature`/`top_p`/`max_tokens` from `CallParams` | P14-003 | BL-536 | `_apply_executor_model_params()` (`core/engine/aider_engine.py` lines 112-152) applies `reasoning_effort`/`thinking_budget`/`extra_params`/`weak_model`/`system_prompt_prefix` but never applies `params.temperature`/`top_p`/`max_tokens` — Aider `Model` has no settable attrs for these. **Already documented** in `policy_applied()` `ignored` list + `note` (lines 335-345), so not silent at trace level, but a footgun: `MCP_CODER_EXECUTOR_TEMPERATURE=0.2` yields Aider default `0.0` with only a trace note. Suggest startup `server_log_warn` when executor `TEMPERATURE`/`TOP_P`/`MAX_TOKENS` env vars set but ignored. Also: `drop_params` diverges (helper `True`, executor litellm default `False`). Filed by P14-003 worker. |
| P14-ISS-006 | open | doc | Inconsistent reasoning param shape between helper and Aider paths | P14-003 | BL-534 | Helper path (`gateway.py`): top-level `reasoning_effort="high"`. Aider path: `extra_body={"reasoning":{"effort":"high"}}` (OpenRouter-native) or `extra_body={"reasoning_effort":"high"}` (non-OpenRouter). Both work dynamically. Aider's design, not our code — documentation-only. Filed by P14-003 worker. |
| P14-ISS-007 | open | robustness | Helper path has no explicit `timeout` or `num_retries` | P14-003 | BL-534 | `LlmGateway.complete()` never sets `timeout`/`num_retries` → litellm/provider defaults (typically 10-60s, 0 retries). Aider path sets `timeout=600`. Smoke confirmed long reasoning models can take 80-128s (GLM 4.6, DeepSeek-R1) — a helper call to such a model could exceed provider default timeout and raise with no retry. Suggest configurable `MCP_CODER_HELPER_TIMEOUT` (default ~300s) + `MCP_CODER_HELPER_NUM_RETRIES` (default ~2). Not blocking 3c. Filed by P14-003 worker. |
| P14-ISS-008 | fixed | structural | `_emit_llm_call_event` imported nonexistent `build_llm_call_record` (should be `build_trace_record`) — supervisor `llm_call(role=supervisor)` trace events were silently never emitted | P14-001 | BL-534 / BL-536 | `core/engine/supervisor.py::_emit_llm_call_event()` (lines ~287-320) imported `build_llm_call_record` from `core.observability.trace`, but that function does not exist — the correct name is `build_trace_record`. The swallowed `ImportError` meant no supervisor `llm_call` trace event was ever written for `confirm_ask` decisions. Two-line fix applied by P14-001 worker (import + call rename). Verified: supervisor trace events now emit. **Note for P14-004:** this is exactly the "best-effort writes that silently swallow errors" pattern the 4c cleanliness audit targets — the `except Exception: pass` in `_emit_llm_call_event` hid this for months. P14-004c should consider reducing silent-swallow surfaces or adding a counter. |

---

## Closed issues

| ID | Status | Summary | Resolution |
|----|--------|---------|------------|
| P14-ISS-004 | closed | `drop_params=True` vs OpenRouter passthrough — resolved (no gap) | Dynamic smoke with `extra_body={"reasoning":{"effort":"high"}}` (OpenRouter-native) + litellm-native `reasoning_effort='high'` both survive `drop_params=True` and return `reasoning_tokens` + text for Sonnet/GLM/DeepSeek-R1/Gemini. No passthrough gap. Filed-and-closed by P14-003 worker. |
| P14-ISS-008 | fixed | `_emit_llm_call_event` imported nonexistent `build_llm_call_record` → supervisor trace events silently never emitted | Two-line fix by P14-001 worker: import + call renamed to `build_trace_record`. Verified supervisor `llm_call` events now emit. Cross-linked BL-534/536. Notable for P14-004c (silent-swallow pattern). |

---

## Changelog

| Date | Event |
|------|-------|
| 2026-06-24 | **P14-002 worker returned** — no new P14-ISS filed. Plan was unambiguous and executed mechanically. Two slices shipped: autonomous `confirm_ask` interception (BL-547 v1) and reviewer findings injection (BL-543 C start). 17 new tests pass. One pre-existing unrelated failure noted by worker. |
| 2026-06-24 | **P14-001 worker returned** — filed + fixed P14-ISS-008 (`_emit_llm_call_event` imported nonexistent `build_llm_call_record`; supervisor trace events silently never emitted for months; two-line fix, verified). Cross-linked BL-534/536. Notable for P14-004c: this is exactly the "best-effort writes that silently swallow errors" pattern the 4c cleanliness audit targets — the `except Exception: pass` in `_emit_llm_call_event` hid the ImportError. |
| 2026-06-24 | **P14-003 worker returned** — filed P14-ISS-001..007. ISS-001 (executor trace omits reasoning_tokens, structural, BL-534); ISS-002 (helper silent omission, structural, BL-534); ISS-003 (`AIDER_MODEL` overrides `MCP_CODER_MODEL` footgun, BL-536); ISS-004 (drop_params passthrough — closed, no gap); ISS-005 (executor ignores temperature/top_p/max_tokens, actionable, BL-536); ISS-006 (inconsistent reasoning param shape, doc-only, BL-534); ISS-007 (helper path no timeout/retries, robustness, BL-534). All cross-linked to BL-534/536 at filing time per Q8 protocol. |
| 2026-06-23 | Phase 14 issues log opened. |
