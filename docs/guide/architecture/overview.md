# Architecture overview

**Status:** Living — update as shipped decisions change.  
**Scope:** Phases 1–5 as implemented. Phase 5+ / observability items in backlog (see § Known gaps).  
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
│  MCP server                                                        │
│  server/mcp_server.py  (~1750 lines)                              │
│  • Registers tools: delegate_to_agent, inspect_context,           │
│    list_delegations, get_delegation_diff, get_checkpoint_detail,  │
│    get_file_history, rag_search, workspace_search                  │
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
   ┌──────────────┐
   │ Execution    │
   │ Backend      │
   │ core/engine/ │
   │              │
   │ aider_engine │  ← only backend today
   │ (Aider API)  │
   └──────────────┘
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
│    sessions/<id>/delegations.jsonl                                │
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

`project_key` = `sha256(resolved_workspace_path)`. BL-318 tracks what happens on repo move.

### D-4: Spec is the contract (D-P4-10)
The spec's `files_edit` list is the only way a path enters `edit-full` tier and Aider `fnames`. The file picker **discovers** read candidates but **never grants edit rights**. That invariant is enforced at compile time in `file_picker.py` + `assemble.py` and checked post-hoc by `post_gateway`.

### D-5: One model per role (D-P4-8)
Every LLM call is tagged with a `role` (`executor`, `context_builder`, `review`, `critic`). Each resolves its model independently via `resolve_role_model_name()` — precedence: env var → `config.yaml` → built-in default. All calls are audited in `model_roles` JSONL. Token counts are currently null for several paths (BL-335).

### D-6: Snapshot-based file diffing (not git)
Pre/post SHA-256 manifests of the workspace bracket the executor. `files_changed` comes from the manifest diff, not from git or from what Aider reports. This works on untracked files, gitignored paths, and repos with no git history. Git is a soft dependency only.

### D-7: JSONL as the audit record
One record per delegation, appended (never mutated) to `delegations.jsonl` under the session dir. It is the canonical truth. Everything else — history DB, RAG, spec reports — is derived from or supplementary to the JSONL record.

### D-8: Optional stages fail open; validation blocks closed
Builder, architect, spec-validation LLM calls are all non-fatal on failure **except** spec-validation when it finds real ambiguity. That is the only stage that can stop the pipeline before spending executor tokens. If a helper LLM fails, delegation continues with the mechanical brief.

---

## Delegation lifecycle (concrete path through code)

For `mode=implement` with a valid spec, `mcp_server.py` runs these in order:

```
delegate_to_agent()
  │
  ├── host context: core/host/cursor.py → transcript path, session hint
  ├── session: core/session/ → new or reuse Coder instance
  │
  ├── spec_read         core/specs/read.py, sections.py → SpecRead
  ├── spec_validation*  core/engine/spec_validation_llm.py  [can BLOCK]
  │
  ├── file_picker       core/context/file_picker.py → CandidateFilesResult
  ├── rag_retrieval*    core/rag/builder_retrieval.py → context_refs + brief section
  ├── context_assemble  core/context/assemble.py → ContextPackage
  ├── architect_pass*   core/engine/architect_pass_llm.py
  ├── builder_llm*      core/engine/context_builder_llm.py
  │
  ├── EXECUTOR          core/engine/aider_engine.py
  │     └── translate_context_package() → fnames + prompt
  │     └── Coder.run(prompt)
  │     └── workspace snapshot post-run
  │
  ├── post_gateway      core/workspace/gateway.py
  │     └── diff snapshots → files_changed, files_unexpected
  │     └── scope_violations if edit_scope: strict
  │
  ├── spec_report       core/specs/write.py → append to reports/
  ├── auto_verify*      core/verify/ → run command, update outcome
  │
  └── audit
        ├── core/logging/delegation_log.py → append delegations.jsonl
        ├── core/workspace/history_db.py → checkpoint row
        └── core/rag/ → index delegation + incremental workspace files (FTS5)
```

`*` = opt-in helper stages default off; `rag_retrieval` runs when `context_builder` on and RAG flags on (defaults **on** since Phase 5).

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
                                →  architect_pass*   →  prepend ## Architect plan
                                →  translate_context_package()
                                     fnames = [edit-full paths]
                                     prompt = brief + fenced read blocks + map block
```

The **mechanical brief** (paths, tiers, task, context_summary) is never rewritten by any LLM. LLMs only **prepend** above a separator line. See T-04 for hands-on walkthrough.

---

## Helper LLM calls (pipeline phases)

Four distinct LLM calls aside from the executor:

| Role | Phase | Model | Input | Output | Fatal? |
|------|-------|-------|-------|--------|--------|
| `spec_validation` | `spec_validation` | `context_builder` tier | Spec + chat transcript | `clarification_needed[]` | **Yes** if ambiguous |
| `context_builder` | `builder_llm` | `context_builder` tier | Mechanical brief + history + picker audit | `## Builder brief` | No |
| `architect` | `architect_pass` | `context_builder` tier | Spec + brief + picker | `## Architect plan` | No |
| `review` | (mode=review) | `review` role | Spec + target files | Q&A text | No |

