# Phase 9 issues

**Status:** **Frozen** — Phase 9 closed 2026-06-17. No open issues; remaining items deferred to backlog.  
**Open:** none  
**Deferred:** P9-ISS-007 → **BL-517** → **Phase 10 P10-004**; P9-014 → **BL-516** → **Phase 10 P10-004** (partial); runtime log-level DX → **BL-518** → **Phase 10 P10-004** (partial); proxy env toggle → **BL-519** → **Phase 10 P10-004**  
**Closed:** `P9-ISS-001`..`P9-ISS-006`, `P9-ISS-008`..`P9-ISS-010`. `P9-OBS-001` promoted to **P9-011 + P9-012**, both **done** (full suite `924 passed, 2 skipped`) — see below.  
**Related PM board:** [PHASE9_MVP.md](./PHASE9_MVP.md) (frozen)
**Viewer milestone disposition:** **P9-013 done** (shipped as v2 boundary viewer architecture) and **P9-015 superseded** (pipeline cards intentionally not continued).

---

## P9-OBS-001 → P9-011 + P9-012 — No model registry; LLM request parameters hardcoded / unset per call site

**Type:** Dogfood observation → promoted to active milestones  
**Milestones:** P9-011 ([spec](../tasks/P9-011-model-policy-layer-v1.md)) + P9-012 ([spec](../tasks/P9-012-generation-params-logging-v1.md))  
**Severity:** high — proxy captures are uninformative until we can actually send thinking tokens  
**Status:** done — P9-011 + P9-012 shipped 2026-06-16 (helper paths unified onto `LlmGateway`; generation params + weak-model default-fill resolve per role; `policy_applied` on every `backend_llm_call`/`llm_call`)  
**Opened:** 2026-06-16 (Phase 9 post-completion dogfood)  
**Promoted:** 2026-06-16 — needed now, not Phase 10; **split into P9-011 (refactor) + P9-012 (params + logging) after code review**  
**Design note:** [docs/notes/model-policy-layer.md](notes/model-policy-layer.md)

### Summary

Phase 9 dogfooding confirmed that `proxy_llm_call.raw_request` contains no `thinking` field for any LLM call path. This is because the executor, owned helpers, and legacy helpers each construct request parameters independently with no shared policy — thinking budget, max tokens, and temperature are hardcoded (or absent) at each call site.

Three separate paths exist:
- **Executor path** — `AiderEngine` → `ObservableModel` (Aider `Model` + litellm)
- **Owned-helper path** — `run_owned_helper_completion` → `LlmGateway` → direct `litellm.completion`
- **Legacy-helper path** — `aider.models.Model` directly (`workspace_summarizer_llm.py`, `spec_review.py`)

### Why it was promoted to Phase 9

Phase 9 built the proxy to capture raw HTTP traffic. But if nothing interesting is being sent (no thinking tokens, no per-role parameter control), the capture infrastructure cannot be used to verify anything meaningful. P9-012 closes the loop: once params are wired, adding `MCP_CODER_EXECUTOR_REASONING_EFFORT=high` to `.env` makes `proxy_llm_call.raw_request` show a `thinking` block — which directly resolves BL-507.

### Resolution (split after 2026-06-16 code review)

A code-grounded review found model ID + budget already centralized in `role_models.py`, and that the "legacy-helper path" bypasses `LlmGateway` and emits no `llm_call` event. Resolution split into two milestones:

- **P9-011** — remove the legacy direct-`Model()` helper calls (route `workspace_summarizer` + `spec_review` through `LlmGateway`); add `core/config/model_registry.py` front door (`resolve(role, workspace) → CallParams`) reusing `role_models` for id/budget. Refactor + skeleton.
- **P9-012** — generation-param env vars, weak-model resolution (default-fill + override), wire `model.extra_params` (executor) + litellm kwargs (gateway), attach `policy_applied` (with per-field `sources`) to `backend_llm_call` + `llm_call`.

Escalation hooks (model/thinking bump after N retries) are deferred to Stage 4 (BL-514); model tiers to BL-515.

---

## P9-ISS-001 — P9-001 AC#8 not yet met (legacy test expectations)

**Milestone:** P9-001  
**Severity:** medium  
**Status:** closed  
**Opened:** 2026-06-15
**Closed:** 2026-06-15

### Summary

