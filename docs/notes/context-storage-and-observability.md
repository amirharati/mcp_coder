<!--
  STEWARDSHIP — primary note for context, storage, and observability foundations.

  - Purpose: unify the foundational compiler/storage/capture model into one current reference.
  - Source lineage: phase2-owned-context.md + storage-and-linking.md + llm-interception-strategies.md.
-->

# Context, storage, and observability

**Status:** Current foundational note for how mcp-coder structures delegation context, where state lives, and how execution is observed.  
**Related anchors:** Phase 2 context compiler, Phase 3 storage/history, Phase 8/9 capture/interception layers.  
**Sibling notes:** [supervisor-agent-architecture.md](./supervisor-agent-architecture.md), [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md), [viewer-and-trace-design.md](./viewer-and-trace-design.md).

---

## Purpose

This note ties together three layers that are often discussed separately but belong to one architecture:

1. **Context formation** — what the system intends to send and why
2. **Persistence/storage** — where delegation state and history live
3. **Observability/capture** — how behavior is recorded and explained

## Context architecture

### Supervisor relationship

The context/storage layers serve the persistent Supervisor-agent design described in [supervisor-agent-architecture.md](./supervisor-agent-architecture.md).

The split is:

| Responsibility | Owner |
|---|---|
| Behavioral contract and package shape | context compiler / adapter layer |
| Durable project memory and lifecycle state | Supervisor/project storage |
| Which context a tool/subagent receives | Supervisor |
| Supervisor's own long-horizon reasoning context | future design, not fully specified |

The last distinction matters: mcp-coder has machinery for packaging context for executors/helpers, but the Supervisor's own project-scale context policy should not be hand-waved. Until it is designed, Supervisor reasoning should remain bounded, reconstructable from durable stores, and visible in trace/storage.

### The core split

The foundational design still starts with three layers:

| Layer | Job |
|---|---|
| **Contract** | What the planner/user/spec intended |
| **Context compiler** | Build a structured context package with tiers/budgets |
| **Execution adapter** | Translate that package for the current backend |

This distinction is still important because it keeps mcp-coder behavior **backend-neutral** at the product layer.

### What each layer still implies

The older Phase 2 design note was more explicit about what each layer owns:

| Layer | Still-relevant meaning |
|---|---|
| **L1 — contract** | edit/read intent, policies, behavioral constraints |
| **L2 — compiler** | materialization tiers, truncation/budget decisions, inspectable pre-exec package |
| **L3 — adapter** | backend-specific translation such as file loading mode or execution request shape |

That separation is still foundational and should not be lost in cleanup.

### Why it still matters

- backend details should not redefine product intent,
- context shaping should be inspectable without running the backend,
- and adapter behavior should be auditable instead of implicit.

### Contract vocabulary worth preserving

The original source note defined a few important concepts that still matter:

- **edit vs read intent are distinct**
- **behavioral contract** matters more than backend API details
- **materialization tier** is a first-class compiler decision
- **backend capabilities** affect translation, not product meaning

## Storage model

### Canonical home

Delegation logs and related metadata live under the mcp-coder home store rather than inside the repo.

Key ideas:

- user-home/project-scoped storage,
- durable IDs and links between sessions/delegations/specs,
- workspace history/checkpoint data separate from user git,
- clear pointers between reports, traces, and history records.

### Canonical layout concepts

The detailed source note defined the store in terms of:

- global/server-level logs,
- per-project storage,
- per-session delegation logs,
- workspace pointers/config under `.mcp-coder/`,
- links to host sessions/transcripts when available.

### IDs and linking

The storage model is not just “some files on disk.” It depends on a clear link chain:

```text
workspace_path -> project_key -> mcp_session_id -> delegation_id
```

And optionally also:

```text
host_kind / host_session_id / host_transcript_path
```

Those IDs are what make inspect/debug tools and history navigation possible.

### What lives there

At a high level the store contains:

- server/session logs,
- delegation records,
- workspace-history/checkpoint data,
- project-level state and linking metadata,
- and other derived artifacts needed for inspect/debug flows.

### Workspace specs and reports

The storage note also tied spec workflow into the storage model:

- planner-owned specs,
- MCP-owned reports,
- and durable links from delegation records back to those artifacts.

That coupling is important because storage is not just runtime logs; it is also how spec/report history stays traceable.

## Observability model

### Audit chain

The system should make it possible to understand:

1. what was intended,
2. what context was assembled,
3. what the backend was actually asked to do,
4. and what happened as a result.

That basic audit-chain idea is still one of the most important architectural constraints in the codebase.

### Four-layer audit chain

The original compiler design described this more concretely as:

1. **contract** — what was intended
2. **package** — what context was assembled
3. **adapter input** — what backend-specific request shape was produced
4. **result** — what actually happened

That four-layer framing is still the best compact explanation of the observability model.

### Capture depth

