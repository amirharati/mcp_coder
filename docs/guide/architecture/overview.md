# Architecture overview

**Status:** Living — update as shipped decisions change.  
**Last updated:** 2026-06-23 (Phase 12/13 — Supervisor persistent state, lifecycle envelope, pause/resume, project memory).  
**How to use:** Read after [how-it-works.md](../how-it-works.md) (operator mental model). This doc is the *layer map and locked design decisions*. For refined design intent see [../../notes/system-design-overview.md](../../notes/system-design-overview.md); for Supervisor-agent deep dive see [../../notes/supervisor-agent-architecture.md](../../notes/supervisor-agent-architecture.md).

---

## Layer map

```
┌───────────────────────────────────────────────────────────────────┐
│  Host agent                                                       │
│  Cursor (only host today) — rules, chat, specs, tool calls        │
│  core/host/   cursor.py  cursor_rules.py  cursor_transcript.py    │
└──────────────────────────────┬────────────────────────────────────┘
                               │  MCP tool calls (stdio JSON-RPC)
                               │  delegate_to_agent  answer  inspect…
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  MCP server  (thin entry, not orchestration owner)                │
│  server/mcp_server.py                                             │
│  • Registers MCP tools, runs preloop helpers, hands off to        │
│    SupervisorAgent for delegation lifecycle                       │
│  • Tools: delegate_to_agent, inspect_context,                     │
│    answer_delegation_question, get_server_status,                 │
│    list_delegations, get_delegation_diff, get_checkpoint_detail,  │
│    get_file_history, rag_search, workspace_search                 │
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
   ┌──────────────────────────────────────────────────────────┐
   │  SupervisorAgent  (persistent project workflow agent)    │
   │  core/engine/supervisor_agent.py                         │
   │                                                          │
   │  Owns delegation lifecycle envelope:                     │
   │    preloop / loop / postloop phase events                │
   │    pause/resume — resume_token, start_fresh              │
   │    inter-turn decisions: done|rerun_aider|escalate_host  │
   │    supervisor_tool_runner — on-demand context retrieval  │
   │                                                          │
   │  Reads / writes persistent state:                        │
   │    project_state.json  cross-delegation memory           │
   │    agent_state.json    checkpoint at delegation end      │
   │    supervisor_states/  expiring pause payloads           │
   │  (all via core/state/)                                   │
   └───────────┬──────────────────────────────────────────────┘
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
   │   delegation_lifecycle_start/end         │
   │   phase_start/end (preloop/loop/postloop)│
   │   llm_call, proxy_llm_call,              │
   │   backend_llm_call, compile_event,       │
   │   supervisor_turn_*, supervisor_decision │
   │   supervisor_paused, supervisor_resumed  │
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
│    project_state.json  cross-delegation Supervisor memory         │
│    agent_state.json    Supervisor checkpoint (process-restart)    │
│    supervisor_states/  expiring pause/resume payloads             │
│    workspace_history.db    delegation_rag.db    workspace_rag.db  │
│    sessions/<id>/                                                 │
│      delegations.jsonl    lean audit row per delegation           │
│      server.jsonl         server lifecycle events                 │
│      traces/<id>.jsonl    full event stream per delegation        │
└───────────────────────────────────────────────────────────────────┘
```

---

## Key architectural decisions (locked)

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
| `~/.mcp-coder/projects/<key>/` | System-owned: JSONL, history DB, RAG, Supervisor state | Never committed; survives workspace moves |

`project_key` = `sha256(resolved_workspace_path)`.

### D-4: Spec is the contract
The spec's `files_edit` list is the only way a path enters `edit-full` tier and Aider `fnames`. The file picker **discovers** read candidates but **never grants edit rights**. Enforced at compile time in `file_picker.py` + `assemble.py` and checked post-hoc by `post_gateway`.

