<!--
  STEWARDSHIP — Tier 0 canonical vision. See docs/VISION_DOCS.md.

  - Do NOT change this file unless the user explicitly asks to update IDEA.md
    or top-level vision.
  - Workers: docs/tasks/*.md only; planning session merges vision here when needed.
  - Preserves 074753b (README.md) + early docs/IDEA.md; add/adapt, do not drop original intent.
-->

# mcp-coder

An MCP server (with optional CLI) that wraps CLI coding agents (Aider, OpenCode, Claude Code, etc.) and exposes them as MCP tools — with task-level orchestration, cross-session memory, and optional spec-driven workflows.

**Delivery plan:** [PHASES.md](./PHASES.md) · **Active PM:** [PHASE3_MVP.md](./PHASE3_MVP.md) · **Backlog:** [BACKLOG.md](./BACKLOG.md) · **Vision map:** [VISION_DOCS.md](./VISION_DOCS.md)

---

## Core problem & why this exists

*(From initial vision — commit `074753b`.)*

Most AI coding agents are **stateless per-invocation** (or lose project memory when a host session ends). Each conversation starts fresh. Users work around **context amnesia** with `AGENTS.md`, `MEMORY.md`, `CHANGELOG.md`, and hand-maintained context files.

**`mcp-coder` bridges that gap:** it manages context and memory **across delegations and sessions** so work can build on prior decisions, not only on whatever fits in the host chat.

The calling agent (Cursor, Claude Desktop, any MCP host) stays **lean** — conversation and planning in the IDE; **actual multi-file editing** goes to a mature CLI coder via MCP, with **mcp-coder** owning routing, sessions, memory, specs, and audit logs in between.

No existing tool offers clean **cross-session / cross-project memory** for coding agents as a first-class, MCP-accessible layer. This project makes that memory **automatic, inspectable, and host-agnostic** (not another ad-hoc markdown pile in the repo).

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

## Shipped vs next (phase arc)

| | **Shipped (Phases 1–2)** | **Active / next (Phase 3+)** |
|---|---|---|
| **MCP tools** | `delegate_to_agent`, spec review/implement, `inspect-context` | Attempt archive, `delegation_diff`, RAG query (lite) |
| **Context** | **Context compiler** — tiers, budget, read-deps ([PHASE2_MVP.md](./PHASE2_MVP.md)) | Workspace tracker + honest non-git attribution (BL-322) |
| **Sessions** | Disk registry; `always_new` \| `align_host`; workspace `config.yaml` | Cross-session recall via RAG lite (BL-002) |
| **Storage** | `~/.mcp-coder` JSONL + sessions | `workspace_history.db`, attempt specs, optional RAG index |
| **Specs** | Local worker specs + review loop (P1-151) | Pre/post gates (BL-151); product `.mcp-coder/specs/` later |

**Current status (2026-06-08):** Phase 1 **closed** (P1-199). Phase 2 **closed** (P2-499) — owned context compiler, audit loop ([phase2-exit-validation.md](./notes/archive/phase2-exit-validation.md)). **Active:** Phase 3 — workspace truth + planner history + RAG lite ([PHASE3_MVP.md](./PHASE3_MVP.md); entry **P3-322a**). Phase 4 = smart context builder / janitor / verify; Phase 5+ = interactive sessions and product surface — see [PHASES.md](./PHASES.md) phase arc table.

---

## Core capabilities (target)

- **Dual mode** — MCP server for Cursor + standalone CLI (same core).
- **Session management** — Persistent sessions, smart new-vs-continue, library of past work (Phase 1.3+ / Phase 3).
- **Memory system** — Semantic / keyword search over old tasks and decisions (RAG — Phase 3).
- **Spec-driven development** — Markdown artifacts as the **contract** between planner and executor (Phase 2+; see below).
- **Workspace history** — Delegation-granularity version control: hash the workspace before each MCP call, store diffs, accumulate checkpoints across sessions. Time-travel to any past call boundary; revert individual files; detect all changes including untracked/new files — independent of user's git ([BACKLOG.md](./BACKLOG.md) **BL-322**; [design](./OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md) — Phase 3).
- **Interactive / supervised modes** — supervised multi-step delegate, live terminal tail, optional terminal handoff ([BACKLOG.md](./BACKLOG.md) **BL-160a–d** — timing TBD; not full Cursor-in-terminal chat by default).
- **Internal multi-agent pipeline** — Planner/architect then executor inside one MCP call ([BACKLOG.md](./BACKLOG.md) **BL-161**).
- **Multi-model per role** — Cheap context/cleanup vs expensive code ([BACKLOG.md](./BACKLOG.md) **BL-162**; overlaps Phase 2 context-builder).
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

This mirrors how we build the product: planning chat → local `docs/tasks/P1-….md` → worker (see [notes/spec-based-development.md](./notes/archive/spec-based-development.md)).

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
            ├── Context compiler (Phase 2 — shipped)
            ├── Workspace tracker + RAG lite (Phase 3)
            ├── Router / janitor (Phase 4+)
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

The wrapper **owns** session state — not the CLI agent. It acts as a **session scheduler**: decide new vs continue from `mcp_session_id`, `host_session_id`, policy (`align_host`), rolling window size, and later spec version. Sessions can be long-lived across multiple turns (Phase 3+ APIs; Phase 1 persists registry + policy only).

### Three context sources (every delegation)

Each task fed to the executor should eventually be compiled from:

1. **System prompt** — fixed project conventions, style, rules (workspace / skills).
2. **RAG context** — relevant slices from past sessions (Phase 3).
3. **Rolling window** — last *N* tokens of the **current** session history (pruned), not the full host chat.

Phase 1 uses `context_summary`, optional constraints, and opt-in host transcript dump; Phase 2+ moves assembly here under owned context ([PHASES.md](./PHASES.md)).

### Cross-session memory (RAG)

Index past delegations: summary, keywords, optional embeddings. Before launch: “have we done this before?” Inject only relevant slices. **Mid-task:** the executor or host may query memory via dedicated tools (e.g. `rag_search` — future).

### Context freshness (janitor)

Audit whether assembled context matches repo reality; refresh cheaply before expensive run.

### Context extraction (MCP walled garden)

MCP tools only receive JSON arguments — not full Cursor chat.

- **Host transcript (Phase 1.4 — shipped):** read Cursor `agent-transcripts/*.jsonl` via host adapter (`host_transcript: dump`). Early ideation mentioned **SpecStory** (`.specstory/history/`); product path is **host adapter + optional dump**, not a hard SpecStory dependency.
- **Fallback:** `context_summary` (+ optional `explicit_constraints`, snippets — P1-115).
- **Long-term:** spec files as contract reduce need for full history ([notes/spec-based-development.md](./notes/archive/spec-based-development.md)).

### Skills injection (future)

Detect topic from task; inject relevant skill files (React, Docker, testing patterns, etc.) from a library. Phase 2 candidate ([BACKLOG.md](./BACKLOG.md) BL-008).

### Sub-agent toolkit (future)

Specialized **one-shot** agents composed by the orchestrator — each spawn → work → return → die (no heavy framework):

- Critic / code reviewer / security scanner  
- Test writer / documenter / pattern extractor  

Same process model as the main executor; cheap model + focused system prompt. Phase 4+ ([PHASES.md](./PHASES.md)).

### Multi-model ensemble (future)

For some tasks, spawn *N* cheap instances with varied prompts, then consolidate — may beat one strong model at lower cost. Experimental; not Phase 1–2 scope.

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

### Future MCP tools (target API — from initial README)

Early schema used `delegate_task`; **Phase 1 ships `delegate_to_agent`** (same role). Planned companions:

| Tool | Purpose |
|------|---------|
| `continue_session` | Follow-up message on an existing `session_id` (wrapper-owned continuity) |
| `get_session_status` | Turns, tokens, files changed, per-turn summaries |
| `rag_search` | Query indexed past work (`query` → ranked hits) |

These sit alongside spec tools and `delegate_to_agent`; timing in [BACKLOG.md](./BACKLOG.md) / [PHASES.md](./PHASES.md).

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
| **Aider** | Python API (`Coder.create`) | Phase 1 default; CLI also supports non-interactive flags (`--yes`, `--no-auto-commits`, `--message`) |
| **OpenCode** | Subprocess (if ever) | **Backlog / very low** — Aider-first ([BACKLOG.md](./BACKLOG.md) BL-004); headless / `opencode run` when explored |
| Claude Code, Codex CLI, Gemini CLI, Goose, etc. | TBD | Non-interactive modes (`--print` / `-p`, `exec`, etc.) when a backend is justified |

*Principle (unchanged):* any CLI coder with a **non-interactive** invocation path can be adapted; we add engines only when Cursor+Aider path is insufficient.

---

## Design principles

- **Keep it simple** — rules + adapters + process spawn; avoid heavy frameworks early.
- **Pay for value** — cheap intelligence for routing/memory; expensive model for code.
- **Composable sub-agents** — each does one thing, returns, dies; orchestrator composes them.
- **Session-owned state** — wrapper owns memory and spec lifecycle, not the CLI agent.
- **Layered optimization** — task logic here; turn logic in proxy.
- **Controlled specs** — MCP tools write structured MD; executors do not own the contract files.
- **Transparent** — logs and specs are inspectable; sessions resumable.
- **Incremental delivery** — Phase 1 proves delegate + logs; spec system and RAG follow evidence.

---

## Suggested evolution (from ideation — not a fixed schedule)

1. ~~Thin MCP wrapper calling Aider~~ → **Phase 1 spine (done)** ([PHASE1_MVP.md](./PHASE1_MVP.md)).
2. ~~P1-199 + spec experiment~~ → **Phase 1 closed** (review/implement loop).
3. ~~**Phase 2 — context compiler**~~ → **done** (P2-499): assemble_context, tiers, budget, audit — not full smart builder ([PHASE2_MVP.md](./PHASE2_MVP.md)).
4. **Phase 3 — workspace truth + memory lite:** BL-322 tracker (manifest-primary `files_changed`), BL-320 attempt archive, BL-002 keyword RAG, BL-151 gates ([PHASE3_MVP.md](./PHASE3_MVP.md)).
5. **Phase 4 — smart context lifecycle:** cheap LLM builder (BL-001), janitor/skills/topic, verify, Cursor workflow, BL-161 internal pipeline ([PHASES.md](./PHASES.md) § Phase 4).
6. **Phase 5+:** interactive supervised delegate (BL-160), multi-host, product UX (BL-152), ensemble (BL-007).
7. Connect `context_optimizer_proxy` by default in templates → backlog / polish.
8. OpenCode / other hosts → **very low priority** (BL-004, BL-201/202).

Manual familiarity with Aider in real repos remains valuable while MCP automates delegation.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-03 | Initial vision (`074753b` README): core problem, three context sources, future MCP/CLI, backends |
| 2026-06-04 | Grok ideation: spec system, role division, interaction modes, Phase 1 vs long-term; P1-100 status |
| 2026-06-05 | Stewardship banner; restored original README anchors; [VISION_DOCS.md](./VISION_DOCS.md) map; P1 spine + transcript dump status |
| 2026-06-07 | Added **workspace history** (BL-322) as core capability — delegation-granularity version control, Phase 3 |
| 2026-06-08 | Phase 2 closed (P2-499); Phase 3 active; phase arc 3–5 in PHASES; tracker-primary attribution |