P9-001 write-always behavior was implemented in `core/observability/trace.py`, and
direct milestone tests were updated. Full suite still failed because 4 additional
tests in other files assert the old verbosity-gated trace contract (no bodies at
lean/standard).

### Evidence (from worker report)

- Targeted test run: `7 passed in 0.28s` (`tests/test_observability_traces.py`)
- Full suite: `813 passed, 1 skipped, 4 failed in 29.27s`
- Failing tests:
  - `tests/test_compile_provenance_p7_003.py::test_build_compile_event_record_lean_hash_only`
  - `tests/test_compile_provenance_p7_003.py::test_build_compile_event_record_standard_includes_brief`
  - `tests/test_executor_loop_p7_002.py::test_build_executor_llm_trace_record_standard_has_preview`
  - `tests/test_observable_model_p8_001.py::test_build_backend_llm_call_record_standard_preview_truncated`

### Impact

- Functional write-always behavior appears correct.
- Milestone acceptance criterion AC#8 ("full suite green") is not yet satisfied.
- Phase 9 minimum exit depends on P9-001 being complete; this issue must be closed first.

### Decision / next action

Run a small follow-up worker pass (P9-001a) to update legacy assertions in the 4
failing tests to the new write-always contract:

- bodies always present (all verbosity tiers)
- previews present at `standard`+ only
- `brief` remains `standard`+ for compile events

No production code changes expected; test-only alignment unless mismatch is found.

### Resolution

P9-001a completed with assertion-only updates in:
- `tests/test_compile_provenance_p7_003.py`
- `tests/test_executor_loop_p7_002.py`
- `tests/test_observable_model_p8_001.py`

No production code changes were required. Full suite is now green:
- `817 passed, 1 skipped in 32.83s`

### Exit criteria for this issue

1. All 4 failing tests updated (or equivalent test contract fix). ✅
2. Full suite green. ✅
3. P9-001 status moved from `partial_done` to `done` in `PHASE9_MVP.md`. ✅

---

## P9-ISS-002 — P9-003 dogfood dual-capture gate not met (backend side missing)

**Milestone:** P9-003  
**Severity:** high  
**Status:** closed  
**Opened:** 2026-06-15  
**Closed:** 2026-06-15

### Summary

Required live dogfood run in `mcp_coder_phase1_e2e` did not meet the P9-003 gate.
Proxy capture is present and attributed, but `backend_llm_call` was absent for the
same delegation trace.

### Evidence (master run)

- Delegation IDs tested:
  - `58cfc3cf-2614-4940-87d7-c26f045bf5cb`
  - `d819130c-8e00-44fe-9197-b3915f06dbbf`
  - `54dd1b23-cb42-4029-bc11-1d4adb00e0b8`
- Latest trace (`54dd1b23-...`):
  - `proxy_llm_call`: 1
  - `backend_llm_call`: 0
  - Proxy attribution present (`delegation_id`, `step_index=1`, `call_index=1`)
  - `raw_response` present
  - HTTP status: `400`
- Error surfaced in delegation output:
  - `OpenrouterException - {"error":"missing API key env ANTHROPIC_API_KEY"}`

### Impact

- P9-003 AC#1/#2/#4/#5 are partially evidenced via proxy path.
- P9-003 AC#3 (dual-capture analyzable in same delegation) is not met in live dogfood.
- Cannot mark P9-003 done until one successful live delegation shows both event types.

### Hypotheses to validate

1. Routing mismatch: proxied model resolves to `anthropic/*` route in runtime, requiring
   `ANTHROPIC_API_KEY`, while environment/operator expectation was OpenRouter path.
2. Model override path not taking effect in this dogfood environment (delegations continued
   to use `openrouter/anthropic/claude-sonnet-4` despite attempted override).
3. Backend event absence is a consequence of upstream 400 before `ObservableModel` completes.

### Decision / next action

Run a focused follow-up worker pass to:
- verify routing/model normalization behavior at runtime,
- document the exact env/model requirements for successful dogfood in this workspace,
- and produce one passing live delegation with both `proxy_llm_call` and `backend_llm_call`.

If code change is required, keep it minimal and scoped to routing/bootstrap/model resolution.

### Progress update (2026-06-15)

**P9-003a (env bootstrap):** `main.py` now calls `_bootstrap_cli_env()` before `main_delegate` on all paths. Full suite `841 passed`.

