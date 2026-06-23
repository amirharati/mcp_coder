<!--
  STEWARDSHIP — shipped / done backlog items (audit archive).

  LLM: grep "^### BL-NNN" done.md — rarely read. Navigate via ../BACKLOG.md index.
  ADD: move section from deferred.md when shipping; set **Status:** done + milestone.
  Do not delete sections; mark obsolete in Status if needed. README.md § For LLMs.
-->

# Done backlog items (audit)

Shipped / completed backlog items, kept for history. For navigation, use the [index](../BACKLOG.md) — this file is rarely read. **How items land here:** [README.md](./README.md) § For LLMs (recipe: item shipped).

---

## Supervisor & orchestration

### BL-530: On-demand context retrieval — `SupervisorToolRunner`

**Status:** `done` — 2026-06-21. Phase 12 P12-003 shipped (commit 367ba27). Phase 13+ tools deferred (see BL-547, BL-531, BL-532).
**Related:** BL-542 (context routing), BL-354 (executor-pull sidecar), BL-531 (multi-turn loops), BL-540 (project state).

**Problem:** All helper models receive a single compiled context snapshot at call time and cannot request additional information. If the supervisor needs to check what changed in the last delegation before approving a risky action, or the planner needs to see a past decision before planning, they simply don't — the result is lower quality decisions with no recourse.

**Goal:** Give the Supervisor and Planner a tool-calling loop (`SupervisorToolRunner`) where the LLM reasons about what context it needs and calls tools on demand. Two-tier context model: Tier 1 (slow-changing base: spec, plan, decision log) assembled once per turn; Tier 2 (action-specific) pulled via tool calls based on the LLM's own reasoning.

**Phase 12 tool set (P12-003):**
- `get_project_state()` — decisions, risks, hot areas from `project_state.json`
- `get_delegation_history(spec_path, n)` — last N delegation summaries + files changed
- `read_file(path)` — file content (truncated to budget)
- `get_diff(delegation_id)` — unified diff from a past delegation
- `get_reviewer_findings(files)` — classified findings for specific files (available after P12-004)

**Phase 13+ tool set (deferred):** `search_past_decisions(query)` (RAG over decision history), cross-project queries, full `HelperToolRunner` for clarity/reviewer roles, sidecar HTTP tool server for executor (BL-354 full).

---

### BL-533: Supervisor agent loop unified (`supervisor_loop_*`)

**Status:** `done` — 2026-06-20. **P11-009 shipped** — supervisor agent loop unified (`supervisor_loop_*` event family + wiring). Remainder: live multi-turn rerun wiring in `mcp_server` follow-up (tracked elsewhere).

**Source:** Phase 11 close — [PHASE11_MVP.md](../PHASE11_MVP.md) P11-009.

---

### BL-540: Persistent project state — cross-delegation planner notebook

**Status:** `done` — 2026-06-21. Phase 12 P12-002 shipped (v1 store; commit 16dfe7b). Full corpus/RAG → Phase 13+.

**Problem:** The Planner has no memory of what was built two sessions ago, what decisions were made, or what risks were surfaced. Every delegation starts from scratch regardless of project history.

**Goal:** A `project_state` object stored in `~/.mcp-coder/projects/<key>/project_state.json` that persists across sessions and is maintained by the Planner. Contains: what the project is, decisions made and why, current "hot areas", open risks / known gaps, and a compact rolling summary (≤ 2k tokens) that fits into every helper's context without blowing budget.

**Lifecycle:** Before delegation Planner reads project state; after delegation Planner updates it; reviewer findings can be promoted to risks (BL-541); supervisor escalation patterns noted; host can add/edit entries via a future `update_project_state` MCP tool.

**Invariant:** Project state must be compact enough (~2k tokens) that all helpers can receive it without dominating their budget. Not a log — a living summary. Old detail is summarised or pruned.

---

### BL-541: Reviewer findings feedback loop — close the loop across delegations

**Status:** `done` — 2026-06-21. Phase 12 P12-004 shipped (commit 604f317). Tier-2 epic review → Phase 13+.

**Problem:** The tier-1 reviewer (`reviewer_pass`, shipped P11-005) runs after each executor turn and appends its findings to the spec report. But that's where the chain ends — findings are written to a file that no subsequent delegation reads.

**Goal:** Close the feedback loop so reviewer findings actually influence future work:
1. `prior_review_notes` in planner context — after a delegation completes, reviewer findings are summarised and stored alongside the spec; next delegation's planner gets them injected.
2. Serious findings → project state — findings above a severity threshold are promoted to `project_state.open_risks` (BL-540).
3. Supervisor can consult reviewer history — `reviewer_history_summary` field included in supervisor's context when relevant (BL-529 extension).

**What this is NOT:** Not a re-delegation trigger. Not automated re-work. Reviewer is advisory — findings surface to Planner and state, not auto-fix.

---

### BL-542: Dynamic context routing — two-tier Supervisor/Planner context model

**Status:** `done` — 2026-06-21. Phase 12 P12-003 shipped (SupervisorToolRunner; commit 367ba27).
**Related:** BL-530 (mechanism), BL-540 (project state), BL-541 (reviewer findings).

**Problem:** The Supervisor and Planner often need context that spans multiple sources (project state, past delegation outcomes, reviewer findings, specific files) and the right selection depends on what they're doing at that moment. A pre-assembled fixed context slice misses the adaptive nature of the need.

