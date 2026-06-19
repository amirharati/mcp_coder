# Phase 11 master session bootstrap

**Created:** 2026-06-18
**Status:** Active — Phase 11 milestones P11-001..P11-007 scoped.
**Purpose:** Record all Phase 11 scope decisions, cross-phase architectural decisions, and the reasoning behind them. Workers read the PM doc; this note is the *why* behind it.
**PM board:** [PHASE11_MVP.md](../PHASE11_MVP.md)
**Related notes:** [phase10-master-session-bootstrap.md](./phase10-master-session-bootstrap.md), [model-policy-layer.md](./model-policy-layer.md)

---

## Phase 11 in one sentence

Make the Aider/MCP relationship bidirectional and supervised: the executor is no longer a blind `yes=True` process, the intent is captured before delegation, and output gets a lightweight quality gate — all with bounded per-delegation cost.

---

## Why Phase 11 is scoped this way

### The honest gap after Phase 10

Phase 10 closed the observability and basic behavior-shaping gaps. The stack is trustworthy: every LLM call is captured, proxy is running, executor options are wired. But the delegation model is still fundamentally **junior developer with headphones on**:

1. **`yes=True` blindness** — P10-003 detects stalls *after* the run and returns `needs_input`. But during the run, every `confirm_ask` — "run this shell command?", "add this out-of-scope file?", "proceed with this risky deletion?" — is auto-approved. No judgment.

2. **No intent verification** — Delegation starts immediately from whatever spec text is given. If the task is ambiguous or missing key decisions, the executor either stalls (costs 2 minutes) or produces something misaligned (costs a review cycle).

3. **No output quality gate** — Whatever Aider produces goes straight to the spec report. No scan for obvious issues, missing docstrings, or import problems.

4. **Cursor has no per-call control** — Model and budget are set globally in env. Cursor can't say "for this complex refactor, use more thinking budget" without restarting the server.

Phase 11 closes all four gaps at the right level of ambition: supervised (not fully autonomous), smart (not brute-force), bounded (not expensive).

### The Aider thread insight

A key realization during planning: when Aider's `confirm_ask()` fires, the Aider thread is **blocked**, waiting for a True/False return. The coder instance is still alive. By subclassing `InputOutput` and overriding `confirm_ask()`, we can:

1. Route the decision to a supervisor LLM — synchronously from the worker thread, no async needed
2. Return the decision — Aider continues uninterrupted
3. For human escalation: optionally block on a `threading.Event` until an answer arrives via a separate MCP tool call

This means no checkpoint/restart is needed for P11-002. The coder continues from exactly where it paused. The existing executor session cache (shipped P2-210) keeps the coder alive across delegations.

The mid-run human gate (P11-004) exploits this further: the Event bridge means Cursor can answer a delegation question *while the delegation is still running*, if the MCP client supports concurrent tool calls. This is experimental in Phase 11 and confirmed or moved to Phase 12 via dogfood.

---

## Cross-phase architectural decisions (permanent platform principles)

These decisions apply to Phase 11 and all future phases. Workers must not violate them.

### D-ARCH-1: Context frugality rule

Every LLM call in the pipeline gets a **purpose-built context bounded to its role**. No LLM call sees the full session state.

| Role | Context budget | What it sees |
|------|----------------|--------------|
| Supervisor | ~2k tokens | Spec contract + question + decision log + output tail |
| Clarity pass | ~3k tokens | Task + spec Files + last 3 delegation titles |
| Architect pass | ~8k tokens | Spec + file map + repo outline |
| Builder brief | ~16k tokens | Spec + relevant files (compiled) |
| Executor | ~32k tokens | Full context package |
| Tier-1 reviewer | ~8k tokens | Diff + changed files + acceptance criteria |

**Why:** "Reason once expensively, propagate downhill" (from AGENTIC_LOOP_LOGGING.md). The expensive model call is at the executor level where reasoning over the full context is justified. Upstream and downstream calls get the minimum sufficient context. This makes even Sonnet-class supervisor calls affordable per delegation.

### D-ARCH-2: Strong LLM for judgment calls

The supervisor LLM that approves/denies/aborts Aider decisions is **not a cheap model**. It needs to:
- Read a spec contract and judge whether a requested action is in-scope
- Detect scope creep and shell command risks
- Maintain consistent decisions across a delegation (via decision log)

A cheap model (Flash/Haiku) may auto-approve dangerous things or apply inconsistent policy. `MCP_CODER_SUPERVISOR_MODEL` defaults to mid-tier (Sonnet-class). Cost is bounded by D-ARCH-1: ~2k tokens × 3-5 calls per delegation = minimal.

### D-ARCH-3: Aider thread stays alive through supervised IO