**P9-003b (routing fallback):** `resolve_route` falls back to OpenRouter when provider-specific key is absent but `OPENROUTER_API_KEY` is present (litellm canonicalizes `openrouter/anthropic/X` → `anthropic/X` before HTTP, so proxy sees `anthropic/` prefix even for OR-routed models). Full suite `847 passed`.

**Live evidence (delegation `81642ee4`, 2026-06-15):**
- No `ANTHROPIC_API_KEY` error — proxy routes to OpenRouter correctly
- 9 × `proxy_llm_call` in trace: `attribution_source: "headers"`, `delegation_id` non-null, `step_index=1`, `call_index 1–9`, `raw_response` non-empty
- 1 × `llm_call` (executor role) — Aider executor record
- **Still missing:** `backend_llm_call` — `ObservableModel` completion event only fires on successful upstream response; 402 aborts retry loop before callback emits
- **Root cause of 402:** OpenRouter account has ~54k credits; `claude-sonnet-4` requests up to 64k `max_tokens` — not a code issue

**Remaining gate:** Add OR credits and re-run dogfood. All code-side requirements are met.

### Exit criteria for this issue

1. One live delegation in `mcp_coder_phase1_e2e` has both `proxy_llm_call` and `backend_llm_call`.
2. Same trace shows non-empty `proxy_llm_call.raw_response`.
3. At least one `proxy_llm_call` has non-null `delegation_id` and `step_index`.
4. P9-003 status updated on `PHASE9_MVP.md`.

**All criteria met.** Delegation `dfe975e7-b30a-4f59-9410-7f18041e2782` (2026-06-15):
- `proxy_llm_call`: `status_code: 200`, `attribution_source: "headers"`, `delegation_id` non-null, `step_index: 1`, `call_index: 1`, `wire_latency_ms: 1993`, `raw_request`/`raw_response` present ✅
- `backend_llm_call`: `call_type: executor_turn`, `usage: {input:2789, output:107}`, `prompt_body` + `response_body` present ✅
- Both in the same trace file ✅
- P9-003 marked `done` on PHASE9_MVP.md ✅


---

## P9-ISS-003 — P9-006 compare CLI crashes on valid dual-capture delegation

**Milestone:** P9-006  
**Severity:** high  
**Status:** closed  
**Opened:** 2026-06-15  
**Closed:** 2026-06-15

### Summary

`mcp-coder compare` crashes with `AttributeError` on a known valid dual-capture delegation (`dfe975e7-...`) during master dogfood validation, so P9-006 AC#1 is not met.

### Evidence (master run)

- Command:
  - `mcp-coder compare dfe975e7-b30a-4f59-9410-7f18041e2782 --workspace ~/Dropbox/CodingProjects/personal_tools/mcp_coder_phase1_e2e`
- Observed failure:
  - `AttributeError: 'NoneType' object has no attribute 'get'`
  - stack points to `core/cli/compare.py`:
    - `_call_index(event)` called with `event=None`
    - from `pair_dual_capture_events()` row assembly line:
      `(_call_index(proxy) or _call_index(backend))`
- Unknown-id behavior still correct:
  - `mcp-coder compare unknown-delegation-id ...` exits `1` with clear message.

### Root cause

In `pair_dual_capture_events()`, row creation unconditionally calls `_call_index(proxy)` and `_call_index(backend)` even when either side is absent (`proxy_only` / `backend_only` pairing path), causing `NoneType` crash.

### Impact

- Compare command is not usable on real dual-capture traces.
- Viewer enrich path may be at risk because it shares pairing helper.
- P9-006 cannot be marked done until runtime dogfood passes.

### Resolution

Applied minimal null-safety fix: `_call_index(event)` now accepts `None` and returns `None` early instead of crashing on `.get()`. Added regression test `test_compare_fallback_backend_only_missing_call_index_no_crash`. Live compare on `dfe975e7` runs successfully (exit 0); null `call_index` rows render correctly in both human and JSON output. P9-ISS-003 closed.

**Dogfood finding:** The live trace for `dfe975e7` yields `proxy_only + backend_only` (not `matched`) because `backend_llm_call` emitted via litellm callback carries no `call_index` while `proxy_llm_call` carries one from header injection. This is honest Phase 9 evidence — the attribution gap is visible and attributable. Flagged for BL-507 analysis follow-up.

### Next action (was)

~~Run a minimal follow-up fix (P9-006a):~~

1. Make `_call_index(...)` / row assembly null-safe.
2. Add regression test that reproduces this exact crash path and asserts no exception.
3. Re-run focused tests + live dogfood compare on `dfe975e7`.