### D-5: One model per role
Every LLM call is tagged with a `role` (`executor`, `planner_pass`, `context_builder`, `supervisor`, `reviewer_pass`, `clarity_check`, `spec_validation`, `review`). Each resolves independently via `model_registry.resolve()` — precedence: host `model_policy` arg → env var → `config.yaml` → built-in default. All calls are audited in `model_roles` with live token counts and a `policy_applied` block on every `backend_llm_call` and `llm_call` event.

### D-6: Snapshot-based file diffing (not git)
Pre/post SHA-256 manifests of the workspace bracket the executor. `files_changed` comes from the manifest diff, not from git or from what Aider reports. Works on untracked files, gitignored paths, and repos with no git history. Git is a soft dependency only.

### D-7: JSONL as the audit record
One lean row per delegation appended to `delegations.jsonl`. Full event stream in `traces/<id>.jsonl`. The JSONL records are canonical truth — history DB, RAG, spec reports are derived or supplementary.

### D-8: Optional stages fail open; hard gates block closed
Helper LLM failures (planner, builder, reviewer) are non-fatal — the delegation proceeds with the mechanical context. `spec_validation` and `clarity_check` are the only stages that can stop the pipeline before spending executor tokens.

### D-9: SupervisorAgent owns post-planning lifecycle and persistent state
After the preloop pipeline hands off, `SupervisorAgent` owns the full delegation lifecycle. It emits the lifecycle envelope (`delegation_lifecycle_start/end`, `phase_start/end` for `preloop`/`loop`/`postloop`), runs executor turns, calls the reviewer, makes per-turn decisions, and handles pause/resume across host round-trips.

Critically: the Supervisor also reads and writes **persistent state across delegations** via `core/state/`:
- `project_state.json` — decisions, risks, hot areas, reviewer finding summaries
- `agent_state.json` — checkpoint at every delegation end; rehydrates Supervisor on process restart (CLI ≡ server)
- `supervisor_states/<token>.json` — expiring pause payloads for mid-delegation or across-call resume

The host does **not** own this memory and does **not** see intermediate loop turns.

### D-10: Context frugality rule
Every LLM call gets a purpose-built context bounded to its role. No call sees full session state:

| Role | Budget | What it sees |
|------|--------|--------------|
| Clarity check | ~3k | Task + spec files + last delegation titles |
| Spec validation | ~3k | Spec text + recent conversation window |
| Planner | ~8k | Spec + project state summary + file map |
| Builder brief | ~16k | Spec + relevant files (compiled) |
| Executor | ~32k | Full context package |
| Supervisor (per decision) | Tier 1 + on-demand tier 2 | Spec + plan + decision log + tool-retrieved context |
| Reviewer | ~8k | Diff + changed files + acceptance criteria |

Supervisor context uses a two-tier model: slow baseline context (tier 1, at turn boundaries) + on-demand tool-pulled context (tier 2, mid-decision via `SupervisorToolRunner`).

---

## Delegation lifecycle (concrete path through code)

For `mode=implement` with a valid spec:

