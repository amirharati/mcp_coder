<!--
  STEWARDSHIP — index and lifecycle map for docs/notes/.

  - Purpose: explain what each note covers, which era it belongs to, and whether it is current, evolved, superseded, or archived.
  - Keep summaries short and reality-based; do not restate full documents.
  - When a note is superseded, point to its successor/current source instead of silently deleting it.
-->

# Notes index

This page is the working index for **all notes under `docs/notes/`** after cleanup. It is meant to answer four questions quickly:

1. What topic does each note cover?
2. Is it still relevant to the current codebase?
3. Has it evolved into a newer note or phase reality?
4. Should it stay active, stay as supporting context, or live only in archive?

**Primary doc set:** the coherent notes set lives at the root of this folder.  
**Design entry point:** [system-design-overview.md](./system-design-overview.md) — refined system map (not vision).  
**Archive:** frozen/historical notes live in [archive/README.md](./archive/README.md).

## Status meanings

| Label | Meaning |
|---|---|
| `current` | Still a primary reference for the current codebase or planning language |
| `supporting` | Still useful, but not the main source for that topic |
| `evolved` | Important historically, but later notes/phases now carry the main truth |
| `superseded` | Replaced by a newer note and kept only for comparison/history |
| `archived` | Historical only; no longer an active design reference |

## Current primary set

Start with [system-design-overview.md](./system-design-overview.md) for the refined whole-system map. Then use the deep notes below.

| New note | Covers | Built from |
|---|---|---|
| [system-design-overview.md](./system-design-overview.md) | Refined design entry point — how all notes fit together | synthesis of the primary set |
| [supervisor-agent-architecture.md](./supervisor-agent-architecture.md) | Persistent Supervisor-agent architecture, project memory, pause/resume, subagent/tool context control | `supervisor-orchestration-layer.md`, `delegation-workflow-vision.md` |
| [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) | Stable Host/Supervisor/subagent vocabulary, delegation lifecycle, shipped modes vs future roles | `delegation-workflow-vision.md`, `spec-review-loop.md`, `workflow-turns.md` |
| [model-routing-and-policy.md](./model-routing-and-policy.md) | Shipped model policy behavior and future routing/escalation direction | `model-policy-layer.md`, `multi-model-roles.md` |
| [context-storage-and-observability.md](./context-storage-and-observability.md) | Contract/compiler/adapter split, storage model, observability/capture layers | `phase2-owned-context.md`, `storage-and-linking.md`, `llm-interception-strategies.md` |
| [spec-workflow.md](./spec-workflow.md) | Current spec-driven workflow for master/worker and review/implement paths | `spec-based-development.md`, `spec-review-loop.md` |
| [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md) | Retrieval/RAG boundaries, corpora, dependency order, FTS vs embeddings, deferred retrieval direction | `rag-gap-analysis.md` |
| [viewer-and-trace-design.md](./viewer-and-trace-design.md) | Delegation viewer mental model, trace mapping, event rendering rules | `viewer-design-principles-v2.md` |

## Quick start

| If you need... | Start here |
|---|---|
| Refined whole-system design map | [system-design-overview.md](./system-design-overview.md) |
| Persistent Supervisor-agent architecture | [supervisor-agent-architecture.md](./supervisor-agent-architecture.md) |
| Host/Supervisor/subagent role vocabulary and lifecycle | [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) |
| Model routing and policy | [model-routing-and-policy.md](./model-routing-and-policy.md) |
| Context/compiler, storage, and observability foundations | [context-storage-and-observability.md](./context-storage-and-observability.md) |
| Retrieval / RAG strategy | [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md) |
| Spec workflow and review/implement loop | [spec-workflow.md](./spec-workflow.md) |
| Viewer / trace design | [viewer-and-trace-design.md](./viewer-and-trace-design.md) |
| Historical validations / runbooks | [archive/README.md](./archive/README.md) |

## New set status

| Note | Status now | Role in the folder |
|---|---|---|
| [system-design-overview.md](./system-design-overview.md) | `current` | Refined design entry point for the notes set |
| [supervisor-agent-architecture.md](./supervisor-agent-architecture.md) | `current` | Primary persistent Supervisor-agent architecture note |
| [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) | `current` | Primary Host/Supervisor/subagent vocabulary note |
| [model-routing-and-policy.md](./model-routing-and-policy.md) | `current` | Primary model-policy and routing note |
| [context-storage-and-observability.md](./context-storage-and-observability.md) | `current` | Primary foundation note for compiler/storage/observability |
| [spec-workflow.md](./spec-workflow.md) | `current` | Primary workflow contract note |
| [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md) | `current` | Primary retrieval/RAG strategy note |
| [viewer-and-trace-design.md](./viewer-and-trace-design.md) | `current` | Primary viewer/trace design note |

