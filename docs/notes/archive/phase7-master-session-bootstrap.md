# Phase 7 master session bootstrap

**Created:** 2026-06-13
**Purpose:** Context and open decisions for the Phase 7 master session. Freeze this file once design decisions are locked and recorded in PHASE7_MVP.md.
**Status:** Active — design decisions not yet locked.
**Authoritative PM docs:** [PHASE7_MVP.md](../../PHASE7_MVP.md) · [PHASE7_ISSUES.md](../../PHASE7_ISSUES.md)
**Design ideas (read before planning):**
- [AGENTIC_LOOP_LOGGING.md](../../OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md) — long-horizon product; Phase 7 is its prerequisite infrastructure
- [REASONING_TRACE_REUSE.md](../../OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md) — reasoning token capture; Phase 7 extends per-executor-turn
- [CONTEXT_AS_GIT.md](../../OTEHR_RELATED_IDEAS/CONTEXT_AS_GIT.md) — "stored context vs runtime context"; informs outer-loop design
**Related backlog:** BL-368, BL-350, BL-333, BL-353, BL-354, BL-351
**Phase 6 exit (frozen):** [phase6-master-session-bootstrap.md](./phase6-master-session-bootstrap.md)

---

## Why Phase 7 — the ROI case

Phase 6 shipped a clean observability substrate. After a delegation you now get:
- 3 helper `llm_call` lines in `traces/<id>.jsonl` (context_builder, architect_pass, spec_validation)
- Non-null `model_roles.*.tokens` for all 3 helper roles
- Lean JSONL (~3 KB per record vs 24 KB before)
- Reasoning hot buffer (session-scoped)
- Training opt-in tuple (opt-in)

**What you still cannot see after Phase 6:**

| Gap | Why it matters |
|-----|----------------|
| Executor LLM turns | The agent may call the model 5+ times per delegation (multi-turn edit loop, lint retry, tool confirm). You see none of it. |
| Executor non-LLM actions | File writes, shell calls, lint runs, auto-confirms (`yes=True`) — invisible to the trace. |
| Executor token costs | `model_roles.executor.tokens` comes from LiteLLM callback on a single call that doesn't reflect the full inner loop. Often wrong or aggregated badly. |
| Compile stage bodies | `builder_input`, `architect_output`, `final_executor_prompt` — what actually went into each stage is not in the trace; only outcome flags. |
| Per-executor-turn reasoning | Even if the model emits `reasoning_content`, Aider strips it before the callback fires for inner turns. |
| Two capture paths | Route A (callback) + Route B (`owned_completion`) — any new LLM call site picks one inconsistently. Unsustainable for Phase 8's write-always requirement. |

**The fix Phase 7 delivers:**

1. **LlmGateway proxy** — one boundary for all LLM calls. New call sites have one place to go. Phase 8's write-always gate is one flag in one place.
2. **Executor loop ownership** — break `coder.run()` into observable turns. Every step is an event; the trace becomes a full audit trail.

---

## What Phase 7 is NOT

Do not scope these into any P7 worker spec:

| Item | Where it belongs |
|------|-----------------|
| Write-always storage (verbosity gate removed) | Phase 8 — needs proxy first |
| Context package blob sidecar | Phase 8 |
| `mcp-coder replay <id>` CLI | Phase 8 |
| Storage GC / TTL enforcement (BL-357) | Phase 8 |
| Novelty scoring / curation pipeline | Phase 8+ |
| Cross-session reasoning persistence | BL-333 after dogfood validates same-session value |
| Host escalation / `yes=True` → smart confirm (BL-351) | Phase 8+ |
| Embeddings for delegation_rag.db (BL-366) | After FTS recall measured |
| Multi-host / Cursor SDK backend (BL-340) | Later arc |

---

## Open design questions — resolve in master session

### Q1: LlmGateway location and interface

**Options:**
- **A (preferred):** `core/observability/gateway.py` — `LlmGateway` wraps `litellm.completion`; `ObservabilityBackend.record_llm_call()` called synchronously post-completion. Proxy = observability concern.
- **B:** `core/engine/gateway.py` — proxy is an engine concern; observability backend receives events from it. Cleaner separation if proxy eventually handles routing/budget, not just logging.
- **C:** Replace `owned_helper_llm.py` in place — no new class; just make `owned_completion` the single standard path.

**Recommendation:** Option A keeps `core/observability/` extractable and self-contained. Option B may be cleaner long-term if proxy grows routing/budget/redaction features. Decide in master session; lock as D-P7-1.

### Q2: Executor loop route — outer loop vs Aider subclass

**Route A — outer loop (preferred):**
- mcp-coder owns `compile → run(bounded sub-task, N turns) → inspect → recompile → run`
- Each sub-run is bounded (max step count + timeout)
- Results inspected between steps; file expansion only via policy (D-P4-10)
- Pros: backend-neutral; clean audit trail; composes with future BL-340 (Cursor SDK)
- Cons: multiple executor calls; step budget design needed; may need more context compile rounds

**Route C — Aider `Coder` subclass:**
- Wrap or subclass `Coder.run()` for per-turn LLM hooks
- Can inject messages, capture `reasoning_content` before Aider strips it
- Pros: richest per-turn control; single executor call
- Cons: high maintenance; Aider version coupling; violates thin-adapter spirit; hard to port to BL-340

**Recommendation:** Start with Route A. Route C is the fallback if Route A cannot produce per-turn trace events with acceptable fidelity. Lock as D-P7-2.

### Q3: Trace event schema for executor turns

Today helper events use:
```json
{"event_type": "llm_call", "role": "context_builder", "model": "...", "delegation_id": "...", ...}
```

