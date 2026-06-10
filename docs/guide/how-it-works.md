# How mcp-coder works

**Purpose:** the mental model. Everything you need to keep in your head to operate, debug, or extend the system. Re-read when coming back after a break. Deeper detail lives in [architecture/](./architecture/) and the [tutorials](./tutorials/); module-by-module map in [code-structure.md](./code-structure.md).

**Covers:** Phases 1–4 as shipped. Last updated: 2026-06-10.

---

## 1. What it is, in one paragraph

mcp-coder is an MCP server that lets a **planner agent** (a Cursor chat session) delegate implementation work to a **cheaper executor** (Aider driving an LLM) — while mcp-coder itself owns everything in between: reading the task spec, compiling the context the executor sees, enforcing the file-edit contract, snapshotting the workspace, verifying the result, and writing an audit trail. The planner stays high-level and chatty; the executor gets a focused, self-contained prompt; mcp-coder is the disciplined middle layer that makes that split safe and observable.

## 2. The three actors

```
┌─────────────┐   MCP tools    ┌──────────────┐   compiled prompt   ┌──────────────┐
│  Planner     │ ─────────────▶ │  mcp-coder   │ ──────────────────▶ │  Executor    │
│  (Cursor     │                │  (this repo) │                     │  (Aider +    │
│   session)   │ ◀───────────── │              │ ◀────────────────── │   LLM)       │
└─────────────┘  result + audit └──────────────┘   file edits        └──────────────┘
```

- **Planner / host** — *today* this is the Cursor agent you talk to. It writes specs, calls `delegate_to_agent`, and judges results. Guided by host rules that mcp-coder syncs into the workspace (`.cursor/rules/use-mcp-coder.mdc`). It never sees executor internals; it sees the response payload and the JSONL audit.
- **mcp-coder** — stateless per call, stateful on disk. All logic in `core/`, all MCP wiring in `server/mcp_server.py`. Backend-neutral everywhere except `core/engine/aider_engine.py`.
- **Executor** — *today* Aider's Python API running its own internal edit loop (search/replace blocks, reflection retries) against the configured model. It only knows what the compiled context package tells it.

Plus **helper LLMs** in supporting roles (see §6): spec validation, context-builder brief, architect plan, review. These are separate calls, distinct from the executor.

> **Not locked in (important).** Cursor (host) and Aider+provider (backend) are the *current* starting point, not the architecture. Both sit behind adapters — the host behind `core/host/` (`HostContextProvider`), the executor behind `core/engine/` (`ExecutionEngine` + `factory.py`). Everything in `core/` outside `core/engine/aider_engine.py` and `core/config/aider_runtime.py` is deliberately backend-neutral, and a non-Cursor host or a non-Aider backend (e.g. a Cursor-SDK executor, see BL-340) is expected to land later. When reading the code or this doc, treat "Cursor" and "Aider" as *the first implementation of an adapter*, not as the system.

## 3. The unit of work: a delegation

Everything revolves around one call: `delegate_to_agent(task, target_files, context_summary, spec_path?, mode?)`.

Two modes:
- **`implement`** (default) — executor edits files on disk. The full pipeline below runs.
- **`review`** — no edits; an LLM answers questions about the spec/code. Most pipeline stages are skipped.

A delegation gets a `delegation_id`, runs the pipeline, and produces:
- a **response payload** for the planner (`success`, `outcome`, `files_changed`, `judgment_checklist`, `delegation_diff`, …)
- one **JSONL record** appended to the session's `delegations.jsonl` (the full audit)
- a row in **`workspace_history.db`** and the **RAG index**
- an appended **report** under `.mcp-coder/specs/reports/` if a spec was used

## 4. The delegation pipeline (the core mental model)

For `mode=implement` with a valid spec, the phases run in this order. Each phase is timed and recorded in `delegation_pipeline` (statuses: `ok | skipped | error | blocked`):

