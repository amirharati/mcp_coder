# Architecture overview

**Status:** Living — update as shipped decisions change.  
**How to use:** Read as a structural reference after [how-it-works.md](../how-it-works.md). That doc is the *operator* mental model; this one is the *layer map and design decisions*. Deeper per-subsystem docs live alongside this file.

---

## Layer map

```
┌───────────────────────────────────────────────────────────────────┐
│  Host / Planner                                                   │
│  Cursor (only host today) — rules, chat, specs, tool calls        │
│  core/host/   cursor.py  cursor_rules.py  cursor_transcript.py    │
└──────────────────────────────┬────────────────────────────────────┘
                               │  MCP tool calls (stdio JSON-RPC)
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  MCP server                                                       │
│  server/mcp_server.py                                             │
│  • Registers tools: delegate_to_agent, inspect_context,           │
│    answer_delegation_question, get_server_status,                 │
│    list_delegations, get_delegation_diff, get_checkpoint_detail,  │
│    get_file_history, rag_search, workspace_search                 │
│  • Orchestrates the delegation pipeline                           │
│  • Writes JSONL audit record + updates history DB after each run  │
└──────────────────────────────┬────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   ┌──────────────┐   ┌──────────────────┐   ┌──────────────┐
   │ Context      │   │ Spec & Contract  │   │ Workspace    │
   │ Compiler     │   │ core/specs/      │   │ History      │
   │ core/context/│   │                  │   │ core/        │
   │              │   │ read, sections,  │   │ workspace/   │
   │ picker →     │   │ contract,        │   │              │
   │ assemble →   │   │ policies,        │   │ manifest,    │
   │ brief layers │   │ outcome labels   │   │ snapshot,    │
   └──────┬───────┘   └──────────────────┘   │ gateway,     │
          │                                   │ history_db   │
          ▼                                   └──────────────┘
   ┌──────────────────────────────────────┐
   │ Supervisor Agent Loop                │
   │ core/engine/supervisor_agent.py      │
   │                                      │
   │ SupervisorAgent owns all             │
   │ post-planning control flow:          │
   │   • begin() / begin_turn()           │
   │   • run Aider (executor)             │
   │   • run reviewer check               │
   │   • per-turn decision:               │
   │     done | rerun_aider |             │
   │     escalate_host                    │
   │   • complete_turn() / finish()       │
   │   • emit supervisor_loop_* events   │
   └──────────────┬───────────────────────┘
                  │
                  ▼
   ┌──────────────────────────────────────┐
   │ Execution Backend                    │
   │ core/engine/aider_engine.py          │
   │                                      │
   │ Aider (only backend today)           │
   │ SupervisedIO — routes confirm_ask    │
   │   to DelegationSupervisor LLM        │
   │   (approve / deny / abort /          │
   │    escalate)                         │
   └──────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────┐
   │ Observability                            │
   │ core/observability/                      │
   │                                          │
   │ ObservabilityBackend (base.py)           │
   │   LocalObservability (local.py)          │
   │   NullObservability  (null.py)           │
   │                                          │
   │ LlmGateway + LiteLLM callback shim       │
   │ trace.py → per-delegation trace events   │
   │   llm_call, proxy_llm_call,              │
   │   backend_llm_call, compile_event,       │
   │   tool_call, supervisor_loop_*,          │
   │   supervisor_turn_*, supervisor_decision │
   │ stats.py → maintenance stats             │
   └──────────────────────────────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────────────────────┐
│  Storage (two scopes)                                             │
│                                                                   │
│  <workspace>/.mcp-coder/          IN repo (user-visible)          │
│    config.yaml    specs/    reports/    session.json              │
│                                                                   │
│  ~/.mcp-coder/projects/<sha256>/  OUTSIDE repo                    │
│    workspace_history.db    delegation_rag.db    workspace_rag.db  │
│    sessions/<id>/                                                 │
│      delegations.jsonl    lean audit row (~12 KB, pointers only)  │
│      traces/<id>.jsonl    helper + executor + compile events       │
└───────────────────────────────────────────────────────────────────┘
```

