# Phase 10 master session bootstrap

**Created:** 2026-06-18
**Status:** Active — Phase 10 milestones P10-001..P10-004 scoped.
**Purpose:** Record all Phase 10 scope decisions, design rationale, and locked choices made in the master planning session. Workers read the PM doc; this note is the *why* behind it.
**PM board:** [PHASE10_MVP.md](../PHASE10_MVP.md)
**Related notes:** [phase9-master-session-bootstrap.md](./phase9-master-session-bootstrap.md), [model-policy-layer.md](./model-policy-layer.md)

---

## Phase 10 in one sentence

Shape Aider's behavior before problems occur, see what's happening while it runs, and handle stalls gracefully — all at POC/partial level sufficient for real-project dogfood.

---

## Why Phase 10 is scoped this way

### The honest gap analysis

After Phase 9 closed, the observability and logging infrastructure is excellent. Every LLM call is captured at the HTTP boundary, write-always, replayable. `policy_applied` tracks what parameters were resolved and applied. The stack is trustworthy.

But using `mcp-coder` on a **real project** (not the e2e test workspace) still requires swallowing three things:

1. **Blind `yes=True`** — Aider auto-approves every "add files to chat?" and "run this shell command?" prompt. mcp-coder never knows what was approved. Scope expansion is invisible.
2. **Opaque execution** — Delegations run for 3–5 minutes with only a spinner in Cursor. You can't tell if Aider is making progress, stuck in a loop, or asking for files that aren't in scope.
3. **Silent stall failures** — When Aider asks for a file that wasn't in `target_files`, the delegation returns a generic failure string. The planner has no way to know "I just need to add `src/config.py` and retry."

There are also **executor capability gaps** that compound the problem: `system_prompt_prefix` and `edit_format` are already wired through the model registry and resolved from env — they're just never applied. Adding "stay within the spec Files contract" as a system prefix would directly reduce how often Aider asks for more files, shrinking the blind-`yes=True` blast radius before supervision is needed.

### The chosen theme cluster

Themes 1 (Supervision & Trust), 4 (Visibility), and 5 (Executor Capability) were selected because they form a natural stack:

```
Theme 5 — Shape behavior BEFORE problems occur (system_prompt_prefix, edit_format)
   ↓
Theme 4 — SEE what's happening WHILE it runs (ctx.info notifications, log tail)
   ↓
Theme 1 — REACT when problems occur (stall detect → needs_input)
```

Each one makes the next more useful. A good system prompt (Theme 5) reduces how often supervision (Theme 1) fires. Visibility (Theme 4) lets you verify the prefix is working and understand when supervision triggers. This is not three independent features — it's a coherent trust layer.

Theme 6 (onboarding/ops) was explicitly deprioritized because `mcp-coder setup` + local `.env` already handles this well for local real-project use. The remaining gap (`mcp-coder doctor`) is nice-to-have, not blocking.

### "Partial/POC" level is the right call

None of the three themes are being built to full vision:
- **BL-351 full vision**: supervised `InputOutput` subclass + cheap LLM evaluating every Aider prompt + outer-loop re-compile on expansion approval. Phase 10 does v0: output parsing + structured return.
- **BL-106 full vision**: capture→egress bridge subscribed to all observability events + per-turn executor highlights. Phase 10 does POF: `ctx.info` at pipeline boundaries + thread queue.
- **BL-334 full vision**: per-delegation override via `model_policy` in MCP args (BL-512 Stage 2). Phase 10 does v0: global env/yaml setting.

This is intentional. The goal is to enable **real-project dogfood** first, observe what actually breaks, then invest in full implementations grounded in evidence.

---

## Theme 5: Executor option wiring (BL-334 v0)

### The gap

`core/config/model_registry.py` → `resolve(ROLE_EXECUTOR, workspace)` already returns a `CallParams` with `system_prompt_prefix` and `edit_format` fields (added in Phase 9 model registry work). `_apply_executor_model_params` in `aider_runtime.py` applies `reasoning_effort`, `thinking_budget`, `extra_params`, and `weak_model` — but never touches `system_prompt_prefix` or `edit_format`.

The fields exist in the schema. The env vars follow the existing pattern (`MCP_CODER_EXECUTOR_*`). This is a pure wiring gap, not a design problem.

### Why `system_prompt_prefix` matters for real projects

Aider's default `main_system` prompt is focused on general coding. For mcp-coder use, we want Aider to know:
- "The spec Files list is the contract — don't ask to edit files not in it."
- "Don't ask to add more files to context — work with what you have."
- "If you can't complete the task without out-of-scope files, say so clearly."

These instructions prevent the most common stall patterns before they happen. A prefix like: `"You are operating within a managed spec-based delegation. Respect the spec's Files contract. Do not add files outside the provided target list."` will measurably reduce blind expansions.

### Backend-neutral architecture

Per existing rule: the *resolver* (`CallParams.system_prompt_prefix`) lives in `core/config/`. The *application* (`model.system_prompt_prefix = value`) stays in `core/engine/aider_runtime.py`. Other execution backends (BL-340 Cursor SDK, etc.) would ignore the Aider-specific setter.

---

## Theme 4: Visibility (BL-106 POF + BL-520 POF)

### Two complementary surfaces

**BL-106: MCP `ctx.info` notifications** — push to the host (Cursor) while the delegation is running. Cursor renders these as streamed message lines in the chat. The user sees progress without leaving the editor.

**BL-520: `logs tail` CLI** — pull from disk (trace JSONL) in a side terminal. Enabled by Phase 9's write-always storage: trace events are written to disk as they occur. A tail command can follow the file in real time with no network or MCP involvement.