All use LiteLLM directly (comes in via Aider's transitive dep). All audited in `model_roles`. Builder input prompt and raw completions are **not currently logged** in JSONL (BL-353 gap).

---

## Sessions and executor caching

A **session** groups related delegations under one `mcp_session_id` and caches an Aider `Coder` instance (`core/session/executor_cache.py`). Reusing a `Coder` avoids startup overhead; the compiler still rebuilds the `ContextPackage` fresh each time.

Session policy:
- `always_new` — new session per delegation (clean, no executor state leakage)
- `align_host` — try to match an active Cursor host session (more reuse, slight coupling)

Executor reuse is audited: `executor_reused: true/false` and `executor_recreated: true/false` in `delegations.jsonl`. When the Coder is reused, Aider may retain internal multi-turn context from the previous `coder.run()` — this is a performance side effect, not an intentional memory feature.

---

## Storage layout (key paths)

```
~/.mcp-coder/
  projects/
    <sha256(workspace_path)>/
      project.json
      workspace_history.db          SQLite: manifests, checkpoints, file-level diffs
      delegation_rag.db             SQLite FTS5: delegation index
      workspace_rag.db              SQLite FTS5: per-file summary index (Phase 5)
      sessions/
        <mcp_session_id>/
          delegations.jsonl         canonical audit trail
          server.jsonl              server-side event log

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

Full layout: [storage-layout.md](./storage-layout.md) (pending) and [`notes/storage-and-linking.md`](../../notes/storage-and-linking.md).

---

## Known gaps and open seams

| Gap | Where it hurts | Backlog |
|-----|----------------|---------|
| **Token counts null** for builder/architect/validation | `model_roles` audit incomplete; cost estimates unreliable | BL-335 |
| **Helper LLM inputs not logged** | Can't replay or audit what builder saw | BL-353 |
| **Validation block → empty `context_refs`** | Looks like RAG regression when spec blocks | BL-364 |
| **`delegations.jsonl` carries full bodies opt-in** | Grows with `prompt_full`; lean-refs partial (`context_refs` shipped) | BL-356 |
| **Single executor backend (Aider)** | `opencode_engine.py` stub exists; no second backend | BL-340 |
| **Session policy heuristics** | `align_host` matching is fragile (slug-based) | BL-317 |
| **Embeddings / recall metric** | FTS-only retrieval; no measured recall | P5-005 deferred |

---

## What is intentionally NOT here

- **No routing logic** — mcp-coder does not decide which tasks to attempt; the planner/human does.
- **No owned UI** — `view delegations` spawns a static HTML viewer; Cursor is the primary UI.
- **No git dependency** — storage and diffing work without git; git is informational only.
- **No multi-repo or cross-project coordination** — everything is scoped to one workspace path. Cross-project is Phase 8–9 vision (BL-002 / Corpus 4).

---

## Future direction (not architecture today)

| Area | Note |
|------|------|
| **LLM wire logging** | LiteLLM pass-through tap for all roles; per-delegation trace files (BL-353) |
| **Lean JSONL refs** | Expand `context_refs[]`; drop inline bodies once corpora mature (BL-356) |
| **Executor-pull tools** | `mcp-coder search --format plain` pre-shapes BL-354 |
| **Workflow turns** | Named modes beyond implement/review: digest, polish, refactor (BL-359) |
| **Alternate backends** | Cursor-SDK executor (BL-340) |
| **Storage lifecycle** | Retention, promote-then-prune, gc (BL-357) |

---

## Deeper dives

| Topic | Document |
|-------|---------|
| Mental model / operator guide | [how-it-works.md](../how-it-works.md) |
| Context compiler full walkthrough | [context-pipeline.md](./context-pipeline.md) (pending) + T-04 tutorial |
| Storage paths and JSONL schema | [storage-layout.md](./storage-layout.md) (pending) |
| Per-role model registry | [per-role-models.md](./per-role-models.md) (pending) |
| Where reality diverges from docs | [reality-vs-spec.md](./reality-vs-spec.md) (pending) |
| Module-by-module map | [code-structure.md](../code-structure.md) |
| Terminology | [terminology.md](../terminology.md) |
| RAG (shipped) + open items | [rag-gap-analysis.md](../../notes/rag-gap-analysis.md) |
| Workflow turns (future modes) | [workflow-turns.md](../../notes/workflow-turns.md) |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | Phase 5 — `rag_retrieval`, `workspace_rag.db`, `workspace_search`; gaps table refresh |
| 2026-06-12 | Initial version — layer map, 8 locked decisions, delegation lifecycle, context compiler, helper LLMs, sessions, storage paths, known gaps |