---

## Key architectural decisions (locked)

These are concrete decisions baked into the codebase. Changing them would require significant rework.

### D-1: MCP stdio, not HTTP
`mcp_server.py` runs as a stdio process registered in Cursor's `mcp.json`. All tool calls are JSON-RPC over stdin/stdout. Consequence: stdout is owned by MCP — `core/engine/stdio_isolation.py` captures Aider's output so it doesn't corrupt the transport.

### D-2: Adapter seams (host + backend)
`core/host/` and `core/engine/` are the only places where Cursor- or Aider-specific code is allowed. Everything else is adapter-neutral:
- `HostContextProvider` (`core/host/base.py`) — what a host must provide
- `ExecutionEngine` (`core/engine/base.py`) — what a backend must implement
- `factory.py` in each — maps string names to implementations

**Invariant:** No Aider API terms (`fnames`, `yes=True`, `Coder`) outside `aider_engine.py` + `aider_runtime.py`. No Cursor path logic outside `core/host/`.

### D-3: Home vs workspace storage split
| Location | What | Why |
|----------|------|-----|
| `<workspace>/.mcp-coder/` | User-owned: config, specs, reports | User checks in, edits, reads |
| `~/.mcp-coder/projects/<key>/` | System-owned: JSONL, history DB, RAG | Never committed; survives workspace moves |

`project_key` = `sha256(resolved_workspace_path)`.

### D-4: Spec is the contract
The spec's `files_edit` list is the only way a path enters `edit-full` tier and Aider `fnames`. The file picker **discovers** read candidates but **never grants edit rights**. That invariant is enforced at compile time in `file_picker.py` + `assemble.py` and checked post-hoc by `post_gateway`.

### D-5: One model per role
Every LLM call is tagged with a `role` (`executor`, `planner`, `context_builder`, `supervisor`, `reviewer`, `clarity_check`, `spec_validation`). Each resolves its model independently via `model_registry.resolve()` — precedence: host `model_policy` arg → env var → `config.yaml` → built-in default. All calls are audited in `model_roles` JSONL with live token counts and a `policy_applied` provenance block on every `backend_llm_call` and `llm_call` event.

### D-6: Snapshot-based file diffing (not git)
Pre/post SHA-256 manifests of the workspace bracket the executor. `files_changed` comes from the manifest diff, not from git or from what Aider reports. This works on untracked files, gitignored paths, and repos with no git history. Git is a soft dependency only.

### D-7: JSONL as the audit record
One record per delegation, appended (never mutated) to `delegations.jsonl` under the session dir. It is the canonical truth. Everything else — history DB, RAG, spec reports — is derived from or supplementary to the JSONL record.

### D-8: Optional stages fail open; validation blocks closed
Helper LLM calls (clarity, planner, builder, reviewer) are all non-fatal on failure. Spec validation is the only stage that can stop the pipeline before spending executor tokens — and only when it finds genuine ambiguity, not on error.

### D-9: Supervisor owns post-planning control flow
After the pre-handoff pipeline (spec_validation → clarity → planner → context_builder), the `SupervisorAgent` takes over. It runs the executor, collects reviewer results, and decides per-turn whether to finish, rerun, or escalate to the host. The host does **not** see intermediate turns. Supervisor events are the single source of truth for post-planning lifecycle — there is no separate outer-loop in `mcp_server.py`.

### D-10: Context frugality rule
Every LLM call gets a purpose-built context bounded to its role. No call sees full session state:

| Role | Budget | What it sees |
|------|--------|--------------|
| Clarity pass | ~3k tokens | Task + spec Files + last 3 delegation titles |
| Planner | ~8k tokens | Spec + file map + repo outline |
| Builder brief | ~16k tokens | Spec + relevant files (compiled) |
| Executor | ~32k tokens | Full context package |
| Supervisor (per-turn) | ~2k tokens | Spec contract + question + decision log + output tail |
| Tier-1 reviewer | ~8k tokens | Diff + changed files + acceptance criteria |

