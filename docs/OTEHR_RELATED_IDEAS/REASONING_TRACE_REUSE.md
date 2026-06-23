<!--
  STEWARDSHIP — Tier 3 related idea (not canonical). See docs/VISION_DOCS.md.

  - May inform BL-* items; does not override docs/IDEA.md.
  - Do not treat as shipped product design without user + backlog entry.
  - Backlog anchor: BL-333. Related: CONTEXT_AS_GIT.md, WORKSPACE_HISTORY.md, notes/multi-model-roles.md
-->

# Reasoning Trace Reuse — Capturing the Model's Thinking as First-Class Context

**Status:** Idea — captured from mcp-coder Phase 4 dogfood discussion (2026-06-09)
**Backlog:** [BL-333](../BACKLOG.md#bl-333-reasoning-trace-capture--cross-delegation-context-feed)
**Related:** [CONTEXT_AS_GIT.md](./CONTEXT_AS_GIT.md) · [WORKSPACE_HISTORY.md](./WORKSPACE_HISTORY.md) · [multi-model-roles.md](../notes/archive/multi-model-roles.md)

---

## The core idea

Modern reasoning models (Claude extended thinking, DeepSeek R1, o-series, Gemini thinking) produce a **hidden reasoning trace** before their visible answer. That trace contains the model's *uncertainty, considered alternatives, rejected paths, and causal justification* — a far richer signal than the final output.

Today this trace is **thrown away** the instant a turn completes. Aider explicitly calls `remove_reasoning_content()` after each LLM call; we only keep the SEARCH/REPLACE edits.

**The idea:** capture reasoning traces during an MCP session, store them, and **selectively feed them into later, cheaper model calls** so a mid/low-tier model inherits the expensive model's thinking instead of rediscovering it.

```text
Step 1   High-end model (Claude Sonnet + extended thinking)
         reasons deeply about API design, edge cases, contract risks
         → trace captured, summarized, stored

Step 2   Mid-tier model (Gemini Flash / gpt-4o-mini) on an easier sub-task
         → receives compressed, relevant slice of step 1's reasoning
         → produces output as if it had done the hard thinking itself
```

---

## Why it's useful (the motivation)

A captured trace is valuable along **three independent axes** — each unlocks a different capability, and they compound:

| # | Use | What it enables | Horizon |
|---|-----|-----------------|---------|
| **1** | **Model upgrade / escalation inside the MCP loop** | The trace is the live signal that a model is struggling (confused, looping, hedging, low-confidence). Use it to auto-escalate to a stronger model mid-loop — or at minimum *suggest* an upgrade to the planner — instead of waiting for a failed delegation. | Near-term |
| **2** | **Traces as context — transfer intelligence** | Inject a high-end model's reasoning into later *cheaper* calls so the cheap model inherits the expensive thinking rather than rediscovering it. "Reason once expensively, propagate downhill." | Near/mid-term |
| **3** | **Training data — distillation & module replacement** | Accumulated `(task, context, reasoning, outcome)` tuples are a proprietary dataset: fine-tune/distill a smaller model to mimic the high-end reasoning, or train **e2e learned modules** that replace today's hand-written heuristics (file picker, context builder, validation). | Long-term / strategic |

The sections below expand each axis.

### 1. Reasoning is higher-signal than output

The visible output says *what* changed. The reasoning says *why*, *what was risky*, and *what was almost done differently*. For downstream tasks, the "why" prevents repeated mistakes far more than the "what".

**Concrete example:**

- **Step 1 executor (high-end):** internally reasons *"I'll extend `Ledger.load()` rather than add `LedgerV2`, because the existing API contract must not break and three callers depend on the current signature."* — then ships a small diff.
- That reasoning is discarded.
- **Step 2 builder (cheap model):** sees only history "`load()` modified". It has no idea the contract is load-bearing, so its brief doesn't warn the next executor — which then breaks `load()`.

With trace reuse, step 2's brief carries *"prior reasoning flagged `load()` API contract as load-bearing (3 callers); do not change its signature."*

### 2. Expensive thinking amortized across cheap calls

Pay once for deep reasoning on the hard/ambiguous step; reuse that reasoning to lift the quality of many cheaper calls. This is the economic core of multi-model routing (BL-162): **spend reasoning budget where it matters, propagate the result downhill.**

### 3. The missing signal for model escalation

A reasoning trace is the natural trigger for tiered escalation (BL-321): when a cheap model's trace shows it is *confused, looping, or hedging*, that is the signal to step up to a stronger model — rather than waiting for a failed delegation.

### 4. Better cross-session memory

Workspace history (Phase 3) stores outcomes and diffs. Reasoning summaries are an orthogonal, higher-value channel for "what did we learn building this?" — closer to how a human teammate remembers *why* the codebase is shaped a certain way.

### 5. Model upgrade / escalation signal (axis 1, expanded)

A reasoning trace is the natural trigger for tiered escalation (BL-321): when a cheap model's trace shows it is *confused, looping, hedging, or low-confidence*, that is the signal to step up — rather than waiting for a failed delegation.

Two strengths:
- **Auto-escalation:** mid-loop, swap to a stronger model for the remainder of the task.
- **Suggestion-only:** if we don't want autonomous spend, surface "executor reasoning looks uncertain — consider a stronger model" to the planner/host. Lower-risk first step; pairs with the gatekeeping idea.

This is the cheapest axis to ship: it needs only *capture + a confusion heuristic*, not storage or training.

### 6. Training data — distillation & learned modules (axis 3)

Every delegation can emit a structured tuple:

```text
(task_spec, assembled_context, reasoning_trace, edits, outcome, verify_result)
```

Accumulated over real usage, this is a **proprietary, in-distribution dataset** of how strong models reason about *this codebase / this user's tasks*. Two distinct payoffs:

- **LLM distillation:** fine-tune a smaller/cheaper model to imitate the high-end model's reasoning on our task shapes — lowering cost while keeping quality, and reducing dependence on any single frontier vendor.
- **Replace modules with e2e learned components:** several mcp-coder modules are currently hand-written heuristics — the file picker, the context builder brief, spec validation, the confusion/escalation heuristic above. With enough labelled traces + outcomes, these become **trainable**: learn the picker from "which files did good reasoning actually touch?", learn the brief from "which context led to success?". The heuristic version ships first and *generates the labels* for its own learned replacement.

This reframes mcp-coder's logs from an audit byproduct into a **data flywheel**: the better the system works, the more high-quality reasoning/outcome pairs it captures, the better the models and learned modules it can train.

> Caveat: training use raises consent, licensing, and privacy questions (whose code, whose traces, vendor ToS on reasoning content). Treat captured traces as sensitive; gate any training-data export behind explicit opt-in. Out of scope for a first capture spec — but the **capture schema should be designed with this future use in mind** (keep task/context/outcome alongside the trace, not just the trace).

---

## Where it plugs into mcp-coder

| Layer | Injection point | Value |
|-------|----------------|-------|
| Context builder (P4-001b) | `gather_builder_history()` adds a `reasoning_summary` field per history entry | Brief explains *why*, not just *what* |
| Architect pass (P4-020) | Architect sees prior reasoning before planning | Avoids re-litigating settled design choices |
| Workspace history DB | `delegation_reasoning_summary` column | Cross-session "design memory" |
| Model routing (BL-162/321) | Trace inspected for confusion markers | Escalation trigger / upgrade suggestion (axis 1) |
| Training / data export | `(task, context, trace, outcome)` tuple persisted with consent flag | Distillation + learned-module dataset (axis 3) |

---

## How to capture it

Aider receives `reasoning_content` from the LiteLLM completion (`completion.choices[0].message.reasoning_content`), wraps it in `<thinking-content-…>` tags, then strips it via `remove_reasoning_content()` before storing the reply. We must intercept before that, or capture outside Aider.

| Route | How | Trade-offs |
|-------|-----|-----------|
| **A — LiteLLM callback** *(recommended)* | Register `litellm.success_callback` at MCP startup; capture `reasoning_content` + `usage.reasoning_tokens` for every completion (builder, validation, architect, **and** Aider's executor calls, since Aider uses LiteLLM). | Zero Aider patching; uniform across all roles. Depends on LiteLLM callback API/version; need to map callback → delegation_id. |
| **B — `model.reasoning_tag = None`** | Tell Aider not to strip; raw trace lands in `partial_response_content`; extract via `aider/reasoning_tags.py` patterns after run. | Simple for executor, but bloats edit output and can trip `infer_run_success()` error-marker scan. |
| **C — Coder subclass / patch** | Override `send_message` to grab `reasoning_content` before stripping. | Cleanest for Aider specifically; Aider internal API is not stable. |

**Recommended:** Route A as the primary mechanism — it is backend-neutral (works for our own cheap-model calls too) and keeps the capture concern out of the Aider adapter, consistent with the backend-neutral rule.

---

## Storage and budget

- **Per-delegation:** `delegation_reasoning_summary: str | null` in `delegations.jsonl` (truncated, e.g. 2k chars — summary, not the full 10k-token trace).
- **Session (in-memory):** `{delegation_id: reasoning_summary}` for same-session injection without DB round-trips.
- **History (optional):** persist in `workspace_history.db` for cross-session builder context.
- **Budget:** reasoning summaries compete with other history sections in `core/context/builder_prompt.py` and are truncated to fit the per-role token budget (never truncate contract paths).

A raw trace can be 10k+ tokens — so the pipeline stores/injects a **summary** (possibly produced by the same cheap builder model), not the verbatim trace, except where a short trace fits the budget directly.

---

## Open questions (decide at spec time)

1. **Capture policy:** always-on when the model emits reasoning, or opt-in config (`capture_reasoning: true`)?
2. **Summarize vs verbatim:** who compresses the trace, and to what budget?
3. **Scope:** same-session only (cheap, in-memory) vs cross-session (DB, storage cost, staleness)?
4. **Does it actually help?** Injecting executor reasoning into a cheap builder call might add noise rather than signal — needs dogfood evidence before committing to cross-session persistence.
5. **Privacy/size:** reasoning traces can leak secrets or balloon logs; reuse existing `redact_secrets` + truncation.

---

## Relation to other ideas

- **BL-162 / multi-model-roles.md** — trace reuse is the mechanism that makes "expensive reason once, cheap execute many" real; prerequisite for informed escalation.
- **BL-321** — reasoning trace is the *step-up signal*.
- **CONTEXT_AS_GIT.md** — a captured trace is a high-value artifact to checkpoint/branch alongside context.
- **WORKSPACE_HISTORY.md** — reasoning summary is a new column/signal on the existing delegation history substrate.
- **P4-001b builder history** — the natural first injection point once capture exists.
