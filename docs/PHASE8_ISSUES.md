<!--
  STEWARDSHIP — Phase 8 issue tracker. See docs/VISION_DOCS.md.

  - Workers: do not edit. Gaps found during implementation → open new P8-ISS-NNN rows here via master session.
  - New backlog items → BACKLOG BL-* via planning session.
-->

# Phase 8 issue tracker

**Status:** Active — master session complete 2026-06-13; workers pending.
**Purpose:** Gaps found during Phase 8 implementation and dogfood.
**Milestone board:** [PHASE8_MVP.md](./PHASE8_MVP.md)
**Phase 7 issues (frozen):** [PHASE7_ISSUES.md](./PHASE7_ISSUES.md)

Status: `open` | `done` | `wontfix` | `carried`

---

## Issues

| ID | Status | Priority | Title | Resolution |
|----|--------|----------|-------|------------|
| P8-ISS-001 | open | medium | `owned_completion.py` dead code — deferred from P7-ISS-002 | P7-ISS-002 noted this as cleanup for Phase 8. Delete or formally deprecate `owned_completion.py` now that `LlmGateway` is the canonical path. Handle in P8-001 scope. |
| P8-ISS-002 | open | high | Double-recording risk: Route A `success_callback` fires for Aider inner-loop calls AND `ObservableModel` will also fire — same root cause as P7-ISS-001 for helpers | P8-001 added `_backend_call_active` dedup guard and unit tests. **Still open until live dogfood:** verify streaming path does not clear dedup context too early (send_completion returns wrapper before stream exhaustion), causing Route A to re-emit `llm_call` duplicates in real runs. |
| P8-ISS-003 | open | medium | Streaming response capture: `send_completion()` returns a stream iterator when `stream=True` — full body not available until stream is exhausted | **Locked in P8-001 spec (D-P8-6):** transparent stream iterator wrapper — accumulate on exhaustion; do not require `--no-stream`. Worker must verify in tests + dogfood. |
| P8-ISS-004 | carried | low | Thinking token availability: need to verify litellm passes thinking blocks through to `ModelResponse` for all providers we use (Anthropic extended thinking, OpenRouter reasoning) | **Live dogfood status:** complex Sonnet run (`86fe232f-3bdd-4d04-a9e3-bdcbd3d8ce63`) produced no `thinking_text`/`thinking_tokens` fields on `backend_llm_call`. Not a Phase 8 blocker, but keep open as a follow-up check on a known thinking-enabled model/path and capture settings. |
| P8-ISS-005 | open | low | `aider_output_parse` token counting hack becomes redundant after P8-001 | Phase 6 shipped `aider_output_parse` to extract token counts from Aider's text output (a fragile hack). `ObservableModel` gives exact per-call tokens directly from the `ModelResponse`. Flag for deprecation in P8-001 or Phase 8 cleanup pass. |
| P8-ISS-006 | done | high | Live dogfood showed **zero** `backend_llm_call` events (A1 hard fail) | **Resolved by P8-001a.** `aider_engine` now submits `ctx.run` into threadpool (`copy_context` propagation). Re-dogfood delegation `70d63f1a-c7fc-4633-ac6d-dd3f2285e3f7` confirms `backend_llm_call` appears in trace with `call_type: executor_turn` and `step_index: 1`. |

---

## Observations