### Exit criteria for this issue

1. `mcp-coder compare dfe975e7-b30a-4f59-9410-7f18041e2782 ...` exits `0` and prints comparison output.
2. JSON mode works on same delegation (`--format json`).
3. Unknown-id behavior remains exit `1`.
4. Focused compare/viewer tests green, including regression for null-side pairing.
5. P9-006 status updated on `PHASE9_MVP.md` only after live validation passes.

---

## P9-ISS-004 — `backend_llm_call` events carry `call_index: null` — compare can't pair with `proxy_llm_call`

**Milestone:** P9-007  
**Severity:** high  
**Status:** closed  
**Opened:** 2026-06-15  
**Closed:** 2026-06-15

### Summary

`mcp-coder compare` shows all Aider inner-loop calls as `proxy_only + backend_only` instead of `matched`. Both event types are present and correct — the join is broken because `backend_llm_call.call_index` is always `null`.

### Root cause

`ObservableModel._inject_attribution_headers()` increments `self._call_index` (1, 2, 3…) and writes it to the `X-Mcp-Call-Index` request header. The proxy reads this header and stores it on `proxy_llm_call.call_index`. But `_record_backend_call()` — called immediately after — never reads `self._call_index` and never passes it to `record_backend_llm_call()`. The slot already exists in the schema (`call_index: int | None = None` in `base.py`, `local.py`, `trace.py`). It is a pure wiring gap.

Same problem on the streaming path: `_StreamCaptureWrapper._finalize()` calls `_record_backend_call()` without `call_index`.

### Evidence

Live compare on delegation `dfe975e7`:
```
proxy_only  step=1 call=1   model=anthropic/claude-sonnet-4
backend_only step=1 call=None model=openrouter/anthropic/claude-sonnet-4
```
Both are the same call. The proxy has `call_index=1` from the header; the backend record has `call_index=None`.

### Fix (for P9-007)

In `core/engine/observable_model.py`:
1. Add `call_index: int | None = None` param to `_record_backend_call()` and pass it through to `record_backend_llm_call()`.
2. In `ObservableModel.send_completion()`: after `_inject_attribution_headers()`, capture `_ci = self._call_index`. Pass `call_index=_ci` to both `_record_backend_call()` (non-streaming) and `_StreamCaptureWrapper(call_index=_ci, ...)`.
3. In `_StreamCaptureWrapper`: store `call_index`, pass to `_record_backend_call()` in `_finalize()`.

No schema changes needed.

### Exit criteria

1. `backend_llm_call` events in trace have non-null `call_index` matching Aider turn order (1, 2, 3…).
2. `mcp-coder compare <id>` shows `matched` rows for inner-loop calls.
3. Regression tests for both streaming and non-streaming paths.
4. Full suite green.

### Resolution

Worker implemented minimal wiring in `core/engine/observable_model.py`:
- `_record_backend_call()` now accepts `call_index: int | None = None`
- `send_completion()` captures `_ci` after header injection and passes it in both paths
- `_StreamCaptureWrapper` now accepts/stores `call_index` and forwards it in `_finalize()`

Regression coverage updated in `tests/test_observable_model_p8_001.py`:
- non-streaming call records `call_index=1`
- streaming finalize records `call_index=1`
- sequential calls increment (`1,2,3`) on the same model instance

Reported validation:
- Focused: `pytest -q tests/test_observable_model_p8_001.py` → `16 passed`
- Full suite: `pytest -q` → `877 passed, 1 skipped`

---

## P9-ISS-005 — `prompt_full` in `delegations.jsonl` still gated by `MCP_CODER_LOG_FULL_PROMPT` env var (BL-510)

**Milestone:** P9-008  
**Severity:** medium  
**Status:** closed  
**Opened:** 2026-06-15  
**Closed:** 2026-06-15

### Summary

`build_delegation_record()` in `core/logging/delegation_log.py` line 223 still checks `should_log_full_prompt()` before writing `prompt_full` to the delegation row. This is the only remaining runtime write gate on audit data, violating D-P9-8 (write-always). The trace file already has the full prompt body (P9-001), but the delegation row convenience field is inconsistent.

### Root cause

```python
# delegation_log.py line 223
if prompt_full is not None and should_log_full_prompt():
    record["context"]["prompt_full"] = prompt_full
```