```
spec_read          parse spec front-matter, sections, Files contract
spec_validation*   helper LLM: does spec match the conversation? → can BLOCK
file_picker        rules-based: spec paths + rg symbol scan + repo map → candidates
context_assemble   build ContextPackage: tiers, budget, mechanical brief
architect_pass*    helper LLM: prepend "## Architect plan" to the brief
builder_llm*       helper LLM: prepend narrative "## Builder brief" (mechanical brief stays verbatim)
executor           Aider runs; pre/post workspace snapshots taken around it
post_gateway       diff snapshots → files_changed; check against spec Files contract
spec_report        append audit section to specs/reports/<spec-name>.md
auto_verify*       run verify command (e.g. pytest); failure downgrades success → partial
```

`*` = opt-in flag, off by default. If `spec_validation` finds real ambiguity, the pipeline **blocks**: no executor runs, the planner gets `outcome: needs_input` + `clarification_needed: [...]`, and later phases never appear.

**Key property:** failures in optional LLM stages (builder, architect) are non-fatal — the delegation proceeds with the mechanical context. Only validation can block; only the executor/contract can fail.

## 5. Context compiling: what the executor actually sees

The executor's prompt is a **ContextPackage** (`core/context/package.py`), not raw chat history. Mental model:

1. **Spec is the contract.** A markdown file under `.mcp-coder/specs/tasks/` with front-matter + `## Goal / ## Files / ## Constraints / ## Acceptance`. The `Files` section defines what may be edited (enforced post-hoc by the gateway).
2. **Tiers control cost.** Files enter the package at different fidelity: full payload (edit targets) → read-only payload → excerpt → map-only (def/class outline from the repo map). A token budget trims from the bottom.
3. **The picker discovers, the assembler materializes.** The file picker ranks candidates (spec paths, symbol hits via ripgrep, repo map); discovered files become *read* tiers only — discovery never grants edit rights (D-P4-10).
4. **The brief is layered.** Bottom: the *mechanical brief* (authoritative paths/tiers, never rewritten by any LLM). On top, optionally: builder LLM narrative, then architect plan. LLMs annotate; they don't replace.
5. **`context_summary` is the planner's voice.** Decisions from chat that the executor can't otherwise see. With `host_transcript: dump` enabled, a tail of the actual host transcript is also available to the validation/builder LLMs.

You can see exactly what would be sent — without spending executor tokens — via `mcp-coder inspect-context` or the `inspect_context` MCP tool.

## 6. Per-role models

One delegation may involve up to five model calls, each **independently configurable** (precedence: default → env → `.mcp-coder/config.yaml`). The point of the role split is that you pick the right model *per task* — not that any role is inherently cheap or expensive:

| Role | Used by | Current default |
|------|--------|-----------------|
| `executor` | Aider edit loop | `AIDER_MODEL` / `resolve_model_name()` |
| `context_builder` | builder brief, spec validation, architect pass | Gemini Flash today |
| `review` | `mode=review` | falls back to executor model |
| `critic` | reserved (stub) | falls back to executor model |

Every call is audited in the JSONL `model_roles` block with tokens/duration/cost-estimate. (Known gap: token counts currently `None` for several paths — BL-335.)

**On "cheap" vs "expensive" — don't over-fit to the current defaults.** The architecture lets you route each role to a different model; whether that's cheaper or pricier than the executor is a tuning decision, not a property of the role. Examples:
- A `spec_validation` pass that just checks a spec against the conversation can run on a small, cheap model.
- An `architect_pass` that is really a *plan-improvement / brainstorm* step — possibly iterating with the host on an epic or a hard task — may justify a **stronger, more expensive** model than the executor. This is **TBD** and will be tuned with real telemetry.

So the durable idea is **"right model for each role,"** not "expensive plans, cheap edits." The split *enables* cost optimization (and lets a strong model think while a fast model types) but does not mandate any particular price direction. Today's defaults are a starting point, expected to change as BL-335 telemetry lands.

## 7. Memory: what persists where

Two storage scopes — repo vs home — and the distinction matters:

```
<workspace>/.mcp-coder/          IN the repo (user-visible)
  config.yaml                    user-owned config (flags, models) — never written by mcp-coder
  session.json                   pointer to current session (system-managed)
  specs/tasks/*.md               step task specs (the contracts)
  specs/reports/*.md             per-spec audit reports (appended by mcp-coder)

~/.mcp-coder/projects/<sha256-of-workspace-path>/    OUTSIDE the repo
  project.json                   project registry entry
  workspace_history.db           SQLite: per-file hashes, delegation checkpoints, diffs
  delegation_rag.db              FTS5 index over past delegations (search shipped; pipeline use = Phase 5)
  sessions/<mcp_session_id>/
    delegations.jsonl            one record per delegation — the canonical audit trail
```

Cross-session memory works through this: `prior_failed_attempts` (past failures on the same spec surface in the next delegation), builder history (past delegations fed to the builder LLM), `list_delegations` / `get_file_history` / `rag_search` MCP tools for the planner.

**Sessions:** delegations group into MCP sessions (policy `always_new` or `align_host`). An Aider `Coder` instance is cached per session, so consecutive delegations in one session reuse executor state.

## 8. Trust and verification model

mcp-coder doesn't trust the executor; it checks:

- **Snapshots, not git.** SHA-256 manifest of the workspace before and after the executor → `files_changed` (created/modified/deleted) independent of what Aider claims.
- **Scope gateway.** `files_changed` is compared to the spec's Files contract; out-of-scope edits flag the outcome and surface in `files_unexpected`.
- **Outcome labels.** `success | partial | needs_input | error` — e.g. edit-format failures → `needs_input`; verify failure after applied edits → `partial`.
- **Judgment checklist.** The response hands the planner a structured checklist (paths match? tests run?) so the *planner* does final judgment — mcp-coder informs, the planner decides.
- **Auto-verify (opt-in).** Runs e.g. `pytest -q` after a successful executor pass; only runs when edits applied and executor succeeded.

## 9. Configuration in one view

Precedence is layered, later wins: **built-in default → env var → `.mcp-coder/config.yaml`** (workspace yaml is the strongest, so a repo can pin behavior regardless of your shell env). The notable flags:

| Flag | Default | Effect |
|------|---------|--------|
| `context_builder` | **on** | file picker + repo map |
| `context_builder_llm` | **on** | builder LLM narrative brief |
| `spec_validation` | off | pre-delegate coherence check (can block) |
| `architect_pass` | off | architect plan in brief |
| `auto_verify` | off | post-delegate verify command |
| `host_transcript` | off | dump Cursor transcript tail for helper LLMs |

API keys and model ids live in `.env` (OpenRouter is the common provider for everything today).

## 10. Invariants worth memorizing

1. **The spec is the contract.** No valid spec → degraded Phase-1-style delegation; edits are judged against the spec's Files section.
2. **Host and backend are adapters, not the architecture.** Cursor and Aider are the *current* implementations; both are swappable. Aider-specific anything lives only in `core/engine/aider_engine.py` + `core/config/aider_runtime.py`; host-specific anything in `core/host/`. The rest of `core/` is neutral by design.
3. **LLM helpers can only annotate, never mutate the mechanical truth.** Brief layers stack; tiers/paths from the assembler are authoritative.
4. **Optional stages fail open; validation blocks closed.** A builder-LLM error never kills a delegation; a real spec ambiguity stops it before money is spent.
5. **Everything is audited.** If it isn't in `delegations.jsonl`, it didn't happen. Debugging always starts there (or `scripts/view_delegations.py` / `tools/delegation_viewer.html`).
6. **Discovery ≠ permission.** Picker-discovered files are read-only context; edit rights come only from the spec.
7. **mcp-coder never writes user config.** `.mcp-coder/config.yaml` is yours; `session.json` and reports are the system's.

## 11. Where to go deeper

| Want | Go to |
|------|-------|
| Definition of a term | [terminology.md](./terminology.md) |
| Which module does X | [code-structure.md](./code-structure.md) |
| Hands-on walkthroughs | [tutorials/](./tutorials/) (T-01…T-07) |
| Subsystem internals | [architecture/](./architecture/) |
| What's planned / deferred | [../PHASES.md](../PHASES.md), [../BACKLOG.md](../BACKLOG.md) |
| Known gaps from dogfooding | [../PHASE4_ISSUES.md](../PHASE4_ISSUES.md) (frozen), [gap-analysis.md](./gap-analysis.md) |
