# mcp-coder: Phases & Delivery (BD)

This document is the **delivery plan**: what to build, in what order, and how we validate each step. Vision and rationale live in [IDEA.md](./IDEA.md). Implementation happens in focused coding sessions once a phase (or sub-step) is agreed.

**Status:** Planning. Phase 1 is broken into sub-steps so we can experiment with Cursor before adding complexity.

---

## Principles (all phases)

| Principle | Meaning |
|-----------|---------|
| **MCP = thin JSON in** | The host (Cursor) does not send full chat history to MCP tools—only tool arguments. Full context must be obtained another way or summarized by the host LLM. |
| **Cursor = orchestrator (cheap)** | Use a capable-but-cheap model in Cursor for planning, summarization, and tool calls. Heavy coding runs inside `mcp-coder` + CLI agent (expensive model only where it matters). |
| **Execution = adapter** | Each CLI coder (Aider, OpenCode, …) gets an adapter using the *best* integration for that tool (Python API vs subprocess). |
| **Proxy is separate** | [context_optimizer_proxy](https://github.com/amirharati/context_optimizer_proxy) optimizes per-turn LLM calls. `mcp-coder` optimizes per-task delegation. They compose but are independent projects. |
| **Phase 1 = pass-through** | Reuse the same context Cursor already has (SpecStory file or Cursor summary). No owned context pipeline in Phase 1. |
| **Phase 2+ = owned context** | RAG, multi-LLM roles (build context vs execute), repo docs, routers—see below. |
| **Log every delegation** | From step **1.0** onward—one structured record per MCP tool call (see Observability below). |

### Phase boundary (important)

| | **Phase 1** | **Phase 2 and beyond** |
|---|-------------|------------------------|
| **Context source** | **SpecStory:** full chat transcript (same as Cursor). **Fallback:** Cursor’s *summary* only—not full chat parity | `mcp-coder` builds and manages its own context |
| **LLMs inside mcp-coder** | None required (only Aider → provider). **Optional:** one cheap call for fallback session `new`/`reuse` (1.3, no SpecStory) | Yes—context-builder, RAG, file pick, etc. |
| **Memory / RAG** | No | Yes—session store, past tasks, repo docs, embeddings optional |
| **Session logic** | Reuse Aider instance when useful; **new session** when context clearly changed | Explicit sessions, linking, “have we done this before?” |
| **Smart steps** | **None** beyond delegate + pass context + session heuristic | File picking, summarization, janitor, verification, sub-agents, etc. |

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
| **Pass-through context** (SpecStory or Cursor summary) | Compacting, ranking, or rewriting context ourselves |
| **Session reuse** when context unchanged (see below) | Cross-day memory, embeddings, multi-LLM orchestration |
| Return: success, output tail, files touched, `session_reused` | Skills injection, critic/test sub-agents, ensemble |
| **Structured delegation logs** (JSONL, per call) | Fancy UI (optional later); full prompt retention only in debug mode |

### Observability & logging (Phase 1 — from 1.0)

We need **precise, inspectable logs** from the first coding sub-session—not added later. Goal: answer “what happened, when, and why” for every `delegate_to_agent` call without guessing.

Inspired by trip-style logging in [context_optimizer_proxy](https://github.com/amirharati/context_optimizer_proxy) (one JSONL line per unit of work), but scoped to **delegations** (MCP in → Aider out → MCP response).

#### One record per delegation

Each tool invocation produces exactly one **`delegation`** record, written at end of call (or on failure). Append to:

```
<workspace>/.mcp-coder/logs/delegations.jsonl
```

(Configurable via env, e.g. `MCP_CODER_LOG_DIR`; default under project root. Gitignore `.mcp-coder/logs/` unless user opts in.)

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
| `context_mode` | `specstory` \| `fallback` |
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
| `context.specstory_path` | Path to `.md` used, or null |
| `context.specstory_mtime` | File mtime if Mode B |
| `context.specstory_hash` | SHA-256 of transcript file (detect change → new session) |
| `context.specstory_bytes` | Size of transcript injected |
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
| `timing.context_load_ms` | SpecStory read / hash / assemble |
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
- **1.0 deliverable:** logging works in fallback mode with `session_action: new` and `first_call` only; extend fields as SpecStory and session reuse land in 1.2 / 1.3.
- Later: small CLI `mcp-coder logs tail` or `inspect_delegations.py` (like proxy’s `inspect_logs.py`)—not required for 1.0.

### Context in Phase 1: pass-through only (no owned context pipeline)

We do **not** build smarter context in Phase 1—no internal LLM, RAG, or repo-wide assembly. What Aider sees depends on the mode:

| Source | Same as Cursor’s full chat? | What we pass to Aider |
|--------|------------------------------|------------------------|
| **Mode B — SpecStory** | **Yes** (for practical purposes) | Latest `.specstory/history/*.md`—the transcript SpecStory saves from Cursor/Composer |
| **Mode A — Fallback** | **No** | Only what Cursor’s LLM puts in the tool call (`context_summary`, constraints, snippets). That is a **subset** of the chat—good enough for scoped tasks, easy to lose nuance |

**Important:** Without SpecStory, `mcp-coder` does **not** see what Cursor sees. Cursor still has the full thread in its own context window; the MCP tool only receives the arguments Cursor chooses to send. Phase 2+ is where we stop depending on that and build our own context (RAG, context-builder LLM, etc.).

No summarization *inside* `mcp-coder` in Phase 1. In fallback mode, summarization happens **in Cursor** before the tool call; in SpecStory mode, we read the full saved transcript from disk.

### Context size limits & expected failures (Phase 1)

**Yes—we should expect errors once context gets large.** Phase 1 does not summarize, rank, or trim intelligently. Long Cursor chats + file contents in Aider’s context can exceed the executor model’s window (or provider limits).

| Mode | Typical overflow scenario |
|------|---------------------------|
| **SpecStory** | Transcript grows over a long Composer session; we prepend the **entire** `.md` plus `task` and file contents → prompt too large |
| **Fallback** | Less common for chat text (Cursor already compressed), but huge `code_snippets_from_chat` or many large `target_files` can still blow the budget |
| **Session reuse** | Reused Aider instance **accumulates** its own turn history **in addition** to whatever we inject each call—increases risk on follow-ups |

**How failures may appear**

- Provider / Aider errors: context length exceeded, max tokens, 400 with “prompt too long”, etc.
- Timeouts or truncated failures on very large prompts
- Degraded results (model silently drops middle context)—harder to detect; logs help

**What logging is for (Phase 1)**

Before changing behavior, use delegation logs to **inspect what we sent**:

- `context.prompt_chars`, `context.prompt_tokens_est`, `context.prompt_hash`
- `context.specstory_bytes` / `specstory_hash` (did the transcript grow?)
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

- `MCP_CODER_MAX_PROMPT_CHARS` or `MCP_CODER_MAX_SPECSTORY_BYTES`
- When exceeded: truncate transcript (e.g. keep **tail** = most recent messages) and set in log:
  - `context.truncated: true`
  - `context.truncation_reason: "max_specstory_bytes"`
  - `context.bytes_dropped: N`

This is **not** summarization—it is an explicit, logged chop so we can still run experiments. Prefer learning from uncapped failures first, then add cap if needed.

**Success criterion for experiments:** When a call fails, one JSONL line should be enough to answer: “Was it too much context? How big? SpecStory or fallback? New or reused session?”

#### Mode A — Summary fallback (build first)

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

#### Mode B — SpecStory transcript (add after Mode A works)

**How it works:** If the project has `.specstory/history/` (from the [SpecStory](https://docs.specstory.com/integrations/cursor) extension), read the **most recently modified** `.md` file in that folder. That file is the live Cursor/Composer transcript for this workspace. Prepend it to the prompt sent to Aider (or use instead of `context_summary` when fresh enough).

**Heuristic for “active chat”:** e.g. file `mtime` within last N minutes (configurable, start with 5–10).

**Pros:** Full fidelity without Cursor re-sending 50k tokens; shared repo filesystem.

**Cons:** Requires SpecStory (or similar) installed; Cursor-specific path for now; schema of `.md` is stable enough for experimentation but not a formal API.

**Fallback:** If no fresh SpecStory file → Mode A fields only.

### Session persistence in Phase 1 (only when useful)

Each MCP call is a new MCP message. Whether we **reuse** the in-process Aider `Coder` or **start a new** one depends on **context mode** and a **configurable policy**. Always log the decision (`session_action`, `session_reason`, `session_policy`).

**We do not persist sessions to disk in Phase 1**—only an in-memory singleton per workspace/process.

#### SpecStory (Mode B) — context-driven only

Reuse is justified when the **transcript we inject** is the same as last time:

| Decision | Condition |
|----------|-----------|
| **Reuse** | Same newest `.specstory/history/*.md` path **and** same `specstory_hash` as last delegation |
| **New** | Different transcript file, or hash changed (new chat / SpecStory appended), or first call |

No separate “always new” toggle for SpecStory—the file *is* the session boundary.

#### Fallback (Mode A, no SpecStory) — try both; default **always new**

Without a transcript on disk, we **cannot** know if Cursor’s chat continued or jumped topics. Two policies:

| Policy | Behavior | When to use |
|--------|----------|-------------|
| **`always_new`** (default) | Every MCP call → `Coder.create(...)` fresh. No in-process reuse. | **Start here (1.0–1.1).** Predictable; avoids stale Aider history + wrong `context_summary` combo; easier to debug. |
| **`heuristic`** | Reuse if time + files + summary hash match (see below). | **Experiment in 1.3** after logs from `always_new` baseline. |
| **`cheap_llm`** (optional) | One small LLM call decides `new` vs `reuse` before starting Aider (see below). | **1.3+ if we have time**—fallback / no SpecStory only. |

Env (proposed):

```bash
# fallback only; SpecStory ignores this
MCP_CODER_FALLBACK_SESSION=always_new   # default
# MCP_CODER_FALLBACK_SESSION=heuristic
# MCP_CODER_FALLBACK_SESSION=cheap_llm   # optional experiment
```

Log on every delegation:

| Field | Example |
|-------|---------|
| `session_policy` | `fallback:always_new` \| `fallback:heuristic` \| `fallback:cheap_llm` \| `specstory:context` |
| `session_action` | `new` \| `reuse` |
| `session_reason` | see enum below |

**Heuristic reuse (fallback only)** — when `MCP_CODER_FALLBACK_SESSION=heuristic`:

| Reuse when (all configurable) | New session when |
|------------------------------|------------------|
| Last delegation &lt; `MCP_CODER_REUSE_MAX_AGE_SEC` (default 300) | Gap exceeded → `heuristic_new_time` |
| `target_files` overlaps previous set | No overlap → `heuristic_new_files` |
| `context_summary` (+ constraints/snippets) hash unchanged | Hash changed → `heuristic_new_summary` |

**Why try `always_new` first in fallback**

- Each call’s prompt is **only** what Cursor sent this time—no hidden turns in Aider from an earlier summary.
- Follow-ups still work: Cursor sends a **new** `context_summary` that should reflect the thread (quality depends on Cursor, not Aider memory).
- Reuse in fallback can **inflate** context (Aider history + new summary) and cause overflows sooner—compare in logs.

**Why still try `heuristic` later**

- If logs show Cursor’s summaries are stable and follow-ups benefit from Aider remembering file edits, heuristic reuse may save tokens/time.
- A/B in experiments: same task sequence with `always_new` vs `heuristic`, compare `prompt_tokens_est`, success, `duration_ms`.

#### Optional: cheap LLM session classifier (Phase 1 — fallback / no SpecStory only)

**Not required for Phase 1 done.** If we have time during **1.3** (still no SpecStory path), try a **single cheap LLM call** (mini / Flash) to choose `new` vs `reuse` instead of hash/time heuristics.

**Only applies when** `context_mode=fallback` (no SpecStory). SpecStory mode keeps **context-driven** rules (transcript path + hash)—no classifier.

**Classifier prompt (example):** Given previous delegation summary + this call’s `task`, `context_summary`, `target_files`—is this a follow-up on the same work or a new topic? Return JSON: `{ "session_action": "new"|"reuse", "confidence": 0-1, "reason": "..." }`.

**Inputs (keep small):** last log line’s `mcp_request`, `context.fallback_summary_hash`, `files_requested`, `task`—not full chat history.

**Logging (required if enabled):** nested `session_classifier` on the delegation record: `model`, `tokens`, `latency_ms`, `request_preview`, `raw_response`, decision. `session_reason`: `classifier_reuse` \| `classifier_new`. Compare side-by-side with `always_new` and `heuristic` runs in experiment notes.

**Config:** `MCP_CODER_FALLBACK_SESSION=cheap_llm` (or `always_new` + `MCP_CODER_SESSION_CLASSIFIER=cheap_llm`—pick one knob when implementing).

This is **not** Phase 2 context-building—only a boundary test for “should we keep the same Aider instance?” in the no-SpecStory case.

#### Session reason enum (log + MCP return)

| Value | Meaning |
|-------|---------|
| `first_call` | No prior in-process session |
| `policy_always_new` | Fallback; forced new by `MCP_CODER_FALLBACK_SESSION=always_new` |
| `specstory_unchanged` | Reuse (Mode B) |
| `specstory_changed` | New (Mode B) |
| `heuristic_reuse` | Fallback heuristic matched |
| `heuristic_new_time` | Fallback; gap exceeded |
| `heuristic_new_files` | Fallback; no file overlap |
| `heuristic_new_summary` | Fallback; summary hash changed |
| `classifier_reuse` | Fallback; cheap LLM said reuse |
| `classifier_new` | Fallback; cheap LLM said new |

**Not in Phase 1 (required):** DB-backed sessions, `continue_session` tool, full context-builder / RAG.

Phase 2+ links explicit sessions to RAG. Phase 1 optional: cheap LLM classifier for **fallback session only**—see above.

### Adapter architecture (Phase 1)

```
core/engine/
  base.py          # ExecutionResult, ExecutionEngine protocol
  aider_engine.py  # AiderEngine — Coder.create + run, InputOutput(yes=True)
  # opencode_engine.py  — Phase 1 optional / early Phase 2 (subprocess)
```

Factory: `get_engine(backend: str) -> ExecutionEngine`. Phase 1 default: `aider`.

**Aider integration:** Prefer Python API (`aider.coders.Coder`, `aider.models.Model`, `aider.io.InputOutput(yes=True)`). Document that the scripting API is unofficial and may change.

**OpenCode (later):** `opencode run --dangerously-skip-permissions ...` via subprocess when we add a second adapter.

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

### Phase 1 sub-steps (implementation order)

#### 1.0 — Barebones sub-agent (summary only) + logging

- Python MCP server (stdio), official `mcp` SDK.
- `AiderEngine` + `delegate_to_agent` with `task`, `target_files`, `context_summary`.
- Prompt to Aider: combine `context_summary` + `task`; pass `fnames=target_files`.
- **`delegation_log`:** JSONL per call (timing, model, mcp_request, context hashes/preview, response, success).
- **Fallback sessions:** `MCP_CODER_FALLBACK_SESSION=always_new` → every call `session_action: new`, `session_reason: first_call` or `policy_always_new`.
- No SpecStory, no heuristic reuse yet, no git diff parsing beyond basics.
- **Experiment:** Register in Cursor `mcp.json`, simple task (“add a function to X”), inspect `.mcp-coder/logs/delegations.jsonl` after run.

**Done when:** Cursor calls tool → Aider edits files → one complete log line answers what/when/how long/what context.

#### 1.1 — Smarter schema (still Mode A only)

- Add `explicit_constraints`, `code_snippets_from_chat` to schema and prompt assembly.
- Tune tool **description** so Cursor’s model fills them for nuanced requests.
- **Experiment:** Task with exact hex code / API name; verify they appear in Aider prompt.

**Done when:** Structured fields reliably improve output vs single `context_summary` blob.

#### 1.2 — SpecStory mode (Mode B)

- Resolve project root (cwd or `workspace_path`).
- If `.specstory/history/` exists, pick newest `.md` by mtime; if fresh, prepend full transcript to Aider prompt (cap size if needed).
- Else Mode A.
- Document: recommend SpecStory extension for Cursor users.
- **Experiment:** Long chat in Cursor + SpecStory autosave → delegate → confirm Aider sees full thread.

**Done when:** With SpecStory on, follow-ups work without Cursor re-summarizing; without SpecStory, Mode A still works.

#### 1.3 — Session policies (SpecStory + fallback experiments)

- **SpecStory:** context-driven reuse (transcript path + hash unchanged → reuse).
- **Fallback:** implement `heuristic`; compare against 1.0–1.1 baseline (`always_new`).
- **Fallback (optional if time):** `cheap_llm` session classifier—log `session_classifier` block; compare to `always_new` / `heuristic`.
- In-process singleton + metadata: SpecStory path/hash, last files, summary hash, last run time, active `session_policy`.
- Return `session_reused`, `session_reason`, `session_policy` (must match delegation log).
- **Experiments:**
  1. Fallback + `always_new`: two quick follow-ups—does quality depend only on Cursor’s new summary?
  2. Fallback + `heuristic`: same sequence—compare logs (`prompt_tokens_est`, reuse vs new).
  3. Fallback + `cheap_llm` (optional): same sequence—did classifier beat heuristics?
  4. SpecStory: same chat → reuse; new `.md` or hash change → new.

**Done when:** Policies are configurable, always logged, and we have notes on which policy to prefer per mode (classifier optional).

### Phase 1 success criteria (overall)

- [ ] Cursor discovers and uses the tool for non-trivial coding when prompted (rules/skills can nudge).
- [ ] Token usage on Cursor side stays low (tool call + summary, not full-repo agent loop).
- [ ] Aider completes tasks on scoped files; user can review diffs in Cursor.
- [ ] Mode A and Mode B documented with known limitations.
- [ ] Each delegation has a complete JSONL record (timing, context snapshot, model, tokens if available, response).
- [ ] Notes captured from experiments (routing reliability, failure modes, follow-up behavior) for Phase 2/3—grounded in logs, not memory.

### Phase 1 open questions (resolve during experiments)

1. Does Cursor reliably pass `target_files`, or do we need to infer from open tabs / `@` mentions in `task`?
2. Optimal tool name/description for ~70–90% routing on “big” tasks without nagging every turn?
3. SpecStory freshness window (5 vs 10 min); whether to enable dumb tail-truncation cap by default after measuring failures in logs.
4. At what `prompt_tokens_est` do we consistently fail per model (document in experiment notes)?
5. Should Aider point at `context_optimizer_proxy` base URL by default in our config template?
6. Dry-run mode for MCP (`--dry-run` Aider) for safe first tests?

### Suggested project layout (when coding starts)

```
mcp_coder/
  pyproject.toml
  main.py                 # --mcp | CLI later
  server/mcp_server.py    # wraps handler with delegation_log
  core/
    logging/
      delegation_log.py   # JSONL record builder + append (from 1.0)
    engine/base.py
    engine/aider_engine.py
    context/
      summary.py            # Mode A assembly
      specstory.py          # Mode B reader
    session.py              # 1.3 reuse vs new (SpecStory change vs fallback heuristics)

# Per workspace (gitignored by default):
.mcp-coder/logs/delegations.jsonl
```

---

## Phase 2 and beyond: Owned context management

Starting Phase 2, `mcp-coder` stops relying solely on Cursor/SpecStory and **builds and manages context itself**. This is where the vision in [IDEA.md](./IDEA.md) (router, janitor, RAG, token tiers) is implemented.

### Multi-LLM roles (intent)

| Role | Typical model tier | Job |
|------|-------------------|-----|
| **Context builder** | Cheap (mini / Flash) | Summarize chats, pick files, query RAG, compress history, refresh stale facts |
| **Executor** | Expensive (Sonnet / Opus) | Run inside Aider/OpenCode for actual edits |
| **Optional helpers** | Cheap | RAG query, lint/test check, critic before returning to Cursor |

Phase 1 uses only the executor (via Aider). Phase 2+ adds the context-builder (and later helpers) **inside** `mcp-coder`.

### Phase 2: Task-level context pipeline

**Goal:** Reduce bad delegations and token waste without requiring Cursor to pass perfect `target_files` or summaries.

**Scope (indicative—not Phase 1):**

- Cheap LLM (or rules + ripgrep) to propose `target_files` from `task` + repo map.
- First version of **owned** context assembly: system prompt + selected files + compact task brief (may still *also* read SpecStory if present).
- Optional second adapter (OpenCode).
- Dual-mode CLI + MCP share same core.

**Still light on memory:** may log turns locally but not full RAG yet.

**Success:** Fewer wrong-file edits; smaller, focused prompts to Aider than raw pass-through.

*(Fallback session classifier via cheap LLM is a **Phase 1 optional** experiment—see [Optional: cheap LLM session classifier](#optional-cheap-llm-session-classifier-phase-1--fallback--no-specstory-only). Phase 2 may reuse that pattern for file picking and RAG pre-filter.)*

### Phase 3: RAG and cross-session memory

**Goal:** “Have we done this before?” across sessions and days.

**Scope:**

- SQLite (or JSON) + FTS for `session_entry` / `rag_entry` (see IDEA.md).
- After each delegation: store summary, keywords, files, diff snippet.
- Before launch: context-builder LLM searches RAG and injects relevant past work.
- Explicit tools optional: `continue_session`, `get_session_status`, `rag_search`, `rag_summarize`.
- Embeddings optional; keyword + recency enough for v1.

**Success:** User does not re-explain architecture; agent recalls prior decisions.

### Phase 4: Advanced orchestration

**Goal:** Janitor, verification, composable sub-agents.

**Scope:** Context freshness audit, cheap model grades executor output, critic / test-writer one-shots, optional multi-model ensemble (see IDEA.md).

---

## Host support matrix (intent)

| Host | Phase 1 | Context Mode A | Context Mode B (SpecStory) |
|------|---------|----------------|----------------------------|
| **Cursor** | Primary testbed | Yes | Yes (extension) |
| Claude Desktop | Later | Yes | No (unless similar export exists) |
| Windsurf / others | Later | Yes | TBD |

---

## Relationship to `context_optimizer_proxy`

```
Phase 1:
  Cursor (cheap model, summary + tool call)
    → mcp-coder (pass-through context, session heuristic only)
         → Aider → [optional] context_optimizer_proxy → LLM

Phase 2+:
  Cursor (thin orchestrator)
    → mcp-coder (context-builder LLM + RAG + …)
         → Aider (executor LLM) → [optional] proxy → LLM
```

Both projects can be developed in parallel. Phase 1 does not require the proxy or any LLM inside `mcp-coder`.

---

## Next action (planning)

- [x] Phase 1 tasks tracked in [PHASE1_MVP.md](./PHASE1_MVP.md); backlog in [BACKLOG.md](./BACKLOG.md).
- [ ] Create local `docs/tasks/P1-1.0-barebones-mcp-aider.md`; worker implements from that file (gitignored).
- [ ] After 1.0: P1-110 → P1-120 → P1-130 (optional P1-131); create task spec per milestone before each worker session.
