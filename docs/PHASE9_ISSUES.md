# Phase 9 issues

**Status:** Active — P9-ISS-004, P9-ISS-005 open  
**Related PM board:** [PHASE9_MVP.md](./PHASE9_MVP.md)

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
**Status:** open  
**Opened:** 2026-06-15

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

---

## P9-ISS-005 — `prompt_full` in `delegations.jsonl` still gated by `MCP_CODER_LOG_FULL_PROMPT` env var (BL-510)

**Milestone:** P9-008  
**Severity:** medium  
**Status:** open  
**Opened:** 2026-06-15

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