`SupervisedIO` blocks the Aider thread at `confirm_ask()` and returns a decision. No restart. No re-run. The existing executor session cache keeps the coder alive. This is the correct exploitation of the architecture that was already built.

### D-ARCH-4: Per-delegation supervisor state (in-memory decision log)

`DelegationSupervisor` maintains a compact decision log per delegation run. Growing log is summarized when it exceeds the token budget. Persisted to trace JSONL at end of delegation. This gives the supervisor **cross-decision coherence**: it can recognize "I already approved X because Y, now this request contradicts that."

### D-ARCH-5: Human escalation v1 = abort-and-resume; mid-run gate is experimental

The default path when supervisor can't auto-decide: abort cleanly, return `needs_input` with supervisor reasoning (same pattern as P10-003, but triggered by supervisor judgment not stall detection). The `answer_delegation_question` tool (P11-004) is experimental. If Cursor's MCP client supports concurrent tool calls, it works. If not, timeout fires and falls back to abort. Dogfood determines which path to invest in for Phase 12.

### D-ARCH-6: model_policy is additive (host > env > code defaults)

Host-passed `model_policy` overrides the env layer for one delegation. Each role is independently configurable. This enables Cursor to set high thinking budget for complex tasks and low budget for trivial ones without a global env change.

---

## Multi-LLM orchestration pattern

The Phase 11 pipeline uses multiple LLM roles with different model tiers:

```
[clarity pass]     Flash       "is this task clear?"          ~3k tokens
      ↓
[architect pass]   Sonnet      "what's the implementation plan?"  ~8k tokens
      ↓
[builder brief]    Flash       "compress context for executor"    ~16k tokens
      ↓
[executor]         configured  "write the code"                   ~32k tokens
      ↕ confirm_ask events
[supervisor]       Sonnet+     "approve/deny/abort this action"   ~2k tokens/call
      ↓
[tier-1 reviewer]  Flash       "scan changed files"               ~8k tokens
```

Total per delegation: ~6-8 LLM calls. Most are tiny. The executor is the only large one. The per-delegation cost delta vs Phase 10 is modest; the quality delta is large. This is the economics that makes Phase 11 viable.

---

## Decisions on mid-run statefulness

### Can we continue Aider from where it left off between delegations?

Yes — the executor session cache (P2-210) keeps the Aider Coder instance alive between `delegate_to_agent` calls in the same MCP session. The coder's conversation history persists. This is already shipped.

### Can we pause mid-run and resume with human input?

Phase 11: **Yes, experimentally** (P11-004). The Aider thread blocks at `confirm_ask()`. A separate tool call can unblock it. Depends on Cursor concurrent tool call support.

Phase 12: **Full async resume**. Multi-step plan object (goal + steps + state) persisted to disk. `resume_token` on `delegate_to_agent`. Outer-loop supervisor decides next step autonomously.

### Should the supervisor use RAG for cross-delegation decisions?

Yes — for the "have we seen this pattern before?" dimension. BL-354 v0 (P11-003) is prompt-only, but the supervisor can query `rag_search(question)` for past delegation decisions as a Phase 11 extension. Not in initial scope; add if supervisor hit rate is low in dogfood.

---

## Explicit non-goals for Phase 11

| Item | Reason |
|------|--------|
| Multi-step plan object with async resume | Needs Phase 11 dogfood to define the right plan schema |
| BL-513 AI-suggested parameters | Phase 11 has file-count heuristic (P11-006); full AI suggestion needs corpus |
| BL-514 dynamic escalation | Needs BL-513 + critic/supervisor data |
| Full executor-pull sidecar HTTP server | P11-003 ships prompt-only; sidecar needs dogfood signal on what tools Aider actually needs |
| Cross-session reasoning persistence | Needs Phase 11 traces as training data |
| Tier-2 epic-boundary review | Needs epic concept (what is "last step of an epic"?) |
| Out-of-process proxy extension (Claude Code etc.) | Independent of Phase 11 scope |

---

## Phase 12 preview (from this session)

Based on what Phase 11 does, Phase 12 will likely own:

- **Multi-step plan object** — goal + ordered steps + state, persisted to `plans.db`; `resume_token` on `delegate_to_agent`; outer-loop supervisor decides next step
- **True async mid-run human gate** — if Cursor concurrent tool calls don't work for P11-004, Phase 12 designs a protocol-level solution
- **Full executor-pull sidecar** — lightweight HTTP server exposing `rag_search`, `read_file`, `search_history`; injected as tools in Aider's function-calling context
- **Tier-2 epic-boundary review** — plan knows "last step of epic", triggers serious reviewer at that boundary
- **BL-513/514 AI-suggested + dynamic escalation** — built on Phase 11 supervisor infrastructure
- **Cross-session reasoning persistence** — BL-333 remainder, Phase 11 traces as bootstrap corpus