`should_log_full_prompt()` returns `True` only when `MCP_CODER_LOG_FULL_PROMPT=1`. Without it, `prompt_full` is silently dropped from the row even when the caller provides a value.

### Impact

- Delegation rows written without `prompt_full` can't be used for inline audit without opening the trace file separately.
- The data isn't lost (it's in the trace), but the row schema is inconsistent with D-P9-8.
- `mcp-coder replay` already loads from the trace, so this is UX polish — not a data correctness issue.

### Fix (for P9-008)

In `core/logging/delegation_log.py`:
- Change `if prompt_full is not None and should_log_full_prompt():` → `if prompt_full is not None:`
- Deprecate `should_log_full_prompt()` (keep as no-op stub returning `True`, or remove if no external callers)

Check `core/observability/base.py` + `local.py` + `null.py` for any abstract `should_log_full_prompt` method and remove it.

Update tests that assert `prompt_full` is absent without the env var.

### Exit criteria

1. `prompt_full` written to delegation row unconditionally when caller provides it.
2. `MCP_CODER_LOG_FULL_PROMPT` documented as deprecated / ignored.
3. `should_log_full_prompt()` removed or demoted to no-op stub.
4. Tests updated. Full suite green.

### Resolution

Worker implemented P9-008 within scoped files:
- `server/mcp_server.py`
  - removed outer `prompt_full` gate (`obs.should_log_full_prompt()`)
  - now always passes `prompt_full=executor_prompt`
- `core/logging/delegation_log.py`
  - removed inner `prompt_full` gate (`and should_log_full_prompt()`)
  - `prompt_full` now written whenever non-null
  - retained `should_log_full_prompt()` as deprecated no-op returning `True`
- `core/observability/base.py`, `core/observability/local.py`, `core/observability/null.py`
  - removed obsolete `should_log_full_prompt` abstraction/implementations
- `core/logging/__init__.py`
  - removed `should_log_full_prompt` re-export
- tests updated:
  - `tests/test_host_cursor.py`
  - `tests/test_spec_delegate.py`
  - removed env-var dependency for prompt_full assertions

Reported validation:
- Focused: `pytest -q tests/test_host_cursor.py tests/test_spec_delegate.py` → `21 passed`
- Full suite: `pytest -q` → `887 passed, 1 skipped`

---

## P9-ISS-006 — `proxy_llm_call.raw_response` is gzip-corrupted — BL-507 finding uncertain

**Milestone:** P9-009  
**Severity:** critical  
**Status:** closed  
**Opened:** 2026-06-15  
**Closed:** 2026-06-15

### Summary

Every `proxy_llm_call` event in traces has an unreadable `raw_response` field. The proxy captures gzip-compressed HTTP response bodies and stores them as UTF-8-decoded strings with replacement characters. The content is irrecoverably corrupted — the data written to disk cannot be decompressed.

### Root cause

`core/proxy/local_proxy.py` does not set `Accept-Encoding: identity` on outgoing upstream requests. OpenRouter (and likely other providers) return gzip-compressed responses by default. The proxy then calls:

```python
raw_response = body_bytes.decode("utf-8", errors="replace")
```

Gzip byte `0x8b` is not valid UTF-8 and is replaced with `U+FFFD`. The original bytes are discarded. The stored string is undecodable back to the original binary.

**litellm is not affected** — the proxy forwards the original compressed bytes and the original `Content-Encoding: gzip` header, so litellm decompresses correctly. Only the trace record is corrupted.

### Evidence

Inspection of delegation `dfe975e7`:
- `proxy_llm_call.status_code: 200` — delegation succeeded
- `proxy_llm_call.raw_response` first 4 chars: `ords=[31, 65533, 8, 0]` — second byte is `U+FFFD` (replacement), confirming gzip byte `0x8b` was corrupted
- `backend_llm_call.response_body` is clean (litellm decompressed correctly)

### Impact

1. **`raw_response` is unreadable for all existing traces** where the provider returned gzip — data is permanently lost in those records.
2. **BL-507 finding is uncertain**: we declared "thinking tokens NOT present at HTTP boundary" based on `compare` output, but `proxy_thinking=False` was derived from a corrupted `raw_response`. The actual HTTP response content has never been readable.
3. **Dual-path analysis is blocked**: the primary value of the proxy is inspecting the raw response before litellm normalization — this is currently impossible.

### Fix (P9-009)

