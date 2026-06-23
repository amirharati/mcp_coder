<!--
  STEWARDSHIP — primary Supervisor agent architecture note. See docs/VISION_DOCS.md.

  - Purpose: current cross-phase architecture for the persistent SupervisorAgent, state, pause/resume, and subagent/tool control.
  - Keep this grounded in shipped reality first; future direction must be clearly labeled.
  - Source lineage: supervisor-orchestration-layer.md + delegation-workflow-vision.md.
  - Former path: orchestration-architecture.md (renamed 2026-06-23).
-->

# Supervisor agent architecture

**Status:** Current architecture note — aligned to shipped Phase 12 and verified Phase 13 behavior as of 2026-06-23.  
**Design map:** [system-design-overview.md](./system-design-overview.md) — start here for the whole refined design; this note is the deep dive on the Supervisor runtime.  
**Primary PM context:** [PHASE12_MVP.md](../PHASE12_MVP.md) (closed) and [PHASE13_MVP.md](../PHASE13_MVP.md) (active docs/test cleanup).  
**Related backlog:** BL-540..BL-547, BL-525, BL-526, BL-527, BL-529, BL-530, BL-553..BL-555.  
**Related current notes:** [delegation-roles-and-lifecycle.md](./delegation-roles-and-lifecycle.md), [context-storage-and-observability.md](./context-storage-and-observability.md), [retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md), [model-routing-and-policy.md](./model-routing-and-policy.md).

---

## Purpose

This note explains the **current Supervisor agent architecture** of mcp-coder:

- which parts are stateful vs stateless,
- what the Supervisor owns,
- how project state and continuation state work,
- how helper context is assembled,
- how pause/resume preserves work,
- and which parts are shipped now vs still deferred.

This is the main architecture note for the persistent Supervisor agent. It is intended to be a real replacement for the phase-era source notes, not just a summary.

## North Star

The long-horizon design is a **persistent Supervisor agent for a whole project workflow**, not just a wrapper around one executor call.

In that design:

- the **host agent** (Cursor or another MCP host) remains the user-facing collaborator and strategic interface,
- the **SupervisorAgent** is mcp-coder's long-lived project agent, reached by the host through delegations,
- each delegation is one interaction/turn between the host and the Supervisor, not an isolated subprocess,
- the Supervisor accumulates durable project memory across delegations,
- the Supervisor coordinates narrower subagents/workers such as Executor, Reviewer, Planner, Clarity, validators, and future specialists,
- and later high-level agents such as CTO/Architect remain possible but intentionally undecided.

This is the “partner, not tool” shift from the archived design note: the host provides user-facing direction; mcp-coder provides execution control, project memory, and continuity.

### Current vs target wording

| Layer | Current shipped reality | Long-horizon target |
|---|---|---|
| **Host** | calls `delegate_to_agent`, relays user intent, handles conversation | collaborates with a persistent project Supervisor through many delegations |
| **SupervisorAgent** | owns lifecycle envelope, checkpoint, pause/resume, project state, helper/tool orchestration slices | persistent project agent with long-term memory, richer autonomous interception, and tool/subagent context control |
| **Subagents/workers** | Executor, Reviewer, Planner/helper slices, Clarity/validation paths | mostly stateless specialists called by the Supervisor with scoped context |
| **Future high-level roles** | Architect/CTO is deferred and not product truth | possible strategic agents at epic/project boundaries; exact boundary with Host and Planner remains open |

This target should guide naming and documentation, but shipped behavior must still be described honestly.

## Current shipped reality

### Core principle

The current system is built around one principle:

> **Only the Supervisor owns long-lived orchestration state.**

Everything else is either:

- **stateless per call**,
- **state derived from storage**,
- or **ephemeral helper execution**.

### Layer model

