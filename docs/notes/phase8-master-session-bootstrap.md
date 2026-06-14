# Phase 8 master session bootstrap

**Created:** 2026-06-13
**Purpose:** Context, open design questions, and interception strategy notes for the Phase 8 master session. Keep live until decisions are locked in PHASE8_MVP.md.
**Status:** Active — scope locked at high level; interception approach TBD.
**Authoritative PM docs:** PHASE8_MVP.md (to be created) · PHASE8_ISSUES.md (to be created)
**Design ideas (read before planning):**
- [AGENTIC_LOOP_LOGGING.md](../OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md) — long-horizon product; Phase 8 builds the capture substrate it requires
- [REASONING_TRACE_REUSE.md](../OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md) — thinking tokens are highest-value Phase 8 capture item
**Related backlog:** BL-371, BL-369, BL-370, BL-367 (Phase 9 target), BL-350 (remainder), BL-357
**Phase 7 exit (frozen):** [phase7-master-session-bootstrap.md](./phase7-master-session-bootstrap.md)

---

## Why Phase 8 — the ROI case

Phase 7 shipped a clean capture boundary for owned paths:
- All owned helper LLM calls route through `LlmGateway` (`core/observability/gateway.py`)
- Executor outer-loop events: `llm_call`, `tool_call`, `action` per step
- Compile provenance bundle: all 8 `compile_event` stages in the same JSONL

**What you still cannot see after Phase 7:**

| Gap | Why it matters |
|-----|----------------|
| Aider-internal LLM sub-calls | Aider's loop may call the model 3–10× per delegation (multi-turn, lint retry, token budget probes). You see the outer delegation event but not each sub-call. |
| Thinking tokens inside Aider | Extended thinking (Claude, o-series) produces a reasoning trace that is the most valuable training signal. Currently lost inside Aider's opaque litellm calls. |
| Aider retries / tool-call sub-turns | Within a single executor "step", Aider may make multiple LLM round-trips (tool call → response → tool call). Only the net result surfaces to Phase 7's outer loop. |
| Future backends (OpenCode, etc.) | Any new backend adapter added without explicit interception will have zero inner-turn visibility from day one. |
| Attribution (which step owns which sub-call) | Even when Route A callback fires for Aider sub-calls, we cannot reliably infer which outer executor step they belong to. |

Phase 8 closes these gaps — **passive full-fidelity capture**. Zero intervention, zero control.

**What Phase 8 is NOT:**

- Not active supervision (injecting context between turns) — that is **BL-351, Phase 9+**
- Not `yes=True` replacement — Phase 9+
- Not write-always storage / replay CLI — those require this Phase first → **Phase 9** (BL-367)
- Not curation, novelty filter, training export — AGENTIC_LOOP_LOGGING months 2+

---

## Phase 8 exit acceptance

After Phase 8, this statement must be true:

> For every LLM call in any path through mcp-coder — owned helper, executor outer loop, Aider sub-calls, future backends — there is a **known, tested interception point** in `core/observability/`. Thinking tokens are captured. Attribution (delegation_id, step_index) is present on every event.

Phase 9 then flips the write gate (write-always) without needing new capture infrastructure.

---

## Scope decisions locked (2026-06-13 brainstorm)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Phase 8 = capture/visibility only | ✓ | Control (BL-351) cannot be built on a partial view; see Phase 9 |
| Write-always storage deferred | Phase 9 | Need the capture substrate complete before claiming "100%" at storage layer |
| Thinking tokens are P8 scope | ✓ | Highest-value signal; requires deep interception to preserve |
| Backend interception contract | Phase 8 must define it | Any future backend added without a contract = immediate blind spot |

---

## Locked phase sequencing (2026-06-13)

```
Phase 7  (done): LlmGateway (owned paths) + executor outer loop + compile events
Phase 8  (next): Aider full interception — subclass Model.send_completion(), thinking tokens,
                 backend interception contract
Phase 9         : Write-always storage + context blobs + replay CLI
                 ("100% log" claim is now honest because Phase 8 closed Aider capture gaps)
Phase 10+       : HTTP proxy for Claude Code / Codex / OpenCode
                 + inner loop control (BL-351 — supervisor, pause, inject)
                 + additional backends as they become relevant
```