---

## Delegation lifecycle (concrete path through code)

For `mode=implement` with a valid spec, `mcp_server.py` runs these in order:

```
delegate_to_agent()
  │
  ├── host context: core/host/cursor.py → transcript path, session hint
  ├── session: core/session/ → new or reuse Coder instance
  │
  ├── spec_read           core/specs/read.py, sections.py → SpecRead
  ├── spec_validation*    core/engine/spec_validation_llm.py  [can BLOCK]
  ├── clarity_check*      core/context/clarity_llm.py         [can BLOCK]
  │
  ├── file_picker         core/context/file_picker.py → CandidateFilesResult
  ├── rag_retrieval*      core/rag/builder_retrieval.py → context_refs + brief section
  ├── context_assemble    core/context/assemble.py → ContextPackage
  ├── planner_pass*       core/engine/planner_pass_llm.py  (was: architect_pass)
  ├── builder_llm*        core/engine/context_builder_llm.py
  │
  ├── SupervisorAgent.begin()    ← supervisor loop opens here
  │     │
  │     └── turn 1:
  │           ├── EXECUTOR         core/engine/aider_engine.py
  │           │     └── translate_context_package() → fnames + prompt
  │           │     └── Coder.run(prompt) via SupervisedIO
  │           │           └── confirm_ask() → DelegationSupervisor LLM
  │           │                 (approve / deny / abort / escalate)
  │           │     └── workspace snapshot post-run
  │           │
  │           ├── reviewer_pass*   core/engine/reviewer_llm.py (advisory)
  │           │
  │           └── supervisor decision: done | rerun_aider | escalate_host
  │
  ├── SupervisorAgent.finish()   ← supervisor loop closes here
  │
  ├── post_gateway        core/workspace/gateway.py
  │     └── diff snapshots → files_changed, files_unexpected
  │     └── scope_violations if edit_scope: strict
  │
  ├── spec_report         core/specs/write.py → append to reports/
  ├── auto_verify*        core/verify/ → run command, update outcome
  │
  └── audit
        ├── core/observability/local.py → build_delegation_record()
        │     delegation_log.py → append delegations.jsonl (lean row)
        │     trace.py → sessions/.../traces/<id>.jsonl (all events)
        │     training_capture.py → -training.json (opt-in)
        ├── core/workspace/history_db.py → checkpoint row + diffs
        └── core/rag/ → index delegation + incremental workspace files (FTS5)
```

`*` = opt-in or conditional; `rag_retrieval` runs when `context_builder` on and RAG flags on (default on). Clarity and spec_validation are default on; planner_pass and reviewer_pass are default on.

---

## Context compiler in brief

The compiler converts spec + workspace → a structured `ContextPackage` that the backend adapter translates to executor inputs (Aider today: `fnames` + `prompt`).

```
spec contract
    + target_files hints        →  file_picker      →  CandidateFilesResult
    + symbol scan (rg / py fallback)                     ranked paths + tiers
    + repo map (def/class outlines)
                                →  assemble_context  →  ContextPackage
                                     PathEntry per file:
                                       tier: edit-full | read-full | read-excerpt | map-only | pointer
                                       bytes, excerpt_path
                                →  budget            →  trim read entries to fit
                                →  rag_retrieval*    →  ## Relevant prior work + context_refs
                                →  builder_llm*      →  prepend ## Builder brief
                                →  planner_pass*     →  prepend ## Planner plan
                                →  translate_context_package()
                                     fnames = [edit-full paths]
                                     prompt = brief + fenced read blocks + map block
```

The **mechanical brief** (paths, tiers, task, context_summary) is never rewritten by any LLM. LLMs only **prepend** above a separator line. See tutorial T-04 for a hands-on walkthrough.

---

## Role model (all active LLM roles)

Each role has its own model, budget, and trace audit line. Model precedence: host `model_policy` arg → env var → `config.yaml` → built-in default.