```text
┌──────────────────────────────────────────────────────────────────┐
│ SupervisorAgent  (persistent project workflow agent)            │
│                                                                  │
│ SESSION STATE (in-flight, per-delegation)                       │
│   turn_index, plan, decision_log, completed_turn_artifacts      │
│   pause/resume state: resume_token + serialized session         │
│                                                                  │
│ PROJECT STATE (durable, cross-delegation)                       │
│   decisions, hot areas, prior reviews, reviewer summaries       │
│   long-term project memory                                      │
│                                                                  │
│ INTERCEPTION LAYER                                               │
│   answers sub-helper questions before escalating when possible  │
│                                                                  │
│ ROUTING LAYER                                                    │
│   decides what helper to call, what context to inject, and      │
│   how much model weight a decision deserves                     │
│                                                                  │
│ CONTEXT CONTROL                                                  │
│   decides what each tool/subagent receives; own long-context     │
│   policy is still evolving                                      │
│                                                                  │
│ calls scoped subagents/workers:                                  │
│   Planner / Reviewer / Clarity / Validator / Executor / future  │
└──────────────────────────────────────────────────────────────────┘
```

### What is stateful today

| Component | State model | Current role |
|---|---|---|
| **Supervisor** | Stateful across a delegation and persisted across delegations via project/checkpoint state | Long-horizon project workflow agent; owns control flow, pause/resume, project-aware orchestration |
| **Project state** | Persisted | Compact cross-delegation memory: risks, summary, hot areas, reviewer carry-forward |
| **Executor session** | Semi-stateful, under Supervisor control | Code-editing runtime that may be reset or reused |
| **Planner / reviewer / other helpers** | Stateless per call | Context consumers, not long-lived owners |

### What shipped in Phase 12 and Phase 13

| Capability | Status |
|---|---|
| Persistent project state | shipped |
| Reviewer findings feedback loop | shipped |
| Tool-calling helper loop for Supervisor-owned context retrieval | shipped v1 |
| Pause/resume across host round-trips | shipped |
| Planner as a real agent loop (initial slice) | shipped v1 |
| Delegation lifecycle envelope unification | shipped |
| Cross-process checkpointing via `AgentCheckpoint` | shipped |
| Clarity-block auto-resume on host return | shipped |
| Typed failure surfacing / classification hardening | shipped, with some watch-for-evidence backlog items |

### What is still only partial or deferred

| Theme | Current status |
|---|---|
| Confirm/ask enrichment and richer continuation briefing | partial |
| Autonomous interception beyond current slices | deferred |
| Full planner-as-agent loop | partial / deferred remainder |
| Architect/CTO role | deferred |
| Smarter executor session adaptation | deferred |
| Deeper host-intent inference from conversation history | deferred |

## Why this architecture exists

The move to a stateful orchestration layer solves concrete product problems:

- repeated human interruptions for questions the system could answer itself,
- loss of context across pauses or multiple delegations,
- no durable place to keep reviewer findings and project risks,
- and no clean ownership of continuation or reset decisions.

The goal is to make mcp-coder feel less like a thin subprocess launcher and more like a partner that can think across turns while remaining auditable.

### Host and Supervisor interaction

The host and Supervisor are different agents with different responsibilities:

| Actor | Owns | Should not own |
|---|---|---|
| **Host agent** | user conversation, strategic direction, when to delegate, final human-facing presentation | hidden project memory inside mcp-coder; executor session lifecycle |
| **SupervisorAgent** | delegation lifecycle, subagent/tool routing, project memory, pause/resume, context injection, durable state writes | user product authority; unbounded chat interpretation without provenance |

The interaction between them happens through delegations:

```text
User <-> Host agent
          |
          | delegate_to_agent(...)
          v
     SupervisorAgent  <->  Executor / Reviewer / Planner / tools / future specialists
          |
          | result / pause / resume token / questions
          v
        Host agent
```

The host may be weak or strong. The architecture must not assume it is a senior planner; this is why internal quality gates, state, and memory live inside mcp-coder.

## Orchestration flow

```text
Host request
  -> planning/helper stages
  -> Supervisor owns delegation lifecycle
  -> Executor does implementation work
  -> Reviewer/helper outputs feed back into project state and result shaping
  -> Supervisor decides continue / pause / finish
  -> Host receives result or a resumable pause
```

### Lifecycle responsibilities

| Stage | Primary owner | What matters |
|---|---|---|
| Pre-execution planning | Planner/helper stages under Supervisor-owned lifecycle | Build a plan and gather enough context without making helpers stateful |
| Execution | Executor | Edit/apply work; may reuse or reset session |
| Supervision | Supervisor | Decide when to ask, intercept, resume, finish, or escalate |
| Post-execution shaping | Reviewer + Supervisor | Feed findings into project state and final outcome |

