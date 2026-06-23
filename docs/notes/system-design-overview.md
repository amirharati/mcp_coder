<!--
  STEWARDSHIP — refined design entry point for docs/notes/. See docs/VISION_DOCS.md.

  - Purpose: short map of how the current system fits together; links to deep design notes.
  - This is refined design, not vision. Do not merge brainstorming or phase PM content here.
  - Vision / why lives in IDEA.md and related tier-0 docs; this note explains how the design pieces connect.
-->

# System design overview

**Status:** Current refined-design entry point for `docs/notes/` as of 2026-06-23.  
**Vision upstream:** [IDEA.md](../IDEA.md) (why, product intent, brainstorming-era framing).  
**Doc map / stewardship:** [VISION_DOCS.md](../VISION_DOCS.md).

---

## Vision vs refined design

| Layer | Where it lives | What it is for |
|---|---|---|
| **Vision** | [IDEA.md](../IDEA.md), phase PM docs, backlog, archived brainstorms | Why the product exists, early ideas, phase history, open questions |
| **Refined design** | `docs/notes/` (this folder) | Current architecture and workflow decisions grounded in shipped reality |

Use this note when you want the **refined system picture**. Use [IDEA.md](../IDEA.md) when you want the **original product intent**. They should stay separate.

## One-sentence summary

mcp-coder is a task-level MCP layer where a **persistent Supervisor agent** runs project workflows across delegations, coordinates scoped subagents (Planner, Executor, Reviewer, helpers), and sits on top of shared foundations for context, storage, observability, retrieval, model policy, and trace inspection.

## System map

```text
User
  <-> Host agent (Cursor / MCP client)
        |
        | delegate_to_agent(...)
        v
  mcp-coder boundary
        |
        +-- Spec / workflow contract
        +-- Context compiler + storage + observability
        +-- Retrieval / RAG (where genuinely needed)
        +-- Model routing / policy
        |
        v
  SupervisorAgent  (persistent project workflow agent)
        |
        +-- Planner / Clarity / validators
        +-- Executor (implementation backend)
        +-- Reviewer / post-exec shaping
        +-- tools / future specialists (CTO/Architect TBD)
        |
        v
  Durable records + traces + viewer
```

The Supervisor is the **central runtime agent**, but not the only architectural concern. Foundations and workflow contracts exist around it and feed it.

## Design layers

| Layer | Question it answers | Primary note |
|---|---|---|
| **Roles & lifecycle** | Who does what, and in what order? | [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) |
| **Supervisor runtime** | How does the persistent project agent work? | [supervisor-agent-architecture.md](./supervisor-agent-architecture.md) |
| **Context / storage / observability** | How is intent compiled, stored, and audited? | [context-storage-and-observability.md](./context-storage-and-observability.md) |
| **Retrieval / RAG** | What is retrieval-shaped vs storage/index/policy? | [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md) |
| **Model policy** | How are models and parameters chosen? | [model-routing-and-policy.md](./model-routing-and-policy.md) |
| **Spec workflow** | How do review/implement and task specs work? | [spec-workflow.md](./spec-workflow.md) |
| **Viewer / trace** | How should execution be represented and inspected? | [viewer-and-trace-design.md](./viewer-and-trace-design.md) |

## How the pieces relate

```text
spec-workflow
  -> defines task/review/implement contracts

context-storage-and-observability
  -> compiles context packages, stores delegation history, captures audit chain

retrieval-and-rag-strategy
  -> feeds relevant history/code into compiler / Supervisor tools when retrieval is the right tool

model-routing-and-policy
  -> resolves model/params for roles and internal Supervisor decisions

delegation-roles-and-lifecycle
  -> names Host, Supervisor, Planner, Executor, Reviewer, future Architect

supervisor-agent-architecture
  -> owns project memory, pause/resume, subagent routing, context control

viewer-and-trace-design
  -> renders the resulting lifecycle and trace for humans
```

### Central idea

> The Host talks to mcp-coder through delegations.  
> The Supervisor is mcp-coder's long-horizon project agent.  
> Everything else is either foundation or a scoped worker the Supervisor coordinates.

## Read next

| If you need... | Read |
|---|---|
| The full refined design map (this page) | This note |
| Host vs Supervisor vs subagent boundaries | [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md) |
| Project memory, pause/resume, interception, context control | [supervisor-agent-architecture.md](./supervisor-agent-architecture.md) |
| L1/L2/L3 context, home store, audit chain, capture | [context-storage-and-observability.md](./context-storage-and-observability.md) |
| Whether a problem is RAG vs storage/policy | [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md) |
| Shipped model policy and future escalation | [model-routing-and-policy.md](./model-routing-and-policy.md) |
| `mode=review` / `mode=implement` and task specs | [spec-workflow.md](./spec-workflow.md) |
| Delegation viewer and event model | [viewer-and-trace-design.md](./viewer-and-trace-design.md) |
| Note lifecycle / archive map | [README.md](./README.md) |
| Product vision / brainstorming source | [IDEA.md](../IDEA.md) |

## Shipped vs still open (system level)

| Area | Shipped foundation | Still evolving / deferred |
|---|---|---|
| Supervisor as persistent project agent | lifecycle envelope, checkpoint, project state, pause/resume v1, tool-runner v1 | autonomous interception, Supervisor self-context policy, fuller planner loop |
| Roles | Host, Supervisor, Planner, Executor, Reviewer in current slices | Architect/CTO boundary undecided |
| Context / storage | contract/compiler/adapter, home store, audit chain, capture layers | retention/GC, deeper multi-backend parity |
| Retrieval | compile-push basics, corpora direction | richer code-intel, federation, embeddings where justified |
| Model policy | Stage 1 registry + `model_policy` | dynamic escalation, fuller multi-model orchestration |
| Spec workflow | review/implement, worker spec model | broader workflow-turn cadence |
| Viewer | current event model + enrichment path | fidelity/truncation polish |

For detail and backlog anchors, use the deep notes — especially [supervisor-agent-architecture.md](./supervisor-agent-architecture.md).

## Maintenance

1. Keep this note **short**. If a topic needs depth, put it in a sibling note and link it here.
2. Do not turn this into a second IDEA.md or phase PM board.
3. When a new primary note is added under `docs/notes/`, update the layer table and read-next table here.
4. When Supervisor scope changes materially, update [supervisor-agent-architecture.md](./supervisor-agent-architecture.md) first, then adjust this map.