| Date | Finding |
|------|---------|
| 2026-06-14 | A5-focused complex dogfood delegation `86fe232f-3bdd-4d04-a9e3-bdcbd3d8ce63` confirms `backend_llm_call` capture on `openrouter/anthropic/claude-sonnet-4`, but no `thinking_text`/`thinking_tokens` fields were emitted. This is treated as provider/path behavior, not capture failure. |
| 2026-06-14 | Joint dogfood delegation `334072d7-2a19-46a2-853b-7a12dc481f3f` (model `openrouter/anthropic/claude-sonnet-4`) confirms `backend_llm_call` capture remains live after P8-001a (`call_type: executor_turn`, `step_index: 1`). `maintenance stats --verbose` prints Aider interception profile as expected (P8-002 validation). |
| 2026-06-14 | Live dogfood delegation `dda44d00-d18e-44db-b82b-2a5b816dec9c` (workspace `mcp_coder_phase1_e2e`) produced **no** `backend_llm_call` events. Trace counts: `trace_header=1`, `action=1`, `llm_call=1`, `tool_call=2`, `compile_event=1`. Confirmed P8-ISS-006 root issue. |
| 2026-06-14 | Re-dogfood delegation `70d63f1a-c7fc-4633-ac6d-dd3f2285e3f7` after P8-001a fix: trace now includes `backend_llm_call` (`call_type: executor_turn`, `step_index: 1`) plus expected outer-loop `llm_call`/`tool_call` events. P8-ISS-006 closed. |
| 2026-06-13 | Master session: Aider audit complete — `litellm.completion()` has exactly two call sites: `Model.send_completion()` (all real LLM turns, verified at `models.py:1021`) and `warm_cache_worker` (background cache pings, `max_tokens=1`, at `base_coder.py:1373`). All providers (OpenRouter, Anthropic, Gemini, Bedrock, Copilot) route through `send_completion()` — litellm is Aider's universal adapter. See notes/llm-interception-strategies.md § Per-backend audit. |
| 2026-06-13 | Master session: Approach locked as D-P8-1 — subclass `Model.send_completion()` (2a). All other interception strategies (monkey-patch, sys.modules, package substitution, HTTP proxy) documented in notes/llm-interception-strategies.md with pros/cons for future phases. HTTP proxy confirmed as Phase 10+ approach for Claude Code / Codex / OpenCode. |
| 2026-06-13 | Master session: Phase sequencing locked — Phase 8 = Aider capture; Phase 9 = write-always storage + replay; Phase 10+ = HTTP proxy for other backends + inner loop control (BL-351). Phase 9 "100% capture" claim is only honest after Phase 8 closes Aider inner-loop gaps. |
| 2026-06-13 | Master session: Other backend architectures audited — Claude Code (TypeScript, Anthropic SDK, `ANTHROPIC_BASE_URL` proxy), Codex (Rust, `/v1/responses` API, has own `codex-responses-api-proxy` crate), OpenCode (Bun/TS, plugin system, custom provider base URL). All support HTTP proxy via base URL config — universal Phase 10+ strategy. Hook systems across all three are for tool execution, not LLM call capture. |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-14 | P8-ISS-004 set to `carried` (follow-up): Sonnet/OpenRouter dogfood did not expose reasoning fields; revisit with known thinking-enabled model/path so this signal is not lost. |
| 2026-06-14 | Joint dogfood + CLI validation confirms P8-002 acceptance (`maintenance stats --verbose` shows interception profile block). |
| 2026-06-14 | P8-ISS-006 closed after P8-001a + re-dogfood success (`70d63f1a-c7fc-4633-ac6d-dd3f2285e3f7`). |
| 2026-06-14 | P8-001a hotfix delivered for P8-ISS-006: `aider_engine` now uses `ctx = copy_context(); pool.submit(ctx.run, _run_coder)`. Added regression tests (`test_context_propagation_p8_001a.py`) and full suite pass (792 passed, 1 skipped). Keep P8-ISS-006 open until live re-dogfood confirms `backend_llm_call` events appear. |
| 2026-06-14 | P8-ISS-006 opened after live dogfood hard-fail (no `backend_llm_call` events). P8-001 remains open pending context propagation fix + re-dogfood. |
| 2026-06-14 | P8-001 worker implementation landed with unit pass + full suite pass. P8-ISS-002 remains open pending live streaming dedup verification; P8-ISS-004 remains open pending live thinking-token verification. |
| 2026-06-13 | Created — Phase 8 issue tracker; P8-ISS-001 (owned_completion cleanup carry), P8-ISS-002 (double-recording dedup guard — **critical for P8-001 correctness**), P8-ISS-003 (streaming capture), P8-ISS-004 (thinking token availability), P8-ISS-005 (aider_output_parse deprecation) opened at master session |