**Why this order:**
- Phase 8 closes the Aider observation gap → Phase 9 can claim "100% captured" for the primary backend without caveats
- Phase 9 flips the write gate → all captured data is now durably stored, replayable from disk
- Phase 10+ adds proxy for non-Python backends + control story (BL-351) — both require the storage substrate Phase 9 provides

**What Phase 8 does NOT include:**
- Write-always storage (Phase 9) — capture completeness comes first
- HTTP proxy for other backends (Phase 10+) — Aider is primary backend today
- Inner loop control / BL-351 (Phase 10+) — visibility before intervention

---

## Milestone sketch (Phase 8)

| ID | Milestone | Backlog |
|----|-----------|---------|
| **P8-001** | Aider inner-loop interception — capture every sub-call with attribution and thinking tokens | BL-371 |
| **P8-002** | Backend adapter interception contract — per-adapter matrix; standard interface any new backend must implement | BL-371 |
| **P8-003** | CLI gateway bootstrap hardening (BL-369) — centralize `LlmGateway` init; remove per-command self-heal branches | BL-369 |
| **P8-004** | Host transcript byte-range provenance — extend compile events with `byte_start`/`byte_end` for replay-fidelity | BL-370 |
| **P8-005** *(optional)* | Extend P7-002 executor continuation — richer multi-step retry policy (less conservative break-on-failure) | BL-350 remainder |

---

## Open design question: interception approach for P8-001

Full analysis of all four approaches with pros/cons, comparison table, and recommended sequencing lives in the standalone design note:

**→ [llm-interception-strategies.md](./llm-interception-strategies.md)**

**Summary of recommendation for Phase 8:**
- **P8-001 primary:** Approach 2 (monkey-patch `litellm.completion`) — closes Aider gap, thinking tokens guaranteed, opens Phase 9 control path
- **Approach 1** (Route A callback) stays as a complementary cross-check/fallback, not replaced
- **Approach 3** (own inner loop) and **Approach 4** (HTTP proxy) deferred to Phase 9+ when the control story justifies the engineering investment

---

## Open questions for master session

Interception-approach-specific questions live in [llm-interception-strategies.md](./llm-interception-strategies.md) § Open questions.

Phase 8 planning questions:

1. **Dogfood bar:** Does Phase 8 acceptance require a live delegation proving Aider sub-calls appear in the trace, or is a mocked-Aider unit test sufficient? Recommended: live dogfood (same pattern as Phase 7).

2. **Backend contract format:** For P8-002, does the interception contract live as a Python `@dataclass InterceptionProfile` per adapter, a documented JSON matrix, or a runtime-checked assertion in the adapter base class?

3. **Milestone ordering:** Should P8-003 (CLI bootstrap) + P8-004 (byte ranges) precede P8-001/002 as warm-up milestones, or run after?

4. **Route A retirement:** Once monkey-patch is in place, does the LiteLLM `success_callback` (Route A) become redundant for Aider? Or keep it as a cross-check / fallback?

---

## Confusion traps (Phase 8 worker rules)

- **Do not** modify `core/engine/aider_engine.py` for interception logic — interception lives in `core/observability/` only.
- **Do not** claim "100% capture" in Phase 8 docs — the correct claim is "known interception point for all current paths." Write-always + replay is Phase 9.
- **Route A** (litellm callback) and **Approach 2** (monkey-patch) are complementary, not alternatives — Route A stays for backward compat; Approach 2 supplements it for Aider sub-call attribution and thinking tokens.
- Thinking tokens must appear in the trace as a **separate field** (`thinking_tokens: int`, `thinking_text: str | null`) — not embedded in the response body string.

---

## Phase 8 → Phase 9 handoff

| Phase 8 delivers | Phase 9 requires |
|-----------------|-----------------|
| Known interception point for every LLM call | ✓ (remove write gate once capture is complete) |
| Thinking tokens in trace schema | ✓ (include in blob + replay) |
| Attribution (delegation_id, step_index) on every event | ✓ (replay can reconstruct turn-by-turn) |
| Backend adapter contract | ✓ (new backends can be verified before Phase 9 write-always) |