## State and context model

### Single statefulness principle

Only the Supervisor owns durable session-state semantics. Helpers do not maintain their own hidden memory.

That means:

- Planner may read persistent state, but does not own it
- Reviewer returns findings, but does not persist them directly
- Clarity/validation helpers are reconstructable stateless calls
- Executor may keep a working session, but the lifecycle policy lives above it

### Supervisor memory layers

The Supervisor's memory is intentionally layered:

| Memory layer | Scope | Status | Purpose |
|---|---|---|---|
| **In-flight session state** | current delegation | shipped | pause/resume, decision log, completed turns |
| **Agent checkpoint** | cross-process Supervisor continuity | shipped | reload Supervisor/project agent state when process cache is gone |
| **Project state** | project-wide, cross-delegation | shipped foundation | durable decisions, risks, reviewer findings, hot areas |
| **Retrieval memory** | project/global corpora | partial/future | relevant prior delegations, file summaries, session digests, worked patterns |
| **Supervisor's own long-context policy** | Supervisor internal reasoning context | not fully designed | decide what long-term memory/context the Supervisor itself carries between decisions |

The important unresolved piece is the last row: we have patterns for context sent **to tools/subagents**, but the Supervisor's own long-horizon context policy still needs explicit design. Until then, keep Supervisor context bounded, auditable, and assembled from durable stores.

### Two-tier state model

| State type | Scope | Purpose |
|---|---|---|
| **Session state** | one in-flight delegation | pause/resume without replaying completed stages |
| **Project state** | cross-delegation | durable memory across tasks/sessions |

### Two-tier context model

The current design uses a two-tier context model:

| Tier | Typical contents | Refresh pattern | Why it exists |
|---|---|---|---|
| **Tier 1 — slow context** | spec summary, current plan, compact project-state summary, decision-log tail | delegation start, resume, or turn boundary | stable baseline context |
| **Tier 2 — action-specific context** | targeted history lookups, file reads, diffs, reviewer findings, project-state details | on demand during helper reasoning | avoids bloated static context and keeps decisions fresh |

### Context control responsibility

The Supervisor controls context for tools and subagents. That means it decides:

- which project-state facts are relevant,
- which retrieval/history refs to inject,
- which file/diff details a helper sees,
- which findings should affect the next plan,
- when context is too thin and a tool call is needed,
- and when uncertainty must escalate to the host.

This context-control responsibility is separate from the context compiler's lower-level contract/tier work described in [context-storage-and-observability.md](./context-storage-and-observability.md). The compiler builds packages; the Supervisor decides how project memory and tool results should shape orchestration decisions.

### Project state

Project state is the durable memory layer for orchestration. It is intentionally compact and is meant to preserve:

- what the project is,
- what risks remain open,
- what reviewer findings should persist,
- what decisions have already been made,
- and what context should survive across multiple delegations/sessions.

It is **not** meant to become a raw transcript or a second log store.

## Pause and resume

### Current behavior

Pause/resume is part of the main orchestration contract now, not an afterthought.

There are two practical categories:

| Pause type | Current behavior |
|---|---|
| **Clarity-block / host-return path** | auto-resume can happen without explicit answer in shipped paths |
| **Escalation / mid-loop human input** | still answer-gated in some cases; follow-up verification remains in backlog watch items |

### Core invariants

- resume should not replay already-completed lifecycle stages unnecessarily,
- the Supervisor should remain the control owner,
- host clarification should be injected as structured continuation context,
- resume behavior must preserve auditable state transitions.

### What should skip on resume

The source architecture was explicit that resume is not a full restart. Conceptually, resume should skip already-completed work like:

- clarity checks,
- spec validation,
- earlier planning/setup stages that are still valid,
- and completed executor turns.

Host input should be treated as **continuation input**, not as a reason to rebuild the whole lifecycle blindly.

### Current watch items

The architecture is shipped, but some edge behavior is still explicitly tracked for validation:

- clarity-block vs escalation pause semantics,
- executor error classification edge cases,
- typed unknown-cause surfacing in real dogfood traces.

## Helper and interception model

The Supervisor is the orchestration brain, but not every question should go to the host.

