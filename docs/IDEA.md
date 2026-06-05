# mcp-coder

An MCP server (with optional CLI) that wraps CLI coding agents (Aider, OpenCode, Claude Code, etc.) and exposes them as MCP tools — with task-level orchestration, cross-session memory, and optional spec-driven workflows.

**Delivery plan:** [PHASES.md](./PHASES.md) · **Phase 1 tasks:** [PHASE1_MVP.md](./PHASE1_MVP.md) · **Backlog:** [BACKLOG.md](./BACKLOG.md)

---

## Overall goal

Build a **powerful, token-efficient coding agent system** that works well with **Cursor** while keeping **maximum control** and **auditability**.

- **Cursor** stays a thin conversation + planning layer.
- **mcp-coder** owns task delegation, sessions, memory, spec structure, and optimization at the **task** boundary.
- **Aider / OpenCode** own the gritty edit loop (mature execution engines — we do not rebuild them).
- **[context_optimizer_proxy](https://github.com/amirharati/context_optimizer_proxy)** (separate repo) squeezes tokens at the **per-turn** boundary inside the execution engine’s LLM calls.

---

## Two complementary projects

| Project | Layer | Role |
|---------|--------|------|
| **`context_optimizer_proxy`** (existing) | **Turn-level** | Compression, noise removal, token control, output cleaning, A/B experimentation on every LLM request |
| **`mcp-coder`** (this repo) | **Task-level** | Session management, memory library, task optimization, “have we done this before?”, spec handling, delegation to CLI coders |

*Do not merge these into one codebase. They compose via configuration (execution engine → proxy → provider).*

### Layered flow (target architecture)

```
Cursor (thin layer — chat, planning, user Q&A)
   ↓  MCP tool calls
mcp-coder (task-level orchestrator + memory + spec tools)
   ↓  subprocess / Python API
OpenCode / Aider (execution engine)
   ↓  LLM API (optional)
context_optimizer_proxy (fine-grained per-turn optimization)
   ↓
Actual LLM provider
```

### Role division

| Actor | Responsibility |
|-------|------------------|
| **Cursor’s LLM** | Main conversation, explains “why did we do this?”, routes work, fills summaries / spec fields when asked |
| **mcp-coder** | High-level tools: delegate, memory, spec CRUD, session boundaries, logs — not line-by-line editing in the IDE |
| **Aider / OpenCode** | Reliable multi-file edits, git integration, internal agent loop |
| **context_optimizer_proxy** | Transparent prompt/response shaping on each turn |

---

## Phase 1 today vs long-term vision

| | **Now (Phase 1)** | **Later (Phase 2+)** |
|---|-------------------|----------------------|
| **MCP tools** | `delegate_to_agent` (+ logging) | Spec tools, RAG query, session APIs |
| **Context** | Summary in MCP args; opt-in Cursor transcript dump (`host_transcript: dump`) | Owned context pipeline |
| **Sessions** | Disk registry under `~/.mcp-coder`; `always_new` \| `align_host`; workspace `config.yaml` | Cross-day memory, explicit continue |
| **Storage** | User-home canonical logs; `session.json` pointer + user `config.yaml` | Team sync / DB optional |
| **Specs** | Dogfood local worker specs while building; **product spec at Phase 1 exit review** | `.mcp-coder/specs/` + gatekeeper (later) |

**Checkpoint:** End of Phase 1 — spec strategy, gatekeeper, Phase 2 goals ([PHASE1_MVP.md](./PHASE1_MVP.md)).

**Current status (2026-06-05):** Phase 1 spine shipped (MCP → Aider, home storage, host adapter, sessions, server log, opt-in transcript dump). **Next:** P1-199 exit review (spec strategy, gatekeeper, Phase 2).

---

## Core capabilities (target)

- **Dual mode** — MCP server for Cursor + standalone CLI (same core).
- **Session management** — Persistent sessions, smart new-vs-continue, library of past work (Phase 1.3+ / Phase 3).
- **Memory system** — Semantic / keyword search over old tasks and decisions (RAG — Phase 3).
- **Spec-driven development** — Markdown artifacts as the **contract** between planner and executor (Phase 2+; see below).
- **Optional interactive mode** — Delegate to a full interactive Aider session in the terminal when `interactive: true` (backlog / post-P1).
- **Adapter pattern** — Pluggable execution engines (Aider Python API, OpenCode subprocess, etc.).

---

## Spec-driven communication (direction from ideation)

Structured Markdown as the **main API/contract** between components — not raw chat dumps and not unconstrained file writes by the executor.

### Proposed workspace artifacts (under `.mcp-coder/specs/` or similar)

| File | Purpose |
|------|---------|
| `task-spec.md` | Goal, scope, files, done-when — **primary handoff** |
| `plan.md` | Steps the orchestrator or planner intends |
| `decisions.md` | Append-only architectural decisions |
| `context.md` | Constraints, links, environment notes |
| `implementation.md` | What was actually done (post-run) |
| `feedback.md` | Review notes, follow-ups |

**Controlled access:** Do **not** let Aider/OpenCode write these files directly. Expose **dedicated MCP tools** that enforce structure, validation, section boundaries, and permissions.

This mirrors how we build the product: planning chat → local `docs/tasks/P1-….md` → worker (see [notes/spec-based-development.md](./notes/spec-based-development.md)).

### Proposed MCP tools (spec layer — future)

| Tool | Purpose |
|------|---------|
| `create_task_spec` | Initialize a new task spec from template |
| `read_spec_file` | Read section(s) with stable schema |
| `update_spec_file` | Section-based update (not free-form overwrite) |
| `append_decision` | Append-only decisions log |
| `propose_plan` | Write/update plan section |
| `get_task_status` | Status for active task |
| `list_active_tasks` | Enumerate in-flight work |
| `ask_user_about_spec` | Clarification hook for Cursor to present to user |

**Execution tools (today / near-term):**

| Tool | Purpose |
|------|---------|
| `delegate_to_agent` | Run Aider/OpenCode for implementation ( **Phase 1 — shipped** ) |

One MCP server can expose **many tools**; use clear descriptions so Cursor does not call internal/spec tools for routine coding.

---

## Interaction modes (target)

| Mode | Behavior |
|------|----------|
| **Default** | Hands-off — Cursor calls `delegate_to_agent`, gets result + log line |
| **Clarification in IDE** | Tools like `ask_user_clarification` / `ask_user_about_spec` before delegating |
| **Full interactive Aider** | Optional flag → spawn real terminal Aider with pre-optimized context (heavy; backlog) |

---

## The two-tiered optimization architecture

1. **Tier 1: Task-level (`mcp-coder`)**  
   Coarse-grained, once per delegation: scope files, pull memory, assemble spec/context, choose session, launch executor.

2. **Tier 2: Turn-level (`context_optimizer_proxy`)**  
   Fine-grained, every LLM call inside the executor: strip noise, compress paths, cache-aware boundaries.

*Separation keeps orchestration safe and the proxy free to experiment without breaking delegation.*

---

## Architecture (internal components — mature state)

```
You (human)
  └── MCP Host (Cursor / Claude Desktop / etc.)
       └── mcp-coder
            ├── Spec tools (controlled MD contract)
            ├── Router / janitor (cheap LLM — Phase 2+)
            ├── RAG memory (Phase 3)
            ├── Session scheduler
            └── CLI Coder adapter (Aider / OpenCode)
                 └── context_optimizer_proxy (optional)
                      └── LLM provider
```

Each sub-agent remains a **spawn → work → return** process where possible. No heavy agent framework unless a phase proves we need it.

---

## Key concepts

### Cheap orchestrator, expensive executor

Cheap model (mini / Flash) for routing, RAG, spec compaction, session classification. Expensive model (Sonnet / Opus) only inside the executor for code changes.

### Session management

The wrapper **owns** session state — not the CLI agent. Decides new vs continue from `mcp_session_id`, `host_session_id`, policy (`align_host`), and later spec version.

### Cross-session memory (RAG)

Index past delegations: summary, keywords, optional embeddings. Before launch: “have we done this before?” Inject only relevant slices.

### Context freshness (janitor)

Audit whether assembled context matches repo reality; refresh cheaply before expensive run.

### Context extraction (MCP walled garden)

MCP tools only receive JSON arguments — not full Cursor chat.

- **Host transcript (Phase 1.4):** read Cursor `agent-transcripts/*.jsonl` via host adapter — not SpecStory.
- **Fallback:** `context_summary` (+ optional `explicit_constraints`, snippets — P1-115).
- **Long-term:** spec files as contract reduce need for full history ([notes/spec-based-development.md](./notes/spec-based-development.md)).

### Dual-mode operation (MCP + CLI)

Same backend for Cursor MCP and terminal `mcp-coder …` when CLI lands (Phase 2+).

---

## Advantages of this design

- Leverages **mature** execution tools instead of rebuilding an editor agent.
- **Two-layer** token/cost control (task + turn).
- **Transparent** — `delegations.jsonl`, spec files, delegation viewer.
- **Flexible** interaction: hands-off ↔ clarification ↔ optional interactive terminal.
- **Future-proof** — sub-sessions, more MCP tools, multi-agent via same protocol.
- Works **in Cursor** and **standalone**.

---

## Data models

### Session entry

```python
session_entry = {
  "id": "sess_001",
  "created": "timestamp",
  "turns": [
    {
      "turn": 1,
      "task": "original task from host",
      "model_used": "claude-sonnet-4",
      "files": ["..."],
      "diff": "raw git diff",
      "summary": "human-readable summary",
      "tokens_used": 0,
      "timestamp": "timestamp",
    },
  ],
  "rolling_context": "last N tokens (pruned)",
  "total_tokens": 0,
}
```

### RAG entry

```python
rag_entry = {
  "session_id": "sess_001",
  "turn": 1,
  "summary": "short description",
  "keywords": ["..."],
  "embedding": [],  # optional
  "timestamp": "timestamp",
}
```

For v1 RAG, keyword + recency may suffice before embeddings.

---

## MCP tools — delegation (Phase 1)

```json
{
  "delegate_to_agent": {
    "params": {
      "task": "add pagination to /users endpoint",
      "target_files": ["routes/users.ts"],
      "context_summary": "decisions from chat",
      "backend": "aider"
    },
    "returns": {
      "success": true,
      "output": "...",
      "files_changed": ["routes/users.ts"],
      "session_reused": false,
      "session_reason": "policy_always_new",
      "session_policy": "fallback:always_new"
    }
  }
}
```

Future: `session_id`, spec paths, `interactive`, richer context fields — see spec tools table above.

---

## CLI equivalent (same backend — planned)

```bash
mcp-coder --model claude "add pagination to /users" routes/users.ts
mcp-coder --session sess_001 "now add sorting"
mcp-coder status sess_001
mcp-coder rag "pagination params"
```

---

## Backends supported

| Engine | Integration | Notes |
|--------|-------------|--------|
| **Aider** | Python API (`Coder.create`) | Phase 1 default |
| **OpenCode** | Subprocess `opencode run …` | Adapter stub / Phase 2 |
| Claude Code, Codex CLI, etc. | TBD | As needed |

---

## Design principles

- **Keep it simple** — rules + adapters + process spawn; avoid heavy frameworks early.
- **Pay for value** — cheap intelligence for routing/memory; expensive model for code.
- **Session-owned state** — wrapper owns memory and spec lifecycle, not the CLI agent.
- **Layered optimization** — task logic here; turn logic in proxy.
- **Controlled specs** — MCP tools write structured MD; executors do not own the contract files.
- **Transparent** — logs and specs are inspectable; sessions resumable.
- **Incremental delivery** — Phase 1 proves delegate + logs; spec system and RAG follow evidence.

---

## Suggested evolution (from ideation — not a fixed schedule)

1. ~~Thin MCP wrapper calling Aider~~ → **Phase 1 (in progress)**.
2. Home storage, host adapter, sessions, full context → **rest of Phase 1** ([PHASE1_MVP.md](./PHASE1_MVP.md)).
3. Markdown spec system + controlled MCP spec tools → **Phase 2 candidate** (review at end of Phase 1).
4. RAG + persistent session DB → **Phase 3**.
5. Optional interactive Aider delegation; connect proxy by default in templates → **backlog / polish**.
6. Sub-agents and multi-tool orchestration inside one server → **Phase 4+**.

Manual familiarity with Aider/OpenCode in real repos remains valuable even while MCP automates delegation.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-03 | Initial vision, two-tier arch, data models |
| 2026-06-04 | Grok ideation: spec system, role division, interaction modes, Phase 1 vs long-term; P1-100 status |