Observability now spans multiple depths:

| Depth | Example |
|---|---|
| **Contract/plan level** | spec/task/policy/context-package decisions |
| **Execution boundary level** | backend invocation, adapter inputs, output/result shaping |
| **LLM/capture level** | helper/backend/proxy/inner-call visibility where supported |
| **History/storage level** | durable traces, records, and checkpoint/history inspection |

### Inspectability requirement

One important design goal from the source notes is that context assembly should be inspectable **before** backend execution. That is why compiler/package-level observability matters separately from backend/proxy capture.

## Interception and backend capture

Third-party execution backends do not automatically expose their inner LLM calls. The current architecture therefore distinguishes:

- what mcp-coder owns directly,
- what it can capture through wrappers/substitution,
- and what requires proxy/interception style solutions.

This matters because “observability” is not one thing:

- some visibility is about the delegation contract,
- some is about trace structure,
- some is about raw backend/provider traffic.

### Capture approaches from the source note

The interception source note distinguished several architectural seams:

| Approach family | Why it matters |
|---|---|
| callback-style post-call hooks | light visibility, weaker control |
| wrapper/subclass seams | stronger owned capture for specific backends |
| owned inner-loop control | maximum control, maximum coupling |
| local proxy / process-boundary capture | backend-agnostic raw request/response visibility |

Even if the exact implementation evolves, those seam categories remain useful design vocabulary.

## Current shipped reality

### Shipped foundations

| Area | Status |
|---|---|
| Contract/compiler/adapter split | shipped foundation |
| Context package / tiered materialization | shipped foundation |
| Home-store layout and linking model | shipped foundation |
| Workspace-history/checkpoint model | shipped |
| Deeper owned/external LLM capture layers | shipped in current observability stack, with backend-specific boundaries |

### Still-useful details from the Phase 2 source note

These details are old, but still architecturally important:

- the compiler decides materialization tiers instead of blindly mirroring backend semantics,
- backend capabilities can cause predictable degradation or translation,
- and “audit, don’t block” was an explicit early design stance for some executor behaviors.

### Still-useful details from storage/linking

- home-store layout is canonical,
- workspace `.mcp-coder` files are pointers/config, not the primary audit store,
- JSONL is canonical audit; history DB is a browse surface,
- and delegation/spec/report links are part of the designed navigation model.

### Still-useful details from interception

- backend capture depth differs by seam,
- proxy/interception is about both observability and future control,
- and not every backend path offers the same capture guarantees.

### Still-important constraints

- keep contract semantics distinct from backend mechanics,
- keep storage canonical and navigable,
- make traces reconstructable across layers,
- and do not treat every retrieval/visibility problem as “RAG”.

Additional constraints preserved from the source notes:

- backend-neutral logic should stay out of backend-specific modules,
- capability differences should degrade behavior predictably rather than invisibly,
- and path/layout decisions should remain stable enough for tooling and docs to rely on.

## RAG boundary

The detailed retrieval strategy lives in [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md), but one boundary is worth preserving here:

> Not every missing piece of context is a retrieval problem.

Sometimes the right answer is:

- better storage/indexing,
- better observability,
- better linking,
- or better compiler policy,

not a new retrieval system.

That “RAG litmus test” is one of the most valuable parts of the older planning notes and should remain explicit.

## Deferred / future direction

These areas remain active evolution points:

| Theme | Direction |
|---|---|
| Richer code-intel / retrieval | beyond the original Phase 2 compiler foundation |
| Retention / GC policy | lifecycle management across logs, traces, RAG, history |
| Multi-backend capture parity | deeper observability for more executor backends |
| Cleaner unified architecture docs | eventually replace some legacy phase-era notes entirely |

### Older ideas that may now be stale or moved

Some source material was phase-timed and should now be read as historical framing rather than current sequencing:

- Phase-number-specific rollout language
- early “before/after compiler ships” transition notes
- some backend-specific seam preferences that may have been overtaken by later shipped capture layers

Those ideas are still worth preserving as rationale, but not as current roadmap truth.

## Coverage notes

This note intentionally preserves:

- the L1/L2/L3 architecture split,
- the home-store and link-chain model,
- the four-layer audit chain,
- the distinction between compiler/package observability and backend/raw-call capture,
- and the “not everything is RAG” boundary.

Viewer rendering details now live in [viewer-and-trace-design.md](./viewer-and-trace-design.md). Retrieval corpus and ranking details now live in [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md).

## Legacy source notes

This note consolidates the still-relevant foundation from:

- [phase2-owned-context.md](./archive/phase2-owned-context.md)
- [storage-and-linking.md](./archive/storage-and-linking.md)
- [llm-interception-strategies.md](./archive/llm-interception-strategies.md)
- [rag-gap-analysis.md](./archive/rag-gap-analysis.md) for the RAG boundary and corpus strategy now split into [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md)