For executor turns we need:
- `step_index` — monotonic per delegation (1, 2, 3…)
- `parent_call_id` — links sub-turns to the delegation
- `executor_turn: true` flag or `role: "executor_turn_N"`

**Decision needed:** How to distinguish executor `llm_call` events from helper `llm_call` events in the trace file — role field vs separate event type vs flag. Lock as D-P7-3.

### Q4: Non-LLM action event types

What event types do we emit for non-LLM executor actions?
- `tool_call` — file write, shell exec (Aider tool calls)
- `action` — lint retry, auto-confirm, other state transitions
- Or collapse into one `executor_action` type with a `kind` field

**Decision needed:** event type taxonomy. Lock as D-P7-4.

### Q5: Compile provenance storage

Where do compile bundle events live?
- **Same trace file** — `compile_event` lines in `traces/<delegation_id>.jsonl` alongside `llm_call` lines. Simpler; one file.
- **Separate sidecar** — `traces/<delegation_id>-compile.jsonl`. Keeps trace file for LLM events only; cleaner query.

**Recommendation:** Same trace file (one artifact per delegation). Phase 8 can split if needed. Lock as D-P7-5.

### Q6: Step budget defaults

How many executor turns per delegation before we stop and return?
- Default: 10 turns (outer loop) — enough for most tasks; prevents runaway
- Hard max: 20 turns (regardless of config)
- Timeout: 5 min per step, 30 min total

**Decision needed in master session.** Lock as part of D-P7-2.

---

## Current capture paths (Phase 6 state — know before designing Phase 7)

```
Helper LLMs (context_builder, architect_pass, spec_validation):
  owned_helper_llm.py → litellm.completion → record_owned_completion()
  → trace_file.append(llm_call event)   [synchronous, works]
  → model_roles tokens overlay          [synchronous, works]

Executor (Aider):
  aider_engine.py → Aider coder.run()
    → Aider internal → litellm.completion (per turn)
      → LiteLLM success_callback          [fires AFTER completion, async]
      → litellm_callback.py overlay       [races; often misses inner turns]
  
  Result: executor_tokens often wrong; inner turns invisible; no per-step events
```

**Phase 7 target state:**
```
All LLM calls:
  any_engine.py → LlmGateway.complete()
    → litellm.completion (or backend)
    → obs.record_llm_call()             [synchronous, always captures]
    → return response

Executor:
  mcp_server.py outer loop:
    compile() → gateway.complete() × N turns
    → trace event per turn (step_index, prompt, response, tokens)
    → non-LLM actions → trace event (tool_call/action)
    inspect() → recompile if needed → repeat
```

---

## Confusion traps for Phase 7 workers

1. **P7-001 before P7-002.** LlmGateway must exist before executor turns can route through it. Never dispatch P7-002 worker before P7-001 is done.
2. **Route A is not "just call aider_engine twice."** The outer loop needs a step-bounded sub-run, not a full delegation-style recursive call. Keep scope narrow.
3. **Trace events vs `delegations.jsonl`.** The canonical JSONL stays lean (Phase 6 D-P6-3 unchanged). New events go into `traces/<delegation_id>.jsonl` only.
4. **`core/observability/` extractability rule.** No imports from `server/` or `core/engine/aider_engine.py` in `core/observability/`. Gateway wraps `litellm`; engine calls gateway.
5. **`yes=True` is NOT replaced in Phase 7.** BL-351 (smart confirm / escalation) is Phase 8+. The outer loop can detect when Aider stalls but not route decisions back to Cursor yet.
6. **Verbosity gates stay as-is in Phase 7.** Write-always (Phase 8) requires proxy first (Phase 7). Don't remove verbosity gates during P7 — just make sure proxy is the single gate point so Phase 8 can flip one switch.
7. **P7-003 (compile provenance) is independent.** After P7-001 lands, P7-003 can be dispatched in parallel with P7-002.
8. **Do not add `context_package` blobs to trace files.** That is the Phase 8 blob sidecar — different file, different lifecycle.

---

## Worker rules (enforce when dispatching P7-* workers)

- Single source of truth: attached `docs/tasks/P7-<NNN>-<name>-v1.md` only (gitignored)
- Fill `§ Results` in spec; propose PM changes under **§ Results → Suggested for master session**
- Do NOT edit IDEA, PHASES, PHASE*_MVP, BACKLOG, PHASE*_ISSUES, VISION_DOCS unless task spec explicitly lists them
- No Aider API terms (`fnames`, `yes=True`, `Coder`) in `core/observability/` — backend-neutral rule
- `core/observability/` must have no imports from `server/` or `core/engine/aider_engine.py` (extractability constraint)
- Worker specs: `docs/tasks/P7-NNN-name-v1.md`

---

## Phase 6 exit (frozen reference)

Phase 6 closed 2026-06-13. Shipped: `core/observability/` seam, Route A callback, Route B `owned_completion`, per-delegation trace files (3 helper lines), live helper tokens, reasoning hot buffer, lean JSONL. Open carries:
- **BL-368** → P7-001 (LlmGateway proxy)
- **BL-350** → P7-002 (executor loop ownership)
- **BL-333** → extend in P7-002 (per-executor-turn reasoning)
- **BL-353** → P7-003 (compile provenance remainder)
- **BL-367** → Phase 8 (full-capture substrate; verbosity as display filter)
- **BL-357** → Phase 8 (storage GC first slice)

See [phase6-master-session-bootstrap.md](./phase6-master-session-bootstrap.md) for Phase 6 design decisions and confusion traps.
