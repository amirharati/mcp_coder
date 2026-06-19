<!--
  STEWARDSHIP — Tier 1 delivery plan. See docs/VISION_DOCS.md.

  - Do NOT rewrite phase boundaries or principles without explicit user request.
  - Must stay consistent with docs/IDEA.md (canonical WHY).
  - Workers: docs/tasks/*.md only; planning session updates this doc.
-->

# mcp-coder: Phases & Delivery (BD)

This document is the **delivery plan**: what to build, in what order, and how we validate each step. Vision and rationale live in [IDEA.md](./IDEA.md) · doc map: [VISION_DOCS.md](./VISION_DOCS.md). Implementation happens in focused coding sessions once a phase (or sub-step) is agreed.

**Status:** Phase 1 **complete** (P1-199). Phase 2 **complete** (P2-499). Phase 3 **complete** (P3-499). Phase 4 **complete** (2026-06-09). Phase 5 **complete** (2026-06-13). Phase 6 **complete** (2026-06-13). Phase 7 **complete** (2026-06-13; optional capstone met). Phase 8 **complete** (2026-06-14; P8-001..P8-006 delivered). Phase 9 **complete** (2026-06-17; P9-001..P9-013 shipped, P9-015 superseded). **Phase 10 complete** (closed 2026-06-18; P10-001..P10-004 shipped). See [PHASE10_MVP.md](./PHASE10_MVP.md).

---

## Principles (all phases)

| Principle | Meaning |
|-----------|---------|
| **MCP = thin JSON in** | The host (Cursor) does not send full chat history to MCP tools—only tool arguments. Full context must be obtained another way or summarized by the host LLM. |
| **Cursor = orchestrator (cheap)** | Use a capable-but-cheap model in Cursor for planning, summarization, and tool calls. Heavy coding runs inside `mcp-coder` + CLI agent (expensive model only where it matters). |
| **Execution = adapter** | Each CLI coder (Aider, OpenCode, …) gets an adapter using the *best* integration for that tool (Python API vs subprocess). |
| **Proxy is separate** | [context_optimizer_proxy](https://github.com/amirharati/context_optimizer_proxy) optimizes per-turn LLM calls. `mcp-coder` optimizes per-task delegation. They compose but are independent projects. |
| **Phase 1 = pass-through** | Cursor summary in MCP args; later Cursor transcript on disk via **host adapter**. No owned context pipeline in Phase 1. |
| **Phase 1 = infra first** | User-home store (`~/.mcp-coder`), adapters, linked logs — then session persistence, then full transcript context. |
| **Host vs core** | Cursor-specific paths only in `core/host/cursor.py`. Other clients get their own host adapter later. |
| **Phase 2+ = owned context** | RAG, multi-LLM roles (build context vs execute), repo docs, routers—see below. |
| **Log every delegation** | From step **1.0** onward—one structured record per MCP tool call (see Observability below). |

### Phase boundary (important)

| | **Phase 1** | **Phase 2 and beyond** |
|---|-------------|------------------------|
| **Context source** | **Early:** Cursor `context_summary` in tool args. **Late P1:** Cursor `agent-transcripts` via host adapter. Not SpecStory. | `mcp-coder` builds and manages its own context |
| **LLMs inside mcp-coder** | None required (only Aider → provider). Optional cheap classifier → backlog | Yes—context-builder, RAG, file pick, etc. |
| **Memory / RAG** | No | Yes—session store, past tasks, repo docs, embeddings optional |
| **Session logic** | Disk-backed `mcp_session_id` under `~/.mcp-coder`; link to `host_session_id`; policies `always_new` \| `align_host` | Cross-day memory, explicit `continue_session`, RAG |
| **Storage** | Canonical logs/sessions in `MCP_CODER_HOME`; workspace pointer only | Optional team sync / DB |
| **Smart steps** | **None** beyond delegate + pass context + session heuristic | File picking, summarization, janitor, verification, sub-agents, etc. |

### Phase arc (what each phase owns)

| Phase | One-line focus | PM / design |
|-------|----------------|-------------|
| **1** | Delegate + pass-through context + sessions + specs | [PHASE1_MVP.md](./PHASE1_MVP.md) (frozen) |
| **2** | **Context compiler** — what goes *in* the prompt per delegate | [PHASE2_MVP.md](./PHASE2_MVP.md) (frozen); [phase2-owned-context.md](./notes/phase2-owned-context.md) |
| **3** | **Workspace truth** + planner history + delegation RAG shipped (scope → Phase 5) | [PHASE3_MVP.md](./PHASE3_MVP.md); [WORKSPACE_HISTORY.md](./OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md) |
| **4** | **Context builder + manager** — smart assembly, cheap LLM file picker, janitor, verify, internal pipeline | [PHASE4_MVP.md](./PHASE4_MVP.md) **complete** 2026-06-09; carried gaps → BACKLOG § Phase 4 exit |
| **4.5** | **Full stack onboarding** — Phases 1–4 tutorials, architecture docs, live inspection, gap analysis; no new arc number | [PHASE4.5_MVP.md](./PHASE4.5_MVP.md) **active** |
| **5** | **RAG + retrieval integration** — retrieval contract, delegation RAG → builder, workspace-file corpus, RAG toolset (CLI+MCP) | [PHASE5_MVP.md](./PHASE5_MVP.md) **complete** 2026-06-13 |
| **6** | **Observability substrate + reasoning buffer** — `core/observability/` adapter seam; live tokens; trace files; reasoning hot buffer; training opt-in (POC/MVP of AGENTIC_LOOP_LOGGING product) | [PHASE6_MVP.md](./PHASE6_MVP.md) **complete** 2026-06-13 |
| **7** *(complete)* | **Executor loop ownership + unified LLM boundary** — own every executor turn (BL-350); `LlmGateway` proxy for all LLM calls (BL-368); compile provenance bundle; per-turn trace events | Closed 2026-06-13 — see `PHASE7_MVP.md` |
| **8** *(complete)* | **Backend interception: full Aider visibility** — `ObservableModel` captures Aider inner-loop calls; backend interception contract; CLI bootstrap hardening; transcript byte-range provenance; streaming dedup hardening | [PHASE8_MVP.md](./PHASE8_MVP.md) **complete** 2026-06-14 |
| **9** *(complete)* | **Write-always + universal proxy + replay** — `LocalLlmProxy` between litellm and provider captures raw HTTP before normalization; write-always storage; context package blobs; `mcp-coder replay <id>`; storage GC first slice | [PHASE9_MVP.md](./PHASE9_MVP.md) **complete** 2026-06-17 |
| **10** *(complete)* | **Trustable real-project dogfood** — executor behavior shaping (`system_prompt_prefix` / `edit_format`); MCP `ctx.info` progress notifications + `logs tail`; stall detection → `needs_input`; Phase 9 backlog clearance | [PHASE10_MVP.md](./PHASE10_MVP.md) **complete** 2026-06-18 |
| **11** *(active)* | **Supervised execution + smarter context** — `SupervisedIO` + `DelegationSupervisor` (replace `yes=True`); pre-delegation clarity pass; executor-pull `/read` hint; mid-run human gate (experimental); tier-1 post-executor reviewer; smart architect trigger; host `model_policy` arg (BL-512 Stage 2) | [PHASE11_MVP.md](./PHASE11_MVP.md) **active** 2026-06-18 |
| **12+** | Multi-step plan object + async resume token; full executor-pull sidecar; tier-2 epic-boundary review; BL-513 AI-suggested params; BL-514 dynamic escalation; cross-session reasoning (BL-333); out-of-process proxy extension | BL-350, BL-513–515, BL-321, BL-160, BL-007, BL-333 |

**Principle (Phase 3+ attribution):** MCP reports `files_changed` from **delegation-scoped workspace manifest delta** — git-agnostic, backend-agnostic. User git is complementary; optional `git_tracked` metadata later (trivial).

---

## Phase 1: Delegation + pass-through context (MVP)

### Goal

Prove end-to-end value in **Cursor only**:

1. Cursor delegates implementation to an MCP tool instead of doing multi-file edits itself.
2. Aider (via adapter) runs the task and writes to disk.
3. Cursor sees results and can continue the conversation.
4. We learn how Cursor routes to MCP and whether session reuse helps follow-ups.

**Phase 1 does not do context management.** It forwards context and runs the coder. All “smart” context work starts in Phase 2.

### What Phase 1 is (and is not)

| In scope | Out of scope (Phase 2+) |
|----------|-------------------------|
| One primary MCP tool: `delegate_to_agent` | Any LLM inside `mcp-coder` (context builder, router, janitor) |
| Aider adapter (Python API) | RAG DB, `rag_search`, internal repo-doc library |
| **Pass-through context** (summary, then Cursor transcript via host adapter) | Compacting, ranking, or rewriting context ourselves |
| **Home storage** + host adapter + session registry on disk | Cross-day RAG, spec gatekeeper |
| **Session reuse** per `mcp_session_id` / `align_host` (see below) | Arbitrary resume across hosts without reconstruction |
| Return: success, output tail, files touched, `session_reused` | Skills injection, critic/test sub-agents, ensemble |
| **Structured delegation logs** (JSONL, per call) | Fancy UI (optional later); full prompt retention only in debug mode |

### Observability & logging (Phase 1 — from 1.0)

We need **precise, inspectable logs** from the first coding sub-session—not added later. Goal: answer “what happened, when, and why” for every `delegate_to_agent` call without guessing.

Inspired by trip-style logging in [context_optimizer_proxy](https://github.com/amirharati/context_optimizer_proxy) (one JSONL line per unit of work), but scoped to **delegations** (MCP in → Aider out → MCP response).

#### One record per delegation

Each tool invocation produces exactly one **`delegation`** record, written at end of call (or on failure). **Canonical path** (P1-110+):

```
~/.mcp-coder/projects/<project_key>/sessions/<mcp_session_id>/delegations.jsonl
```

See [notes/storage-and-linking.md](./notes/storage-and-linking.md). Env: `MCP_CODER_HOME` (default `~/.mcp-coder`).

**P1-100 legacy:** `<workspace>/.mcp-coder/logs/delegations.jsonl` — replaced by home store; optional mirror via `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE=1`.

Every record includes `project_key`, `mcp_session_id`, `session_dir`, `log_path`, and (when known) `host_kind`, `host_session_id`.

Optional: mirror a human-readable **summary line** to stderr when `MCP_CODER_LOG_VERBOSE=1`.

#### Required fields (every delegation)

| Field | Purpose |
|-------|---------|
| `delegation_id` | UUID for this call |
| `timestamp_start` / `timestamp_end` | ISO-8601 UTC |
| `duration_ms` | Wall time for entire delegation (MCP handler) |
| `workspace_path` | Project root used |
| `tool_name` | e.g. `delegate_to_agent` |
| `mcp_request` | Full tool arguments as received (JSON object) |
| `backend` | e.g. `aider` |
| `context_mode` | `fallback` \| `host_transcript` (P1-140+) |
| `session_action` | `new` \| `reuse` |
| `session_reason` | Machine-readable why (see session enum below) |
| `session_policy` | e.g. `fallback:always_new`, `fallback:heuristic`, `specstory:context` |
| `session_id` | In-process id for reused Aider instance (stable until `new`) |
| `model` | Model id/name passed to Aider (and provider if known) |
| `success` | boolean |
| `error` | string or null (exception class + message on failure) |
| `response_to_cursor` | Exact object/string returned to MCP host (may truncate in normal mode) |
| `files_requested` | `target_files` from MCP |
| `files_changed` | Best-effort list after run (git diff / adapter) |

#### Context snapshot (what Aider actually saw)

Log **provenance and size**, not only the user’s `task`:

| Field | Purpose |
|-------|---------|
| `context.host_transcript_path` | Path to host transcript (e.g. Cursor `.jsonl`), or null |
| `context.host_transcript_mtime` | File mtime if used |
| `context.host_transcript_hash` | SHA-256 of transcript injected |
| `context.host_transcript_bytes` | Size of transcript injected |
| `context.specstory_*` | **Deprecated** — do not use for new work; SpecStory → backlog |
| `context.fallback_summary_hash` | Hash of `context_summary` (+ constraints/snippets) for fallback |
| `context.prompt_chars` / `context.prompt_tokens_est` | Final prompt length sent to Aider (chars + rough token estimate) |
| `context.prompt_hash` | Hash of assembled prompt (compare across calls) |
| `context.prompt_preview` | First ~500 chars (normal mode) |
| `context.prompt_full` | Full prompt only if `MCP_CODER_LOG_FULL_PROMPT=1` |
| `context.truncated` | `true` if dumb cap applied (Phase 1 optional) |
| `context.truncation_reason` | e.g. `max_specstory_bytes` |
| `context.bytes_dropped` | How much was cut (if truncated) |

This makes it obvious whether follow-ups reused the same context or silently shifted—and whether a failure correlates with prompt size.

#### Timing breakdown

| Field | Purpose |
|-------|---------|
| `timing.context_load_ms` | Host transcript read / hash / assemble |
| `timing.session_decision_ms` | Reuse vs new logic |
| `timing.engine_run_ms` | Aider `Coder.run()` (or subprocess) |
| `timing.post_process_ms` | git diff, file list, log write |

#### Token usage (best effort)

Aider/provider may expose usage inconsistently. Log what we can; never fail the delegation if missing.

| Field | Purpose |
|-------|---------|
| `tokens.input` / `tokens.output` / `tokens.total` | If reported by adapter |
| `tokens.source` | e.g. `aider_message`, `provider_response`, `unavailable` |
| `tokens.note` | Optional string if estimated or partial |

Phase 2+ may add separate token lines for the context-builder LLM; Phase 1 only tracks **executor** (Aider) usage.

#### Session reasons (standard enum)

Same values as [Session persistence in Phase 1](#session-persistence-in-phase-1-only-when-useful)—use in logs and MCP return. Include `session_policy` on every record.

#### Example record (abbreviated)

```json
{
  "type": "delegation",
  "delegation_id": "a1b2c3d4-...",
  "timestamp_start": "2026-06-03T19:45:01.123Z",
  "timestamp_end": "2026-06-03T19:47:22.456Z",
  "duration_ms": 141333,
  "workspace_path": "/path/to/repo",
  "tool_name": "delegate_to_agent",
  "mcp_request": { "task": "...", "target_files": ["src/foo.py"], "context_summary": "..." },
  "backend": "aider",
  "context_mode": "fallback",
  "session_action": "reuse",
  "session_reason": "heuristic_reuse",
  "session_id": "sess-inproc-1",
  "model": "claude-sonnet-4-20250514",
  "context": {
    "specstory_path": null,
    "fallback_summary_hash": "abc123...",
    "prompt_chars": 4200,
    "prompt_tokens_est": 1050,
    "prompt_hash": "def456...",
    "prompt_preview": "..."
  },
  "timing": {
    "context_load_ms": 2,
    "session_decision_ms": 1,
    "engine_run_ms": 140800,
    "post_process_ms": 530
  },
  "tokens": { "input": 12000, "output": 3400, "total": 15400, "source": "aider_message" },
  "success": true,
  "error": null,
  "files_requested": ["src/foo.py"],
  "files_changed": ["src/foo.py"],
  "response_to_cursor": { "success": true, "summary": "...", "session_reused": true, "session_reason": "heuristic_reuse" }
}
```

#### Implementation notes (for coding sub-session)

- **`core/logging/delegation_log.py`** — build record, append JSONL, redact secrets (API keys in env dumps).
- Wrap MCP tool handler: `timestamp_start` → work → `timestamp_end` → write log (even on exception).
- Adapter hook: after `coder.run()`, try to parse token usage from return value / coder state (document what Aider exposes when implementing).
- **1.0 deliverable:** logging works in fallback mode with `session_action: new` and `first_call` only; extend fields as home storage (1.1), host hints (1.2), session reuse (1.3), transcript inject (1.4).
- Later: small CLI `mcp-coder logs tail` or `inspect_delegations.py` (like proxy’s `inspect_logs.py`)—not required for 1.0.

### Storage & linking (Phase 1 — from P1-110)

**Canonical store:** `MCP_CODER_HOME` (default `~/.mcp-coder`). Sessions and logs are **not** the source of truth inside the git repo.

| Artifact | Path |
|----------|------|
| Project registry | `~/.mcp-coder/projects/<project_key>/project.json` |
| Session metadata | `.../sessions/<mcp_session_id>/session.json` |
| Delegation log | `.../sessions/<mcp_session_id>/delegations.jsonl` |
| Workspace pointer | `<workspace>/.mcp-coder/project.json` (optional) |
| Cursor transcript (read-only) | `~/.cursor/projects/<slug>/agent-transcripts/<host_session_id>.jsonl` |

Full schema: [notes/storage-and-linking.md](./notes/storage-and-linking.md).

### Context in Phase 1: pass-through only (no owned context pipeline)

We do **not** build smarter context in Phase 1—no internal LLM, RAG, or repo-wide assembly. What Aider sees evolves in **sub-steps**:

| Stage | When | What we pass to Aider |
|-------|------|------------------------|
| **Fallback (P1-100–1.3)** | Now | `context_summary` + `task` from MCP tool args (Cursor-compressed subset) |
| **Host transcript (P1-140)** | After session infra | Normalized text from Cursor `agent-transcripts` via **host adapter**, plus summary + task |

**SpecStory is out of scope** for Phase 1 (see [BACKLOG.md](./BACKLOG.md) BL-203 / BL-505). **Spec-as-contract** is decided at **end of Phase 1** (P1-199), not a blocking milestone.

No summarization *inside* `mcp-coder` in Phase 1. Summarization in Cursor before the tool call remains valid for fallback mode.

### Context size limits & expected failures (Phase 1)

**Yes—we should expect errors once context gets large.** Phase 1 does not summarize, rank, or trim intelligently. Long Cursor chats + file contents in Aider’s context can exceed the executor model’s window (or provider limits).

| Mode | Typical overflow scenario |
|------|---------------------------|
| **Host transcript** | Transcript grows over a long Composer session; we prepend the **entire** `.jsonl` (or tail) plus `task` and file contents → prompt too large |
| **Fallback** | Less common for chat text (Cursor already compressed), but huge `code_snippets_from_chat` or many large `target_files` can still blow the budget |
| **Session reuse** | Reused Aider instance **accumulates** its own turn history **in addition** to whatever we inject each call—increases risk on follow-ups |

**How failures may appear**

- Provider / Aider errors: context length exceeded, max tokens, 400 with “prompt too long”, etc.
- Timeouts or truncated failures on very large prompts
- Degraded results (model silently drops middle context)—harder to detect; logs help

**What logging is for (Phase 1)**

Before changing behavior, use delegation logs to **inspect what we sent**:

- `context.prompt_chars`, `context.prompt_tokens_est`, `context.prompt_hash`
- `context.host_transcript_bytes` / `host_transcript_hash` (did the transcript grow?)
- `context.prompt_preview` vs `MCP_CODER_LOG_FULL_PROMPT=1` for forensics
- On failure: `error`, `success: false`, same context fields → correlate size with breakage

**Phase 1 policy (no smart compression)**

| Do in Phase 1 | Defer to Phase 2+ |
|---------------|-------------------|
| Log size metrics on every delegation | Context-builder LLM to summarize / select |
| Optional **dumb safety cap** (see below) | RAG: inject only relevant past sessions |
| Return clear error message to Cursor when provider rejects prompt | Janitor: refresh stale context |
| Document limits in README | Token-tier budgets per task type |

**Optional dumb cap (experimentation only—not “smart”)**

If we hit overflows often during 1.2 testing, allow a config guardrail without building Phase 2:

- `MCP_CODER_MAX_PROMPT_CHARS` or `MCP_CODER_MAX_TRANSCRIPT_BYTES`
- When exceeded: truncate transcript (e.g. keep **tail** = most recent messages) and set in log:
  - `context.truncated: true`
  - `context.truncation_reason: "max_transcript_bytes"`
  - `context.bytes_dropped: N`

This is **not** summarization—it is an explicit, logged chop so we can still run experiments. Prefer learning from uncapped failures first, then add cap if needed.

**Success criterion for experiments:** When a call fails, one JSONL line should be enough to answer: “Was it too much context? How big? Transcript or fallback? New or reused session?”

#### Mode A — Summary fallback (P1-100 through P1-130)

**How it works:** Tool schema requires Cursor’s LLM to pack relevant chat into structured fields before calling the tool.

**Pros:** Works with Cursor only; no extra extensions; validates plumbing fast.

**Cons:** “Telephone game”—nuance (exact hex codes, variable names, “the trick we discussed”) can be lost if the summarizer omits them.

**Mitigation (schema design):** Don’t rely on a single blob. Require:

- `task` — what to do now
- `target_files` — paths to scope Aider
- `context_summary` — high-level goal and decisions
- `explicit_constraints` (optional array) — rules, names, colors, APIs that must not be paraphrased
- `code_snippets_from_chat` (optional array) — verbatim snippets from the user

**Cursor setup note:** Prefer Auto or a cheap/fast model for chat + tool routing; execution model is chosen inside Aider (or via env pointing at `context_optimizer_proxy`).

#### Mode B — Host transcript (P1-140, Cursor first)

**How it works:** `CursorHostProvider` resolves `host_session_id` and reads `~/.cursor/projects/<slug>/agent-transcripts/<id>.jsonl`. Transform JSONL → text block; prepend to Aider prompt with `context_summary` + `task`.

**Heuristic for “active chat”:** e.g. newest transcript by mtime, or match to current Composer session when detectable.

**Pros:** No SpecStory extension; aligns with Cursor’s on-disk layout; linkable via `host_session_id` in our session store.

**Cons:** Undocumented Cursor schema; may change; parsing lives only in `core/host/cursor.py`.

**Fallback:** If no transcript → Mode A fields only.

### Session persistence in Phase 1 (disk registry + in-process executor)

Each MCP call is a new MCP message. **mcp-coder owns `mcp_session_id`** under `~/.mcp-coder`. Cursor (or another host) supplies **`host_session_id`** as a hint—not the sole session key.

| Layer | Persists? | Notes |
|-------|-----------|-------|
| **Disk** (`session.json`, `delegations.jsonl`) | Yes | Survives MCP restart |
| **In-process Aider `Coder`** | Per `mcp_session_id` | Re-created after restart; prompt reconstructed from spec/summary/transcript later |

#### Policies (P1-130)

| Policy | Behavior |
|--------|----------|
| **`always_new`** (default) | New `mcp_session_id` folder every delegation |
| **`align_host`** | Reuse **latest** session with same `(project_key, host_session_id)`; if host unknown → `always_new` |

Env:

```bash
MCP_CODER_SESSION_POLICY=always_new   # default
# MCP_CODER_SESSION_POLICY=align_host
```

**Many mcp sessions per Cursor chat** is normal (record all; picking a “main” session is backlog). See [storage-and-linking.md](./notes/storage-and-linking.md).

#### Session reason enum (log + MCP return)

| Value | Meaning |
|-------|---------|
| `first_call` | No prior session for this policy |
| `policy_always_new` | Forced new |
| `align_host_reuse` | Reused session for same host id |
| `align_host_new` | New session (no host id or first for this host) |
| `heuristic_*` / `classifier_*` | Backlog optional experiments |

**Not in Phase 1:** `continue_session` with arbitrary id, DB sync, cross-machine session port.

### Adapter architecture (Phase 1)

**Four layers — do not mix host paths into engine or logging.**

```
core/host/
  base.py              # HostContextProvider protocol, HostSessionHint
  cursor.py            # Cursor-only: slug, agent-transcripts (ONLY Cursor imports here)
  factory.py           # get_host_provider() — cursor default for P1

core/storage/          # P1-110
  paths.py             # MCP_CODER_HOME, project_key, session dirs
  project_registry.py
  session_store.py     # P1-130

core/engine/           # P1-100 — unchanged contract
  base.py              # ExecutionEngine
  aider_engine.py
  factory.py

core/logging/
  delegation_log.py    # writes under session_dir from storage layer
```

| Adapter | Swaps | Phase 1 |
|---------|--------|---------|
| **Host** | Cursor vs Claude Desktop vs … | Cursor only |
| **Execution** | Aider vs OpenCode | Aider only |
| **Provider** | OpenRouter, Anthropic, … | Via Aider env |

**OpenCode (later):** subprocess adapter in Phase 2 or spike ([BACKLOG.md](./BACKLOG.md) BL-004).

### MCP tool (target shape)

**Name:** `delegate_to_agent` (or `deep_code_execution` — pick one and tune description so Cursor routes “real coding” here).

**Description (intent):** Tell Cursor this is the primary implementation tool for multi-file / complex work; host must supply context the isolated agent cannot see.

**Parameters (evolve across sub-steps):**

| Parameter | Step | Required |
|-----------|------|----------|
| `task` | 1.0 | yes |
| `target_files` | 1.0 | yes |
| `context_summary` | 1.0 | yes (Mode A) |
| `explicit_constraints` | 1.1 | optional |
| `code_snippets_from_chat` | 1.1 | optional |
| `backend` | 1.0 | optional, default `aider` |
| `workspace_path` | 1.2 | optional if cwd is enough |

**Returns:** `success`, `output` (truncated log), `files_changed` (best-effort from git status or Aider output), optional `session_reused: bool`.

### Phase 1 sub-steps (implementation order — replanned)

Track tasks in [PHASE1_MVP.md](./PHASE1_MVP.md).

#### 1.0 — Barebones (done, P1-100)

- MCP + `AiderEngine` + `delegate_to_agent`; workspace-local JSONL; `always_new`.

#### 1.1 — Home storage & linking (P1-110) **next**

- `MCP_CODER_HOME`, `project_key`, per-session folders, linked JSONL fields.
- Optional workspace `project.json` pointer; migrate off workspace-only logs.

**Done when:** Every delegation is findable under `~/.mcp-coder/projects/.../sessions/...`.

#### 1.2 — Host adapter — Cursor (P1-120)

- `HostContextProvider` + `cursor.py`; populate `host_session_id` on session + logs.
- No transcript injection yet.

**Done when:** Cursor-specific paths exist only under `core/host/`.

#### 1.3 — Session persistence (P1-130) — `done`

- `SessionStore`; policies `always_new` | `align_host`; executor cache per `mcp_session_id`.
- Host scoring: `max(transcript mtime, delegation history)` + tie window.
- E2E 2026-06-04: `align_host`, 5 delegations → one `mcp_session_id`. See `docs/tasks/P1-1.3-session-persistence.md` § Results.

**Done when:** `align_host` reuses same `mcp_session_id` for follow-ups in one Cursor chat. ✓

#### 1.4 — Full context — Cursor transcript (P1-140)

- Parse `agent-transcripts/*.jsonl`; inject into prompt; size caps + logging.

**Done when:** Long-chat experiment beats summary-only; failure modes visible in JSONL.

#### 1.9 — Phase 1 exit review (P1-199)

- Spec-as-contract, gatekeeper, Phase 2 priorities — from real logs.

#### Optional / backlog

- P1-115: `explicit_constraints`, snippets — if transcript still loses nuance.
- P1-131 / BL-102: cheap LLM session classifier.
- SpecStory integration — **not planned** (BL-505).

### Phase 1 success criteria (overall)

- [ ] Cursor discovers and uses the tool for non-trivial coding when prompted (rules/skills can nudge).
- [ ] Token usage on Cursor side stays low (tool call + summary, not full-repo agent loop).
- [ ] Aider completes tasks on scoped files; user can review diffs in Cursor.
- [ ] Mode A (summary) and Mode B (host transcript) documented with known limitations.
- [ ] Home storage and session linking documented ([storage-and-linking.md](./notes/storage-and-linking.md)).
- [ ] Each delegation has a complete JSONL record (timing, context snapshot, model, tokens if available, response).
- [ ] Notes captured from experiments (routing reliability, failure modes, follow-up behavior) for Phase 2/3—grounded in logs, not memory.

### Phase 1 open questions (resolve during experiments)

1. Does Cursor reliably pass `target_files`, or do we need to infer from open tabs / `@` mentions in `task`?
2. Optimal tool name/description for ~70–90% routing on “big” tasks without nagging every turn?
3. Transcript tail cap default after measuring failures in logs (P1-140).
4. Spec-as-contract: when and how (P1-199 only).
5. At what `prompt_tokens_est` do we consistently fail per model (document in experiment notes)?
6. Should Aider point at `context_optimizer_proxy` base URL by default in our config template?
7. Dry-run mode for MCP (`--dry-run` Aider) for safe first tests?

### Suggested project layout

```
mcp_coder/
  pyproject.toml
  main.py
  server/mcp_server.py
  core/
    host/                   # P1-120 — cursor.py only place for Cursor paths
    storage/                # P1-110, P1-130
    engine/                 # P1-100
    logging/delegation_log.py
    context/summary.py      # Mode A; transcript assembly P1-140

# User home (canonical):
~/.mcp-coder/projects/<project_key>/sessions/<mcp_session_id>/

# Workspace (optional pointer, gitignored):
<workspace>/.mcp-coder/session.json   # system pointer (project_key, sessions_root)
<workspace>/.mcp-coder/config.yaml    # user-owned session_policy etc.
```

---

## Phase 2 and beyond: Owned context management

Starting Phase 2, `mcp-coder` stops relying solely on pass-through (`context_summary`, opt-in transcript dump) and **builds and manages context itself** — a **context compiler** with per-path materialization tiers ([notes/phase2-owned-context.md](./notes/phase2-owned-context.md)). This is where the vision in [IDEA.md](./IDEA.md) (router, janitor, RAG, token tiers) is implemented.

**Explicitly not Phase 2 focus:** OpenCode or other execution adapters ([BACKLOG.md](./BACKLOG.md) BL-004 — very low / if ever). **Aider + Cursor** until the product is useful. Other hosts (Claude Desktop, Windsurf) are also low priority (BL-201/202).

### Multi-LLM roles (intent)

| Role | Typical model tier | Job |
|------|-------------------|-----|
| **Context builder** | Cheap (mini / Flash) | Summarize chats, pick files, topic boundaries, query RAG (Phase 3), compress history, refresh stale facts |
| **Executor** | Expensive (Sonnet / Opus) | Run inside **Aider** for actual edits |
| **Optional helpers** | Cheap | RAG query, lint/test check, critic before returning to Cursor |

Phase 1 uses only the executor (via Aider). Phase 2+ adds the context-builder **inside** `mcp-coder`.

### Phase 2: MCP-owned context (two halves)

**Goal:** Useful delegations without huge prompts or wrong-topic context — without new engines or hosts.

| Half | What |
|------|------|
| **Context creation** | What to put in the prompt: spec-as-contract (experiment), file pickers, skills, constraints — not a raw chat dump by default |
| **Context window management** | Stay inside model limits: rolling transcript, summarize chunks, caps, logged truncation — same program as creation |

**Indicative scope** ([BACKLOG.md](./BACKLOG.md) § Post–Phase 1 focus):

1. **Spec workflow** (BL-150 **done** P1-151) — epic/step specs, reports, review loop; extend with owned assembly (BL-001); gatekeeper still BL-151.
2. **Owned assembly** (BL-001) — compact task brief + selected files; cheap LLM and/or rules + ripgrep.
3. **Topic / task detection** (BL-153) — bound work to the right “topic” for sessions and context slices.
4. **Window budget** (BL-154) — rolling history, summarizers, prompt templates.
5. **Skills** (BL-008) — inject by topic/task type.
6. **Executor cache** (BL-155) — build on P1-130 in-process `Coder` cache: today prompt is **rebuilt fully each call**; explore multi-turn carry-over, TTL, survive more than `target_files` equality — not “discard executor state by default.”
7. **Janitor / router** (BL-003) — after basics work.

**Still light on long-term memory:** local turn logs OK; full RAG → Phase 3 (BL-002).

**Success:** Fewer wrong-file edits; smaller focused prompts; topic-aware sessions; measurable `prompt_tokens_est` down vs `host_transcript: dump`.

*(Cheap LLM session classifier remains optional — BL-102; may feed topic detection.)*

### Phase 3: Workspace truth, planner history, and memory

**PM board:** [PHASE3_MVP.md](./PHASE3_MVP.md) · **Issues:** [PHASE3_ISSUES.md](./PHASE3_ISSUES.md)

**Goal:** Trustworthy delegation audit in non-git workspaces; planner-visible retry history; light cross-session recall. **Not** a full smart context-builder phase — that is Phase 4.

**What Phase 3 is:**

| In | Out (→ Phase 4+ / backlog) |
|----|------------------------------|
| Workspace tracker (`workspace_history.db`) | Cheap LLM file picker / janitor |
| Manifest-primary `files_changed` / `files_unexpected` | Rolling chat summarization |
| Failed-attempt archive (BL-320) | Skills, topic router (BL-008, BL-153) |
| RAG **lite** — keyword + recency (BL-002) | Embeddings-first RAG |
| Post/pre gates (322c, BL-151) | Multi-step internal pipeline (BL-161) |
| `delegation_diff` in MCP (322d) | Live terminal / supervised mega-delegate (BL-160) |

**Waves:** [PHASE3_MVP.md](./PHASE3_MVP.md) — **closed** 2026-06-09 (P3-499). Waves 1–3 shipped; Wave 4 gates → Phase 4 backlog.

**Success:** ✓ Non-git attribution; checkpoint inspect; delegation RAG shipped; versioned specs (`v1`). Residual planner UX → BL-324–328.

**Issues (frozen):** [PHASE3_ISSUES.md](./PHASE3_ISSUES.md)

---

### Phase 4: Context builder + manager

**Goal:** Use Phase 2 compiler + Phase 3 history to **actively build and manage** context — smart file selection, cheap-LLM assembly, janitor, verify loop, internal pipeline.

**Rationale (2026-06-09):** Build the context pipeline first; RAG is an *input* to it. Once Phase 4 is running you'll know exactly which retrieval problems are real, what query shapes are needed, and whether the existing delegation RAG (`core/rag/`) is sufficient or needs extending with workspace-file summaries.

| Theme | Backlog / intent |
|-------|------------------|
| **Smart context builder** | BL-001 — file picker (rules + ripgrep, D-P4-11 repo map) + cheap-LLM brief (session history, mode-aware, D-P4-12) |
| **Per-role models** | D-P4-8 — one configurable model + audit per role (executor/review/builder); Stage 2+ escalation/critic/swarm → BL-162, [notes/multi-model-roles.md](./notes/multi-model-roles.md) |
| **Topic / skills** | BL-153 topic boundaries; BL-008 skills injection |
| **Janitor / router** | BL-003 freshness audit; BL-006 critic / test-writer one-shots |
| **Window & cache** | BL-155 multi-turn executor cache; BL-154 rolling transcript beyond per-call budget |
| **Verification** | BL-310b pytest hook; `partial` outcomes; optional auto re-delegate |
| **Cursor workflow** | BL-106 progress; BL-312 auto-review suggest; richer tool payloads; host transcript policy |
| **Internal pipeline** | BL-161 — architect pass then executor inside one MCP call |
| **Deferred hard cases** | BL-331 symbol-scoped edit files (Phase 5+, executor format change) |

**Success:** Fewer wrong-file edits from smarter prompts; planner acts on structured MCP context; verify-before-accept loop in place; clear picture of where RAG would help.

---

### Phase 4.5: Stack literacy gate *(active)*

**Goal:** Systematic onboarding onto the real Phase 1–4 stack — tutorials, architecture docs, live inspection, and gap analysis — before committing Phase 5 corpus design. No new product phase number; no renumbering of 5+.

**Rationale:** The project was built fast with AI assistance. The pace was intentional but left operator literacy thin. Phase 5 planning should be grounded in evidence from understanding and using the real system, not from specs alone.

| Track | Deliverable |
|-------|-------------|
| **Tutorials (T-01–T-07)** | Phase 1–4 walkthroughs: setup, sessions/storage, specs, context compiler, workspace history/RAG, delegation pipeline, end-to-end trace |
| **Architecture docs** | `docs/notes/architecture-overview.md`; layer map; storage layout; per-role models; "where reality diverges from spec" log |
| **Live inspection** | Flag matrix experiments; real delegation traces; picker recall; token telemetry investigation |
| **Gap analysis** | `docs/notes/phase4.5-gap-analysis.md` — what Phase 5 actually needs to solve (BL-335, BL-338, unknown gaps) |
| **Tool fixes** | Opportunistic small fixes found during inspection; worker dispatched only if > ~30 lines |

**PM board:** [PHASE4.5_MVP.md](./PHASE4.5_MVP.md) · **Issues:** [PHASE4.5_ISSUES.md](./PHASE4.5_ISSUES.md)  
**Does not change:** Phase 5 scope, PHASES.md arc numbers, IDEA.md.  
**Success:** Written gap analysis + walkthrough docs + any small fixes shipped → use findings to finalize Phase 5 RAG corpus decision.

---

### Phase 5: RAG + retrieval integration *(closed 2026-06-13)*

**PM board:** [PHASE5_MVP.md](./PHASE5_MVP.md) (frozen) · **Issues:** [PHASE5_ISSUES.md](./PHASE5_ISSUES.md) (frozen) · **Design:** [notes/rag-gap-analysis.md](./notes/rag-gap-analysis.md)

**Exit:** Recommended tier met (dogfood `712a04d9`, 5+5 `context_refs`). P5-001…P5-004 + P5-006 done. P5-005 deferred. RAG defaults **on**. Carried: BL-335, BL-364.

**Goal (archive):** Move the context builder from *recency + `rg`* toward *relevance retrieval* — delegation RAG + workspace-file summaries + RAG toolset (CLI + MCP).

**Rationale:** Phase 4 shipped the context builder pipeline. Phase 4.5 (literacy gate) confirmed what retrieval problems are real: (1) cross-spec delegation history ignored by builder; (2) fuzzy file recall misses concept-name mismatches. Phase 5 solves both with infra + wiring. Scope locked 2026-06-13.

| Milestone | Status | What |
|-----------|--------|------|
| **P5-001** | done | `ContextRef` + `retrieve()`; BL-335 extractor (live tokens still BL-335) |
| **P5-002** | done | `rag_retrieval` phase; `mcp-coder search delegations` |
| **P5-003** | done | `workspace_rag.db`; `index-workspace`; `search files`; `workspace_search` MCP |
| **P5-004** | done | Picker/builder file hints; merged `context_refs` |
| **P5-006** | done | FTS fix (long tasks, hyphen tokens) |
| **P5-005** | deferred | Recall metric; cost delta; embeddings go/no-go |

**RAG toolset principle:** CLI tools (`mcp-coder search delegations`, `mcp-coder search files`) share implementation with MCP tools. `--format plain` output can be embedded directly in executor prompts — pre-shapes BL-354 (executor-pull) without mid-loop wiring.

**Explicitly NOT Phase 5:** Chat distillation (BL-356), embeddings (measure first), executor-pull BL-354, cross-project RAG, full wire logging BL-353, workflow turns BL-359.

**Success:** Builder pulls a relevant fact from a different spec’s prior delegation and a file the symbol scan would have missed — both visible in `context_refs` and reachable via CLI.

---

### Phase 5+: Reasoning traces & backend prompt control *(placeholder — after Phase 5)*

**Goal (draft):** Capture hidden `reasoning_content` from LLM calls (today discarded by Aider) and turn delegation logs into a reusable intelligence layer — not just audit.

**When to enter:** Phase 5 RAG is running (2026-06-13). Phase 4 builder/manager stable. **Still open:** reliable per-role token telemetry (**BL-335**).

**Three axes** ([REASONING_TRACE_REUSE.md](./OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md)):

| Axis | Intent | Backlog |
|------|--------|---------|
| **Model upgrade / escalation** | Use trace confusion/hedging as signal to step up mid-loop or suggest a stronger model to the planner | BL-321, BL-333 |
| **Transfer intelligence** | Summarize high-end reasoning → inject into later cheap calls (builder, architect, next delegation) | BL-333, P4-001b history |
| **Training / distillation** | `(task, context, trace, outcome)` tuples for fine-tuning and replacing hand-written modules with learned e2e components | BL-333 (long-term) |

**Companion (smaller):** BL-334 — executor `system_prompt_prefix` + edit-format knobs on the Aider adapter (what we *send* at the LLM boundary; BL-333 is what we *keep*).

**Not in scope until Phase 5+:** no capture implementation during Phase 4/5 unless a small observability fix (token counts) unblocks measurement. Design doc + backlog only for now.

---

### Phase 6+: Long-running workflows & product surface

**Goal:** How humans and hosts live in the system for hours/days — not core compiler features.

| Theme | Backlog |
|-------|---------|
| **LLM boundary observability** (full pass-through logging — all roles, all turns) | **BL-353** (TBD; high ROI for gap-finding, RAG/context direction, eval; may share foundation with BL-335 in Phase 5) |
| Interactive / supervised delegate | BL-160a–d |
| Multi-host | BL-201/202 |
| Git-native task branches | BL-502 (pairs with non-git BL-322) |
| Alternate engines | BL-004 OpenCode; **BL-340** Cursor SDK executor |
| Product UX (viewer, team) | BL-152 |
| Multi-model ensemble | BL-007 |

**Turn-level optimization** stays **[context_optimizer_proxy](https://github.com/amirharati/context_optimizer_proxy)** — separate repo under Aider.

### Deferred — tracked in [BACKLOG.md](./BACKLOG.md)

| ID | Theme | Typical phase |
|----|--------|----------------|
| BL-160 | Interactive sessions | 6+ |
| BL-161 | Multi-agent inside MCP (v1 pipeline + architect pass) | **done** P4-020; BL-160 full REPL deferred |
| BL-162 | Multi-model routing | 4 |
| BL-002 | RAG / cross-session memory | 5 |
| BL-315 / P2-315 | MCP progress notifications | 4 |
| BL-333 | Reasoning trace capture + cross-delegation feed | 5+ |
| BL-334 | Backend prompt customization (system prefix, edit-format) | 5+ |
| BL-340 | Cursor SDK execution backend (beside Aider) | 6+ |

---

## Host support matrix (intent)

| Host | Phase 1 | Summary (Mode A) | Host transcript (Mode B) |
|------|---------|------------------|---------------------------|
| **Cursor** | Primary | Yes | Yes (`agent-transcripts`) via `core/host/cursor.py` |
| Claude Desktop | Later | Yes | Separate host adapter when needed |
| Windsurf / others | Later | Yes | TBD |

---

## Relationship to `context_optimizer_proxy`

```
Phase 1:
  Cursor (cheap model, summary + tool call)
    → mcp-coder (pass-through context, session heuristic only)
         → Aider → [optional] context_optimizer_proxy → LLM

Phase 2 (shipped):
  Cursor → mcp-coder (context compiler: assemble_context, tiers, budget)
         → Aider → [optional] proxy → LLM

Phase 3+:
  + workspace tracker + attempt archive + delegation RAG (core/rag/ shipped)

Phase 4+:
  + smart context builder / file picker / janitor / verify / internal pipeline

Phase 5 (closed):
  + delegation + workspace-file RAG wired into builder; RAG defaults on; FTS hardened

Phase 5+ (placeholder):
  + reasoning trace capture (escalation, transfer intelligence, training flywheel)
  + backend prompt control (BL-334)
```

Both projects can be developed in parallel. Phase 1 does not require the proxy or any LLM inside `mcp-coder`.

---

## Phase 7: Executor loop ownership + unified LLM boundary *(complete)*

**Status:** Closed 2026-06-13 — P7-001/002/003 shipped; optional capstone exit met.
**PM doc:** (to be created: `PHASE7_MVP.md`)
**Backlog inputs:** BL-350, BL-368, BL-333, BL-353 (remainder)

### One-line goal

Own every executor turn and route all LLM calls through a single proxy — so Phase 8 can capture 100% with no bypass paths.

### What Phase 7 owns

#### A — Unified LlmGateway proxy (BL-368)

Replace the current dual-path capture (Route A LiteLLM callback + Route B `owned_helper_llm.py`) with one `LlmGateway` in `core/observability/`:

- All owned LLM calls (helpers, `test-model`, future backends) route through it
- Executor path: proxy tap even while still using Aider adapter
- Scope beyond logging: tokens, trace bodies, reasoning, budget caps, redaction, rate limits
- `NullObservability` / tests can swap proxy for no-op
- Callback becomes thin shim or removed once proxy covers all paths

#### B — Executor loop ownership (BL-350)

Break the `coder.run(prompt)` black box into an owned loop:

- **Per-turn LLM I/O** — every executor prompt + response logged as `llm_call` trace event
- **Non-LLM actions** — file edits, shell calls, lint retries between turns logged as `tool_call` / `action` events
- **Step index + parent_call_id** — turn sequence reconstructable from trace alone
- **Reasoning tokens** per executor turn (when model emits) — captured before Aider strips them (BL-333 extend)
- Preferred route: outer loop (Route A) — `compile → run(bounded sub-task) → inspect → recompile → run`; Aider `Coder` subclass (Route C) only if Route A insufficient

#### C — Compile provenance bundle (BL-353 remainder)

Store what went into each pipeline phase — not just flags:

- `mechanical_brief`, `builder_input`, `builder_output`, `architect_input`, `architect_output`, `validation_input`, `validation_output`, `final_executor_prompt` — hashes + bodies in trace
- Host transcript provenance: `source_path`, byte range, `last_source_line` — enough to slice Cursor JSONL for replay
- RAG hits already covered by lean `context_refs` + DB join (Phase 6 done)

### What Phase 7 does NOT own

| Item | Why deferred |
|------|-------------|
| Write-always trace storage (verbosity gate removed) | Needs proxy first — Phase 8 |
| Context package blob sidecar | Phase 8 |
| Systematic delegation replay from disk | Phase 8 (needs all captures in place) |
| Novelty filter / curation | After raw corpus exists — Phase 8+ |
| Cross-session reasoning persistence (BL-333) | After dogfood shows same-session working well |
| Host escalation / blind yes=True replacement (BL-351) | Phase 8+ |

### Phase 7 acceptance (dogfood)

After a live `delegate_to_agent` call:

1. **Every executor LLM turn** is a `llm_call` line in `traces/<id>.jsonl` — prompt + response bodies + tokens.
2. **Non-LLM actions** (file writes, lint runs) appear as `tool_call` / `action` events in the same trace.
3. **All LLM calls** (helpers + executor) pass through `LlmGateway` — one code path, one capture point.
4. **Compile bundle** fields (`builder_input`, `architect_output`, `final_executor_prompt`) are present in trace or sidecar.
5. `mcp-coder maintenance stats` shows executor turns counted per delegation.

---

## Phase 9: Write-always storage + universal proxy + replay *(complete — frozen 2026-06-17)*

**Status:** Complete — frozen 2026-06-17; P9-001..P9-013 shipped; P9-015 superseded; polish deferred to **BL-516**..**BL-519** (CLI log table, `policy_applied` ignored params, log-level DX, proxy env toggle).  
**PM doc:** [PHASE9_MVP.md](./PHASE9_MVP.md) (frozen) · **Issues:** [PHASE9_ISSUES.md](./PHASE9_ISSUES.md) (frozen)

### One-line goal

Capture every LLM byte at the HTTP boundary before litellm normalization, write it unconditionally, and make any delegation replayable from disk.

### What Phase 9 owns

#### A — Write-always trace storage (BL-367 core, D-P9-8)

Remove verbosity from the write gate:

- Trace file written for every delegation unconditionally
- At all verbosity tiers, full prompt and response bodies always written to disk
- `lean` / `standard` / `full` become viewer/CLI/export display filters and RAG promotion gates only

#### B — Context package blob sidecar (BL-367 C1)

Store the exact assembled context package per delegation:

```
sessions/<session_id>/context_packages/<context_package_hash>.json
```

- Deduplication by hash — same package reused across delegations stored once
- Combined with trace file + JSONL row: any delegation is fully replayable from disk without Cursor chat

#### C — Universal internal proxy (BL-508, D-P9-1..D-P9-7)

`LocalLlmProxy` started at MCP server bootstrap. **All in-process LLM calls route through it** (LlmGateway helpers + AiderEngine via litellm). Proxy sits between litellm and the real provider — captures raw HTTP request + response before litellm normalization.

```
litellm → LocalLlmProxy → real provider (OpenRouter / Anthropic / OpenAI)
```

- Model-prefix routing table built from env vars (no separate config)
- Attribution via active context store (`delegation_id_var` + `step_index_var`) — no header injection needed for in-process callers
- Emits `proxy_llm_call` events cross-checked against `backend_llm_call` (Phase 8 `ObservableModel`)
- Proves 100% coverage: any gap shows up as a `proxy_llm_call` with no matching `backend_llm_call`
- Resolves BL-507: raw response at HTTP level reveals definitively whether thinking tokens are present before litellm touches them
- Same proxy extended in Phase 10+ to out-of-process backends (Claude Code, Codex, OpenCode) by pointing their base URL at it — no new proxy code

#### D — Replay CLI (BL-367 E1–E5)

`mcp-coder replay <delegation_id>` reconstructs the full delegation from disk — context package, every executor turn and proxy-captured LLM call, outcome. No Cursor required.

#### E — Storage GC first slice (BL-357)

`mcp-coder maintenance gc [--dry-run]` + TTL config. Promote-then-prune policy. First pass: trace + blob pruning by age.

### What Phase 9 does NOT own

| Item | Why deferred |
|------|-------------|
| Out-of-process backends (Claude Code / Codex / OpenCode) | Phase 10+ — just a base URL config change once proxy exists |
| Inner loop control / BL-351 supervisor | Phase 10+ — visibility before intervention |
| Full re-execution replay (sandboxed) | Phase 10+ |
| Novelty / curation pipeline | After raw corpus exists |
| Training dataset export UI | Separate product scope |
| Cross-session reasoning (BL-333) | Needs corpus to validate |
| Embeddings for RAG (BL-366) | Measure FTS recall first |

### Phase 9 acceptance (dogfood)

After a live `delegate_to_agent` call at any verbosity setting:

1. **Full prompt and response bodies** written to `traces/<id>.jsonl` — not truncated, not gated on verbosity.
2. **Context package blob** stored at `context_packages/<hash>.json` under session dir.
3. **`proxy_llm_call` events** in trace for every LLM call — cross-check vs `backend_llm_call` shows no gaps.
4. **BL-507 resolved** — proxy raw log answers whether thinking tokens are present at the HTTP boundary.
5. `mcp-coder replay <delegation_id>` reconstructs the full delegation from disk — no Cursor.
6. `mcp-coder maintenance gc --dry-run` reports what would be pruned by retention policy.

### Why this order matters

```
Phase 6 — seam + helpers + tokens + lean JSONL  → observability skeleton
Phase 7 — LlmGateway + executor loop            → no bypass paths, all turns captured
Phase 8 — ObservableModel + interception proof  → Aider inner-loop visible
Phase 9 — write-always + proxy + blobs + replay → 100% proven at HTTP boundary, replayable
Phase 10 — trust + visibility + executor shaping → real-project dogfood
Phase 11+ — multi-backend + full outer-loop control
```

---

## Phase 10: Trustable real-project dogfood *(complete)*

**Status:** Complete — closed 2026-06-18; P10-001..P10-004 shipped.
**PM doc:** [PHASE10_MVP.md](./PHASE10_MVP.md) · **Issues:** [PHASE10_ISSUES.md](./PHASE10_ISSUES.md) · **Bootstrap:** [notes/phase10-master-session-bootstrap.md](./notes/phase10-master-session-bootstrap.md)

### One-line goal

Shape Aider's behavior before problems occur, see what is happening while it runs, and handle stalls gracefully — POC/partial level sufficient for real-project dogfood.

### What Phase 10 owns

| Milestone | Theme | Backlog |
|-----------|-------|---------|
| P10-001 | Executor option wiring (`system_prompt_prefix`, `edit_format`) | BL-334 v0 |
| P10-002 | MCP `ctx.info` notifications + `mcp-coder logs tail` | BL-106 POF, BL-520 POF |
| P10-003 | Stall detect → `needs_input` structured response | BL-351 v0 |
| P10-004 | Backlog clearance (policy_applied, proxy toggle, trace summary, env docs) | BL-516/517/518/519 |

### What Phase 10 does NOT own

| Item | Why deferred |
|------|-------------|
| Full inner-loop supervision (BL-350 continuation) | Phase 11 — needs dogfood evidence |
| AI-suggested model params (BL-513) | Phase 11 |
| Dynamic escalation (BL-514) | Phase 11 |
| Out-of-process backend proxy extension | Phase 11 |
| Critic/reviewer (BL-358, BL-006) | Phase 11 |

### Phase 10 acceptance (dogfood)

1. `MCP_CODER_EXECUTOR_SYSTEM_PREFIX` measurably shapes executor behavior.
2. `ctx.info` progress visible in Cursor during delegation (≥5 milestone messages). *(Partial on some Cursor versions — `logs tail` is the reliable fallback.)*
3. `mcp-coder logs tail --latest` follows a live delegation in a side terminal.
4. Aider "add files to chat" stall returns `needs_input` with `files_requested[]` — not silent failure.
5. Executor `policy_applied.ignored` present when temperature/top_p set but not applied.
6. `MCP_CODER_PROXY_ENABLED=0` runs without proxy; `backend_llm_call` still captured.

---

## Phase 11: Supervised execution + smarter context

**Status:** Active — opened 2026-06-18; **P11-001 shipped** 2026-06-19; P11-002..P11-007 pending.
**PM doc:** [PHASE11_MVP.md](./PHASE11_MVP.md) · **Issues:** [PHASE11_ISSUES.md](./PHASE11_ISSUES.md) · **Bootstrap:** [notes/phase11-master-session-bootstrap.md](./notes/phase11-master-session-bootstrap.md)

### One-line goal

Make the Aider/MCP boundary bidirectional and supervised: replace `yes=True` with a judgment-capable supervisor, verify intent before delegation, and scan output quality — all with bounded per-delegation cost.

### What Phase 11 owns

| Milestone | Theme | Backlog |
|-----------|-------|---------|
| P11-001 | Pre-delegation spec clarity pass | BL-521 (new) |
| P11-002 | SupervisedIO + DelegationSupervisor + decision log | BL-351 full |
| P11-003 | Executor-pull v0: system prefix `/read` hint | BL-354 v0 |
| P11-004 | Mid-run human gate: `answer_delegation_question` tool (experimental) | BL-522 (new) |
| P11-005 | Tier-1 post-executor reviewer (cheap model scan on files_changed) | BL-358 v0 |
| P11-006 | Smart planner-pass trigger: heuristic skip for trivial tasks *(named architect trigger until P11-008 rename)* | — |
| P11-007 | Host `model_policy` arg on `delegate_to_agent` | BL-512 Stage 2 |

### Cross-phase architectural decisions (locked in Phase 11)

See full table in [PHASE11_MVP.md](./PHASE11_MVP.md) § Cross-phase architectural decisions. Summary:

- **D-ARCH-1:** Context frugality — every LLM call gets a purpose-built bounded context (2k–32k depending on role)
- **D-ARCH-2:** Strong LLM (Sonnet-class) for judgment calls (supervisor); cheap for review/clarity
- **D-ARCH-3:** Aider thread stays alive through SupervisedIO — no restart on supervisor decision
- **D-ARCH-4:** Per-delegation in-memory decision log — supervisor has cross-decision coherence
- **D-ARCH-5:** Human escalation v1 = abort-and-resume; mid-run gate is experimental
- **D-ARCH-6:** `model_policy` is additive — host > env > code defaults, per-role

### What Phase 11 does NOT own

| Item | Why deferred |
|------|-------------|
| Multi-step plan object + async resume token | Phase 12 |
| Full executor-pull sidecar HTTP server | Phase 12 — P11 ships prompt-only |
| Tier-2 epic-boundary review | Phase 12 — needs epic boundary concept |
| BL-513 AI-suggested params / BL-514 dynamic escalation | Phase 12 |
| Cross-session reasoning persistence (BL-333) | Phase 12 |

### Phase 11 acceptance (dogfood)

1. `SupervisedIO` fires on at least one real delegation; decision logged in trace; no regressions.
2. Clarity pass returns `clarification_needed` for vague task; returns `CLEAR` and proceeds normally for clear spec.
3. Executor-pull hint: `needs_input` stall frequency measurably lower in dogfood.
4. Tier-1 reviewer note appears in spec report; non-fatal on reviewer error.
5. `model_policy` overrides executor thinking budget from Cursor for one delegation.

---

## Next action (planning)

- [x] Phase 1 tasks tracked in [PHASE1_MVP.md](./PHASE1_MVP.md); gaps in [PHASE1_ISSUES.md](./PHASE1_ISSUES.md); backlog in [BACKLOG.md](./BACKLOG.md).
- [x] Barebones MCP + Aider, home storage, Cursor host adapter, session persistence (incl. `config.yaml`, MCP singleton).
- [x] Full Cursor transcript context — opt-in `host_transcript: dump` ([PHASE1_MVP.md](./PHASE1_MVP.md) P1-140).
- [x] Persistent server log ([PHASE1_ISSUES.md](./PHASE1_ISSUES.md) P1-ISS-004 / P1-125).
- [x] Spec-based delegate + review loop ([PHASE1_MVP.md](./PHASE1_MVP.md) P1-150/151; BL-150 done).
- [x] Phase 1 exit review P1-199 — closed 2026-06-06; [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) frozen.
- [x] Phase 2 complete — context compiler, audit loop, P2-499 exit ([PHASE2_MVP.md](./PHASE2_MVP.md)).
- [x] Phase 3 Wave 1 — workspace tracker + inspect ([PHASE3_MVP.md](./PHASE3_MVP.md); P3-401 signed off 2026-06-09).
- [x] Phase 3 — **P3-311** read-deps auto-merge (D-P3-7); 412 pytest.
- [x] Phase 3 exit — **P3-499** (2026-06-09); [PHASE3_MVP.md](./PHASE3_MVP.md) closed.
- [x] Phase 4 complete — context builder + manager + pipeline (P4-499 exit 2026-06-09); [PHASE4_MVP.md](./PHASE4_MVP.md).
- [x] Phase 4.5 — stack literacy gate; tutorials, inspect, gap analysis; [PHASE4.5_MVP.md](./PHASE4.5_MVP.md).
- [x] Phase 5 — RAG + retrieval (P5-001…P5-004, P5-006); recommended exit met 2026-06-13; [PHASE5_MVP.md](./PHASE5_MVP.md).
- [x] Phase 6 — observability substrate + reasoning buffer (P6-001…P6-008); recommended exit + post-dogfood fixes met 2026-06-13; [PHASE6_MVP.md](./PHASE6_MVP.md).
- [x] **Phase 8 complete** — backend interception (P8-001..P8-006); `ObservableModel` + `InterceptionProfile` + bootstrap + byte-range provenance + streaming dedup; see `PHASE8_MVP.md` (closed 2026-06-14).
- [x] **Phase 9 complete** — write-always storage + `LocalLlmProxy` + context blobs + replay CLI + GC + v2 boundary viewer (P9-001..P9-013); closed 2026-06-17; see [PHASE9_MVP.md](./PHASE9_MVP.md).
- [x] **Phase 10 complete** — P10-001..P10-004 shipped (executor options, visibility, structured `needs_input`, and deferred Phase 9 polish). See [PHASE10_MVP.md](./PHASE10_MVP.md).
- [x] **P11-001 shipped** — clarity_check pipeline phase (BL-521); opt-in `MCP_CODER_CLARITY_PASS`; 2026-06-19.
- [ ] **Phase 11 active** — P11-002..P11-007: supervised execution (SupervisedIO + DelegationSupervisor), executor-pull v0, mid-run human gate (experimental), tier-1 reviewer, smart architect trigger, host model policy. See [PHASE11_MVP.md](./PHASE11_MVP.md).