**Goal:** The two-tier context model (D-ARCH-11): Tier 1 (slow-changing, assembled at turn start) + Tier 2 (on-demand via the Supervisor's own tool calls based on its reasoning). BL-530 is the mechanism; BL-542 is the design decision about which sources matter and how they compose.

**Constraint:** All tool calls logged as `supervisor_tool_call` trace events. Budget enforcement: total retrieved context stays within the role's D-ARCH-1/11 budget. Max 3 tool rounds per decision call (configurable).

---

### BL-544: Supervisor pause/resume — stateful agent across multiple delegate_to_agent calls

**Status:** `done` — 2026-06-21. Phase 12 P12-001 shipped (implicit resume P12-ISS-001; singleton P12-ISS-002; commit 16dfe7b+). Phase 13 P13-016 added clarity-block auto-resume.
**Related:** BL-528 (late-answer resume, specific case), BL-351 (SupervisedIO), BL-543 (context lifecycle), BL-350 (outer-loop continuation).

**Problem:** When the Supervisor escalates to the host mid-loop, the current model aborts the delegation and returns `needs_input`. The next `delegate_to_agent` call is a completely fresh start: clarity, spec_validation, context_compile, planner_pass all re-run from scratch. This breaks real multi-step work.

**Goal:** A general pause/resume mechanism. On escalation, the Supervisor serializes its full state. The host gets a `resume_token`. When the host calls `delegate_to_agent` again with that token, the Supervisor resumes from exactly where it paused — no re-running of pipeline stages already completed.

**Supervisor state (serialized on pause):**
```
SupervisorState {
    resume_token, spec_path, turn_index, plan, decision_log,
    completed_turns: [{files_changed, output_tail, reviewer_findings}],
    pause_reason, questions, context_ref, paused_at, expires_at
}
```
Stored in `~/.mcp-coder/projects/<key>/supervisor_states/<resume_token>.json`.

**Resume call:** skips clarity_check, spec_validation, context_compile, planner_pass, completed executor turns; loads state; injects host's answer into continuation brief (BL-543); Supervisor may ask Planner to revise plan; runs turn N.

**Phase 13 P13-016 addition:** Clarity-blocked preloop delegations now auto-resume on the next host return (no `answer` needed), emitting `lifecycle_start(resumed=true)` + `supervisor_resumed(clarity_block_reentry)`. Escalation pauses remain answer-gated (see BL-553 watch item).

---

### BL-545: Supervisor-owned executor session lifecycle (v1 — control plane)

**Status:** `done` — 2026-06-21. BL-545 v1 shipped (commit 2d7307b). Smart adaptation → BL-546 (deferred).
**Related:** BL-544 (pause/resume), BL-543 (context lifecycle), BL-546 (deferred adaptation), P12-ISS-002/003 (shipped interim fixes).

**Problem:** Aider session lifetime is currently controlled by `session_policy` keyed on the **host Cursor session ID** — an external signal that has nothing to do with the project's needs. Wrong owner; stale session after pause/resume.

**Goal (v1 — infrastructure-first):** Put the *control* of executor-session reset in the Supervisor and wire the plumbing end to end. **Not** smart context adaptation — keep current session/context behavior except where correctness forces a reset.

**v1 scope:** Extend `ExecutorFn` with a `reset_session` hint. `SupervisorAgent` signals `reset_session=True` only when: first turn after a resume (`_resumed_from_pause`) — correctness requirement; or optional every-N turns via `MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY` — default OFF. On reset, v1 only calls `drop_coder(mcp_session_id)`; existing Coder creation path rebuilds context exactly as today.

**Interim fixes (shipped):** P12-ISS-002 `drop_coder` on pause; P12-ISS-003 resume path receives acquired `mcp_session_id` after `SessionStore().acquire(...)`.

**Deferred → BL-546:** hot-area drift, `session_policy` as Supervisor hint, token-window signals, smarter context rebuild on reset.

---

## Context & RAG

### BL-002: RAG / cross-session memory (Phase 5 compile-push slice)

**Status:** `partial` — Phase 5 compile-push slice done (2026-06-13). P5-001…P5-004 + P5-006 dogfood fix; optional P5-005 capstone deferred (→ BL-366). Remaining gaps tracked in deferred.md (BL-354, BL-356–357, BL-365–366).

**Shipped:** Delegation RAG indexed post-delegate; wired into builder + `rag_retrieval` (P5-002). Workspace-file RAG: `workspace_rag.db`, `index-workspace`, `search files`, picker/builder hints (P5-003…P5-004). Defaults on (`builder_history_rag`, `workspace_file_rag`, `workspace_file_hints`).

**Living design note:** [notes/retrieval-and-rag-strategy.md](../notes/retrieval-and-rag-strategy.md)
**Code:** `core/rag/`, `core/config/rag.py`, `core/cli/search.py`, `core/cli/index_workspace.py`

**Shipped CLI/MCP toolset (reference):**

| Capability | CLI | MCP |
|---|---|---|
| Search delegations | `search delegations`, `rag search` | `rag_search` |
| Search workspace files | `search files` | `workspace_search` |
| Index workspace | `index-workspace` | — |
| Backfill delegation index | `rag index` | auto on delegate |
| Builder retrieval | `delegate`, `inspect-context` | `delegate_to_agent` |

**Corpus decisions (locked Phase 4):** Workspace source files (primary, hash + LLM summary + FTS5); delegation records (4+, FTS5 when scale hurts); decision log (5, structured exit notes → FTS5); spec files (skip — grep); chat transcripts (skip raw — revisit via BL-356 curated digests); cursor rules/config (skip — direct read).

**What we explicitly don't do (Phase 4):** No sub-file chunking; no vector embeddings (FTS5 BM25 sufficient); no delegation history in same DB; no raw chat transcript indexing.

---

## Observability & logging

### BL-353: LLM boundary observability — full pass-through logging

**Status:** `done` — 2026-06-16. Phase 9 completes this item. Phases 6+7+8+9 fully shipped: P6 helpers/tokens, P7 executor step events + compile provenance, P8 Aider inner-loop + thinking tokens, P9 write-always + universal proxy + context blob + model registry + policy_applied. BL-367 closed.

**Problem:** A full `delegate_to_agent` run appends one `delegations.jsonl` row — but most wire traffic was missing or only inferable. Hard to answer: "What exact prompt did the builder LLM see?" "What did Aider get on turn 3?"

**Goal:** One backend-neutral pass-through at the LLM boundary — every completion crosses a shared hook. Plus a compile provenance bundle so each LLM call's inputs are attributable to pipeline stage.

**Mechanism:** `litellm.success_callback` at MCP startup; thin `completion()` wrapper all roles use. Coverage: executor (all Aider turns), context_builder, architect_pass, spec_validation, test-model. Correlation via `contextvars`: `delegation_id`, `role`, `pipeline_phase`, `step_index`, optional `parent_call_id`.

**Compile bundle:** Per delegate, structured refs + hashes: `mechanical_brief`, `builder_input`, `builder_output`, `architect_*`, `validation_*`, `final_executor_prompt`, `context_package` entry tiers — "what came from what step" without re-parsing one blob.

**Host transcript provenance:** Extend `transcript_log_context`: `source_path`, `file_bytes`, `lines_parsed`, `last_source_line` (or byte offset range), `truncation_policy`, `bytes_dropped` — enough to slice the Cursor JSONL file for replay.

**Storage tiers:** Metadata always (model, role, tokens, latency, status, content hashes); Truncated bodies (default in trace file); Full bodies opt-in (`capture_llm_traces: full`). Supersedes ad-hoc `MCP_CODER_LOG_FULL_PROMPT` over time.

**Storage sketch:** `~/.mcp-coder/projects/<key>/sessions/<id>/traces/<delegation_id>.jsonl` (one line per LLM call + optional compile event); slim `delegations.jsonl` row holds pointers + hashes.

**Composes:** BL-333, BL-335, BL-350, BL-343, BL-354 (tool-call audit), BL-356 (lean refs). Design refs: [AGENTIC_LOOP_LOGGING.md](../OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md), [REASONING_TRACE_REUSE.md](../OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md).

---

### BL-367: Full-capture substrate — LlmGateway proxy + verbosity as display-only filter

**Status:** `done` — 2026-06-16. Phase 9 complete. P9-001 (write-always), P9-002 (context blob), P9-003 (universal proxy), P9-004 (replay CLI), P9-005 (GC), P9-006 (compare), P9-007–P9-010 (attribution, prompt_full, gzip fix, trace inspect), P9-011 (unified helper path + registry), P9-012 (generation params + policy_applied). All Phase 9 north-star criteria verified including BL-507 (thinking tokens at HTTP boundary).

**Origin:** Phase 6 exit review. Phase 6 shipped the observability seam and helper traces — but verbosity still controls what gets written to disk, meaning at `lean` or `standard` verbosity, prompt bodies and executor turns are permanently lost. Wrong direction: training-data quality, forensic replay, and debugging all require that nothing is ever silently dropped at write time.

**Architectural shift:**

| Phase 6 (current) | BL-367 target |
|---|---|
| `verbosity: lean` → writes hashes only; previews lost | Always write 100% to disk at the capture boundary |
| `verbosity: standard` → writes 500-char previews; bodies lost | Verbosity = display/export filter only (viewer, CLI, RAG promotion) |
| `verbosity: full` → writes bodies | Same result, but now the **default** for storage |
| Executor inner loop: opaque (no data) | Executor loop owned → every turn captured |
| Helpers via `litellm.completion` Route B | All LLM calls through unified `LlmGateway` proxy |

**Why "capture everything first, filter after":** the AGENTIC_LOOP_LOGGING bootstrap sequence says *log everything raw — no filtering — until you have enough data to train a classifier*. Filtering before that destroys signal you didn't know you needed. Storage cost for one heavy user is trivial (~10–18 MB/day raw). The current verbosity tiers remain useful as **retention / promotion policy** (what gets indexed into RAG, what gets exported for training) — not as a capture gate.

**What this required:** Unified `LlmGateway` completion proxy (BL-368); Executor loop ownership (BL-350); Write-always trace store; Context package blob storage; Systematic replay path.

**Verbosity after BL-367:**

| Tier | Storage | Viewer | RAG promotion | Training export |
|---|---|---|---|---|
| `lean` | 100% captured | Hashes + counts only | No | No |
| `standard` | 100% captured | Previews (500 chars) | Summaries | No |
| `full` | 100% captured | Full bodies | Full bodies | Opt-in tuples |

---

### BL-368: Unified LlmGateway completion proxy

**Status:** `done` — 2026-06-13. Phase 7 (P7-001) shipped for owned callsites. From P6-ISS-002.

**Origin:** Phase 6 shipped two capture paths — LiteLLM `success_callback` (Route A, executor + shim) and `owned_helper_llm.py` + `record_owned_completion()` (Route B, helpers). Both work but are transitional.

**Goal:** Replace per-backend capture hacks with `LlmGateway` (or equivalent) in `core/observability/` — single boundary for helpers, executor, `test-model`, and future backends. Scope broader than logging: tokens, trace bodies, reasoning, budget caps, redaction, rate limits.

**Prerequisite for:** BL-367 (full-capture substrate — proxy must exist before capture-everything-always makes sense).

**Acceptance (shipped for owned paths):**
- All owned LLM calls route through proxy (no direct `litellm.completion` scattered in engine modules)
- Executor path: proxy tap even when still using Aider adapter (until BL-350 owns loop)
- `NullObservability` / tests can swap proxy for no-op
- Callback becomes thin shim or removed once proxy covers all paths

**Related:** BL-350, BL-353, BL-367, BL-371, [AGENTIC_LOOP_LOGGING.md](../OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md).

---

### BL-369: CLI gateway bootstrap hardening

**Status:** `done` — 2026-06-14. Carry from P7-ISS-005.

**Problem:** Some CLI paths self-heal `LlmGateway` initialization ad hoc. Inconsistent and fragile if new CLI entry points are added.

**Goal:** Centralize gateway bootstrap in shared observability initialization so all CLI commands have a consistent owned LLM boundary without per-command guards.

**Shipped:** P8-003 (`core/observability/bootstrap.py`) with server + `test-model` bootstrap wiring and tests.

---

### BL-370: Host transcript byte-range provenance

**Status:** `done` — 2026-06-14. Carry from P7-ISS-006.

**Problem:** `validation_input` compile provenance includes `source_path` / `last_source_line`, but not precise `byte_start` / `byte_end`, limiting replay slicing precision.

**Goal:** Extend host transcript resolution metadata so compile events can include exact byte ranges for replay-grade provenance.

**Shipped:** P8-004 — transcript loader computes `source_byte_start`/`source_byte_end`; `validation_input` compile events emit byte ranges for replay slicing.

---

### BL-507: Thinking token capture verification

**Status:** `done` — 2026-06-16. Resolved in Phase 9. `MCP_CODER_EXECUTOR_REASONING_EFFORT=high` → `reasoning:{effort:high}` in proxy `raw_request`; `thinking_tokens=38` in `backend_llm_call.thinking_tokens`; `compare` CLI confirms `proxy_thinking=True, backend_thinking=True`. Litellm preserves thinking tokens through normalization; nothing is stripped.

**Problem:** Live dogfood of Phase 8 (`ObservableModel`) with `openrouter/anthropic/claude-sonnet-4` produced no `thinking_text`/`thinking_tokens` fields on `backend_llm_call` events. Phase 8 capture infrastructure was correct but the provider/litellm path may not expose these fields for that model/route.

**Goal:** Verify thinking field capture end-to-end with a known thinking-enabled model+provider path.

---

### BL-508: Universal internal HTTP proxy

**Status:** `done` — 2026-06-16. Phase 9 (P9-003 + P9-009 gzip fix). `LocalLlmProxy` running as a local HTTP server; all in-process litellm calls route through it; `proxy_llm_call` events with call_index attribution, raw request/response bodies, and `Accept-Encoding: identity` for readable payloads.

**Problem:** Phase 8's `ObservableModel` captures Aider inner-loop calls above litellm's normalization layer. Whatever litellm silently drops (thinking blocks, provider extensions) is permanently lost before we see it. No way to prove "100% captured" from user-space instrumentation alone.

**Goal:** A local HTTP proxy (`LocalLlmProxy`) that sits between litellm and the real provider. All in-process LLM callers route through it. Proxy captures raw HTTP request + response before litellm normalization, emits `proxy_llm_call` events, and cross-checks against Phase 8 `backend_llm_call` events.

**Architecture:** Async HTTP server on `localhost:PORT`; `api_base` globally overridden at bootstrap; model-prefix routing table from env vars; attribution via `delegation_id_var` + `step_index_var`; SSE tee for streaming; raw response body stored on `proxy_llm_call` event.

**Phase 10+ extension:** Same proxy extended to out-of-process backends (Claude Code, Codex, OpenCode) by pointing their base URL at it — no new proxy code.

---

### BL-510: Remove `should_log_full_prompt` write gate from delegation row

**Status:** `done` — 2026-06-16. Phase 9 (P9-008). `MCP_CODER_LOG_FULL_PROMPT` gate removed from `delegation_log.py` and `mcp_server.py`; `prompt_full` now written unconditionally; `should_log_full_prompt()` retired as a deprecated no-op.

**Problem:** `should_log_full_prompt()` (env var `MCP_CODER_LOG_FULL_PROMPT`) gates whether the executor prompt is written to the `prompt_full` field of the `delegations.jsonl` row. Separate write gate from the trace file verbosity gate fixed in P9-001, but violates the same D-P9-8 principle: write-always; no runtime gate on what reaches disk.

---

### BL-511: Model registry Stage 1 (front door + unified helper path + params + logging)

**Status:** `done` — 2026-06-16. Phase 9 (P9-011 + P9-012). 924 passed, 2 skipped. BL-507 end-to-end verified.
**Design note:** [notes/model-policy-layer.md](../notes/archive/model-policy-layer.md)
**Specs:** P9-011 (unify helper path + registry front door), P9-012 (params + weak model + logging)

**Problem:** Generation params (thinking/temperature/etc.) are set nowhere. Two helper paths emit `llm_call`; a third (`workspace_summarizer`, `spec_review`) bypasses the gateway and emits no trace event. Proxy confirmed `proxy_llm_call.raw_request` carries no `thinking` field. Model ID + budget are *already* centralized in `role_models.py` — reuse, do not rewrite.

**Architecture:** Single front door `model_registry.resolve(role, workspace) → CallParams` reusing `role_models` for id/budget; generation params + weak model layered on top with per-field `sources` provenance. One helper path (`LlmGateway`); `ExecutionEngine` stays pluggable; Aider is a read-only metadata source.

**P9-011 (refactor):** remove legacy direct-`Model()` helper calls (route through `LlmGateway`); create `model_registry.py` skeleton (id + budget only). Behaviour-neutral apart from new uniform logging.

**P9-012 (params + logging):** generation-param env vars; weak-model default-fill (Sonnet/Opus→Haiku, logged, opt-out via `=self`); wire `model.extra_params` + litellm kwargs; `policy_applied` on `backend_llm_call` + `llm_call`.

**New env vars (P9-012, all optional):** `MCP_CODER_<ROLE>_REASONING_EFFORT`, `_THINKING_BUDGET`, `_MAX_TOKENS`, `_TEMPERATURE`, `_TOP_P`, `_EXTRA_PARAMS` (JSON), `_WEAK_MODEL`. `reasoning_effort` is the portable thinking knob; `drop_params=True` always.

---

### BL-517: Executor `policy_applied` ignored params

**Status:** `done` — Phase 10 P10-004 shipped. Migrated from Phase 9 issue P9-ISS-007.

**What:** `_apply_executor_model_params` applies `reasoning_effort`, `thinking_budget`, `extra_params`, and `weak_model` to the Aider `Model` — but **not** `temperature`, `top_p`, or `max_tokens` (Aider owns those). Today `policy_applied()` can still log env-resolved values for those fields, implying they were applied.

**Resolution:** Add `"ignored": ["temperature", "top_p", ...]` (and optional `note`) to executor `policy_applied`.

**Workaround:** Force via `MCP_CODER_EXECUTOR_EXTRA_PARAMS={"temperature": 0.5}` — passed into Aider `extra_params` and forwarded by litellm.

---

### BL-519: `MCP_CODER_PROXY_ENABLED` env toggle

**Status:** `done` — Phase 10 P10-004 shipped.

**Problem:** `ensure_observability_bootstrap()` always starts `LocalLlmProxy` and rewrites `OPENROUTER_API_BASE` / `OPENAI_API_BASE` / `ANTHROPIC_API_BASE` to the local proxy URL. No env escape hatch to run litellm direct-to-provider without editing code or test hooks.

**Scope shipped:**
- `MCP_CODER_PROXY_ENABLED=0` (or yaml `local_llm_proxy: false`) skips proxy start and leaves provider `*_API_BASE` env vars untouched.
- Default **on** — preserves Phase 9 dual-capture behavior and north-star acceptance.
- When disabled: `proxy_llm_call` events absent; `backend_llm_call` + litellm callback paths still run (partial capture).
- Bootstrap + CLI paths share the same resolver (`core/observability/bootstrap.py`).

**Use cases:** isolate proxy routing bugs vs provider bugs; faster local iteration; CI scenarios that mock providers; emergency workaround if proxy misroutes a model prefix.

---

### BL-106: MCP live progress + logging notifications

**Status:** `done` (POF) — Phase 10 P10-002 shipped (`ctx.info` milestones + thread bridge). Capture→egress bridge + `report_progress` remain backlog follow-ups. Cursor chat rendering is host-version dependent.

**Problem:** Long `delegate_to_agent` runs show only a spinner in Cursor until the tool returns. mcp-coder emits brief stderr at start/end and writes full detail to disk — but does not send MCP protocol notifications mid-run. Users cannot see pipeline phase or executor step progress in the host UI.

**What (POF → MVP):**
1. Inject FastMCP `Context` into `delegate_to_agent`.
2. `ctx.report_progress(progress, total, message)` at pipeline milestones.
3. `ctx.info` / `ctx.log` for short redacted status lines (throttled).
4. Capture → egress bridge — subscribe to observability events already written to trace; map to live notifications.
5. Thread bridge — executor runs in worker thread; queue async `ctx.log` on MCP event loop.

**POF scope:** pipeline milestones only (~6–8 messages per delegation).
**MVP scope:** + executor step index + "edited `path`" highlights.

**Not in scope v1:** streaming raw Aider tokens into chat; duplicating Phase 9 trace bodies over MCP.

---

### BL-520: Live log tail / follow delegation

**Status:** `done` (POF) — Phase 10 P10-002 shipped (`mcp-coder logs tail` on trace JSONL with `--latest` / `--delegation-id`). `server.jsonl` filter + BL-160b tee remain backlog follow-ups.

**Problem:** Even with BL-106, host UIs vary (Cursor progress visibility flaky across versions). Operators need a reliable local view while a delegation runs without opening the full viewer.

**What:**
1. `mcp-coder logs tail` (or extend existing maintenance/log CLIs): `--delegation-id <id>` or `--follow latest`; tail `traces/<delegation_id>.jsonl` as new events append (enabled by Phase 9 write-always); optional tail `server.jsonl` filtered by `delegation_id`; optional tail executor tee file when BL-160b writes `sessions/<id>/executor_tee.log`.
2. Human-readable line format — one line per trace event (`compile_event`, `llm_call`, `proxy_llm_call`, `executor_stall`, etc.).
3. `make logs-tail` / docs pointer for dogfood workflow.

---

## Executor & backends

### BL-334: Backend prompt customization (system prompt prefix + edit-format control)

**Status:** `done` — Phase 10 P10-001 shipped (v0: env/yaml wiring + audit). Per-delegation override remains deferred to BL-512 Stage 2 (Phase 11).

**Origin:** We hand Aider a prompt, but Aider wraps it with its own system prompt (`main_system`), hard-coded example conversations, and a SEARCH/REPLACE `system_reminder`. We currently pass content only; we don't shape Aider's framing.

**Aider hooks available (no forking):**

| Hook | What it does | mcp-coder use |
|---|---|---|
| `model.system_prompt_prefix` | String prepended to Aider's `main_system` before the LLM call | Inject delegation-level constraints / persona / "respect spec contract" reminder |
| `Coder.create(edit_format=…)` | Selects edit format (editblock, whole-file, udiff, …) | Per-delegation or per-model edit-format choice |
| Subclass `gpt_prompts` | Replace `main_system` / `system_reminder` wholesale | Heavier; out of scope for v1 |

**Shipped scope (v1):**
- BL-334a: `core/config/` resolver for an optional executor system prompt prefix (env `MCP_CODER_EXECUTOR_SYSTEM_PREFIX` + yaml `executor_system_prefix`); applied via `model.system_prompt_prefix` in `aider_engine.py`. Default: none (byte-identical to today).
- BL-334b: Optional edit-format override (env/yaml `executor_edit_format`) passed into `delegation_coder_kwargs()` / `Coder.create()`. Audit chosen format in JSONL `context` block.
- BL-334c: Audit: record `system_prefix_applied: bool` and `edit_format` on the delegation record.

**Backend-neutral rule:** the *resolver* lives in `core/config/` (no Aider terms); the *application* (`system_prompt_prefix`, `edit_format`) stays in `core/engine/aider_engine.py` / `aider_runtime.py`. Other backends ignore unknown knobs.

---

### BL-351: Simulated interactive mode + host escalation (human intervention)

**Status:** `done` — Phase 10 P10-003 + Phase 11 P11-002 shipped: stall detect + structured `needs_input` plus supervised confirm handling (`SupervisedIO` + `DelegationSupervisor`, abort-on-escalate). Remainder deferred: mid-run async resume / outer-loop continuation in Phase 12 (now BL-544).

**Problem:** Headless Aider uses `InputOutput(yes=True)` — every confirm is auto-approved without mcp-coder judgment. When the model asks for files in prose, we fail the delegation rather than help. No path for the executor to route a decision back to the Cursor planner for human intervention inside a supervised delegate.

**Goal:** Replace blind `yes=True` with simulated interactive supervision:
1. Cheap supervisor (helper LLM or rules) handles routine prompts: add path as read, widen context, continue step, deny out-of-contract edit.
2. Re-compile context when supervisor approves expansion (BL-350, BL-347).
3. Escalate to host when supervisor is uncertain or policy requires human OK → return structured `needs_input` / `clarification_needed` (same pattern as BL-329 spec validation) so Cursor shows the question; planner answers; delegation resumes via retry / outer-loop step.

**Implementation sketches:**

| Sketch | Mechanism |
|---|---|
| **D — Supervised `InputOutput`** | Subclass Aider `InputOutput`: `confirm_ask` / prompts → supervisor LLM instead of `yes=True`; escalate → abort run with host payload |
| **Outer loop + host gate** | BL-350 route A: after each sub-run, supervisor inspects; auto-fix or return to Cursor before next step |
| **Async / long-running** | If human latency exceeds MCP timeout, persist "awaiting_host" state + resume token (BL-501 adjacency) |

**Why powerful:** Combines automation (cheap model handles 80% of "add `foo.py` as read") with human judgment for contract changes, risky shell, or ambiguous scope — without a real terminal REPL (BL-160d). Cursor stays the planner; mcp-coder owns the supervise → escalate → resume protocol.

---

### BL-354: Executor context tools (pull) — RAG/history/read during backend loop

**Status:** `done` — Phase 11 P11-003 v0 shipped (system prefix `/read` hint only, prompt-level behavior). Full sidecar HTTP tool server (Sketch B below) deferred to Phase 12.

**Dual model (intentional):**

| Mode | Who | When | Today |
|---|---|---|---|
| **A — Compile-push** | mcp-coder compiler + builder | Before `coder.run()` | **Default** — picker, tiers, brief, `fnames` |
| **B — Executor-pull** | Backend LLM during inner loop | Mid-run, model-chosen | **v0 shipped** — `/read` prompt hint; full tool server deferred |

**Goal:** Keep **A** as the baseline. Add **B** so the executor can organically fetch more context — RAG queries, delegation history, file excerpts, recent touches (BL-348/349) — via specialized read-only tools alongside normal edit/shell tools. Less mcp-coder micromanagement than BL-350; more model-driven than front-loading everything.

**Candidate tool surface (backend-neutral):** `search_delegations` / `rag_search`, `workspace_search`, `get_delegation_summary` / `get_file_history`, `read_path_excerpt`, `list_recent_files`, `ask_planner` / escalate (policy).

**Not in v1:** executor tools that widen `files_edit` without spec/policy; arbitrary shell; duplicating planner-only MCP surface wholesale.

**Implementation routes (try in order):** CLI subprocess from Aider; Backend function tools (native tool schema); BL-340 Cursor SDK (cleanest first backend for real tool calling).

**vs BL-350:** Outer loop = mcp-coder controls steps and re-compile. BL-354 = mcp-coder offers tools; backend LLM decides when to pull. Composable: compile-push defaults + pull on demand; supervisor loop for hard cases.

---

### BL-335: Per-role token audit in delegation JSONL

**Status:** `done` (partial) — P6-002/P6-008 closed live null-token gap for helpers; executor via `aider_output_parse`. Remaining: per-step executor token audit inside Aider inner loop → BL-350 (deferred).

**Shipped (Phase 6):** LiteLLM callback + `owned_helper_llm.py` Route B; dogfood v3 `f9cb07fc` — all four `model_roles.*.tokens` non-null.

**Why mandatory later:** BL-162 Stage 2, BL-333, BL-002 RAG cost budgeting, BL-353 observability — per-role usage now available at delegation level; inner-loop granularity needs BL-350.

---

## Models & policy

### BL-521: Pre-delegation spec clarity pass (Phase 11 P11-001)

**Status:** `done` — Phase 11 P11-001 shipped 2026-06-19. Remainder: cross-session intent history in clarity context → Phase 12.

**Problem:** Delegations start immediately from whatever spec text is given. If the task is ambiguous, the executor either stalls (wastes 2–3 minutes) or produces a misaligned output. No pre-flight check that verifies the task is clear enough to delegate with confidence.

**Goal:** A cheap LLM call before delegation checks whether the task description and spec Files contract are sufficient. If key decisions are missing or ambiguous, return `clarification_needed` with 2–3 targeted questions. Only run the executor after the task is validated as `CLEAR`.

**Design:**
- New pipeline phase `clarity_check` inserted before `compile` when `clarity_pass: true` (spec yaml) or `MCP_CODER_CLARITY_PASS=1` (env)
- Cheap model (Flash/Haiku tier), small context: task description + spec Files section + last 3 delegation titles in session (~3k tokens)
- Prompt: "What is unclear or missing? List at most 3 specific questions. If nothing is unclear, return CLEAR."
- On `CLEAR` → proceed normally (latency overhead = one cheap LLM call, ~100ms)
- On questions → return `clarification_needed: [...]` early (same field shape as BL-329 spec validation)
- Distinct from BL-329: validation checks spec coherence; clarity pass checks task completeness and intent
- Trace event: `clarity_check_result: {status: clear | clarification_needed, questions: [...]}`

---

## Specs & workflow

### BL-329: Pre-delegate spec validation + clarifying loop

**Status:** `done` — P4-009 (2026-06-09). Opt-in `spec_validation`; `clarification_needed` blocks executor; rules v14.

**Phase 5 dogfood note (P5-ISS-004):** When validation blocks (`needs_input`), the compile pipeline — including `rag_retrieval` — does not run; `context_refs` stays empty. This is expected but easy to misread as a RAG regression. Session `1432fc02-c6b1-4452-aa28-261ce77f896b` entries #2–#4. Optional: log `rag_retrieval: skipped (spec_validation_blocked)` in `delegation_pipeline` for blocked delegates (BL-353 observability → tracked as BL-364).

**Goal:** Before delegating, the context builder reads the host session transcript and checks whether the spec is well-aligned with the current conversation. If ambiguous or contradictory, return a `clarification_needed` list to Cursor instead of delegating — forcing the host to answer before retrying.

**Mechanism:**

| Step | Detail |
|---|---|
| Builder reads `host_transcript` | Uses existing P1-140 infra |
| Cheap-LLM coherence check | Same model as P4-001b; checks spec task + constraints against recent conversation decisions |
| `clarification_needed: [...]` response | New MCP response field; non-empty = delegation withheld; Cursor answers + retries |
| Normal path | Coherence check passes → transparent, no user-visible latency change |

**New MCP response field:** `clarification_needed: list[str] | null`

**Relation to existing items:** P4-001b — same builder call; BL-161 / P4-020 — P4-009 is pre-Aider validation; BL-161 is post-validation architect pass — they compose; BL-324 — judgment loop is post-delegation; this is pre-delegation; together they close both ends.

---

## Storage & lifecycle

### BL-322: Workspace history — delegation-granularity version control (Wave 1)

**Status:** `partial` — Wave 1 shipped (BL-322a–f, P3-322a–322f); restore/fork sub-items deferred (BL-322g/h).
**Full design:** [docs/OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md](../OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md)

**Problem addressed:** P2-ISS-002 (`files_changed` misses new files without git); strict scope enforcement that reports violations but leaves workspace dirty; inability to time-travel to any MCP call boundary across a project lifecycle.

**Core insight:** mcp-coder can own a lightweight, delegation-scoped version control layer — SQLite delta store, independent of git, invisible to the user, automatic. Hash the whole workspace before each delegation; store unified diffs (not full copies) of what changed; accumulate checkpoints across sessions. Purpose-built for the "what did the AI do between calls?" question that no existing tool answers at this granularity.

**Why it matters:** AI coding tools either ignore the audit problem, force auto-commits (pollutes git), or depend on git (fails for untracked files, dirty workspaces, non-git repos). This approach is non-invasive — user's git, WIP, and untracked files are untouched — and works at exactly the right granularity (per delegation call = per human review opportunity).

**Storage:** `~/.mcp-coder/projects/<key>/workspace_history.db` — SQLite, stdlib only. Delta + content-addressable blobs. ~6–10MB for months of work on a typical project.

**Phase 3 sub-items:**

| Sub | Item | Status |
|---|---|---|
| **BL-322a** | Workspace hash snapshot (manifest) | done |
| **BL-322b** | Content snapshot for contract files | done |
| **BL-322c** | Post-delegation gateway (diff vs policy) | done |
| **BL-322d** | Diff in MCP response + CLI history | done |
| **BL-322e** | Checkpoint metadata (dataset labels) | done |
| **BL-322f** | History inspect (browse DB) | done |
| **BL-322g** | Restore to checkpoint | deferred |
| **BL-322h** | Checkpoint fork / sandbox try | deferred |

**Shipped undo (not restore):** `revert_to_before` + CLI `history revert` (BL-322b) undoes one delegation on selected paths — distinct from BL-322g "go back to known-good state."

**Snapshot scan exclusions:** `node_modules/`, `.venv/`, `__pycache__/`, `.git/`, `dist/`, `build/`, `.mcp-coder/`; binary extensions; size cap default 1 MB (`MCP_CODER_SNAPSHOT_MAX_FILE_MB`). No `.gitignore` dependency.

**Rollback design (BL-322b + BL-322c strict):** Before delegation, snapshot contents of `files_edit` files. Aider runs, also modifies a violation file. Post-gate (strict): violation file reverted to pre-delegation content; contract-allowed files accepted; created non-contract files reverted. Result: workspace has ONLY the contract-allowed changes.

---

### BL-320: Failed-delegate attempt archive (spec-adjacent)

**Status:** `done` — Phase 3 Wave 2 rules-only (P3-320); P3-ISS-002 closed.

**Problem:** Planner-facing `specs/reports/*.md` tracks current step status; failed retries are either buried in Run log (truncated) or only in JSONL. No first-class "attempt history" per step.

**Shipped:**
- BL-320a: Workspace config `retain_failed_attempts: true` (default off or `on_failure_only`)
- BL-320b: Write `.mcp-coder/specs/attempts/<spec_id>/<delegation_id>.md` on failed implement/review
- BL-320c: Main report stays lean: Status + latest success; Attempts section lists links to failed archives (last N)
- BL-320d: Optional MCP tool `list_delegation_attempts(spec_path)`

---

## Reliability & error handling

### BL-309: Delegation hardening — partial shipped

**Status:** `partial` — P1-ISS-012 (`wontfix-p1` at Phase 1 exit). BL-309g `conversational implement` partial done P1-151 (`infer_run_success` rejects "add files to chat"). Remaining subs (BL-309a–f) still deferred — see deferred.md.

---

### BL-310: Planner verify / report status split — partial shipped

**Status:** `partial` — BL-310b/c done P4-010 (2026-06-09); BL-310a deferred.

| Sub | Item | Status |
|---|---|---|
| BL-310a | Report status `verified_ok` (planner sets?) vs MCP `delegated_ok` / `reviewed` / `blocked` | deferred |
| BL-310b | Optional MCP hook: run `pytest` post-implement | done P4-010 — `auto_verify` opt-in; `verify_result` on MCP + JSONL |
| BL-310c | `outcome: partial` when edits applied but tests fail | done P4-010 — `apply_verify_outcome()` |

---

### BL-311: Read-deps from spec Files section — done

**Status:** BL-311a done (P2-110); BL-311b done (P3-311, 2026-06-09); BL-311c deferred.

| Sub | Item | Status |
|---|---|---|
| BL-311a | Warn in tool response when `mode=implement` and spec Files paths ⊄ `target_files` | done P2-110 |
| BL-311b | Auto-merge read-only paths into delegate context from spec Files | done P3-311 |
| BL-311c | Cursor rule generator: split Files into "edit" vs "read" in delegate call hints | deferred |

---

### BL-314: Honest delegation file reporting — partial done

**Status:** `partial` — partial done P1-152 (2026-06-06).

| Sub | Item | Status |
|---|---|---|
| BL-314a | `files_changed` = all git-touched paths during delegation | done P1-152 |
| BL-314b | `files_unexpected` in tool response + JSONL | done P1-152 |
| BL-314c | Spec report Scope expansion section when `files_unexpected` non-empty | deferred |
| BL-314d | Tie to `edit_scope: strict` enforcement | deferred → BL-315 |

---

### BL-315: `edit_scope` + spec Files YAML — partial done

**Status:** `partial` — BL-315a/b done P2-115; BL-315c → P2-200 context compiler.

| Sub | Item | Status |
|---|---|---|
| BL-315a | YAML front matter: `files_edit`, `files_read` | done P2-115 |
| BL-315b | `edit_scope: discover` \| `strict` — post-check `scope_violation` | done P2-115 |
| BL-315c | Builder reads spec as primary contract when `spec_path` set | P2-200 |

---

## Phase 1 / early done items (one-liners)

| ID | Item | Completed |
|---|---|---|
| BL-101 | Transcript tail cap | 2026-06-05 — P1-140 (`MCP_CODER_MAX_TRANSCRIPT_BYTES`) |
| BL-125 | Persistent MCP server log | 2026-06-05 — P1-125 |
| BL-305 | Server log scope | 2026-06-05 — P1-125 (default `global`; `project` / `both` in yaml/env) |
| BL-150 | Spec-based delegation (v0 + v2 + review loop) | 2026-06-05 — P1-150/151 |
| BL-203 | Cursor agent-transcripts | 2026-06-05 — P1-120 + P1-140 |
| BL-154 (partial) | Usage telemetry (preflight + actual + static cost) | 2026-06-06 — P2-120; window budget enforcement → P2-220 |
| BL-319 | Static model rates table (deferred: dynamic refresh) | 2026-06-06 — P2-120 (`resources/model_rates.yaml`); dynamic refresh → deferred.md |
| BL-342 | `test-model` list/select/all | P4.5-001 — `test-model --all` pings each role sequentially, pass/fail table |
| BL-343 | Structured delegation log viewer | Phase 9 (P9-013 done, 2026-06-17) — v2 boundary-table viewer with Python middleware |
| BL-371 (partial) | Backend-specific interception strategy | Phase 8 delivered for Aider (P8-001 + P8-002 + P8-006); non-Python backends → deferred.md |
| BL-509 | Content-addressable dedup for trace bodies | Post-Phase 9 stance: write raw inline text; optimization deferred → deferred.md |
| BL-533 | Supervisor agent loop unified (`supervisor_loop_*`) | Phase 11 P11-009 — done; live multi-turn rerun wiring in `mcp_server` follow-up |

---

## Removed / superseded (kept for audit, no longer active)

| ID | Item | Notes |
|---|---|---|
| BL-402 | SpecStory freshness window | N/A — SpecStory replaced by Cursor host transcript (P1-140) |
| BL-505 | SpecStory `.specstory/history/*.md` | Replaced by Cursor host transcript (P1-140) |