```
delegate_to_agent()
  │
  ├── host context: core/host/cursor.py → transcript path, session hint
  ├── session: core/session/ → new or reuse Coder instance
  │
  │── PRELOOP ──────────────────────────────────────────────────────────
  │
  ├── spec_read           core/specs/read.py, sections.py → SpecRead
  ├── spec_validation*    core/engine/spec_validation_llm.py  [can BLOCK]
  ├── clarity_check*      core/context/clarity_llm.py         [can BLOCK / PAUSE]
  │
  ├── file_picker         core/context/file_picker.py → CandidateFilesResult
  ├── rag_retrieval*      core/rag/builder_retrieval.py → context_refs + brief section
  ├── context_assemble    core/context/assemble.py → ContextPackage
  ├── planner_pass*       core/engine/planner_pass_llm.py
  │     └── reads project_state.json via helper_llm_pipeline.py
  ├── builder_llm*        core/engine/context_builder_llm.py
  │
  │── SUPERVISOR LOOP ──────────────────────────────────────────────────
  │
  ├── SupervisorAgent.begin()         lifecycle: delegation_lifecycle_start
  │   supervisor reads project_state  core/state/project_state.py
  │   (via SupervisorToolRunner       core/engine/supervisor_tool_runner.py)
  │     │
  │     └── turn 1..N (N = supervisor_max_turns, default 1):
  │           │  phase_start(loop)
  │           ├── EXECUTOR           core/engine/aider_engine.py
  │           │     └── translate_context_package() → fnames + prompt
  │           │     └── Coder.run(prompt) via SupervisedIO
  │           │           └── confirm_ask() → DelegationSupervisor LLM
  │           │                 (approve / deny / abort / escalate)
  │           │     └── workspace snapshot post-run
  │           │
  │           ├── reviewer_pass*     core/engine/reviewer_llm.py (advisory)
  │           │
  │           └── supervisor_decision: done | rerun_aider | escalate_host
  │                 ├── done or max_turns → exit loop
  │                 ├── rerun_aider → next turn
  │                 └── escalate_host → supervisor_paused, return needs_input
  │                       host may answer via `answer` param on next call
  │                       or via answer_delegation_question (concurrent)
  │
  ├── SupervisorAgent.finish()        project_state.save() + agent_state.save()
  │                                   lifecycle: delegation_lifecycle_end
  │
  │── POSTLOOP ────────────────────────────────────────────────────────
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

`*` = conditional/default-on. Clarity and spec_validation are default on; planner_pass, builder_llm, reviewer_pass default on. `rag_retrieval` runs when context_builder and RAG flags on (default on).

### Pause / resume paths

Two distinct pause semantics:

| Pause type | Trigger | Resume |
|---|---|---|
| **Clarity-block** | clarity_check gate fires, unanswered questions | Host edits spec Q&A and re-delegates; clarity-block path can auto-resume without explicit `answer` |
| **Escalation** | Supervisor decides `escalate_host` inside the loop | Host passes `answer` on next `delegate_to_agent`; `start_fresh=true` abandons the pause entirely |

Completed preloop stages and executor turns are not replayed on resume where policy allows.

---

## Context compiler in brief

The compiler converts spec + workspace → a `ContextPackage` the backend adapter translates to executor inputs.

```
spec contract
    + target_files hints        →  file_picker      →  CandidateFilesResult
    + symbol scan (rg / py)                              ranked paths + tiers
    + repo map (def/class outlines)
                                →  assemble_context  →  ContextPackage
                                     PathEntry per file:
                                       tier: edit-full | read-full | read-excerpt | map-only | pointer
                                       bytes, excerpt_path
                                →  budget            →  trim read entries to fit
                                →  rag_retrieval*    →  ## Relevant prior work + context_refs
                                →  builder_llm*      →  prepend ## Builder brief
                                →  planner_pass*     →  prepend ## Planner plan
                                     (may include project_state summary)
                                →  translate_context_package()
                                     fnames = [edit-full paths]
                                     prompt = brief + fenced read blocks + map block
```

The **mechanical brief** (paths, tiers, task, context_summary) is never rewritten by any LLM. LLMs only **prepend** above a separator. See tutorial T-04 for a hands-on walkthrough.

---

## Role model

Each role has its own model, budget, and trace audit line. Precedence: host `model_policy` → env var → `config.yaml` → built-in default.

| Role | Code name | Default tier | Budget | Job |
|------|-----------|--------------|--------|-----|
| `spec_validation` | `spec_validation` | Flash | ~3k | Coherence check; can block |
| `clarity_check` | `clarity_check` | Flash | ~3k | Task clarity; can block or pause |
| `planner_pass` | `planner_pass` | Sonnet | ~8k | Plan in brief; reads project state |
| `context_builder` | `context_builder` | Flash | ~16k | Builder brief narrative |
| `supervisor` | `supervisor` | Sonnet | tier 1 + tool-pulled | Inter-turn decisions + confirm_ask resolution |
| `executor` | `executor` | Configurable | ~32k | Write code (Aider) |
| `reviewer_pass` | `reviewer_pass` | Flash | ~8k | Advisory post-exec scan; findings → project state |
| `review` | `review` | executor fallback | — | `mode=review` Q&A only |

Helper calls route via `LlmGateway`; every call emits an `llm_call` trace event with `role`, `model`, token summary, and `reasoning_tokens` where returned.

---

## Supervisor agent

`SupervisorAgent` (`core/engine/supervisor_agent.py`) is the persistent project workflow agent and the single owner of post-planning orchestration state.

### Lifecycle envelope (Phase 13)

Every delegation that enters the Supervisor emits a canonical set of trace events:

```
delegation_lifecycle_start   {delegation_id, resumed, …}
  phase_start(preloop)
  phase_end(preloop)
  phase_start(loop)
    supervisor_turn_start    {loop_id, turn_index}
      [executor runs]
      [reviewer runs if enabled]
    supervisor_turn_end      {loop_id, turn_index, worker_outcome, checks_result}
    supervisor_decision      {loop_id, turn_index, action, reason, model, tokens}
  phase_end(loop)
  phase_start(postloop)
  phase_end(postloop)