In `core/proxy/local_proxy.py`, in `_forward_headers()` (or the request-building block): add `"Accept-Encoding": "identity"` to the forwarded headers unconditionally. This instructs providers to send uncompressed responses. The proxy is localhost, so bandwidth is irrelevant.

After the fix: all new traces will have readable `raw_response`. Existing corrupted traces cannot be recovered — fresh delegations needed for BL-507 re-verification.

### BL-507 re-verification required

After P9-009 ships: run a fresh delegation with `claude-sonnet-4` (or any thinking-enabled model) and inspect `proxy_llm_call.raw_response` directly. The `raw_request` includes `"thinking": {"type": "enabled", "budget_tokens": N}` if Aider passes budget params. Check if `raw_response` contains a thinking block before litellm strips it.

### Exit criteria

1. `proxy_llm_call.raw_response` in a fresh trace is readable JSON text.
2. Non-streaming and streaming (SSE) paths both verified.
3. BL-507 re-verified: `raw_response` inspected for thinking block presence/absence.
4. Full suite green.

### Resolution

Worker implemented P9-009 exactly within scoped files:
- `core/proxy/local_proxy.py`
  - `_forward_headers()` now strips incoming `accept-encoding`
  - always injects `forwarded["Accept-Encoding"] = "identity"`
- `tests/test_proxy_routing_p9_003.py`
  - added `test_forward_headers_strips_accept_encoding`
  - added `test_forward_headers_overrides_client_gzip`
  - added `test_forward_headers_no_accept_encoding_in_input`

Reported validation:
- Focused tests: `pytest -q tests/test_proxy_routing_p9_003.py tests/test_proxy_local_p9_003.py` → `19 passed`
- Full suite: `pytest -q` → `876 passed, 1 skipped`

Outcome:
- New traces should store readable UTF-8 `proxy_llm_call.raw_response` instead of gzip-corrupted replacement text.
- Existing historical corrupted traces remain irrecoverable and should not be used for BL-507 conclusions.

---

## P9-ISS-008 — Proxy routing: `google/*` models get 400 — Gemini helpers silently fail

**Type:** Bug — proxy routing gap  
**Severity:** critical — all Gemini helper LLMs (spec_validation, architect_pass, context_builder, workspace_summarizer) returned `BadRequestError 400` on every call; delegation proceeded with mechanical-only briefs  
**Status:** closed  
**Opened:** 2026-06-17 (A-to-Z dogfood session 1)  
**Closed:** 2026-06-17

### Root cause

litellm strips the `openrouter/` prefix before forwarding to the proxy. A model configured as `openrouter/google/gemini-2.5-flash` arrives at the proxy as `google/gemini-2.5-flash`. `resolve_route()` in `core/proxy/routing.py` had explicit rules only for `openrouter/`, `anthropic/`, and `openai/` prefixes — no match for `google/*` → `RouteResolutionError: no route for model 'google/gemini-2.5-flash'` → litellm raises `BadRequestError`.

### Fix

Added a catch-all fallback at the end of `resolve_route()`: if no prefix rule matches but `OPENROUTER_API_KEY` is set, return the OpenRouter fallback route. Covers `google/*`, `meta-llama/*`, `mistralai/*` and any other provider litellm strips to a non-listed prefix. Updated `test_resolve_route_missing_prefix_raises` to assert it only raises when OPENROUTER_API_KEY is also absent; added `test_resolve_route_unknown_prefix_falls_back_to_openrouter`.

### Verification

Post-fix dogfood (session `42820299`, `f33fdbaf`): all `proxy_llm_call` events `status=200`; `llm_call` events present for all helper roles with token counts; `compile_event.brief` fields contain real LLM output.

---

## P9-ISS-009 — `backend_llm_call.usage` input/output tokens always null for streaming executor

**Type:** Observability gap — token counts missing from trace events  
**Severity:** medium — tokens available in `model_roles.executor.tokens` (from Aider stdout parse) but not in the per-turn trace event  
**Status:** closed  
**Opened:** 2026-06-17 (A-to-Z dogfood analysis)  
**Closed:** 2026-06-17

### Root cause

Aider calls litellm with `stream=True` by default. OpenRouter/Anthropic do not include a `usage` block in stream chunks unless explicitly requested. `_assemble_stream_response()` already collects the last chunk's `usage` attribute, but without `stream_options: {"include_usage": True}` in the request, no usage chunk is sent → `usage=None` → `build_backend_llm_call_record(usage=None)` → no `usage` field in the event.