| Role | Code name | Default model tier | Input budget | Job |
|------|-----------|-------------------|-------------|-----|
| `spec_validation` | `spec_validation` | Flash | ~3k | Check spec/task coherence; block if ambiguous |
| `clarity_check` | `clarity_check` | Flash | ~3k | Ask targeted questions if task is underspecified; block if unclear |
| `planner` | `planner_pass` | Sonnet | ~8k | Produce implementation plan prepended to executor brief |
| `context_builder` | `context_builder` | Flash | ~16k | Compress relevant context into Builder brief |
| `supervisor` | `supervisor` | Sonnet | ~2k/call | Approve / deny / abort Aider confirm_ask decisions during execution |
| `executor` | `executor` | Configurable | ~32k | Write code (Aider backend) |
| `reviewer` | `reviewer_pass` | Flash | ~8k | Advisory scan of changed files; note appended to spec report |

Helper calls route via `LlmGateway` and remain audited in `model_roles` with live token counts. Every call emits an `llm_call` trace event with `role`, `model`, token summary, and `reasoning_tokens` when the provider returns reasoning.

---

## Supervisor agent loop

The `SupervisorAgent` (`core/engine/supervisor_agent.py`) owns all post-planning control flow. This replaced a dual-loop design (inner `supervised_io.py` + outer `mcp_server.py`) that was hard to reason about.

**Canonical trace events (one lifecycle per delegation that reaches executor):**

```
supervisor_loop_start     {loop_id, max_turns}
  supervisor_turn_start   {loop_id, turn_index}
    [executor runs]
    [reviewer runs if enabled]
  supervisor_turn_end     {loop_id, turn_index, worker_outcome, checks_result}
  supervisor_decision     {loop_id, turn_index, action, reason, model, tokens}
supervisor_loop_end       {loop_id, turns_completed, final_action, end_reason}
```

**`max_turns` config:** `MCP_CODER_SUPERVISOR_MAX_TURNS` / `supervisor_max_turns` yaml. Default `1` = single Aider run (current behavior). Set to `2`–`3` to enable autonomous fix+retry without a host roundtrip.

**Intra-turn supervision** (separate from the loop): while the executor runs, `SupervisedIO` routes every Aider `confirm_ask()` to `DelegationSupervisor` — a separate, synchronous LLM call that returns `approve | deny | abort | escalate`. These fire at a finer granularity than the loop turns and are not the same as the per-turn `supervisor_decision` event.

---

## Sessions and executor caching

A **session** groups related delegations under one `mcp_session_id` and caches an Aider `Coder` instance (`core/session/executor_cache.py`). Reusing a `Coder` avoids startup overhead; the compiler still rebuilds the `ContextPackage` fresh each time.

Session policy:
- `always_new` — new session per delegation (clean, no executor state leakage)
- `align_host` — try to match an active Cursor host session (more reuse, slight coupling)

Executor reuse is audited: `executor_reused: true/false` and `executor_recreated: true/false` in `delegations.jsonl`.

---

## Storage layout (key paths)

```
~/.mcp-coder/
  projects/
    <sha256(workspace_path)>/
      project.json
      workspace_history.db          SQLite: manifests, checkpoints, file-level diffs
      delegation_rag.db             SQLite FTS5: delegation index
      workspace_rag.db              SQLite FTS5: per-file summary index
      sessions/
        <mcp_session_id>/
          delegations.jsonl         canonical audit trail
          server.jsonl              server-side event log
          traces/
            <delegation_id>.jsonl   full event stream (all LLM + tool + supervisor events)

<workspace>/
  .mcp-coder/
    config.yaml                     user-owned; never written by mcp-coder
    session.json                    current session pointer (system-managed)
    specs/
      tasks/   <epic>-<step>.md     task specs (contracts)
      epics/   <slug>.md            epic specs
      reports/ <spec-name>-report.md audit reports (appended)
    context/
      excerpts/ *.excerpt.txt        materialized read-excerpt files
```

---

## Known gaps and open seams