### Current direction

- simple answers should be resolved inside the orchestration layer when safe,
- helper/tool calls are preferred over blind escalation,
- escalation remains available when confidence, authority, or context is insufficient.

### Tool-calling helper loop

The Supervisor’s helper decisions are not meant to stay single-shot forever. The current design supports a helper/tool loop where the helper can:

1. start from tier-1 context,
2. pull tier-2 context when needed,
3. iterate a bounded number of times,
4. emit a final decision.

This is relevant for:

- continuation decisions,
- confirm/ask interception,
- routing context,
- and reducing unnecessary escalation to the host.

### Decision-weighted model use

Not every orchestration decision deserves the same model weight. The source design explicitly distinguished:

- cheap yes/no routing,
- medium context-routing or continuation assembly,
- stronger plan revision or higher-risk escalation decisions.

The exact knobs may evolve, but the principle should remain.

## Cross-phase decisions that still matter

The detailed D-ARCH tables remain in the legacy source note, but these are the constraints that still define the architecture:

| Decision theme | Constraint |
|---|---|
| **State ownership** | Supervisor is the sole durable owner of session/project orchestration state |
| **Interception order** | try to resolve from known context before escalating to the human |
| **Resume behavior** | preserve completed pipeline work; inject host answer into continuation |
| **Model weighting** | internal orchestration decisions can use different model tiers |
| **Two-tier context** | separate slow baseline context from on-demand decision context |
| **Host/Supervisor split** | host owns user-facing intent; Supervisor owns mcp-coder memory and orchestration |
| **Context control** | Supervisor scopes context for tools/subagents; its own long-term context remains an explicit future design area |

## Still relevant design constraints

These older design constraints remain important even after the phase work shipped:

- **single orchestration owner**: do not spread durable state across helpers,
- **clear shipped-vs-future boundaries**: do not describe deferred autonomy as current behavior,
- **stateless helper preference**: most helper roles should stay reconstructable from stored context,
- **auditable lifecycle**: pause/resume and helper decisions must remain explainable in trace/storage,
- **project state stays compact**: memory is summarized state, not raw history,
- **interception before human interruption**: ask the host only when the system truly lacks enough knowledge or authority.

## Deferred / future direction

These are still relevant, but are not current product truth:

| Theme | Deferred direction |
|---|---|
| Supervisor context lifecycle | richer confirm/ask enrichment and fuller continuation briefing |
| Autonomous interception | more proactive Supervisor-driven interception beyond current shipped slices |
| Planner maturity | fuller planner-as-agent loop and richer mutable planning behavior |
| Architect role | epic-boundary CTO-style role remains conceptual/deferred |
| Executor session adaptation | smarter reset/rebuild policy beyond current control plane |
| Host intent inference | deeper host-chat-aware orchestration support |
| Supervisor's own context policy | explicit long-horizon context/memory assembly for Supervisor reasoning |
| High-level specialist agents | CTO/Architect/API designer/etc. coordination boundaries remain vague and deferred |

### Explicit non-goals

These “what this is not” boundaries from the source notes are worth preserving:

- not every helper becomes stateful,
- not every open question becomes a human interruption,
- not all future autonomy ideas are current product commitments,
- orchestration is not the same as uncontrolled multi-agent sprawl,
- and future CTO/Architect-style agents should not be treated as shipped roles until their boundary with Host, Planner, and Supervisor is decided.

## Coverage notes

This note intentionally preserves the important content classes from the source notes:

- state model and D-ARCH-style constraints,
- shipped vs deferred Phase 12/13 reality,
- pause/resume semantics,
- two-tier context model,
- interception/routing philosophy,
- the “Supervisor as sole orchestration owner” principle,
- and the long-horizon “persistent project agent interacting with host through delegations” framing.

The detailed phase-by-phase rollout and exact historical wording still live in the legacy notes until we explicitly decide they are fully redundant.

## Legacy source notes

This note consolidates the current architecture layer from:

- [supervisor-orchestration-layer.md](./archive/supervisor-orchestration-layer.md)
- [delegation-workflow-vision.md](./archive/delegation-workflow-vision.md)

Keep those only as supporting/legacy references until each is compared and explicitly retired or archived.