delegation_lifecycle_end     {outcome, …}
```

Pause events: `supervisor_paused` (clarity-block or escalation) and `supervisor_resumed` (next host call). The viewer renders all of these as rows.

### Persistent state files (`core/state/`)

| File | Class | Scope | Purpose |
|------|-------|-------|---------|
| `project_state.json` | `ProjectState` | cross-delegation | decisions, risks, hot areas, reviewer finding summaries |
| `agent_state.json` | `AgentCheckpoint` | cross-process | non-expiring snapshot at delegation end; rehydrates Supervisor |
| `supervisor_states/<token>.json` | `SupervisorState` | single pause | expiring; turn_index, plan, decision_log, questions |

### Intra-turn supervision

While the executor runs, `SupervisedIO` routes every Aider `confirm_ask()` to `DelegationSupervisor` (`core/engine/supervisor.py`) — a separate synchronous LLM call returning `approve | deny | abort | escalate`. This is finer-grained than the inter-turn `supervisor_decision` event.

### `max_turns`

`MCP_CODER_SUPERVISOR_MAX_TURNS` / `supervisor_max_turns` yaml. Default `1` = single Aider run. Set to `2`–`3` to enable autonomous fix+retry without a host roundtrip.

---

## Sessions and executor caching

A **session** groups related delegations under one `mcp_session_id` and caches an Aider `Coder` instance (`core/session/executor_cache.py`). The compiler always rebuilds `ContextPackage` fresh.

| Policy | Behavior |
|--------|----------|
| `always_new` | New session per delegation — clean, no executor state leakage |
| `align_host` | Try to match an active Cursor host session — more reuse, slight coupling |

`executor_reused` / `executor_recreated` audited in `delegations.jsonl`.

---

## Storage layout (key paths)

```
~/.mcp-coder/
  projects/
    <sha256(workspace_path)>/
      project_state.json        cross-delegation Supervisor memory
      agent_state.json          Supervisor checkpoint (non-expiring)
      supervisor_states/
        <resume_token>.json     pause/resume payload (expiring, configurable TTL)
      project.json
      workspace_history.db      SQLite: manifests, checkpoints, file-level diffs
      delegation_rag.db         SQLite FTS5: delegation index
      workspace_rag.db          SQLite FTS5: per-file summary index
      sessions/
        <mcp_session_id>/
          delegations.jsonl     canonical lean audit rows
          server.jsonl          server lifecycle events
          traces/
            <delegation_id>.jsonl  full event stream (all LLM + supervisor + compile events)

<workspace>/
  .mcp-coder/
    config.yaml                 user-owned; never written by mcp-coder
    session.json                current session pointer (system-managed)
    specs/
      tasks/   <epic>-<step>.md     task specs (contracts)
      epics/   <slug>.md            epic specs
      reports/ <spec-name>-report.md  audit reports (appended)
    context/
      excerpts/ *.excerpt.txt        materialized read-excerpt files