These are complementary, not redundant:
- In Cursor: `ctx.info` gives lightweight milestone progress without switching context.
- In terminal: `logs tail` gives full event visibility for debugging.

### Thread bridge design (BL-106)

The async MCP handler calls `delegate_to_agent` which spawns the pipeline (and Aider) in a worker thread. `ctx.info(msg)` is an async coroutine — it cannot be called from a worker thread directly.

**Design:** `ProgressQueue` — a `threading.Queue` or `asyncio.Queue` (using `asyncio.run_coroutine_threadsafe`). Worker enqueues plain strings. An asyncio task (spawned alongside the delegation) drains the queue periodically (`await asyncio.sleep(0.5)` in loop) and calls `await ctx.info(msg)`.

Pipeline call sites (compiler, builder, validation, executor loop) call `progress_queue.put(msg)` via an injected callback or context variable. The queue is created in the MCP handler and passed down.

### `ctx.report_progress` vs `ctx.info`

`ctx.report_progress(progress, total)` sends a MCP `notifications/progress` message. This requires the client to have set a `progressToken` when calling the tool. Cursor support for `progressToken` is inconsistent across versions.

`ctx.info(msg)` sends a MCP `notifications/message` with level `info`. Cursor renders these as live text. No `progressToken` required. More reliable for POF.

Use `ctx.info`. If `ctx.report_progress` proves useful and supported in a future Cursor version, it can be added alongside.

---

## Theme 1: Supervision v0 (BL-351 v0)

### The stall problem

When Aider asks to add files to chat (e.g.: *"I see that `src/config.py` is needed. Please add it with `/add src/config.py`."*), mcp-coder's current behavior:
1. `_IMPLEMENT_QUESTION_MARKERS` regex matches.
2. `infer_run_success()` returns a failure signal.
3. `delegate_to_agent` returns a generic failure string to Cursor.
4. Cursor has no way to know this was a file request vs a compile error vs a timeout.

The planner cannot help because the structure is lost.

### v0 design: parse, classify, return structured

No Aider `InputOutput` subclass. No mid-loop injection. No outer loop retry (except optional auto-retry).

**Flow:**
1. Executor runs to completion (or early termination).
2. `infer_stall_type(output: str)` classifies the output:
   - `needs_input_files`: matches "add X to the chat", "please add", "/add" references in the output
   - `needs_input_clarification`: matches question patterns ("which", "what should", "I need to know")
   - `success` / `failure`: existing logic
3. If `needs_input_files`: extract file paths from the output (regex + heuristic path extraction).
4. Return structured `needs_input` payload to Cursor.

**Optional auto-retry (P10-003 v1):**
If `MCP_CODER_STALL_AUTO_RETRY=1` and stall type is `needs_input_files`:
- Add the extracted paths as read-only to the Aider context.
- Re-run the executor once.
- If success: return success with `auto_retried: true` in the delegation record.
- If another stall: return `needs_input` as above.

### What v0 does NOT do

- No cheap-LLM supervisor evaluating prompts (that's BL-351 v1).
- No outer-loop re-compile (BL-350 continuation).
- No shell-command escalation (only file-add stalls handled in v0).
- No pause-and-wait API (delegation is not a persistent connection; Cursor retries by calling the tool again with updated args).

---

## High-ROI backlog clearance (P10-004)

Four items from the deferred-from-Phase-9 list that are small enough to batch and valuable enough to not keep deferring:

**BL-517** (`policy_applied` ignored params): Misleading logs where executor `policy_applied` shows `temperature: 0.5` implying it was applied to Aider, but Aider ignores it. Fix is one dict key addition. Should be done alongside P10-001 (executor param wiring) since we're touching the same code.

**BL-519** (proxy env toggle): `MCP_CODER_PROXY_ENABLED=0` escape hatch for debugging. A single guard in `ensure_observability_bootstrap()`. Needed for real-project use when proxy routing issues arise (e.g. new model prefix not in routing table).

**BL-516 partial** (`trace inspect --summary`): Health scorecard per delegation. During real-project dogfood, scanning many delegations to understand patterns is painful without this. The P9-010 `trace inspect` command exists; `--summary` is a new output mode.

**BL-518 partial** (env var matrix docs): The fragmented env var landscape is documented in various `.env.example` comments but nowhere as a unified reference. A table in `docs/guide/` resolves real-project operator confusion. Doc-only.

---

## Relation to future phases

**Phase 11 (draft focus):**
- BL-350 continuation: full outer-loop supervision (compile → bounded run → inspect → re-compile → run)
- BL-512 Stage 2: host-set model policy in `delegate_to_agent` args
- BL-513 Stage 3: AI-suggested parameters (pre-delegation task analysis)
- BL-321: tiered model escalation (retry with stronger model after N failures)
- Out-of-process backend proxy extension (Claude Code, Codex base URL config)

Phase 10 lays the foundation: P10-001 wires the executor option knobs; P10-003 detects the stall signals; Phase 11 builds the outer-loop logic that acts on those signals.

---

## Implementation order rationale

**P10-001 first** — smallest change, highest immediate value. Can be shipped in a focused 1–2 hour session. Affects every subsequent delegation in dogfood. Reduces Phase 10 stall frequency.

**P10-002 second** — requires thread bridge design but is otherwise mechanical. The `ctx: Context` plumbing must be in place before any notification-based debugging is possible. `logs tail` is read-side only (no MCP changes needed) and can be tested independently.

**P10-003 third** — depends on P10-001 having reduced stall frequency (so we can test the remaining stalls are detected correctly). Enhances `infer_run_success` which is in `aider_engine.py`.

**P10-004 last** — backlog items are independent but benefit from the same test suite runs that verify P10-001/002/003.