| Gap | Where it hurts | Backlog |
|-----|----------------|---------|
| **Live multi-turn rerun in mcp_server** | `SupervisorAgent` has rerun logic + tests; wiring a second Aider invocation in `mcp_server.py` is a bounded follow-up | BL-533 follow-up |
| **Reasoning capture completeness** | Some providers redact or truncate reasoning tokens in their API response; gaps are labeled but text may be absent | BL-534 |
| **Trace inspect for specless CLI runs** | `trace inspect <id>` fails when delegation not in history DB | BL-535 |
| **Role attribution completeness** | Some `proxy_llm_call` events still have `role=None` | BL-536 |
| **Backend-complete interception** | In-process callers fully covered; out-of-process (Claude Code, Codex) via base URL config only | BL-371 |
| **Single executor backend (Aider)** | `opencode_engine.py` stub exists; no second backend | BL-340 |
| **Embeddings / recall metric** | FTS-only retrieval; no measured recall | P5-005 deferred |
| **Session policy heuristics** | `align_host` matching is fragile (slug-based) | BL-317 |

---

## What is intentionally NOT here

- **No routing logic** — mcp-coder does not decide which tasks to attempt; the planner/human does.
- **No owned UI** — `view delegations` spawns a static HTML viewer; Cursor is the primary UI.
- **No git dependency** — storage and diffing work without git; git is informational only.
- **No multi-repo or cross-project coordination** — everything is scoped to one workspace path.

---

## Future direction

| Area | Note |
|------|------|
| **Autonomous multi-turn rerun** | Supervisor decides `rerun_aider` autonomously; second Aider invocation wired in `mcp_server.py` (bounded follow-up to current `max_turns=1` default) |
| **Supervisor context enrichment** | Supervisor currently sees spec + question + output tail; add RAG history and cross-delegation signals (BL-529) |
| **On-demand context retrieval** | Helper models get a minimal tool interface (`read_file`, `rag_search`) to pull dynamic context mid-call (BL-530) |
| **Multi-turn helper loops** | Planner/supervisor/reviewer run an internal loop up to N turns to refine before producing final output (BL-531) |
| **Architect role (CTO)** | Epic-boundary context only; no diffs/files; strategic misalignment detection (BL-526) |
| **Full executor-pull sidecar** | Lightweight HTTP server exposing `rag_search`, `read_file`, `search_history` as Aider tools (BL-354 full) |
| **Host model policy Stage 2+** | AI-suggested params (BL-513), dynamic escalation mid-delegation (BL-514) |
| **Alternate backends** | Cursor-SDK executor (BL-340) |
| **Storage lifecycle** | Retention, promote-then-prune, gc — first slice shipped; full policy BL-357 |

---

## Deeper dives

| Topic | Document |
|-------|---------|
| Mental model / operator guide | [how-it-works.md](../how-it-works.md) |
| Context compiler full walkthrough | [context-pipeline.md](./context-pipeline.md) + T-04 tutorial |
| Storage paths and JSONL schema | [storage-layout.md](./storage-layout.md) |
| Per-role model registry | [per-role-models.md](./per-role-models.md) |
| Multi-model role direction | [../notes/multi-model-roles.md](../../notes/multi-model-roles.md) |
| Module-by-module map | [code-structure.md](../code-structure.md) |
| Terminology | [terminology.md](../terminology.md) |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-20 | Full rewrite — supervisor agent loop architecture, updated role model table (clarity/planner/supervisor/reviewer all first-class), D-9 + D-10 added, lifecycle updated with SupervisorAgent, known gaps refreshed |
| 2026-06-17 | Phase 9 sync — observability layer updated, trace event families listed |
| 2026-06-13 | Phase 7 sync — scope updated, trace/event descriptions updated |
| 2026-06-13 | Phase 6 — observability seam + trace files; storage map updated |
| 2026-06-13 | Phase 5 — rag_retrieval, workspace_rag.db, workspace_search |
| 2026-06-12 | Initial version |