## Legacy notes by topic

| Note | Topic | Status now | Why it still exists | Current successor / anchor |
|---|---|---|---|---|
| [supervisor-orchestration-layer.md](./archive/supervisor-orchestration-layer.md) | Orchestration / Supervisor architecture | `archived` | Legacy source note preserved for D-ARCH wording and phase-era rationale | [supervisor-agent-architecture.md](./supervisor-agent-architecture.md) |
| [delegation-workflow-vision.md](./archive/delegation-workflow-vision.md) | Role hierarchy / workflow vocabulary | `archived` | Legacy source note preserved for glossary and long-horizon framing | [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) |
| [model-policy-layer.md](./archive/model-policy-layer.md) | Model registry and policy layers | `archived` | Legacy Phase 9-era implementation framing kept for historical comparison | [model-routing-and-policy.md](./model-routing-and-policy.md) |
| [storage-and-linking.md](./archive/storage-and-linking.md) | `~/.mcp-coder` storage model | `archived` | Legacy detailed field/path reference preserved for reconstruction | [context-storage-and-observability.md](./context-storage-and-observability.md) |
| [spec-based-development.md](./archive/spec-based-development.md) | Spec-driven workflow (repo + consumer) | `archived` | Legacy workflow framing preserved for historical comparison | [spec-workflow.md](./spec-workflow.md) |
| [spec-review-loop.md](./archive/spec-review-loop.md) | `mode=review` / `mode=implement` loop | `archived` | Legacy operational source note preserved for exact old wording | [spec-workflow.md](./spec-workflow.md) |
| [viewer-and-trace-design.md](./viewer-and-trace-design.md) | Viewer / trace design | `current` | Current viewer mental model and rendering rules | This note |
| [llm-interception-strategies.md](./archive/llm-interception-strategies.md) | Backend interception / capture architecture | `archived` | Legacy capture-architecture note preserved for detailed seam analysis | [context-storage-and-observability.md](./context-storage-and-observability.md) |
| [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md) | Retrieval / RAG strategy | `current` | Current retrieval boundary and corpus strategy | This note |
| [rag-gap-analysis.md](./archive/rag-gap-analysis.md) | RAG planning / retrieval scope | `archived` | Legacy Phase 5-era gap analysis preserved for detailed evidence and planning tables | [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md) |
| [multi-model-roles.md](./archive/multi-model-roles.md) | Long-term multi-model direction | `archived` | Legacy direction note preserved for staged future-model ideas | [model-routing-and-policy.md](./model-routing-and-policy.md) |
| [phase2-owned-context.md](./archive/phase2-owned-context.md) | Context compiler foundation | `archived` | Historical Phase 2 design note preserved for original contract vocabulary | [context-storage-and-observability.md](./context-storage-and-observability.md) |
| [workflow-turns.md](./archive/workflow-turns.md) | Future workflow modes | `archived` | Legacy future-turn note preserved after coverage moved into the new lifecycle/workflow notes | [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) |
| [archive/viewer-design-principles-v2.md](./archive/viewer-design-principles-v2.md) | Viewer design v2 | `archived` | Legacy source note preserved after current viewer/trace note was created | [viewer-and-trace-design.md](./viewer-and-trace-design.md) |
| [archive/viewer-design-principles.md](./archive/viewer-design-principles.md) | Old viewer design | `archived` | Older design context only; current source is viewer/trace note | [viewer-and-trace-design.md](./viewer-and-trace-design.md) |

## Chronology and evolution

This is the short “what changed over time?” map for the notes folder.

