# Phase 2 direction: owned context & execution abstraction

**Status:** Direction note — **not** canonical vision. See [IDEA.md](../IDEA.md) for product WHY.  
**PM board:** [PHASE2_MVP.md](../PHASE2_MVP.md)  
**Locked at:** Phase 1 exit (P1-199, 2026-06-06); expanded 2026-06-06 (planning session).  
**Backlog:** [BL-001](../BACKLOG.md#deferred-from-phase-1-by-design--later-phases), [BL-154](../BACKLOG.md#postphase-1-focus-priority-after-p1-199), [BL-311](../BACKLOG.md#bl-311-read-deps-from-spec-files-section), [BL-316](../BACKLOG.md#bl-316-context-builder-file-materialization-tiers).

---

## Why Phase 2 needs this (not just “smarter prompts”)

Phase 1 proved delegation works, but **behavior was implicit**:

- `target_files` meant “Aider `fnames`” = **full file in chat** — an API detail, not product intent.
- Untracked / gitignored paths were invisible unless the planner guessed right.
- Aider could add or create files mid-run (`yes=True`) with **no contract** — only post-hoc `files_unexpected` (P1-152).
- Debugging meant reading Aider internals, not a **mcp-coder audit trail**.

Phase 2 goal: a **lean, debuggable, improvable** delegation pipeline we **control**:

| Need | Phase 2 answer |
|------|----------------|
| **Predictable** | Behavioral contract (what we intend) separate from backend mechanics |
| **Auditable** | Four-layer trace: contract → package → adapter input → result |
| **Improvable** | Compiler + policies testable without running Aider |
| **Portable** | Same `ContextPackage` for Aider today; other backends later |
| **Lean** | Per-path tiers — not “dump everything full text” |

> **Principle:** mcp-coder describes **intent**; adapters **fulfill** it. The audit trail records the gap between the two.

---

## Problem (Phase 1 reality)

Today, `delegate_to_agent(target_files=[…])` passes paths straight to **Aider `fnames`**:

- Every listed path → **full file text** in executor chat.
- **Backend-coupled** — Cursor/planner input is executor input.
- **Blind inclusion** risks token blow-up and wrong cross-step APIs (E2E expense-splitter).
- **Repo map** (Aider) covers **git-tracked** files only — specs, untracked WIP, `.mcp-coder/` are outside the map.

Phase 1 bridge: read-deps conventions (cursor rules v7), `files_changed` + `files_unexpected` (P1-152). **Not the end state.**

---

## Three layers (backend-agnostic middle)

```text
┌─────────────────────────────────────────────────────────────┐
│ L1 — CONTRACT (spec + MCP API + policies)                   │
│   What the planner intended; mcp-coder enforces bounds      │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│ L2 — CONTEXT COMPILER (core/ — no Aider imports)              │
│   assemble_context() → ContextPackage + budget metadata       │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│ L3 — EXECUTION ADAPTER (core/engine/<backend>/)               │
│   translate(ContextPackage) → backend run → ExecutionResult   │
└─────────────────────────────────────────────────────────────┘
```

**Rules**

- L1/L2 never import Aider, OpenCode, or host paths (except host adapter for optional transcript slices).
- L3 is the **only** place that knows `fnames`, repo map, `yes=True`, subprocess flags, etc.
- We do **not** care how Aider works internally — we **recreate the behaviors we want** via adapter + policies.

**Phase 2 hinge:** change `ExecutionEngine.run(prompt, target_files)` → `run(context: ContextPackage)` ([P2-210](../PHASE2_MVP.md#wave-2--context-compiler-core)). Until then, Wave 1 validates **contract** against spec, not Aider semantics.

---

## L1 — Behavioral contract (not API contract)

### API contract (Phase 1 — avoid extending)

*“Pass these paths to Aider `fnames`.”* — leaks backend.

### Behavioral contract (Phase 2)

*“Edit these paths; make these paths available as context; respect scope policy; report everything that changed.”* — mcp-coder owns it.

| Field / policy | Meaning | Source |
|----------------|---------|--------|
| `files_edit` | Paths worker may modify | Spec `### Edit` / YAML ([P2-115](../PHASE2_MVP.md#wave-1--honesty--safety-foundations)) |
| `files_read` | Paths worker must see (tier chosen by compiler) | Spec `### Read` / YAML |
| `edit_scope` | `discover` — model may touch undeclared paths; `strict` — post-check violation | Spec / D-SPEC-8 |
| `allow_create` | May create new paths not in spec? | Spec / policy default |
| `allow_shell` | Executor may run shell commands | Policy (default **off**) |
| `untracked_policy` | How non-git-tracked paths are handled | Policy (see below) |

`target_files` on MCP tool = **planner hint** (usually ≈ `files_edit ∪ files_read` today). When `spec_path` is set, **spec Files wins** ([D-P2-6](#phase-2-architecture-decisions-d-p2)).

---

## L2 — ContextPackage & materialization tiers

`assemble_context(workspace, spec, mcp_request, policies)` →:

```text
ContextPackage
  brief: str                         # spec sections + task + constraints
  edit_paths: list[str]              # edit-full tier
  read_full: list[str]
  read_excerpts: list[Excerpt]       # path, text, reason, byte_range?
  pointers: list[Pointer]            # path + one-liner
  policies: DelegationPolicies
  metadata:
    bytes_by_tier: dict
    truncations: list[{reason, bytes_dropped}]
    token_estimate_preflight: int
    compiler_version: str
```

### Tiers (per path)

| Tier | Executor gets | When |
|------|---------------|------|
| `edit-full` | Full file; may patch | Files in `files_edit` |
| `read-full` | Full file; read-only | Small deps, must-see API |
| `read-excerpt` | Snippet in prompt or `.mcp-coder/context/excerpts/` | Large read-deps |
| `pointer` | Path + summary line in brief | Structure enough |
| `map-only` | Rely on backend repo map (if capable) | Tracked file, symbols enough |
| `hide` | Nothing | Out of scope |

Builder applies tiers **regardless of source**: spec Files, MCP args, JSONL history, optional host transcript slices.

### Example — cross-step CLI (expense-splitter step 2)

**Spec:**

```markdown
### Edit
- expense_splitter/cli.py

### Read
- expense_splitter/splitter.py   # public API from step 1
```

**Phase 1 (today):** planner must put **both** in `target_files` → both full in Aider chat.

**Phase 2 (target):**

```text
assemble_context() →
  edit_paths:  [cli.py]
  read_full:   []                    # if splitter.py small
  read_excerpt:[splitter.py: load_expenses, split_group API only]
  brief:       "Step 2: CLI; use load_expenses(path) -> ..."
```

Adapter maps to Aider: `fnames=[cli.py]` + excerpt block in prompt (or `read_only_fnames` when supported).

### Example — untracked new module (greenfield)

| Path | Git | Aider repo map | Phase 2 compiler |
|------|-----|----------------|------------------|
| `new_pkg/foo.py` | untracked | **No** | `edit-full` in package; never assume map |
| `.mcp-coder/specs/tasks/x.md` | gitignored | **No** | In `brief` or excerpt; not via map |

**`untracked_policy`** (proposed):

| Value | Behavior |
|-------|----------|
| `materialize` (default) | Compiler puts untracked read-deps into package before run |
| `require_declared` | Warn if spec lists untracked path not materialized |
| `block` | Fail delegation if undeclared untracked edit attempted (strict repos) |

---

## L3 — Backend adapter & capabilities

Each adapter implements:

```text
capabilities() → BackendCapabilities
translate(package: ContextPackage) → BackendRunRequest
run(request, *, workspace_path, mcp_session_id) → ExecutionResult
```

### BackendCapabilities (declared, logged)

| Capability | Aider (today) | Why mcp-coder cares |
|--------------|---------------|---------------------|
| `repo_map_source` | `git-tracked-only` | Untracked invisible — compiler must materialize |
| `chat_file_mode` | `full-text-in-chat` | Drives tier choice |
| `supports_read_only_in_chat` | partial | Compiler may degrade `read-full` → excerpt |
| `dynamic_add_files` | yes (headless `yes=True`) | `edit_scope: discover` + audit |
| `dynamic_create_files` | yes | `allow_create` + `files_unexpected` |
| `shell_default` | off | BL-309 safety |
| `session_continuity` | in-process cache | BL-155 |

**Capability-aware compilation:** if `supports_read_only_in_chat` is false, compiler upgrades tier and logs `capability_degraded: read_only_not_supported` — **predictable**, not accidental.

OpenCode (stub) would declare different capabilities; same `ContextPackage` in, different `BackendRunRequest` out.

### Aider behaviors we recreate (not inherit blindly)

| Aider behavior | mcp-coder stance |
|----------------|------------------|
| Repo map = git tree only | Compiler materializes untracked/gitignored |
| `fnames` = full file | Adapter maps `edit_paths` + `read_full` only |
| Model adds file Y mid-run | **Audit** (`files_unexpected`); `edit_scope: strict` → `scope_violation` post-check |
| Model creates `new.py` | Same; optional Scope expansion in spec report ([P2-305](../PHASE2_MVP.md#wave-3--executor--host-contracts)) |
| Empty initial `fnames` | Valid if `allow_create` + greenfield spec; contract still applies post-run |
| Shell / lint / URL scrape | Policy + `aider_runtime.py` — not MCP defaults |

We **do not block mid-run edits in v0** — we **audit** and surface to planner. Mid-run kill is backend-specific and fragile.

### `edit_scope` example

| `edit_scope` | Run | After run |
|--------------|-----|-----------|
| `discover` | Adapter runs; Aider may touch Y/Z | Log `files_unexpected`; report Scope expansion |
| `strict` | Same run | Any touch ∉ `files_edit` → `outcome: scope_violation` |

---

## Audit loop (four layers)

One delegation JSONL record should answer: *what did we intend, assemble, send, and get back?*

```text
1. contract     — files_edit, files_read, policies (from spec + MCP)
2. package      — ContextPackage summary (tiers, bytes, truncations)
3. adapter_in   — what backend received (fnames, prompt hash) — backend-specific snapshot
4. result       — ExecutionResult (success, files_changed, files_unexpected, scope_violations)
```

Phase 1 closes layer 4 partially (`files_changed`, `files_unexpected`). Phase 2 closes **all four** ([P2-212](../PHASE2_MVP.md#wave-2--context-compiler-core)).

### ExecutionResult (target shape)

```text
ExecutionResult
  success: bool
  outcome: str                    # success | failed | needs_input | scope_violation | partial
  output: str
  files_changed: list[str]        # all touches (P1-152)
  files_unexpected: list[str]
  scope_violations: list[str]     # strict mode: outside files_edit
  capability_warnings: list[str]  # e.g. read_only degraded
  tokens: dict
  backend_id: str
  preflight_token_estimate: int | null
  ...
```

Delegation log `context.*` fields carry package + adapter snapshot ([PHASES.md](../PHASES.md) observability section).

---

## Inspect / dry-run (no backend)

Because `assemble_context()` runs **before** the executor:

```bash
# future CLI / MCP tool
mcp-coder inspect-context --spec path/to/task.md --workspace .
```

Returns `ContextPackage` JSON: tiers per path, byte estimates, truncations — **without calling Aider**. Primary debugging tool for planners and for unit tests ([P2-215](../PHASE2_MVP.md#wave-2--context-compiler-core)).

Core compiler tests assert on `ContextPackage` + mock `ExecutionEngine` — no Aider required ([D-P2-7](#phase-2-architecture-decisions-d-p2)).

---

## Phase 1 bridge (until compiler ships)

| Mechanism | What it does |
|-----------|----------------|
| Read-deps convention | Planner lists edit + read in spec and `target_files` |
| `files_unexpected` | Git snapshot delta for undeclared touches |
| Cursor rules v7 | Read-deps checklist |
| `mode=review` | Spec Q&A — does not load step N code |

**Wave 1 caution:** P2-110 validates **spec contract** (Files ⊄ hint), not “what Aider needs in fnames.”

---

## Suggested layout (workspace)

```text
.mcp-coder/
  context/
    index.md              # topic/epic → materialized paths
    excerpts/             # large-file slices (compiler-written)
  specs/                  # unchanged P1-151 layout
```

Not the same as [OTEHR_RELATED_IDEAS/CONTEXT_AS_GIT.md](../OTEHR_RELATED_IDEAS/CONTEXT_AS_GIT.md) (separate product idea).

---

## Phase 2 architecture decisions (D-P2)

| ID | Decision | Implements |
|----|----------|------------|
| D-P2-1 | `ContextPackage` is the **only** input to execution adapters | P2-210 |
| D-P2-2 | Policies (`edit_scope`, `allow_create`, `untracked_policy`) are **mcp-coder owned**, not Aider env | P2-115, P2-200 |
| D-P2-3 | Dynamic file add mid-run: **audit, don't block** in v0 (`discover` default) | P2-115, P2-305 |
| D-P2-4 | Untracked/gitignored: **compiler materializes** — never assume repo map | P2-200, P2-205 |
| D-P2-5 | `BackendCapabilities` per adapter; snapshot in delegation JSONL | P2-212 |
| D-P2-6 | `target_files` = planner hint; when `spec_path` set, **spec Files wins** | P2-110, P2-115, P2-200 |
| D-P2-7 | Compiler + contract layer **unit-testable** without live backend | P2-200, P2-215 |

Inherited from P1: [D-SPEC-4, D-SPEC-7, D-SPEC-8](../PHASE1_MVP.md#p1-199--end-of-phase-1-review-done).

---

## Non-goals (still deferred)

- RAG / cross-session memory → Phase 3 ([BL-002](../BACKLOG.md#deferred-from-phase-1-by-design--later-phases))
- Gatekeeper MCP → [BL-151](../BACKLOG.md#after-phase-1--adapt-our-dev-workflow-to-the-product)
- OpenCode / multi-host → [BL-004](../BACKLOG.md#very-low-priority--other-execution-engines)
- Default full transcript dump → opt-in ([D-SPEC-7](../PHASE1_MVP.md#p1-199--end-of-phase-1-review-done))
- Mid-run interception (“stop, you touched foo.py”) → post-check first; revisit if needed

---

## Task map (PM board)

| Wave | Tasks | This doc sections |
|------|-------|-------------------|
| 1 | P2-110, P2-115, P2-120, P2-125 | L1 contract, audit prep |
| 2 | P2-200, P2-205, P2-210, P2-212, P2-215, P2-220 | L2 compiler, L3 hinge, audit loop, inspect |
| 3 | P2-300, P2-305, P2-310, P2-315 | Result richness, scope reports, cache on package |
| 4 | P2-400, P2-405, P2-410 | Intelligence on top of compiler |

Full board: [PHASE2_MVP.md](../PHASE2_MVP.md).

---

## Changelog

| Date | Note |
|------|------|
| 2026-06-06 | Expanded: three layers, behavioral contract, audit loop, capabilities, examples, D-P2-1–7 |
| 2026-06-06 | Created at P1-199 exit; initial thesis |