```

---

## Known gaps and open seams

| Gap | Where it hurts | Backlog |
|-----|----------------|---------|
| **Autonomous interception** | Supervisor intercepts structurally but confirm_ask still escalates to host in many cases | BL-547 |
| **Full continuation briefing** | Resume injects host answer but richer confirm_ask enrichment partial | BL-543 B/C |
| **Full planner-as-agent loop** | Planner is one-shot in current code; full tool-calling loop deferred | BL-525 |
| **Supervisor self-context policy** | Tier-1 / tier-2 model is in place; richer topic-based refresh not yet built | BL-529 |
| **Escalation pause resume flow** | Clarity-block auto-resume shipped; escalation pause requires explicit answer; edge cases tracked | BL-553..BL-555 |
| **Reasoning capture completeness** | Some providers redact reasoning tokens; gaps labeled but text may be absent | BL-534 |
| **Role attribution completeness** | Some `proxy_llm_call` events have `role=None` | BL-536 |
| **Backend-complete interception** | In-process fully covered; out-of-process (Claude Code, Codex) via base URL only | BL-371 |
| **Single executor backend** | `opencode_engine.py` stub exists; no second backend | BL-340 |
| **Embeddings / recall metric** | FTS-only retrieval; no measured recall | P5-005 deferred |

---

## What is intentionally NOT here

- **No routing logic** — mcp-coder does not choose which tasks to attempt; the planner/host does.
- **No owned UI** — `view delegations` spawns a static HTML viewer; Cursor is the primary UI.
- **No git dependency** — storage and diffing work without git.
- **No multi-repo or cross-project coordination** — scoped to one workspace path per project key.
- **No autonomous goal decomposition** — Supervisor executes a plan; it does not decompose high-level goals into specs.

---

## Deferred / future direction

| Area | Current status | Backlog |
|------|---------------|---------|
| Autonomous interception (D-ARCH-8) | structure in place; intelligence layer not yet wired | BL-547 |
| Full planner-as-agent loop | one-shot today; multi-turn loop deferred | BL-525 |
| Architect / CTO role | deferred; boundary with Host/Planner undecided | BL-526 |
| Smarter executor context adaptation | deferred | BL-546 |
| Host chat intent inference | deferred | BL-527 |
| Supervisor self-context policy | tier model in place; richer refresh TBD | BL-529, BL-530 |
| AI-suggested model params | manual config today | BL-513 |
| Dynamic escalation mid-delegation | deferred | BL-514 |
| Alternate executor backends | Aider only | BL-340 |
| Storage lifecycle / GC | basic stats shipped; full retention policy deferred | BL-357 |

---

## Deeper dives

| Topic | Document |
|-------|---------|
| Operator mental model | [how-it-works.md](../how-it-works.md) |
| Supervisor agent design | [../../notes/supervisor-agent-architecture.md](../../notes/supervisor-agent-architecture.md) |
| Roles and lifecycle vocabulary | [../../notes/delegation-roles-and-lifecycle.md](../../notes/delegation-roles-and-lifecycle.md) |
| Context / storage / observability | [../../notes/context-storage-and-observability.md](../../notes/context-storage-and-observability.md) |
| Model routing and policy | [../../notes/model-routing-and-policy.md](../../notes/model-routing-and-policy.md) |
| Whole-system design map | [../../notes/system-design-overview.md](../../notes/system-design-overview.md) |
| Module-by-module map | [code-structure.md](../code-structure.md) |
| Terminology | [terminology.md](../terminology.md) |
| Context compiler walkthrough | T-04 tutorial |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-23 | Phase 12/13 sync — lifecycle envelope events, pause/resume paths, persistent state (`project_state`, `agent_checkpoint`, `supervisor_states`), updated layer map with `core/state/`, updated D-9, updated Supervisor section, refreshed known gaps, removed broken sub-page links |
| 2026-06-20 | Full rewrite — supervisor agent loop, updated role model, D-9 + D-10 |
| 2026-06-17 | Phase 9 sync — observability layer, trace events |
| 2026-06-13 | Phase 6/7 sync |
| 2026-06-12 | Initial version |