| Era | Notes created / used | Topic | Status now | What they evolved into |
|---|---|---|---|---|
| Phase 1 exit / Phase 2 planning | [phase2-owned-context.md](./archive/phase2-owned-context.md), [spec-based-development.md](./archive/spec-based-development.md), [spec-review-loop.md](./archive/spec-review-loop.md), [storage-and-linking.md](./archive/storage-and-linking.md) | Context compiler, specs, storage, review loop | `archived` | These established the base product vocabulary and contracts |
| Phase 2 / 3 execution and dogfood | [archive/phase2-exit-validation.md](./archive/phase2-exit-validation.md), [archive/wave1-exit-validation.md](./archive/wave1-exit-validation.md), [archive/wave1-wild-test-runbook.md](./archive/wave1-wild-test-runbook.md), [archive/phase3-wave1-exit-validation.md](./archive/phase3-wave1-exit-validation.md) | Exit validation and early dogfood | `archived` | Historical runbooks only |
| Phase 4 / 5 planning | [multi-model-roles.md](./archive/multi-model-roles.md), [rag-gap-analysis.md](./archive/rag-gap-analysis.md), [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md), [workflow-turns.md](./archive/workflow-turns.md) | Multi-model vision, RAG scope, future workflow modes | `current` + `archived` | Retrieval strategy is current; older planning notes live in archive |
| Phase 8 / 9 observability | [llm-interception-strategies.md](./archive/llm-interception-strategies.md), [archive/viewer-design-principles.md](./archive/viewer-design-principles.md), [archive/viewer-design-principles-v2.md](./archive/viewer-design-principles-v2.md), [viewer-and-trace-design.md](./viewer-and-trace-design.md), [model-policy-layer.md](./archive/model-policy-layer.md) | Interception, viewer, model policy | `current` + `archived` | Viewer/trace design is current; older viewer notes live in archive |
| Phase 11 / 12 / 13 orchestration | [delegation-workflow-vision.md](./archive/delegation-workflow-vision.md), [supervisor-orchestration-layer.md](./archive/supervisor-orchestration-layer.md), [supervisor-agent-architecture.md](./supervisor-agent-architecture.md), [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) | Role hierarchy and Supervisor-led architecture | `current` + `archived` | The new pair is the primary set; older notes are now preserved in archive |

## Archived notes

The archive currently contains three kinds of notes:

| Archive group | What it holds | Status |
|---|---|---|
| Legacy source notes for the new primary set | Archived source notes whose still-relevant content was folded into the new coherent notes set | `archived` |
| [archive/phase3-master-session-bootstrap.md](./archive/phase3-master-session-bootstrap.md) through [archive/phase11-master-session-bootstrap.md](./archive/phase11-master-session-bootstrap.md) | Frozen phase planning / handoff prompts | `archived` |
| [archive/phase2-exit-validation.md](./archive/phase2-exit-validation.md), [archive/wave1-exit-validation.md](./archive/wave1-exit-validation.md), [archive/phase3-wave1-exit-validation.md](./archive/phase3-wave1-exit-validation.md), [archive/wave1-wild-test-runbook.md](./archive/wave1-wild-test-runbook.md) | Historical validation and dogfood execution aids | `archived` |

## Likely next cleanup targets

This is the current recommendation after archiving the processed legacy-source set.

| Theme | Keep as primary | Supporting / maybe merge later | Clearly historical |
|---|---|---|---|
| Supervisor agent / roles | [supervisor-agent-architecture.md](./supervisor-agent-architecture.md), [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) | [supervisor-orchestration-layer.md](./archive/supervisor-orchestration-layer.md), [delegation-workflow-vision.md](./archive/delegation-workflow-vision.md), [workflow-turns.md](./archive/workflow-turns.md), [multi-model-roles.md](./archive/multi-model-roles.md) | bootstrap handoffs in archive |
| Model policy | [model-routing-and-policy.md](./model-routing-and-policy.md) | [model-policy-layer.md](./archive/model-policy-layer.md), [multi-model-roles.md](./archive/multi-model-roles.md) | old phase handoffs in archive |
| Retrieval / RAG | [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md) | [context-storage-and-observability.md](./context-storage-and-observability.md) when storage/observability overlap matters | [archive/rag-gap-analysis.md](./archive/rag-gap-analysis.md) |
| Viewer | [viewer-and-trace-design.md](./viewer-and-trace-design.md) | [context-storage-and-observability.md](./context-storage-and-observability.md) when trace/capture overlap matters | [archive/viewer-design-principles-v2.md](./archive/viewer-design-principles-v2.md), [archive/viewer-design-principles.md](./archive/viewer-design-principles.md) |
| Context/compiler | [context-storage-and-observability.md](./context-storage-and-observability.md) | [phase2-owned-context.md](./archive/phase2-owned-context.md), [storage-and-linking.md](./archive/storage-and-linking.md), [llm-interception-strategies.md](./archive/llm-interception-strategies.md) | phase exit runbooks in archive |
| Specs workflow | [spec-workflow.md](./spec-workflow.md) | [spec-based-development.md](./archive/spec-based-development.md), [spec-review-loop.md](./archive/spec-review-loop.md) | validation runbooks in archive |

## Maintenance notes

1. Keep this file focused on **what each note is for now**, not full summaries.
2. If a note changes status (`current` -> `supporting`, `supporting` -> `archived`, etc.), update this file in the same session.
3. If a note is superseded, add the successor/current anchor instead of just saying “old”.
4. Reflect major doc-lifecycle changes in `docs/README.md` and `docs/VISION_DOCS.md` when they affect navigation.