### Fix

In `ObservableModel.send_completion()`, when `stream=True`, inject `stream_options: {"include_usage": True}` into `self.extra_params` before calling `super()`. This is a standard OpenAI parameter that litellm passes through to providers; OpenRouter applies it to all proxied models.

### Verification

Post-fix dogfood: `backend_llm_call.usage.input` and `.output` are populated (e.g. `inp=8630 out=10046`) and `thinking_tokens` also present (e.g. `think=3540`).

---

## P9-ISS-010 — `llm_call.policy_applied` null/absent on executor step events

**Type:** Observability gap — audit field missing  
**Severity:** low — `backend_llm_call` carried it correctly; `llm_call` for executor was missing the field  
**Status:** closed  
**Opened:** 2026-06-17 (A-to-Z dogfood analysis)  
**Closed:** 2026-06-17

### Root cause (two separate paths)

**Path A — litellm callback (`llm_call` via `_append_trace_for_completion`):** The async litellm callback fires after `aider_engine.py`'s `finally` block resets `model_policy_var` to None. So `model_policy_var.get()` returns None at callback time.

**Path B — P7-002 step event builder (`build_executor_llm_trace_record`):** Called in `_bounded_executor_loop` *after* `step_fn` returns (which is also after `model_policy_var` is reset). `build_executor_llm_trace_record` had no `policy_applied` parameter at all.

### Fix

**Path A:** In `_append_trace_for_completion`, when `model_policy_var.get()` is None but `workspace_var.get()` and `role` are available (which they must be for the trace write to succeed), re-derive the policy from `model_registry.resolve()` + `policy_applied()`. Policy is stable within a delegation (reads only env vars + config); re-derivation is cheap and correct.

**Path B:** Added `policy_applied: dict | None = None` parameter to `build_executor_llm_trace_record` in `trace.py`. In `_bounded_executor_loop` in `mcp_server.py`, resolve the executor policy once at loop entry (before any step runs) via `model_registry.resolve(ROLE_EXECUTOR, workspace)` and pass it to `build_executor_llm_trace_record` on every step.

### Verification

Final dogfood session `f33fdbaf`: all 6/6 executor `llm_call` events have `policy_applied` key present and populated with correct `role`, `model`, `reasoning_effort`, and `sources`.

---

## P9-ISS-007 — `policy_applied` misleading for executor-ignored params

**Type:** Logging correctness  
**Severity:** low — not a runtime bug, but `policy_applied` can imply a param was applied to Aider when it wasn't  
**Status:** deferred → **[BL-517](./BACKLOG.md#bl-517-executor-policy_applied-ignored-params)** → **Phase 10 P10-004** (migrated from open issue 2026-06-17)  
**Opened:** 2026-06-16 (post P9-012 review)

### Summary

`_apply_executor_model_params` applies four things to the aider `Model`: `reasoning_effort`, `thinking_budget`, `extra_params`, and `weak_model`. It does **not** apply `temperature`, `top_p`, or `max_tokens` — Aider owns those values internally.

However, if a user sets e.g. `MCP_CODER_EXECUTOR_TEMPERATURE=0.5`, `resolve("executor")` resolves it, and `policy_applied()` faithfully includes it in the trace:

```json
"policy_applied": {"role": "executor", "temperature": 0.5, "sources": {"temperature": "env"}}
```

This is misleading — the value was never passed to Aider. The log suggests it was applied.

### Resolution plan

Add an `"ignored"` key to `policy_applied` for the executor surface. In `_apply_executor_model_params`, collect field names that were resolved but not applicable, and include them in `policy_applied`:

```json
"policy_applied": {
  "role": "executor",
  "reasoning_effort": "high",
  "ignored": ["temperature", "top_p"],
  "note": "temperature/top_p/max_tokens are owned by Aider; use MCP_CODER_EXECUTOR_EXTRA_PARAMS to override",
  ...
}
```

Alternatively, filter them out of executor's `policy_applied` entirely (simpler, but loses the "you set it but it had no effect" signal).

### Workaround

For now, `temperature`/`top_p`/`max_tokens` on the executor can be forced via `MCP_CODER_EXECUTOR_EXTRA_PARAMS={"temperature": 0.5}` (passed directly into Aider's `extra_params` dict which litellm forwards). That **does** work; the registry env knobs for those fields on the executor currently do not.
